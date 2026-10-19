# -*- coding: utf-8 -*-
"""Юнит-тесты rag/embedding.py (этап 4, R2). Без Ollama."""
import math
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from rag.config import RagDependencyError
from rag.embedding import (EmbeddingCache, FakeEmbedder, HashingEmbedder,
                           OllamaEmbedder, SentenceTransformerEmbedder, make_embedder)


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def test_hashing_deterministic():
    emb = HashingEmbedder(dim=256)
    first = emb.embed(["инварианты проекта"])[0]
    second = emb.embed(["инварианты проекта"])[0]
    assert first == second


def test_hashing_dim_stable():
    emb = HashingEmbedder(dim=256)
    assert emb.dim == 256
    assert len(emb.embed(["текст"])[0]) == 256


def test_cosine_same_vs_different():
    emb = HashingEmbedder(dim=256)
    a, b, c = emb.embed(["правила проекта", "правила проекта", "совсем другой текст"])
    assert _cosine(a, b) > 0.999
    assert _cosine(a, c) < 0.9


def test_fake_embedder_reproducible():
    emb = FakeEmbedder(dim=16)
    assert emb.embed(["x"]) == emb.embed(["x"])
    assert len(emb.embed(["x"])[0]) == 16


def test_sentence_transformer_stub_raises():
    try:
        SentenceTransformerEmbedder()
    except RagDependencyError:
        return
    raise AssertionError("заглушка не подняла RagDependencyError")


def test_ollama_rejects_non_localhost():
    try:
        OllamaEmbedder(url="http://example.com:11434", model="bge-m3", dim=1024)
    except ValueError:
        return
    raise AssertionError("не-localhost URL не отвергнут")


def test_make_embedder_hashing():
    import dataclasses
    from rag.config import RagConfig
    cfg = dataclasses.replace(RagConfig.default().embedding, provider="hashing")
    emb = make_embedder(cfg)
    assert isinstance(emb, HashingEmbedder)


def test_embedding_cache_roundtrip(tmp_path):
    path = str(tmp_path / "emb_cache.json")
    cache = EmbeddingCache(path)
    cache.put("abc", [1.0, 2.0])
    cache.save()
    reloaded = EmbeddingCache(path)
    assert reloaded.get("abc") == [1.0, 2.0]
    assert reloaded.stats()["entries"] == 1
