# -*- coding: utf-8 -*-
"""Юнит-тесты локальных LLM-клиентов и реестра моделей (Ревизия 8, этап 2).

Без сети: HTTP-вызовы подменяются фейковым `requests.post`/`get`. Живой прогон
на реальной модели — отдельно (гейт этапа 2), здесь только детерминированные
контракты.
"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from core.llm_client import (
    OpenAICompatClient, OllamaClient, ensure_loopback, LLMClient,
    parse_fallback_tool_call,
)
from core.model_registry import ModelRegistry, ModelSpec

MODELS_PATH = os.path.join(BASE_DIR, "models.json")
LMSTUDIO_ID = "lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K"


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_loopback_guard_rejects_external():
    """Не-loopback адрес → ValueError (приватность локального контура)."""
    for bad in ("http://example.com:1234", "http://10.0.0.5:11434",
                "https://api.openai.com"):
        try:
            ensure_loopback(bad)
            assert False, f"ожидался ValueError для {bad}"
        except ValueError:
            pass


def test_loopback_guard_accepts_localhost():
    assert ensure_loopback("http://127.0.0.1:1234") == "http://127.0.0.1:1234"
    assert ensure_loopback("http://localhost:11434/") == "http://localhost:11434"


def test_openai_compat_payload_and_model(monkeypatch=None):
    """Запрос собран с правильным путём, полем model и параметрами."""
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse({"choices": [{"message": {"content": "ок"}}]})

    import core.llm_client as mod
    original = mod.requests.post
    mod.requests.post = fake_post
    try:
        client = OpenAICompatClient("http://127.0.0.1:1234", "some/model:Q6_K.gguf",
                                    max_tokens=128, timeout=42,
                                    params={"temperature": 0.1})
        answer = client.complete([{"role": "user", "content": "привет"}])
    finally:
        mod.requests.post = original
    assert answer == "ок"
    assert captured["url"] == "http://127.0.0.1:1234/v1/chat/completions"
    assert captured["json"]["model"] == "some/model:Q6_K.gguf"
    assert captured["json"]["max_tokens"] == 128
    assert captured["json"]["temperature"] == 0.1
    assert captured["timeout"] == 42


def test_openai_compat_timeout_returns_none():
    """Сетевой сбой → None, а не исключение."""
    import core.llm_client as mod
    import requests

    def fake_post(url, json=None, timeout=None):
        raise requests.exceptions.Timeout("boom")

    original = mod.requests.post
    mod.requests.post = fake_post
    try:
        client = OpenAICompatClient("http://127.0.0.1:1234", "m")
        assert client.complete([{"role": "user", "content": "x"}]) is None
    finally:
        mod.requests.post = original


def test_ollama_payload_options():
    """Ollama: путь /api/chat, stream=false, options с num_predict/num_ctx."""
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse({"message": {"content": "ответ"}})

    import core.llm_client as mod
    original = mod.requests.post
    mod.requests.post = fake_post
    try:
        client = OllamaClient("http://127.0.0.1:11434", "bge-m3:latest",
                              max_tokens=64, params={"num_ctx": 4096},
                              keep_alive="10m")
        answer = client.complete([{"role": "user", "content": "x"}])
    finally:
        mod.requests.post = original
    assert answer == "ответ"
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["json"]["stream"] is False
    assert captured["json"]["options"]["num_predict"] == 64
    assert captured["json"]["options"]["num_ctx"] == 4096
    assert captured["json"]["keep_alive"] == "10m"


def test_ollama_complete_with_tools_fallback():
    """Ollama: fallback-протокол разбирает {"tool":…} из текста."""
    import core.llm_client as mod

    def fake_post(url, json=None, timeout=None):
        return FakeResponse({"message": {"content": '{"tool": "get_time", "arguments": {"timezone_name": "UTC"}}'}})

    original = mod.requests.post
    mod.requests.post = fake_post
    try:
        client = OllamaClient("http://127.0.0.1:11434", "m")
        reply = client.complete_with_tools([{"role": "user", "content": "время"}],
                                           tools=[{"type": "function",
                                                   "function": {"name": "get_time"}}])
    finally:
        mod.requests.post = original
    assert reply.tool_calls and reply.tool_calls[0]["name"] == "get_time"
    assert reply.tool_calls[0]["arguments"] == {"timezone_name": "UTC"}


def test_registry_builds_all_services():
    """build() для каждого сервиса возвращает объект LLMClient."""
    registry = ModelRegistry(MODELS_PATH)
    for spec in registry.list():
        client = registry.build(spec)
        assert isinstance(client, LLMClient), spec.id


def test_registry_unknown_model_lists_available():
    """use(неизвестный) → KeyError с перечнем доступных."""
    registry = ModelRegistry(MODELS_PATH)
    try:
        registry.use("nope:model")
        assert False, "ожидался KeyError"
    except KeyError as error:
        assert "не найдена" in str(error)
        assert "cloud:stepfun/step-3.5-flash" in str(error)


def test_registry_profile_overrides():
    """Профиль rag-strict накладывает temperature/max_tokens/context_window."""
    registry = ModelRegistry(MODELS_PATH)
    spec = registry.get(LMSTUDIO_ID)
    strict = spec.with_profile(registry.profiles)
    assert strict.params.get("temperature") == 0.1
    assert strict.params.get("max_tokens") == 700
    assert strict.context_window == 8192


def test_registry_use_persists_state(tmp_path):
    """use(id, user_dir) пишет model_state.json; load_state его читает."""
    registry = ModelRegistry(MODELS_PATH)
    user_dir = str(tmp_path / "u1")
    registry.use(LMSTUDIO_ID, user_dir=user_dir)
    state_path = os.path.join(user_dir, "model_state.json")
    assert os.path.exists(state_path)
    with open(state_path, encoding="utf-8") as handle:
        assert json.load(handle)["current"] == LMSTUDIO_ID
    fresh = ModelRegistry(MODELS_PATH)
    assert fresh.load_state(user_dir) == LMSTUDIO_ID


def test_registry_describe_has_label():
    registry = ModelRegistry(MODELS_PATH)
    info = registry.describe(LMSTUDIO_ID)
    assert info["service"] == "lmstudio"
    assert info["local"] is True
    assert info["quant"] == "Q6_K"
    assert "lmstudio/" in info["label"]


def test_agent_set_model_swaps_llm_and_executor():
    """Agent.set_model меняет и self.llm, и self.executor.llm в одном месте."""
    from core.agent import Agent, LLMExecutor
    from core.llm_client import MockClient
    from core.prompt_builder import PromptBuilder
    from memory.manager import MemoryManager, default_layers
    from storage.store import Store

    store = Store(os.path.join(BASE_DIR, "dev", "tests_debug", ".tmp", "reg_store"))
    memory = MemoryManager(default_layers(store), log=lambda l: None)
    builder = PromptBuilder("sys")
    first = MockClient(name="A")
    agent = Agent(first, memory, builder, store, user_id="t")
    second = MockClient(name="B")
    agent.set_model(second, label="lmstudio/test")
    assert agent.llm is second
    assert agent.executor.llm is second
    assert agent.model_label() == "lmstudio/test"