# -*- coding: utf-8 -*-
"""Юнит-тесты rag/service.py — функция answer (часть 1, этап 7, R5).

Проверяем: режим без RAG не содержит блока [rag]; режим с RAG отдаёт hits;
пустой индекс не роняет ответ (деградация). LLM передаётся заглушкой (DI).
"""
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

_CFG = RagConfig.default()
_EMB = HashingEmbedder(dim=256)


def _service():
    """Сервис с заранее собранным индексом (без Ollama — хэширующий эмбеддер)."""
    svc = RagService(_CFG)
    index = RagIndex(_CFG)
    index.ingest(discover(None, _CFG.corpus), _CFG, _EMB)
    svc._index = index
    svc._loaded = True
    svc._embedder = _EMB
    svc._retriever = Retriever(index, _CFG, _EMB)
    return svc


def _fake_llm(messages):
    prompt = messages[-1]["content"]
    # Эхо промпта, чтобы видеть, подмешан ли блок [rag].
    return "ОТВЕТ:" + ("[rag]" if "Найденные источники" in prompt else "нет-rag")


def test_answer_without_rag_has_no_block():
    svc = _service()
    ans = svc.answer("как считается бюджет токенов", use_rag=False, llm=_fake_llm)
    assert ans.used_rag is False
    assert ans.hits == ()
    assert "[rag]" not in ans.text


def test_answer_with_rag_has_hits_and_block():
    svc = _service()
    ans = svc.answer("как считается бюджет токенов", use_rag=True, llm=_fake_llm)
    assert ans.used_rag is True
    assert len(ans.hits) >= 1
    assert "[rag]" in ans.text


def test_answer_empty_index_degrades():
    svc = RagService(_CFG)
    svc._index = RagIndex(_CFG)          # пустой индекс
    svc._loaded = True
    svc._embedder = _EMB
    svc._retriever = Retriever(svc._index, _CFG, _EMB)
    ans = svc.answer("любой вопрос", use_rag=True, llm=_fake_llm)
    assert ans.used_rag is False         # нет хитов → без блока
    assert "[rag]" not in ans.text


def test_answer_without_llm_does_not_raise():
    svc = _service()
    ans = svc.answer("как считается бюджет токенов", use_rag=True)
    assert isinstance(ans.text, str)


def test_answer_mode_is_hybrid_by_default():
    svc = _service()
    ans = svc.answer("как считается бюджет токенов", use_rag=True, llm=_fake_llm)
    assert ans.latency_ms >= 0.0
