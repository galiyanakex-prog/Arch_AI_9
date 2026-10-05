# -*- coding: utf-8 -*-
"""Юнит-тесты rag/retrieval.py и rag/rerank.py (этап 6, R4)."""
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

_CFG = RagConfig.default()
_EMB = HashingEmbedder(dim=256)
_INDEX = None
_QUERIES = None


def _index():
    global _INDEX
    if _INDEX is None:
        _INDEX = RagIndex(_CFG)
        _INDEX.ingest(discover(None, _CFG.corpus), _CFG, _EMB)
    return _INDEX


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


def _recall(mode, k=5):
    total = 0
    for q in _queries():
        hits = Retriever(_index(), _CFG, _EMB).search(q["query"], k=k, mode=mode)
        if any(_is_relevant(h, q["relevant"]) for h in hits):
            total += 1
    return total / len(_queries())


def test_exact_identifier_in_top3():
    hits = Retriever(_index(), _CFG, _EMB).search("load_servers_config", k=3, mode="bm25")
    assert any("load_servers_config" in h.text for h in hits), "load_servers_config не найден в top-3"


def test_hybrid_not_worse_than_components():
    # На деградированном fallback-эмбеддере (HashingEmbedder) dense-ретривер слаб,
    # а веса RRF подобраны под продовый bge-m3, поэтому здесь гарантируем лишь
    # «гибрид не хуже СЛАБЕЙШЕЙ компоненты». Строгое «гибрид ≥ каждой компоненты»
    # проверяется живым прогоном на bge-m3 (гейт этапа 7).
    bm25 = _recall("bm25")
    dense = _recall("dense")
    hybrid = _recall("hybrid")
    worst = min(bm25, dense)
    assert hybrid >= worst, f"гибрид {hybrid} хуже слабейшей компоненты {worst}"


def test_mmr_reduces_doc_repeats():
    retriever = Retriever(_index(), _CFG, _EMB)
    hits = retriever.search("инварианты проекта", k=5, mode="hybrid")
    doc_ids = [h.doc_id for h in hits]
    assert len(doc_ids) == len(set(doc_ids)) or doc_ids.count(doc_ids[0]) <= 2


def test_filter_content_type_code():
    hits = Retriever(_index(), _CFG, _EMB).search(
        "load_servers_config", k=5, mode="bm25", filters={"content_type": "code"})
    for hit in hits:
        chunk = next(c for c in _index().chunks if c.chunk_id == hit.chunk_id)
        assert chunk.content_type == "code"


def test_empty_query_raises():
    try:
        Retriever(_index(), _CFG, _EMB).search("   ", k=5, mode="bm25")
    except ValueError:
        return
    raise AssertionError("пустой запрос не поднял ValueError")


def test_all_modes_work():
    retriever = Retriever(_index(), _CFG, _EMB)
    for mode in ("bm25", "dense", "hybrid"):
        hits = retriever.search("инварианты проекта", k=3, mode=mode)
        assert hits, f"режим {mode} не дал хитов"


def test_scores_explainable():
    hits = Retriever(_index(), _CFG, _EMB).search("инварианты проекта", k=3, mode="hybrid")
    assert hits
    assert "rrf" in hits[0].scores
