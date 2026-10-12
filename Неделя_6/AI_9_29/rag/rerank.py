# -*- coding: utf-8 -*-
"""Реранк кандидатов (этап 6, R4; уточнён на этапе 7, R5).

`LexicalReranker` — дешёвый лексический реранк: мягкое смешивание рангового
скора (RRF) с долей токенов запроса, найденных в чанке.

Почему смешивание, а не пересортировка: на реальном корпусе (bge-m3, 105 чанков)
сортировка только по лексическому пересечению УХУДШАЛА hit-rate@5 с 0.9167 до
0.8333 — лексика вытесняла верный чанк, найденный dense-ретривером. Проверены
также IDF-взвешивание, нормировка на длину, произведение dense×лексика и
мультипликативный буст — ни один дешёвый сигнал не улучшил ранговый фьюжн.
Поэтому сигнал добавляется с малым весом: реранк уточняет порядок, но не ломает
фьюжн. Настоящий cross-encoder (рекомендация куратора, `N5_audio` `[00:23:51]`)
подключается как отдельный провайдер, когда появятся зависимости.
"""
from __future__ import annotations

from rag.text import STOPWORDS, stem, tokenize


class Reranker:
    """Протокол реранкера."""

    def rerank(self, query: str, hits: list) -> list:
        raise NotImplementedError


class LexicalReranker(Reranker):
    """Лексический реранк: RRF-скор + вес × доля токенов запроса в чанке."""

    def __init__(self, weight: float = 0.05):
        self.weight = weight

    def _terms(self, text: str) -> set:
        return {stem(t) for t in tokenize(text) if t not in STOPWORDS}

    def rerank(self, query: str, hits: list) -> list:
        if not hits:
            return []
        query_terms = self._terms(query)
        if not query_terms:
            return list(hits)
        top = max(hit.score for hit in hits) or 1.0
        scored = []
        for hit in hits:
            overlap = len(query_terms & self._terms(hit.text)) / len(query_terms)
            scored.append((hit, (hit.score / top) + self.weight * overlap))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [hit for hit, _ in scored]
