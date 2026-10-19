# -*- coding: utf-8 -*-
"""Юнит-тесты rag/eval.py и rag/compare.py (этап 7, R5)."""
import dataclasses
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from rag.config import RagConfig
from rag.corpus import discover
from rag.embedding import HashingEmbedder
from rag.eval import evaluate
from rag.index import RagIndex
from rag.types import Hit

_CFG = RagConfig.default()
# Юниты не зависят от живого Ollama: сравнение стратегий гоняем на HashingEmbedder.
_CFG_HASH = dataclasses.replace(
    _CFG, embedding=dataclasses.replace(_CFG.embedding, provider="hashing"))
_EMB = HashingEmbedder(dim=256)
_INDEX = None


def _index():
    global _INDEX
    if _INDEX is None:
        _INDEX = RagIndex(_CFG)
        _INDEX.ingest(discover(None, _CFG.corpus), _CFG, _EMB)
    return _INDEX


class _PerfectRetriever:
    """Идеальный ретривер: всегда возвращает релевантный чанк первым."""

    def __init__(self, index):
        self.index = index

    def search(self, query, k=5, mode=None, filters=None, threshold=None):
        chunk = self.index.chunks[0]
        return [Hit(chunk_id=chunk.chunk_id, doc_id=chunk.doc_id, source=chunk.source,
                    title=chunk.title, section=chunk.section, text=chunk.text, score=1.0)]


def test_metrics_in_range():
    report = evaluate(_index(), [{"id": "q", "query": "инварианты", "relevant": ["core/invariants.py::InvariantChecker"]}],
                      k=5, retriever=__import__("rag.retrieval", fromlist=["Retriever"]).Retriever(_index(), _CFG, _EMB))
    for name, value in report.metrics.items():
        assert 0.0 <= value <= 1.0, f"{name}={value} вне [0,1]"


def test_perfect_retriever_recall_one():
    chunk = _index().chunks[0]
    dataset = [{"id": "q1", "query": "x", "relevant": [f"{chunk.source}::{chunk.text[:20]}"]}]
    report = evaluate(_index(), dataset, k=5, retriever=_PerfectRetriever(_index()))
    assert report.metrics["recall@k"] == 1.0
    assert report.metrics["hit_rate@k"] == 1.0


def test_empty_dataset_no_crash():
    report = evaluate(_index(), [], k=5, retriever=_PerfectRetriever(_index()))
    assert report.metrics["recall@k"] == 0.0


def test_ndcg_monotonic_by_position():
    from rag.eval import _dcg
    assert _dcg([1, 0, 0]) > _dcg([0, 1, 0]) > _dcg([0, 0, 1])


def test_compare_all_configurations():
    from rag.compare import compare
    report = compare(_CFG_HASH, ["fixed", "structural"], ["bm25", "hybrid"],
                     [{"id": "q1", "query": "инварианты проекта",
                       "relevant": ["core/invariants.py::InvariantChecker"]}], k=5)
    assert len(report.rows) == 4
    assert report.best
    assert report.model_id


def test_compare_report_renders():
    from rag.compare import compare, render_report
    report = compare(_CFG_HASH, ["fixed", "structural"], ["bm25"],
                     [{"id": "q1", "query": "инварианты проекта",
                       "relevant": ["core/invariants.py::InvariantChecker"]}], k=5)
    text = render_report(report)
    assert "Таблица" in text and "Вердикт" in text
    assert "Эффект реранкинга" in text


def test_weighted_rrf_mechanism():
    """Механизм взвешенного RRF: при равных рангах dense-кандидат выше bm25-кандидата.

    Эмпирическое «гибрид ≥ каждой компоненты» — это гейт ЖИВОГО прогона на bge-m3
    (этап 7: hybrid 0.9167 vs dense 0.875 / bm25 0.750). На деградированном
    fallback-эмбеддере (HashingEmbedder) dense-ретривер слаб, поэтому юнит
    проверяет только сам механизм весов, детерминированно.
    """
    from rag.retrieval import Retriever
    retriever = Retriever(_index(), _CFG, _EMB)
    # bm25: [10, 20]; dense: [20, 30] — кандидат 20 есть в обоих списках.
    fused = retriever._rrf([[10, 20], [20, 30]], rrf_k=60, weights=[0.3, 1.0])
    order = [idx for idx, _ in fused]
    assert order[0] == 20, f"кандидат из обоих списков должен быть первым, получено {order}"
    # При равных весах кандидат 10 (rank 0 в bm25) обгоняет 30 (rank 1 в dense).
    equal = [idx for idx, _ in retriever._rrf([[10, 20], [20, 30]], rrf_k=60, weights=[1.0, 1.0])]
    assert equal.index(10) < equal.index(30), f"равные веса: {equal}"


def test_rrf_weights_configured():
    assert _CFG.retrieval.rrf_weight_dense > _CFG.retrieval.rrf_weight_bm25
