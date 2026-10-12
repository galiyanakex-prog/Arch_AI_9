# -*- coding: utf-8 -*-
"""Сборка цитат ответа (часть 3 Задание.txt, этап 9, R7).

Ответ обязан нести дословные **цитаты** — фрагменты найденных чанков, наиболее
близкие утверждениям ответа. Цитаты берутся из ЧАНКОВ (не из текста ответа),
чтобы проверить, что модель не выдумывает. Переиспользует эвристики
`grounding.py` (`_best_chunk`, `_stems`, `_entities`, `split_sentences`).
"""
from __future__ import annotations

from rag.grounding import _best_chunk, _entities, _stems
from rag.text import split_sentences
from rag.types import Quote


def build_quotes(answer_text: str, hits: list, max_quotes: int = 5,
                 max_chars: int = 300) -> list:
    """Подобрать дословные цитаты из чанков под предложения ответа.

    Для каждого предложения ответа находим лучший чанк (`_best_chunk` по покрытию
    стем-токенов и сущностей) и берём из него предложение с максимальным
    пересечением. Дедуп по (chunk_id, текст), ограничение `max_quotes`.
    """
    if not hits or not answer_text:
        return []
    sentences = split_sentences(answer_text)
    seen = set()
    quotes = []
    for sent in sentences:
        s_stems = _stems(sent)
        s_entities = _entities(sent)
        best, _cov, _ent = _best_chunk(sent, hits, s_stems, s_entities)
        if best is None:
            continue
        fragment = _pick_fragment(sent, best.text, max_chars)
        if not fragment:
            continue
        key = (best.chunk_id, fragment)
        if key in seen:
            continue
        seen.add(key)
        quotes.append(Quote(chunk_id=best.chunk_id, text=fragment,
                            source=getattr(best, "source", "") or ""))
        if len(quotes) >= max_quotes:
            break
    return quotes


def _pick_fragment(sentence: str, chunk_text: str, max_chars: int) -> str:
    """Выбрать из чанка предложение, наиболее близкое к предложению ответа.

    Если чанк короткий — возвращаем его целиком (нормализованный по пробелам);
    иначе ищем предложение чанка с максимальным покрытием стем-токенов запроса.
    """
    text = " ".join((chunk_text or "").split())
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    best, best_score = "", -1.0
    target = _stems(sentence)
    for cand in split_sentences(text):
        cand = cand.strip()
        if not cand:
            continue
        c_stems = _stems(cand)
        score = len(target & c_stems) / len(target) if target else 0.0
        if score > best_score:
            best, best_score = cand, score
    fragment = best or text
    return fragment[:max_chars]


def render_quotes(quotes: list) -> str:
    """Человекочитаемый список цитат (для отчёта/вывода агента)."""
    if not quotes:
        return "Цитаты: —"
    lines = ["Цитаты:"]
    for i, q in enumerate(quotes, 1):
        snippet = " ".join(q.text.split())[:200]
        lines.append(f"  [{i}] {q.source} · {q.chunk_id}\n      «{snippet}»")
    return "\n".join(lines)