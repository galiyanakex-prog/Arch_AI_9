# -*- coding: utf-8 -*-
"""integrations/scheduler/store.py — JSON-хранилище планировщика (День 18, задание 1).

Все данные планировщика сохраняются в JSON **через фасад `Store`**
(`users/<id>/integrations/mcp/scheduler/{jobs,observations,summaries}.json`).
Битый/отсутствующий файл → дефолт (приложение не падает) — наследие устойчивости
`Store.read_json`.
"""
from __future__ import annotations

from integrations.scheduler.models import Job, Observation, Summary

JOBS = "jobs"
OBSERVATIONS = "observations"
SUMMARIES = "summaries"


class SchedulerStore:
    """Обёртка над фасадом `Store`: типизированный доступ к данным планировщика."""

    def __init__(self, store, user_id: str) -> None:
        self.store = store
        self.user_id = user_id

    # -- задачи -------------------------------------------------------------------
    def load_jobs(self) -> list[Job]:
        raw = self.store.read_scheduler(self.user_id, JOBS, {"jobs": []})
        items = raw.get("jobs") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            return []
        jobs: list[Job] = []
        for item in items:
            try:
                jobs.append(Job.from_dict(item))
            except (TypeError, ValueError):
                continue
        return jobs

    def save_jobs(self, jobs: list[Job]) -> str:
        return self.store.write_scheduler(
            self.user_id, JOBS, {"jobs": [j.to_dict() for j in jobs]})

    # -- наблюдения ---------------------------------------------------------------
    def list_observations(self) -> list[Observation]:
        raw = self.store.read_scheduler(self.user_id, OBSERVATIONS, {"observations": []})
        items = raw.get("observations") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            return []
        result: list[Observation] = []
        for item in items:
            try:
                result.append(Observation.from_dict(item))
            except (TypeError, ValueError):
                continue
        return result

    def append_observation(self, observation: Observation) -> str:
        items = self.list_observations()
        items.append(observation)
        return self.store.write_scheduler(
            self.user_id, OBSERVATIONS,
            {"observations": [o.to_dict() for o in items]})

    # -- сводки -------------------------------------------------------------------
    def load_summaries(self) -> list[Summary]:
        raw = self.store.read_scheduler(self.user_id, SUMMARIES, {"summaries": []})
        items = raw.get("summaries") if isinstance(raw, dict) else None
        if not isinstance(items, list):
            return []
        result: list[Summary] = []
        for item in items:
            try:
                result.append(Summary.from_dict(item))
            except (TypeError, ValueError):
                continue
        return result

    def save_summary(self, summary: Summary) -> str:
        items = self.load_summaries()
        items.append(summary)
        return self.store.write_scheduler(
            self.user_id, SUMMARIES, {"summaries": [s.to_dict() for s in items]})

    def latest_summary(self) -> Summary | None:
        items = self.load_summaries()
        return items[-1] if items else None
