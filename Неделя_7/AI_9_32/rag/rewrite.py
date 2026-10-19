# -*- coding: utf-8 -*-
"""Query rewrite (часть 2 Задание.txt, этап 8, R6).

Переформулировка запроса ПЕРЕД поиском: убрать «шумовые» обороты, подтянуть
значимые термины из истории диалога (используется на этапе 11). Два режима:
  * `heuristic` — детерминированно, без LLM (по умолчанию; офлайн/тесты);
  * `llm` — переформулировка через LLM (DI: callable(messages)->str).

Границы: rag/ НЕ импортирует core/ — LLM приходит параметром. Rewrite обязан НЕ
ухудшать recall@5 (проверяется замером; иначе остаётся выключенным).
"""
from __future__ import annotations

import re

from rag.text import STOPWORDS, tokenize

# Шумовые обороты, которые не несут поисковой ценности и мешают BM25/dense.
_NOISE_PATTERNS = (
    r"^(пожалуйста|скажи|подскажи|расскажи|объясни|напомни)\b[,:]?\s*",
    r"\b(мне|нам|пожалуйста|будь добр)\b",
    r"\b(можешь ли ты|не мог бы ты|не подскажешь)\b",
    r"\b(в общем|короче|типа|как бы|вообще)\b",
)


def rewrite(query: str, history: list = None, llm=None, mode: str = "heuristic") -> str:
    """Переформулировать запрос. Возвращает НЕпустую строку (fallback — исходный).

    `history` — список прошлых сообщений пользователя (строки); значимые термины
    из них добавляются к запросу, если он короткий/местоименный. `mode`:
    `heuristic` (по умолчанию) | `llm`.
    """
    query = (query or "").strip()
    if not query:
        return query
    if mode == "llm" and llm is not None:
        result = _rewrite_llm(query, history, llm)
        if result:
            return result
    return _rewrite_heuristic(query, history)


def _rewrite_heuristic(query: str, history: list = None) -> str:
    """Убрать шум, при местоименном запросе — подтянуть термины из истории."""
    cleaned = query
    for pattern in _NOISE_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ?!.,;:")

    # Местоименный/слишком короткий запрос («а как это?») — добавим термины из истории.
    words = [w for w in tokenize(cleaned) if w not in STOPWORDS and len(w) >= 3]
    if history and len(words) <= 2:
        extra = _history_terms(history, limit=6)
        if extra:
            cleaned = (cleaned + " " + " ".join(extra)).strip()
    return cleaned or query


def _history_terms(history: list, limit: int = 6) -> list:
    """Значимые термины последних сообщений пользователя (частотные, дедуп)."""
    counts = {}
    for message in history[-4:]:
        text = message if isinstance(message, str) else str(message)
        for word in tokenize(text):
            if len(word) >= 4 and word not in STOPWORDS:
                counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts, key=lambda w: (-counts[w], w))
    return ranked[:limit]


def _rewrite_llm(query: str, history: list, llm) -> str:
    """Переформулировка через LLM (DI). Ошибка/пусто → "" (вызывающий уйдёт в heuristic)."""
    context = ""
    if history:
        context = "История:\n" + "\n".join(str(h) for h in history[-4:]) + "\n"
    prompt = (
        "Переформулируй поисковый запрос для поиска по базе знаний: сохрани смысл, "
        "убери вежливые обороты, добавь ключевые термины. Верни ОДНУ строку без "
        "пояснений.\n" + context + f"Запрос: {query}")
    try:
        text = llm([{"role": "user", "content": prompt}]) or ""
    except Exception:
        return ""
    line = text.strip().splitlines()[0].strip(" -•\"'") if text.strip() else ""
    return line
