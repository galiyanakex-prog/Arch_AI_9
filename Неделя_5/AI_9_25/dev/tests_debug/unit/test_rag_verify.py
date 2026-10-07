# -*- coding: utf-8 -*-
"""Юнит-тесты источников, цитат и режима «не знаю» (часть 3, этап 9, R7)."""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from rag.config import RagConfig
from rag.corpus import discover
from rag.embedding import HashingEmbedder
from rag.index import RagIndex
from rag.retrieval import Retriever
from rag.service import RagService
from rag.sources import build_sources
from rag.citations import build_quotes
from rag.types import Hit

_CFG = RagConfig.default()
_EMB = HashingEmbedder(dim=256)


def _hit(chunk_id="d1#0", source="a.py", section="S", text="бюджет токенов промпта", score=1.0):
    return Hit(chunk_id=chunk_id, doc_id=chunk_id.split("#")[0], source=source,
               title="", section=section, text=text, score=score)


def _service():
    svc = RagService(_CFG)
    index = RagIndex(_CFG)
    index.ingest(discover(None, _CFG.corpus), _CFG, _EMB)
    svc._index = index
    svc._loaded = True
    svc._embedder = _EMB
    svc._retriever = Retriever(index, _CFG, _EMB)
    return svc


def _fake_llm(messages):
    return "Бюджет токенов ограничивает размер промпта. [src]"


# --- sources ----------------------------------------------------------------------
def test_build_sources_dedup_and_sorted():
    hits = [_hit("d1#0", score=0.5), _hit("d2#0", score=0.9), _hit("d1#0", score=0.5)]
    src = build_sources(hits)
    assert len(src) == 2
    assert src[0].chunk_id == "d2#0"          # выше скор — первым
    assert src[0].source == "a.py"


def test_build_sources_empty():
    assert build_sources([]) == []


# --- citations --------------------------------------------------------------------
def test_build_quotes_from_chunks():
    hits = [_hit(text="Бюджет токенов ограничивает размер промпта. Есть и другие лимиты.")]
    quotes = build_quotes("Бюджет токенов ограничивает размер промпта.", hits)
    assert quotes and quotes[0].chunk_id == "d1#0"
    assert "бюджет" in quotes[0].text.lower()


def test_build_quotes_empty_without_hits():
    assert build_quotes("текст", []) == []


# --- answer с источниками/цитатами -------------------------------------------------
def test_answer_has_sources_and_quotes():
    svc = _service()
    ans = svc.answer("как считается бюджет токенов", use_rag=True, llm=_fake_llm)
    assert ans.sources and ans.quotes
    assert ans.verdict in ("ok", "partial", "hallucination", "insufficient", "unchecked")


def test_answer_insufficient_on_weak_context():
    """Порог выше любого скора → «не знаю» без LLM."""
    svc = _service()
    ans = svc.answer("несуществующая тема про квантовых китов", use_rag=True,
                     threshold=0.99, llm=_fake_llm)
    assert ans.verdict == "insufficient"
    assert ans.sources == () and ans.quotes == ()
    assert "уточн" in ans.text.lower() or "нет ответа" in ans.text.lower()


def test_answer_no_rag_has_no_sources():
    svc = _service()
    ans = svc.answer("как считается бюджет токенов", use_rag=False, llm=_fake_llm)
    assert ans.sources == () and ans.quotes == ()


# --- авто-перегенерация при strict (§9.5) ------------------------------------------
def test_strict_regenerates_on_hallucination():
    """Первый ответ с выдуманным числом и валидной ссылкой → hallucination → перегенерация."""
    svc = _service()
    hits = svc.search("как считается бюджет токенов", k=5, threshold=0.0)
    ref = f"[{hits[0].doc_id}#{hits[0].chunk_id}]"
    calls = {"n": 0}

    def llm(messages):
        calls["n"] += 1
        if calls["n"] == 1:
            return f"В системе ровно 999999 инвариантов. {ref}"
        return f"Бюджет токенов ограничивает размер промпта. {ref}"

    ans = svc.answer("как считается бюджет токенов", use_rag=True, llm=llm)
    assert calls["n"] == 2                      # была ровно одна перегенерация
    assert ans.verdict != "hallucination"


def test_insufficient_does_not_call_llm():
    svc = _service()
    calls = {"n": 0}

    def llm(messages):
        calls["n"] += 1
        return "ответ"

    svc.answer("квантовые киты", use_rag=True, threshold=0.99, llm=llm)
    assert calls["n"] == 0                      # «не знаю» — без вызова LLM


def test_verify_answers_summary():
    from rag.verify import verify_answers
    svc_queries = [{"id": "c99", "query": "как считается бюджет токенов"}]
    result = verify_answers(_CFG, svc_queries, k=5, llm=_fake_llm, limit=1)
    assert result["summary"]["n"] == 1
    assert result["summary"]["sources_ok"] == 1
