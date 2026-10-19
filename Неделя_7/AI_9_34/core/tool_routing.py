# -*- coding: utf-8 -*-
"""core/tool_routing.py — осмысленный выбор инструмента под запрос (День 20, D4).

Чистая функция `rank_tools(query, tools)`: сопоставляет текст запроса (часто
русский) с инструментами каталога (имена + описания на английском) и возвращает
ранжированный список кандидатов с обоснованием.

Зачем RU→EN-эвристика: каталог MCP-серверов описан по-английски
(`get_time`, `search`, `summarize`, `schedule_reminder`), а пользователь пишет
по-русски («который час», «собери данные», «напомни»). Без перевода намерение не
совпадает с именами — маршрут уходит «в никуда».

Модуль НЕ знает ни про MCP SDK, ни про сеть, ни про `ToolRegistry`
(чистые данные: `rank_tools(query, tools)` → `list[ToolMatch]`). Тип элемента
`tools` — любой объект с полями `name`/`description` (`ToolDescriptor` подходит).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# RU→EN-эвристика: ключевые слова запроса → слова, ожидаемые в имени/описании тула.
# Тематический словарь домена задания (время, данные-пайплайн, планировщик, погода).
RU_EN_HINTS: dict[str, tuple[str, ...]] = {
    # время
    "время": ("time",), "час": ("time",), "часов": ("time",), "сейчас": ("time",),
    "дата": ("time", "date"), "который": ("time",),
    # данные / пайплайн (получить → обработать → сохранить)
    "собери": ("search",), "найди": ("search", "find"),
    "данные": ("search", "data"), "данных": ("search", "data"),
    "поиск": ("search", "find"), "ищи": ("search",),
    "сводк": ("summarize", "summary"), "суммируй": ("summarize",),
    "итог": ("summarize", "summary"),
    "файл": ("file",), "сохран": ("save",),
    # планировщик / напоминания
    "напоминание": ("remind", "schedule"), "напом": ("remind", "schedule"),
    "расписан": ("schedule", "job"),
    "периодич": ("schedule", "collection"),
    "задач": ("job", "schedule"), "задани": ("job", "schedule"),
    # погода
    "погод": ("weather", "forecast"), "прогноз": ("forecast",),
    "температур": ("weather", "forecast"), "дожд": ("weather",),
    "город": ("location",), "координат": ("location",),
}

# Глаголы-ДЕЙСТВИЯ: задают основное намерение и перевешивают существительные
# («напомни о СВОДКЕ» — это напоминание, а не сводка). Совпадение по имени — вес 3.
RU_ACTION_HINTS: dict[str, tuple[str, ...]] = {
    "напомни": ("remind",), "напоминай": ("remind",),
    "сохрани": ("save",), "запиши": ("save",),
    "обработай": ("summarize",), "суммируй": ("summarize",),
    "прочитай": ("read",), "открой": ("read",),
    "собери": ("search",), "найди": ("search",), "поищи": ("search",),
    "запланируй": ("schedule",), "запусти": ("run", "due"),
    "покажи": ("get", "latest"), "выдай": ("get",),
}

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_TOKEN = re.compile(r"[a-zA-Zа-яА-Я0-9_]+")

# Частые RU-слова, которые не несут намерения (иначе «что/этот/сделай» ловят ложь).
_STOPWORDS = {
    "что", "этот", "эта", "это", "эти", "как", "для", "мне", "мой", "моя",
    "сделай", "нужно", "надо", "можно", "если", "или", "еще", "ещё", "без",
    "про", "под", "над", "при", "чем", "так", "все", "всё", "уже", "его", "её",
    "the", "and", "for", "with", "that", "this", "from", "into",
}


def _tokens(text: str) -> list[str]:
    """Разбить текст на токены (RU/EN), нижний регистр, длина >= 3, без стоп-слов."""
    return [t.lower() for t in _TOKEN.findall(text or "")
            if len(t) >= 3 and t.lower() not in _STOPWORDS]


def _extended_terms(query: str) -> set[str]:
    """Слова запроса + RU→EN-подсказки (по вхождению префикса ключа)."""
    terms: set[str] = set(_tokens(query))
    lowered = (query or "").lower()
    for key, english in RU_EN_HINTS.items():
        if key in lowered:
            terms.update(english)
    return terms


def _action_terms(query: str) -> set[str]:
    """Слова-ДЕЙСТВИЯ из глаголов запроса (приоритетные намерения)."""
    actions: set[str] = set()
    lowered = (query or "").lower()
    for key, english in RU_ACTION_HINTS.items():
        if key in lowered:
            actions.update(english)
    return actions


def _name_terms(tool) -> set[str]:
    """Токены ИМЕНИ инструмента (camelCase/snake_case, `mcp.<server>.<tool>`)."""
    name = getattr(tool, "name", "") or ""
    pieces: list[str] = []
    for part in name.split("."):
        pieces.extend(_CAMEL_BOUNDARY.sub(" ", part).replace("_", " ").split())
    return {p.lower() for p in pieces if len(p) >= 3}


def _desc_terms(tool) -> set[str]:
    """Токены ОПИСАНИЯ инструмента (без стоп-слов)."""
    return set(_tokens(getattr(tool, "description", "") or ""))


@dataclass
class ToolMatch:
    """Кандидат-инструмент с оценкой и человекочитаемым обоснованием."""

    name: str
    provider: str
    score: float
    reasons: list[str] = field(default_factory=list)


def rank_tools(query: str, tools, top: int = 3) -> list[ToolMatch]:
    """Ранжировать инструменты каталога под запрос `query`.

    Возвращает до `top` кандидатов с ненулевой оценкой, по убыванию оценки.
    Пустой список — «совпадений нет» (не подменяем весь каталог).
    Оценка: пересечение слов запроса/подсказок с именем (вес 2) и описанием (вес 1);
    бонус — вхождение подсказки в ИМЯ тула (сильный сигнал).
    """
    if not tools:
        return []
    terms = _extended_terms(query)
    actions = _action_terms(query)
    if not terms and not actions:
        return []
    matches: list[ToolMatch] = []
    for tool in tools:
        name = getattr(tool, "name", "") or ""
        name_l = name.lower()
        name_terms = _name_terms(tool)
        desc_terms = _desc_terms(tool)
        score = 0.0
        reasons: list[str] = []
        for term in terms:
            if term in name_terms or term in name_l:
                score += 2.0
                reasons.append(f"имя: «{term}»")
            elif term in desc_terms:
                score += 1.0
                reasons.append(f"описание: «{term}»")
        # Глаголы-действия в ИМЕНИ перевешивают существительные (вес 3).
        for act in actions:
            if act in name_terms or act in name_l:
                score += 3.0
                reasons.insert(0, f"действие: «{act}»")
        if score <= 0:
            continue
        matches.append(ToolMatch(
            name=name,
            provider=getattr(tool, "provider", "") or "",
            score=score,
            reasons=reasons[:4],
        ))
    matches.sort(key=lambda m: (-m.score, m.name))
    return matches[:top]
