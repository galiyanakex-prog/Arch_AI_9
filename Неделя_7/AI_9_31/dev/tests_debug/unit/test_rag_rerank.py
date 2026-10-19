# -*- coding: utf-8 -*-
"""Юнит-тесты порога отсечения и query rewrite (часть 2, этап 8, R6).

Офлайн проверяем МЕХАНИЗМ фильтра (отсекает всё выше порога; top-K после ≤ до;
порог 0 = выключен; sim пишется в scores) и rewrite (снятие шума, история,
не-ухудшение recall). Свойство «hit-rate@5 с фильтром не хуже, чем без» зависит
от шкалы эмбеддера и проверяется живым прогоном на bge-m3 (migr_log.md, этап 8),
т.к. порог абсолютный (косинус) и калибруется под модель.

Порог в офлайн-тестах берётся по шкале HashingEmbedder (~0.1–0.2), а не 0.45
(значение для bge-m3).
"""
import json
import os
import sys
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from rag.config import RagConfig
from rag.corpus import discover
from rag.embedding import HashingEmbedder
from rag.index import RagIndex
from rag.retrieval import Retriever
from rag.rewrite import rewrite

_CFG = RagConfig.default()          # threshold=0.0 (порог выключен)
_EMB = HashingEmbedder(dim=256)
_INDEX = None
_QUERIES = None
_HASH_THR = 0.14                     # калибровка под шкалу хэширующего эмбеддера


def _index():
    global _INDEX
    if _INDEX is None:
        _INDEX = RagIndex(_CFG)
        _INDEX.ingest(discover(None, _CFG.corpus), _CFG, _EMB)
    return _INDEX


def _retriever():
    return Retriever(_index(), _CFG, _EMB)


def _queries():
    global _QUERIES
    if _QUERIES is None:
        path = Path(BASE_DIR) / "rag/datasets/queries.jsonl"
        _QUERIES = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return _QUERIES


def _is_relevant(hit, relevant):
    for entry in relevant:
        path, _, symbol = entry.partition("::")
        if hit.source == path and (not symbol or symbol in hit.text or symbol in hit.section):
            return True
    return False


# --- механизм порога --------------------------------------------------------------
def test_high_threshold_cuts_all():
    hits = _retriever().search("несуществующая тема про квантовых китов", k=20,
                               threshold=0.99)
    assert hits == []


def test_topk_after_le_before():
    base = _retriever().search("как считается бюджет токенов", k=20, threshold=0.0)
    filtered = _retriever().search("как считается бюджет токенов", k=20,
                                   threshold=_HASH_THR)
    assert len(filtered) <= len(base)


def test_threshold_monotonic():
    """Выше порог — не больше хитов."""
    counts = [len(_retriever().search("как считается бюджет токенов", k=20, threshold=t))
              for t in (0.0, 0.1, 0.13, 0.16, 0.2)]
    assert counts == sorted(counts, reverse=True)


def test_threshold_zero_is_disabled():
    hits = _retriever().search("как считается бюджет токенов", k=5, threshold=0.0)
    assert len(hits) > 0


def test_sim_recorded_in_scores():
    hits = _retriever().search("как считается бюджет токенов", k=5, threshold=_HASH_THR)
    assert hits and all("sim" in h.scores for h in hits)


# --- rewrite ----------------------------------------------------------------------
def test_rewrite_strips_noise():
    assert "пожалуйста" not in rewrite("пожалуйста, расскажи мне про бюджет токенов")
    assert "бюджет" in rewrite("пожалуйста, расскажи мне про бюджет токенов")


def test_rewrite_empty_is_empty():
    assert rewrite("") == ""


def test_rewrite_keeps_meaningful():
    assert "бюджет" in rewrite("как считается бюджет токенов")


def test_rewrite_heuristic_uses_history():
    out = rewrite("а как это?", history=["как считается бюджет токенов промпта"])
    assert "бюджет" in out or "токенов" in out or "промпта" in out


def test_rewrite_does_not_hurt_recall():
    retriever = _retriever()
    base = rewritten = 0
    for q in _queries():
        hits = retriever.search(q["query"], k=5, threshold=0.0)
        if any(_is_relevant(h, q.get("relevant", [])) for h in hits):
            base += 1
        hits_r = retriever.search(rewrite(q["query"]), k=5, threshold=0.0)
        if any(_is_relevant(h, q.get("relevant", [])) for h in hits_r):
            rewritten += 1
    n = len(_queries())
    assert rewritten / n >= base / n - 1e-9, f"rewrite ухудшил recall: {base} → {rewritten}"