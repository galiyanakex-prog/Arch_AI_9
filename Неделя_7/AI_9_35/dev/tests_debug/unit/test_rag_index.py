# -*- coding: utf-8 -*-
"""Юнит-тесты rag/index.py и rag/corpus.py (этап 5, R3)."""
import dataclasses
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from rag.config import RagConfig
from rag.corpus import delta, discover
from rag.embedding import FakeEmbedder
from rag.index import RagIndex


def _cfg(tmp_path):
    return dataclasses.replace(RagConfig.default(), index_dir=str(tmp_path / "index"))


def _docs():
    return [
        {"doc_id": "d1", "source": "a.md", "title": "A", "text": "инварианты проекта важны",
         "sha1": "s1", "mtime": 1.0, "content_type": "text"},
        {"doc_id": "d2", "source": "b.py", "title": "B", "text": "def build_agent(): return 1",
         "sha1": "s2", "mtime": 2.0, "content_type": "code"},
    ]


def test_build_and_search(tmp_path):
    cfg = _cfg(tmp_path)
    index = RagIndex(cfg)
    index.ingest(_docs(), cfg, FakeEmbedder(dim=16))
    hits = index.search_bm25("инварианты", 5)
    assert hits, "BM25 не нашёл ничего"
    assert index.chunks[hits[0][0]].doc_id == "d1"


def test_roundtrip_bm25_identical(tmp_path):
    cfg = _cfg(tmp_path)
    index = RagIndex(cfg)
    index.ingest(_docs(), cfg, FakeEmbedder(dim=16))
    before = index.search_bm25("build_agent", 5)
    index.save(cfg.index_dir)
    loaded = RagIndex.load(cfg.index_dir, cfg)
    after = loaded.search_bm25("build_agent", 5)
    assert [i for i, _ in before] == [i for i, _ in after]
    assert [round(s, 6) for _, s in before] == [round(s, 6) for _, s in after]


def test_incremental_no_reembed(tmp_path):
    cfg = _cfg(tmp_path)
    index = RagIndex(cfg)
    report1 = index.ingest(_docs(), cfg, FakeEmbedder(dim=16))
    assert report1.embed_calls > 0
    report2 = index.ingest(_docs(), cfg, FakeEmbedder(dim=16))
    assert report2.embed_calls == 0, "неизменённый корпус переэмбеднился"
    assert report2.skipped == 2


def test_incremental_one_changed(tmp_path):
    cfg = _cfg(tmp_path)
    index = RagIndex(cfg)
    index.ingest(_docs(), cfg, FakeEmbedder(dim=16))
    changed = _docs()
    changed[0]["sha1"] = "s1-new"
    changed[0]["text"] = "совсем другой текст про инварианты"
    report = index.ingest(changed, cfg, FakeEmbedder(dim=16))
    assert report.updated == 1
    assert report.skipped == 1
    assert report.embed_calls > 0


def test_rebuild_on_model_change(tmp_path):
    cfg = _cfg(tmp_path)
    index = RagIndex(cfg)
    index.ingest(_docs(), cfg, FakeEmbedder(dim=16))
    assert index.needs_rebuild(cfg, FakeEmbedder(dim=16)) is False
    assert index.needs_rebuild(cfg, FakeEmbedder(dim=32)) is True


def test_empty_index_search(tmp_path):
    cfg = _cfg(tmp_path)
    index = RagIndex(cfg)
    assert index.search_bm25("что угодно", 5) == []
    assert index.search_dense([0.1] * 16, 5) == []


def test_stats_filled(tmp_path):
    cfg = _cfg(tmp_path)
    index = RagIndex(cfg)
    index.ingest(_docs(), cfg, FakeEmbedder(dim=16))
    index.save(cfg.index_dir)
    stats = index.stats()
    assert stats["n_docs"] == 2
    assert stats["n_chunks"] > 0
    assert stats["size_bytes"] > 0


def test_corpus_delta():
    known = {"d1": "s1", "d2": "old"}
    result = delta(_docs(), known)
    assert len(result["added"]) == 0
    assert len(result["updated"]) == 1
    assert result["updated"][0]["doc_id"] == "d2"
    assert result["removed"] == []


def test_corpus_discover_deny(tmp_path):
    cfg = dataclasses.replace(RagConfig.default(),
                              corpus=dataclasses.replace(RagConfig.default().corpus,
                                                         list_file=str(tmp_path / "list.txt")))
    ok = tmp_path / "ok.md"
    ok.write_text("текст", encoding="utf-8")
    (tmp_path / "list.txt").write_text(f"{ok}\n.env\nusers/x.json\n", encoding="utf-8")
    docs = discover(None, cfg)
    sources = [d["source"] for d in docs]
    assert str(ok) in sources
    assert ".env" not in sources


