# -*- coding: utf-8 -*-
"""Сборка списка источников ответа (часть 3 Задание.txt, этап 9, R7).

Ответ обязан нести список источников с указанием `source` (путь) и
`section`/`chunk_id`. Здесь `Hit` → `Source` с дедупом по `chunk_id` и
сортировкой по убыванию скора.
"""
from __future__ import annotations

from rag.types import Source


def build_sources(hits: list) -> list:
    """Из найденных чанков собрать список Source (дедуп по chunk_id, сорт по скору).

    Порядок — по убыванию score: первый источник — самый релевантный. Пустые
    hits → [].
    """
    if not hits:
        return []
    seen = set()
    sources = []
    for hit in sorted(hits, key=lambda h: h.score, reverse=True):
        if hit.chunk_id in seen:
            continue
        seen.add(hit.chunk_id)
        sources.append(Source(
            source=getattr(hit, "source", "") or "",
            section=getattr(hit, "section", "") or "",
            chunk_id=hit.chunk_id,
            score=round(getattr(hit, "score", 0.0) or 0.0, 4)))
    return sources


def render_sources(sources: list) -> str:
    """Человекочитаемый список источников (для отчёта/вывода агента)."""
    if not sources:
        return "Источники: —"
    lines = ["Источники:"]
    for i, s in enumerate(sources, 1):
        section = f" · {s.section}" if s.section else ""
        lines.append(f"  [{i}] {s.source}{section} · {s.chunk_id} · score={s.score}")
    return "\n".join(lines)
