# -*- coding: utf-8 -*-
"""Контракты данных RAG-модуля (этап 0).

Три правила, которые здесь закреплены:
1. все объекты неизменяемы (frozen) — найденный чанк не «дописывается» по дороге;
2. у каждого объекта есть to_dict() — любой артефакт (индекс, отчёт, журнал) пишется
   из них без ручного конструирования словарей;
3. метаданные чанка (source/title/section/chunk_id) обязательны — это требование
   Задание_d21.txt, а не опция.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass(frozen=True)
class Chunk:
    """Кусочек документа — единица индексирования."""
    chunk_id: str                 # "<doc_id>#<номер>" — обязателен, уникален в индексе
    doc_id: str                   # sha1 пути документа
    source: str                   # путь к файлу (относительный от корня проекта)
    title: str                    # H1 документа или имя файла
    section: str                  # путь заголовков: "A > B > C" ("" — начало файла)
    text: str                     # собственно текст чанка
    strategy: str                 # "fixed" | "structural" | "semantic"
    content_type: str = "text"    # "text" | "code" | "table"
    start_line: int = 0
    end_line: int = 0
    tokens: int = 0               # оценка (эвристика), не гарантированный счёт BPE
    sha1: str = ""                # sha1 текста — ключ кэша эмбеддингов
    parent_id: str = ""           # parent-child: id блока, который отдаём в контекст

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DocMeta:
    """След документа в индексе — по нему считается инкрементальная дельта."""
    doc_id: str
    source: str
    sha1: str
    mtime: float
    n_chunks: int
    content_type: str = "text"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Hit:
    """Результат поиска. scores обязателен: выдача должна быть объяснима."""
    chunk_id: str
    doc_id: str
    source: str
    title: str
    section: str
    text: str
    score: float
    scores: dict = field(default_factory=dict)   # {bm25_rank, dense_rank, rrf, rerank}
    source_query: str = ""                       # какая переформулировка нашла (multi-query)
    parent_text: str = ""                        # если есть — отдаём в промпт его

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IngestReport:
    """Итог индексации: сколько и почему пересчитано."""
    added: int = 0
    updated: int = 0
    removed: int = 0
    skipped: int = 0                # совпал sha1 — не переэмбедили
    chunks: int = 0
    seconds: float = 0.0
    embed_calls: int = 0            # сколько раз реально обратились к эмбеддеру
    errors: tuple = ()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvalReport:
    """Метрики качества retrieval на golden-датасете."""
    k: int = 5
    metrics: dict = field(default_factory=dict)      # recall@k, precision@k, hit_rate@k, mrr, ndcg@k
    latency_ms: dict = field(default_factory=dict)   # p50, p95
    per_query: tuple = ()
    dataset: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CompareReport:
    """Сравнение стратегий чанкинга — прямой результат Задание_d21.txt."""
    rows: tuple = ()                # ({strategy, mode, **metrics}, ...)
    best: str = ""                  # "<strategy>/<mode>"
    verdict: str = ""               # человекочитаемое обоснование выбора
    divergences: tuple = ()         # разборы запросов, где стратегии разошлись
    k: int = 5
    model_id: str = ""              # сравнение осмысленно только при одном model_id

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GroundingReport:
    """Проверка «ответ опирается на найденное» (решение пользователя №4)."""
    verdict: str = "unchecked"      # ok | partial | hallucination | unchecked
    sentences: tuple = ()           # ({text, status, best_chunk_id, coverage, numbers_missing})
    citations_ok: bool = False
    regenerated: bool = False
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Source:
    """Источник ответа (часть 3 Задание.txt): путь + раздел + chunk_id + скор."""
    source: str                     # путь к файлу
    section: str                    # "A > B > C" ("" — начало файла)
    chunk_id: str                   # "<doc_id>#<номер>" (уникален в индексе)
    score: float = 0.0              # скор хита

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Quote:
    """Цитата (часть 3 Задание.txt): дословный фрагмент найденного чанка."""
    chunk_id: str
    text: str                       # дословный фрагмент (из чанка, не из ответа)
    source: str                     # путь файла-источника

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Answer:
    """Ответ RAG-функции (часть 1 Задание.txt): вопрос → поиск → LLM.

    Часть 3 добавляет обязательные `sources`/`quotes`/`verdict`: ответ обязан
    нести список источников (source + section/chunk_id) и дословные цитаты, а
    при слабом контексте — режим «не знаю» (verdict="insufficient").
    """
    text: str                       # ответ LLM
    used_rag: bool = False          # режим: с блоком [rag] или без
    hits: tuple = ()                # найденные чанки (Hit) — для отчёта/источников
    sources: tuple = ()             # list[Source]
    quotes: tuple = ()              # list[Quote]
    verdict: str = "unchecked"      # ok | partial | hallucination | insufficient | unchecked
    latency_ms: float = 0.0         # время ответа

    def to_dict(self) -> dict:
        return asdict(self)


