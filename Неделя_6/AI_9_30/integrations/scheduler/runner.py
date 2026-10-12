# -*- coding: utf-8 -*-
"""integrations/scheduler/runner.py — worker планировщика (День 18, задание 1).

Фоновое выполнение обеспечивает **внешний worker** (поток stdlib `threading`), а
не LLM: «у агента нет heartbeat» (канон Задание_d18.txt). Worker по расписанию
выбирает созревшие задачи (`next_run_at <= now`), выполняет их идемпотентно и
пишет наблюдения/сводки в JSON. `run_once()` — детерминированный тик без
ожидания (для тестов и ручного вызова из MCP-инструмента).
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

from integrations.scheduler.aggregator import aggregate
from integrations.scheduler.models import Job, JobState, Observation, Summary, now_iso
from integrations.scheduler.store import SchedulerStore


def _parse_iso(value: str):
    """ISO 8601 → aware datetime (UTC); "" или битое → None."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _plus_seconds(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(timespec="seconds")


class Scheduler:
    """Планировщик фоновых задач: расписание + идемпотентный тик + агрегация."""

    def __init__(self, store: SchedulerStore, log=None,
                 summary_window: int = 0, tick_seconds: float = 0.05) -> None:
        self.store = store
        self.log = log or (lambda line: None)
        self.summary_window = summary_window
        self.tick_seconds = tick_seconds
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # -- задачи -------------------------------------------------------------------
    def add_job(self, kind: str, interval_seconds: float = 0.0, at: str = "",
                payload: dict | None = None) -> Job:
        """Добавить задачу и сохранить её в JSON. Возвращает созданную задачу."""
        job = Job.new(kind=kind, interval_seconds=interval_seconds, at=at, payload=payload)
        job.next_run_at = at or now_iso()
        jobs = self.store.load_jobs()
        jobs.append(job)
        self.store.save_jobs(jobs)
        self.log(f"[Планировщик] задача {job.job_id} ({kind}) добавлена; "
                 f"следующий запуск: {job.next_run_at}")
        return job

    def list_jobs(self) -> list[Job]:
        return self.store.load_jobs()

    # -- расписание ---------------------------------------------------------------
    def due_jobs(self, now: datetime | None = None) -> list[Job]:
        """Созревшие задачи: enabled, не running/paused, next_run_at <= now."""
        now = now or datetime.now(timezone.utc)
        due: list[Job] = []
        for job in self.store.load_jobs():
            if not job.enabled or job.state in (JobState.PAUSED.value, JobState.RUNNING.value):
                continue
            when = _parse_iso(job.next_run_at) or _parse_iso(job.created_at)
            if when is None or when <= now:
                due.append(job)
        return due

    def run_once(self, now: datetime | None = None) -> dict:
        """Один тик: выполнить созревшие задачи → агрегированный результат.

        Идемпотентность: задача помечается running на время выполнения; при
        интервальной задаче `next_run_at` сдвигается вперёд, одноразовая → done.
        """
        now = now or datetime.now(timezone.utc)
        jobs = self.store.load_jobs()
        by_id = {j.job_id: j for j in jobs}
        due = self.due_jobs(now)
        results: list[dict] = []
        summary_text = ""
        ran = 0
        for job in due:
            stored = by_id.get(job.job_id, job)
            stored.state = JobState.RUNNING.value
            try:
                outcome = self._execute(stored)
                stored.last_result = outcome
                stored.run_count += 1
                stored.last_run_at = now_iso()
                ran += 1
                results.append({"job_id": stored.job_id, "kind": stored.kind,
                                "status": "ok", "result": outcome})
            except Exception as exc:  # задача не роняет worker
                stored.state = JobState.FAILED.value
                results.append({"job_id": stored.job_id, "kind": stored.kind,
                                "status": "failed", "result": str(exc)})
                self.log(f"[Планировщик] задача {stored.job_id} упала: {exc}")
                continue
            # Пересчёт расписания.
            if stored.interval_seconds and stored.interval_seconds > 0:
                stored.state = JobState.SCHEDULED.value
                stored.next_run_at = _plus_seconds(stored.interval_seconds)
            else:
                stored.state = JobState.DONE.value
                stored.next_run_at = ""
            if stored.kind == "summary":
                latest = self.store.latest_summary()
                if latest is not None:
                    summary_text = latest.text

        if ran:
            self.store.save_jobs(list(by_id.values()))
        return {"ran": ran, "results": results, "summary": summary_text}

    def _execute(self, job: Job) -> str:
        """Выполнить одну задачу. Наблюдение/сводка пишутся в JSON."""
        if job.kind == "summary":
            observations = self.store.list_observations()
            summary = aggregate(observations, window=self.summary_window)
            self.store.save_summary(summary)
            return summary.text
        # reminder / collect: фиксируем наблюдение из payload.
        payload = dict(job.payload or {})
        source = payload.pop("source", job.kind)
        observation = Observation.new(source=source, payload=payload)
        self.store.append_observation(observation)
        return f"наблюдение записано ({source})"

    # -- фоновый worker -----------------------------------------------------------
    def start(self) -> None:
        """Запустить фоновый поток-тикер (идемпотентно)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="scheduler", daemon=True)
        self._thread.start()
        self.log("[Планировщик] worker запущен (24/7)")

    def stop(self) -> None:
        """Остановить фоновый поток чисто (join с таймаутом)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self.log("[Планировщик] worker остановлен")

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as exc:  # тик не должен ронять поток
                self.log(f"[Планировщик] тик: {exc}")
            self._stop.wait(self.tick_seconds)
