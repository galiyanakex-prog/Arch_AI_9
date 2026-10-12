# -*- coding: utf-8 -*-
"""Нормализация/токенизация/стемминг текста (этап 3, R1).

Ядро — только stdlib. Две дороги:
  * обычный текст — NFKC + casefold + снятие пунктуации, лёгкий рус. стеммер;
  * код — регистр СОХРАНЯЕТСЯ (идентификаторы значимы), snake_case дробится.

Оценка токенов — эвристика len/4 (приближение, не BPE): она нужна для бюджета
чанков, а не для точного счёта. Это помечено явно, чтобы никто не принял её за
реальный токенизатор модели.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# --- стоп-слова ---
_STOPWORDS_PATH = Path(__file__).with_name("stopwords_ru_en.txt")


def _load_stopwords() -> frozenset:
    try:
        lines = _STOPWORDS_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return frozenset()
    return frozenset(
        ln.strip().lower() for ln in lines
        if ln.strip() and not ln.strip().startswith("#")
    )


STOPWORDS = _load_stopwords()

# --- регулярки ---
_WORD_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")
# Сокращения, после которых точка НЕ завершает предложение.
_ABBREV = {"т", "е", "д", "п", "г", "гг", "рис", "см", "стр", "напр", "т.е", "т.д"}
_PUNCT_RE = re.compile(r"[^\w\s]|_", re.UNICODE)
_SNAKE_RE = re.compile(r"[A-Za-z0-9]+")


def normalize(text: str) -> str:
    """NFKC + casefold + снятие пунктуации — для BM25/сравнения строк."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = _PUNCT_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> list:
    """Список токенов (слова + числа) из нормализованного текста."""
    return _WORD_RE.findall(normalize(text))


def stem(word: str) -> str:
    """Лёгкий рус. стеммер: срезает частые окончания (не полный Портер)."""
    w = word.lower()
    if len(w) <= 4:
        return w
    for suffix in ("иями", "ями", "ами", "ого", "ему", "ыми", "ими", "ей", "ой",
                   "ая", "ое", "ые", "ий", "ый", "ов", "ев", "ах", "ях", "ам",
                   "ям", "ом", "ем", "ую", "юю", "ия", "ие", "ый", "а", "я", "о",
                   "е", "у", "ю", "ы", "и", "ь"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[: -len(suffix)]
    return w


def split_sentences(text: str) -> list:
    """Сплит по предложениям; сокращения («т. е.», «рис.») не рвут границу."""
    if not text:
        return []
    parts = _SENT_SPLIT_RE.split(text)
    sentences = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Если предыдущее «предложение» кончается сокращением — склеиваем обратно.
        if sentences and sentences[-1].rstrip(".").split()[-1:]:
            last_word = sentences[-1].rstrip(".").split()[-1].lower()
            if last_word in _ABBREV:
                sentences[-1] = f"{sentences[-1]} {part}"
                continue
        sentences.append(part)
    return sentences


def est_tokens(text: str) -> int:
    """Приблизительная оценка токенов: len/4 (НЕ реальный BPE-счёт)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def normalize_code(text: str) -> str:
    """Нормализация кода: регистр сохраняется, snake_case дробится на части."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    parts = []
    for token in _SNAKE_RE.findall(text):
        # snake_case / kebab-case → отдельные слова; CamelCase → тоже дробим.
        for piece in re.split(r"[_\-]+", token):
            if not piece:
                continue
            parts.extend(re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", piece))
    return " ".join(parts).lower()