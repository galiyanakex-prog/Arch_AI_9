# -*- coding: utf-8 -*-
"""integrations/mcp/scheduler_server.py — MCP-сервер планировщика (День 18, задание 1).

MCP-инструмент с отложенным/периодическим выполнением: напоминание
(`schedule_reminder`), периодический сбор данных (`schedule_collection`), ручная
запись наблюдения (`record_observation`), выполнение созревших задач (`run_due`),
агрегированная сводка (`get_summary`) и возврат уже сохранённой сводки
(`latest_summary`). Всё — над ядром `integrations/scheduler/` (JSON-хранилище +
агрегатор). Фон обеспечивает worker, а НЕ LLM: сводка отдаётся без нового
запроса к модели (канон Задание_d18.txt).

Образец настройки — `doc/mcp/mcp-time-server/time_server_http.py`:
`mcp.server.mcpserver.MCPServer` + `@mcp.tool()` + Streamable HTTP + `uvicorn`.

Запуск:
    python -m integrations.mcp.scheduler_server           # HTTP :8010
    python -m integrations.mcp.scheduler_server --stdio   # stdio (для тестов)

Переменные окружения: `SCHEDULER_MEMORY_DIR` (корень users/), `SCHEDULER_USER_ID`
(по умолчанию `scheduler`), `SCHEDULER_PORT` (по умолчанию 8010).
"""
from __future__ import annotations

import json
import os

from mcp.server.mcpserver import MCPServer

from integrations.scheduler.models import JobState
from integrations.scheduler.runner import Scheduler
from integrations.scheduler.store import SchedulerStore
from storage.store import Store

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MEMORY_DIR = os.getenv("SCHEDULER_MEMORY_DIR", os.path.join(_BASE_DIR, "users"))
_DEFAULT_USER = os.getenv("SCHEDULER_USER_ID", "scheduler")

server = MCPServer("Scheduler Server")

_scheduler: Scheduler | None = None


def configure(memory_dir: str | None = None, user_id: str | None = None) -> None:
    """Переопределить хранилище/пользователя (для тестов и DI)."""
    global _MEMORY_DIR, _DEFAULT_USER, _scheduler
    if memory_dir:
        _MEMORY_DIR = memory_dir
    if user_id:
        _DEFAULT_USER = user_id
    _scheduler = None


def get_scheduler(user_id: str | None = None) -> Scheduler:
    """Ленивая сборка планировщика над фасадом `Store` (JSON-хранилище)."""
    global _scheduler
    if _scheduler is None:
        store = Store(_MEMORY_DIR)
        _scheduler = Scheduler(SchedulerStore(store, user_id or _DEFAULT_USER))
    return _scheduler


@server.tool()
def schedule_reminder(text: str, delay_seconds: float = 0.0, at: str = "") -> str:
    """Запланировать отложенное напоминание (одноразовая задача).

    Args:
        text: Текст напоминания.
        delay_seconds: Задержка в секундах от текущего момента (0 — сразу).
        at: Абсолютное время ISO 8601 (приоритетнее delay_seconds).

    Returns:
        JSON с job_id, состоянием и временем следующего запуска.
    """
    sched = get_scheduler()
    from integrations.scheduler.models import now_iso
    from datetime import datetime, timedelta, timezone
    when = at or (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
                  ).isoformat(timespec="seconds")
    job = sched.add_job("reminder", at=when, payload={"source": "reminder", "text": text})
    return json.dumps({"job_id": job.job_id, "state": job.state,
                       "next_run_at": job.next_run_at}, ensure_ascii=False)


@server.tool()
def schedule_collection(source: str, metric: str = "value", value: float = 0.0,
                        interval_seconds: float = 60.0) -> str:
    """Запланировать периодический сбор данных (числовое наблюдение).

    Args:
        source: Источник наблюдения (например, weather).
        metric: Имя метрики (числовое поле в payload).
        value: Значение метрики при каждом сборе.
        interval_seconds: Интервал между сборами в секундах.

    Returns:
        JSON с job_id и временем следующего запуска.
    """
    sched = get_scheduler()
    payload = {"source": source, metric: value}
    job = sched.add_job("collect", interval_seconds=interval_seconds, payload=payload)
    return json.dumps({"job_id": job.job_id, "interval_seconds": job.interval_seconds,
                       "next_run_at": job.next_run_at}, ensure_ascii=False)


@server.tool()
def record_observation(source: str, value: float = 0.0, metric: str = "value",
                       note: str = "") -> str:
    """Записать наблюдение немедленно (в JSON-хранилище планировщика).

    Args:
        source: Источник наблюдения.
        value: Числовое значение метрики.
        metric: Имя метрики (числовое поле в payload).
        note: Произвольная текстовая заметка.

    Returns:
        JSON с числом наблюдений после записи.
    """
    sched = get_scheduler()
    from integrations.scheduler.models import Observation
    payload = {metric: value}
    if note:
        payload["note"] = note
    sched.store.append_observation(Observation.new(source=source, payload=payload))
    return json.dumps({"observations": len(sched.store.list_observations())},
                      ensure_ascii=False)


@server.tool()
def run_due() -> str:
    """Выполнить созревшие по расписанию задачи и вернуть агрегированный результат.

    Returns:
        JSON с числом выполненных задач и текстом сводки (если задача-сводка сработала).
    """
    sched = get_scheduler()
    outcome = sched.run_once()
    return json.dumps(outcome, ensure_ascii=False)


@server.tool()
def get_summary(window: int = 0) -> str:
    """Посчитать агрегированную сводку по наблюдениям за окно и сохранить её.

    Args:
        window: Окно — последние N наблюдений (0 — все).

    Returns:
        Текст агрегированной сводки (count/min/max/avg/last).
    """
    sched = get_scheduler()
    from integrations.scheduler.aggregator import aggregate
    observations = sched.store.list_observations()
    summary = aggregate(observations, window=window)
    sched.store.save_summary(summary)
    return summary.text


@server.tool()
def latest_summary() -> str:
    """Вернуть УЖЕ сохранённый текст последней сводки (без нового расчёта/LLM).

    Returns:
        Текст последней сохранённой сводки либо пояснение, что сводок ещё нет.
    """
    sched = get_scheduler()
    summary = sched.store.latest_summary()
    if summary is None:
        return "Сводок пока нет (выполните run_due или get_summary)."
    return summary.text


@server.tool()
def list_jobs() -> str:
    """Список задач планировщика (id, kind, состояние, расписание, запусков).

    Returns:
        JSON-массив задач.
    """
    sched = get_scheduler()
    jobs = sched.list_jobs()
    return json.dumps([
        {"job_id": j.job_id, "kind": j.kind, "state": j.state,
         "interval_seconds": j.interval_seconds, "next_run_at": j.next_run_at,
         "run_count": j.run_count} for j in jobs
    ], ensure_ascii=False)


transport_security = None
try:  # HTTP-режим требует разрешённых хостов (образец time_server_http.py)
    from mcp.server.transport_security import TransportSecuritySettings
    transport_security = TransportSecuritySettings(allowed_hosts=[
        "localhost", "localhost:8010", "127.0.0.1", "127.0.0.1:8010",
        "0.0.0.0", "91.188.212.77", "91.188.212.77:8010",
    ])
except Exception:  # необязательная зависимость HTTP-режима
    transport_security = None


app = server.streamable_http_app(transport_security=transport_security) \
    if transport_security is not None else server.streamable_http_app()

# D7 (Ревизия 5): если задан env MCP_AUTH_TOKEN — требовать Bearer-токен.
from integrations.mcp.auth import auth_middleware
app = auth_middleware(app)


if __name__ == "__main__":
    import sys
    if "--stdio" in sys.argv:
        server.run(transport="stdio")
    else:
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("SCHEDULER_PORT", "8010")))

