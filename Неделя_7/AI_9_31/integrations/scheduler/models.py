# -*- coding: utf-8 -*-
"""integrations/scheduler/models.py — контракты планировщика (День 18, задание 1).

Модель без MCP SDK и без сети: ядро планировщика независимо от транспорта.
Состояние фоновой задачи — `JobState` (НЕ TaskStage: фоновая задача ≠ переход
автомата задачи, канон «инструмент ≠ переход»).
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum


def now_iso() -> str:
    """Текущее время в ISO 8601 (UTC, секунды)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobState(str, Enum):
    """Состояние фоновой задачи планировщика (инфраструктурное, не TaskStage)."""

    SCHEDULED = "scheduled"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class Job:
    """Одна фоновая задача (напоминание / периодический сбор / сводка)."""

    job_id: str
    kind: str                       # "reminder" | "collect" | "summary"
    interval_seconds: float = 0.0   # 0 → одноразовая (отложенная) задача
    at: str = ""                    # ISO-время первого запуска ("" → сразу)
    payload: dict = field(default_factory=dict)
    enabled: bool = True
    state: str = JobState.SCHEDULED.value
    created_at: str = field(default_factory=now_iso)
    last_run_at: str = ""
    next_run_at: str = ""
    run_count: int = 0
    last_result: str = ""

    @staticmethod
    def new(kind: str, interval_seconds: float = 0.0, at: str = "",
            payload: dict | None = None, enabled: bool = True) -> "Job":
        """Создать задачу с уникальным id и расписанием первого запуска."""
        return Job(
            job_id=f"job-{uuid.uuid4().hex[:8]}",
            kind=kind,
            interval_seconds=float(interval_seconds or 0.0),
            at=at or "",
            payload=dict(payload or {}),
            enabled=enabled,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "Job":
        """Устойчивое восстановление из dict (неизвестные поля игнорируются)."""
        known = {f for f in Job.__dataclass_fields__}  # type: ignore[attr-defined]
        return Job(**{k: v for k, v in (data or {}).items() if k in known})


@dataclass
class Observation:
    """Одно наблюдение (единица периодического сбора данных)."""

    timestamp: str
    source: str
    payload: dict = field(default_factory=dict)

    @staticmethod
    def new(source: str, payload: dict | None = None) -> "Observation":
        return Observation(timestamp=now_iso(), source=source, payload=dict(payload or {}))

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "Observation":
        known = {f for f in Observation.__dataclass_fields__}  # type: ignore[attr-defined]
        return Observation(**{k: v for k, v in (data or {}).items() if k in known})


@dataclass
class Summary:
    """Агрегированная сводка за окно наблюдений."""

    window: int                     # окно (последние N наблюдений; 0 → все)
    metrics: dict = field(default_factory=dict)
    text: str = ""
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "Summary":
        known = {f for f in Summary.__dataclass_fields__}  # type: ignore[attr-defined]
        return Summary(**{k: v for k, v in (data or {}).items() if k in known})
