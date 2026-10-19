# -*- coding: utf-8 -*-
"""Юнит-тесты LLM-клиента: абстракция, MockClient, RouterAIClient БЕЗ сети.

Любые вызовы RouterAIClient здесь изолированы заглушкой requests — живой вызов
запрещён (§3, §7 п.17).
"""
import os
import sys
from unittest.mock import patch, MagicMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from core.llm_client import LLMClient, MockClient, RouterAIClient


def test_llm_client_is_abstract():
    # LLMClient не инстанцируется напрямую — только через реализации.
    try:
        LLMClient()
        assert False, "LLMClient должен быть абстрактным"
    except TypeError:
        pass


def test_mock_client_deterministic():
    client = MockClient(name="T")
    a = client.complete([{"role": "system", "content": "x"}])
    b = client.complete([{"role": "system", "content": "x"}])
    assert a == b
    assert "T" in a
    assert "x" in a


def test_mock_client_reflects_layers():
    client = MockClient()
    answer = client.complete([
        {"role": "system", "content": "[long_term]\nФакт"},
        {"role": "user", "content": "вопрос"},
    ])
    assert "long_term" in answer


def _fake_response(content):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return resp


def test_router_client_no_network_returns_none(tmp_path):
    # Сеть недостижима — complete обязан вернуть None и не падать.
    import requests as real_requests
    # Патчим ТОЛЬКО post — иначе requests.exceptions в except клиента станет MagicMock.
    with patch("core.llm_client.requests.post",
               side_effect=real_requests.exceptions.ConnectionError("no network")):
        client = RouterAIClient(api_key="test-key")
        assert client.complete([{"role": "user", "content": "x"}]) is None


def test_router_client_parses_choices(tmp_path):
    # Фейковый успех: проверяем разбор choices[0].message.content (без сети).
    with patch("core.llm_client.requests.post", return_value=_fake_response("ответ")):
        client = RouterAIClient(api_key="test-key")
        assert client.complete([{"role": "user", "content": "x"}]) == "ответ"


def test_router_client_429_exhausts(tmp_path):
    # 429 на всех попытках → None (задержки не ждём: патчим time.sleep).
    import core.llm_client as llm
    with patch("core.llm_client.requests.post", return_value=_fake_response("")) as mock_post:
        fake = MagicMock()
        fake.status_code = 429
        mock_post.return_value = fake
        with patch.object(llm.time, "sleep", return_value=None):
            client = RouterAIClient(api_key="test-key")
            assert client.complete([{"role": "user", "content": "x"}]) is None