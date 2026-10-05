# -*- coding: utf-8 -*-
"""Юнит-тесты кэша поиска и multi-query (этап 10, R8).

Не зависят от Ollama: кэш проверяется напрямую, интеграция — на фейковом
ретривере со счётчиком вызовов, multi-query — на детерминированной эвристике.
"""
import os
import sys
import time
import types

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from rag.cache import SearchCache, make_key
from rag.config import RagConfig
from rag.service import RagService, _heuristic_variants
from rag.types import Hit


def cache_cfg(max_entries=256, ttl=900, enabled=True):
    return types.SimpleNamespace(enabled=enabled, max_entries=max_entries,
                                 ttl_seconds=ttl)


def hit(chunk_id="d1#1", doc_id="d1"):
    return Hit(chunk_id=chunk_id, doc_id=doc_id, source="a.md", title="", section="",
               text="текст", score=0.1, scores={})


# --- ключ -------------------------------------------------------------------------
def test_key_normalizes_query_and_is_stable():
    a = make_key("m", "v1", "Как Считается Бюджет?", {"k": 5}, None)
    b = make_key("m", "v1", "как считается бюджет", {"k": 5}, {})
    assert a == b                                   # регистр/пунктуация не важны


def test_key_sensitive_to_params_and_filters():
    base = make_key("m", "v1", "q", {"k": 5}, None)
    assert base != make_key("m", "v1", "q", {"k": 10}, None)
    assert base != make_key("m", "v1", "q", {"k": 5}, {"source": "*.py"})
    assert base != make_key("m", "v2", "q", {"k": 5}, None)   # версия индекса


# --- механика кэша ----------------------------------------------------------------
def test_put_get_roundtrip():
    cache = SearchCache(cache_cfg())
    cache.put("k", [hit()], {"d1": 1.0})
    assert cache.get("k", {"d1": 1.0}) == [hit()]
    assert cache.stats()["hits"] == 1


def test_ttl_expiry():
    cache = SearchCache(cache_cfg(ttl=-1))          # уже истёк
    cache.put("k", [hit()], {})
    assert cache.get("k", {}) is None
    assert cache.stats()["invalidations"] == 1


def test_mtime_invalidation():
    cache = SearchCache(cache_cfg())
    cache.put("k", [hit()], {"d1": 100.0})
    assert cache.get("k", {"d1": 100.0}) is not None   # не изменился
    cache.put("k2", [hit()], {"d1": 100.0})
    assert cache.get("k2", {"d1": 200.0}) is None      # mtime изменился → промах
    assert cache.stats()["invalidations"] == 1


def test_lru_eviction():
    cache = SearchCache(cache_cfg(max_entries=2))
    cache.put("a", [hit()], {})
    cache.put("b", [hit()], {})
    cache.get("a", {})                              # a — свежий
    cache.put("c", [hit()], {})                     # вытесняем b (самый старый)
    assert cache.get("b", {}) is None
    assert cache.get("a", {}) is not None
    assert cache.stats()["evictions"] == 1


def test_disabled_cache_never_stores():
    cache = SearchCache(cache_cfg(enabled=False))
    cache.put("k", [hit()], {})
    assert cache.get("k", {}) is None


# --- интеграция с RagService (счётчик реальных поисков) ---------------------------
class FakeIndex:
    def __init__(self, mtimes=None):
        self.meta = {"model_id": "fake", "dim": 4, "chunker_version": "1",
                     "strategy": "fixed", "docs": {"d1": {"sha1": "x", "mtime": 1.0}}}
        self.chunks = []
        self.vectors = []
        self.dim = 4
        self._mtimes = mtimes or {"d1": 1.0}

    def version(self):
        return "v1"

    def mtimes(self):
        return dict(self._mtimes)

    def stats(self):
        return {"n_docs": 1, "n_chunks": 0, "dim": 4, "model_id": "fake", "size_bytes": 0}


class CountingRetriever:
    def __init__(self, hits):
        self.hits = hits
        self.calls = 0

    def search(self, query, k=5, mode=None, filters=None):
        self.calls += 1
        return list(self.hits)

    def _rrf(self, rank_lists, rrf_k, weights=None):
        weights = weights or [1.0] * len(rank_lists)
        fused = {}
        for weight, ranks in zip(weights, rank_lists):
            for rank, key in enumerate(ranks):
                fused[key] = fused.get(key, 0.0) + weight / (rrf_k + rank + 1)
        return sorted(fused.items(), key=lambda kv: kv[1], reverse=True)


def make_service(hits, mtimes=None):
    svc = RagService(RagConfig.default())
    svc._index = FakeIndex(mtimes)
    svc._loaded = True
    svc._retriever = CountingRetriever(hits)
    return svc


def test_repeated_queries_hit_cache_once():
    svc = make_service([hit()])
    for _ in range(5):
        svc.search("как считается бюджет", k=5)
    assert svc._retriever.calls == 1                # 5 запросов → 1 реальный поиск
    assert svc.stats()["cache"]["hits"] == 4


def test_different_queries_are_separate():
    svc = make_service([hit()])
    svc.search("запрос один", k=5)
    svc.search("запрос два", k=5)
    assert svc._retriever.calls == 2


def test_cache_invalidated_by_mtime_change():
    svc = make_service([hit()], mtimes={"d1": 1.0})
    svc.search("запрос", k=5)
    svc._index._mtimes = {"d1": 2.0}                # документ изменился
    svc.search("запрос", k=5)
    assert svc._retriever.calls == 2                # кэш невалиден → реальный поиск


def test_latency_recorded():
    svc = make_service([hit()])
    svc.search("запрос", k=5)
    assert svc.latency_stats()["n"] == 1


# --- multi-query ------------------------------------------------------------------
def test_heuristic_variants_without_llm():
    variants = _heuristic_variants("как считается бюджет токенов в промпте", 3)
    assert variants and all(v.strip() for v in variants)


def test_rephrase_uses_llm_lines():
    svc = RagService(RagConfig.default())
    def llm(messages):
        return "бюджет токенов промпта\nрасчёт бюджета контекста"
    variants = svc.rephrase("как считается бюджет", llm=llm, n=3)
    assert variants[0] == "как считается бюджет"
    assert "бюджет токенов промпта" in variants


def test_rephrase_falls_back_without_llm():
    svc = RagService(RagConfig.default())
    variants = svc.rephrase("как считается бюджет токенов", llm=None, n=3)
    assert len(variants) >= 2


def test_search_multi_fuses_variants():
    # Разные варианты находят разные чанки → RRF-склейка объединяет их.
    svc = RagService(RagConfig.default())
    svc._index = FakeIndex()
    svc._loaded = True

    class PerQueryRetriever:
        def __init__(self):
            self.calls = 0
        def search(self, query, k=5, mode=None, filters=None):
            self.calls += 1
            if "один" in query:
                return [hit("d1#1", "d1")]
            return [hit("d2#2", "d2")]
        def _rrf(self, rank_lists, rrf_k, weights=None):
            weights = weights or [1.0] * len(rank_lists)
            fused = {}
            for weight, ranks in zip(weights, rank_lists):
                for rank, key in enumerate(ranks):
                    fused[key] = fused.get(key, 0.0) + weight / (rrf_k + rank + 1)
            return sorted(fused.items(), key=lambda kv: kv[1], reverse=True)

    svc._retriever = PerQueryRetriever()
    hits = svc.search_multi("запрос", variants=["запрос один", "запрос два"], k=5)
    ids = {h.chunk_id for h in hits}
    assert ids == {"d1#1", "d2#2"}                  # оба варианта внесли вклад
    assert all("multi_rrf" in h.scores for h in hits)
