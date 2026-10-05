# -*- coding: utf-8 -*-
"""integrations/scheduler/aggregator.py — агрегация наблюдений (День 18, задание 1).

Считает фактические показатели (count / min / max / avg / last) по числовым
полям наблюдений за окно и формирует текст сводки. Никаких вызовов LLM:
текст сводки — детерминированный (LLM может переписать его отдельно, по запросу).
"""
from __future__ import annotations

from integrations.scheduler.models import Observation, Summary


def _numeric_fields(observations: list[Observation]) -> list[str]:
    """Числовые ключи, встречающиеся в payload наблюдений (кроме служебных)."""
    fields: list[str] = []
    for obs in observations:
        for key, value in (obs.payload or {}).items():
            if key in ("source",) or key in fields:
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                fields.append(key)
    return fields


def aggregate(observations: list[Observation], window: int = 0) -> Summary:
    """Сводка по последним `window` наблюдениям (window<=0 → все).

    metrics: {field: {count, min, max, avg, last}, "observations": N, "sources": [...]}
    """
    selected = observations[-window:] if window and window > 0 else list(observations)
    metrics: dict = {"observations": len(selected)}
    metrics["sources"] = sorted({o.source for o in selected})

    for field in _numeric_fields(selected):
        values = [o.payload[field] for o in selected
                  if isinstance(o.payload.get(field), (int, float))
                  and not isinstance(o.payload.get(field), bool)]
        if not values:
            continue
        metrics[field] = {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "avg": round(sum(values) / len(values), 4),
            "last": values[-1],
        }

    text = render_text(metrics, selected)
    return Summary(window=window, metrics=metrics, text=text)


def render_text(metrics: dict, observations: list[Observation]) -> str:
    """Человекочитаемая сводка (детерминированная, без LLM)."""
    lines = [f"Наблюдений в окне: {metrics.get('observations', 0)}"]
    sources = metrics.get("sources") or []
    if sources:
        lines.append(f"Источники: {', '.join(sources)}")
    for field, stats in metrics.items():
        if not isinstance(stats, dict) or "avg" not in stats:
            continue
        lines.append(
            f"{field}: count={stats['count']}, min={stats['min']}, "
            f"max={stats['max']}, avg={stats['avg']}, last={stats['last']}"
        )
    if observations:
        lines.append(f"Последнее наблюдение: {observations[-1].timestamp} "
                     f"({observations[-1].source})")
    return "\n".join(lines)
