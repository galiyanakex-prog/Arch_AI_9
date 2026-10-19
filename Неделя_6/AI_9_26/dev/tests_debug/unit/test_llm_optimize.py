# -*- coding: utf-8 -*-
"""Юнит-тесты оптимизации генерации (Ревизия 8, этап 7, часть 4).

Без сети. Проверяем контракты этапа 7:
  * профили параметров (`default`/`rag-strict`/`fast`) накладываются на спек;
  * параметры попадают в тело запроса — LM Studio (`temperature`/`max_tokens`/
    `top_p`) и Ollama (`options`: `temperature`/`num_predict`/`num_ctx`);
  * неизвестный профиль → KeyError со списком доступных;
  * строгий prompt-шаблон `render_local_rag_template` содержит требование ссылок
    и «не знаю», единую форму ссылки, лимит длины;
  * шаблон применяется ТОЛЬКО для локальной модели (`_apply_local_rag_template`);
  * облачный промпт байт-в-байт прежний (renderer=None → общий блок).
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

# Kod.py парсит argv при импорте — подставляем «пустой» argv.
sys.argv = [os.path.join(BASE_DIR, "Kod.py")]
import Kod  # noqa: E402

from core.model_registry import ModelRegistry  # noqa: E402
from core.prompt_builder import (  # noqa: E402
    render_rag, render_local_rag_template, LOCAL_RAG_INSTRUCTIONS,
    RAG_INSTRUCTIONS,
)

MODELS_PATH = os.path.join(BASE_DIR, "models.json")
LMSTUDIO_ID = "lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K"


class FakeHit:
    def __init__(self, doc="d1", chunk="c1", text="текст источника", source="docs/a.md",
                 section="Раздел", title="Заголовок"):
        self.doc_id = doc
        self.chunk_id = chunk
        self.text = text
        self.source = source
        self.section = section
        self.title = title


# --- 1. Профили параметров ------------------------------------------------------

def test_three_profiles_loaded():
    """Три профиля загружаются из models.json (default/rag-strict/fast)."""
    registry = ModelRegistry(MODELS_PATH)
    for name in ("default", "rag-strict", "fast"):
        assert name in registry.profiles, name


def test_profile_overrides_params():
    """rag-strict накладывает temperature/max_tokens/context_window/top_p."""
    registry = ModelRegistry(MODELS_PATH)
    spec = registry.get(LMSTUDIO_ID)
    strict = spec.with_profile(registry.profiles)
    assert strict.params.get("temperature") == 0.1
    assert strict.params.get("max_tokens") == 700
    assert strict.params.get("top_p") == 0.9
    assert strict.context_window == 8192


def test_default_profile_is_empty():
    """default — пустой профиль (точка «до»): параметры не переопределяются."""
    registry = ModelRegistry(MODELS_PATH)
    assert registry.profiles["default"] == {}


def test_unknown_profile_raises_with_list():
    """Неизвестный профиль → KeyError со списком доступных."""
    registry = ModelRegistry(MODELS_PATH)
    spec = registry.get(LMSTUDIO_ID)
    spec.profile = "bogus"
    try:
        spec.with_profile(registry.profiles)
    except KeyError as error:
        assert "bogus" in str(error)
        assert "rag-strict" in str(error)
        return
    raise AssertionError("ожидался KeyError для неизвестного профиля")


# --- 2. Параметры в теле запроса (оба пути) -------------------------------------

def test_lmstudio_params_in_request_body():
    """LM Studio: temperature/max_tokens/top_p попадают в тело /v1/chat/completions."""
    from core.llm_client import OpenAICompatClient
    captured = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "ок"}}]}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return FakeResponse()

    import core.llm_client as mod
    original = mod.requests.post
    mod.requests.post = fake_post
    try:
        client = OpenAICompatClient(
            "http://127.0.0.1:1234", "m", max_tokens=700,
            params={"temperature": 0.1, "top_p": 0.9})
        client.complete([{"role": "user", "content": "x"}])
    finally:
        mod.requests.post = original
    assert captured["json"]["max_tokens"] == 700
    assert captured["json"]["temperature"] == 0.1
    assert captured["json"]["top_p"] == 0.9


def test_ollama_params_in_options():
    """Ollama: temperature/num_predict/num_ctx попадают в options."""
    from core.llm_client import OllamaClient
    captured = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "ок"}}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return FakeResponse()

    import core.llm_client as mod
    original = mod.requests.post
    mod.requests.post = fake_post
    try:
        client = OllamaClient("http://127.0.0.1:11434", "m", max_tokens=700,
                              params={"temperature": 0.1, "num_ctx": 8192})
        client.complete([{"role": "user", "content": "x"}])
    finally:
        mod.requests.post = original
    assert captured["json"]["options"]["num_predict"] == 700
    assert captured["json"]["options"]["temperature"] == 0.1
    assert captured["json"]["options"]["num_ctx"] == 8192


def test_registry_build_applies_profile():
    """build() с профилем rag-strict кладёт параметры в клиент."""
    registry = ModelRegistry(MODELS_PATH)
    spec = registry.get(LMSTUDIO_ID)
    spec.profile = "rag-strict"
    client = registry.build(spec)
    assert client.max_tokens == 700
    assert client.params.get("temperature") == 0.1


# --- 3. Строгий prompt-шаблон ---------------------------------------------------

def test_local_template_has_citation_and_unknown():
    """Шаблон содержит требование ссылок и «не знаю»."""
    block = render_local_rag_template([FakeHit()], query="вопрос")
    assert "[d1#c1]" in block
    assert "В источниках нет ответа" in block
    assert LOCAL_RAG_INSTRUCTIONS in block


def test_local_template_single_citation_form():
    """Единая форма ссылки [doc_id#chunk_id] и запрет рассуждений вне источников."""
    block = render_local_rag_template([FakeHit()])
    assert "[doc_id#chunk_id]" in block
    assert "ТОЛЬКО по приведённым источникам" in block
    assert "не длиннее 5 предложений" in block


def test_local_template_empty_hits():
    """Пустая выдача → пустой блок (шаблон не добавляется)."""
    assert render_local_rag_template([]) == ""


def test_local_template_differs_from_general():
    """Строгий шаблон отличается от общего блока [rag]."""
    hits = [FakeHit()]
    general = render_rag(hits)
    strict = render_local_rag_template(hits)
    assert general != strict
    assert RAG_INSTRUCTIONS in general
    assert LOCAL_RAG_INSTRUCTIONS not in general


# --- 4. Шаблон только для локальной модели --------------------------------------

def _agent(tmp_path, model_id=None):
    from core.agent import Agent
    from core.llm_client import MockClient
    from core.prompt_builder import PromptBuilder
    from memory.manager import MemoryManager, default_layers
    from storage.store import Store

    store = Store(str(tmp_path / "store"))
    memory = MemoryManager(default_layers(store), log=lambda line: None)
    agent = Agent(MockClient(name="Mock"), memory, PromptBuilder("sys"), store,
                  user_id="t")
    registry = ModelRegistry(MODELS_PATH)
    if model_id:
        registry.use(model_id)
    agent.model_registry = registry
    return agent


def test_template_applied_for_local_model(tmp_path):
    """Локальная модель → строгий шаблон включён."""
    agent = _agent(tmp_path, model_id=LMSTUDIO_ID)
    Kod._apply_local_rag_template(agent)
    assert agent.rag_block_renderer is not None
    block = agent.rag_block_renderer([FakeHit()], "вопрос")
    assert LOCAL_RAG_INSTRUCTIONS in block


def test_template_not_applied_for_cloud_model(tmp_path):
    """Облачная модель → renderer=None (облачный промпт байт-в-байт прежний)."""
    agent = _agent(tmp_path, model_id="cloud:stepfun/step-3.5-flash")
    Kod._apply_local_rag_template(agent)
    assert agent.rag_block_renderer is None


def test_cloud_prompt_unchanged_without_renderer(tmp_path):
    """Без renderer блок [rag] собирается общим шаблоном (как до этапа 7)."""
    from rag.config import RagConfig
    from rag.service import RagService

    cfg = RagConfig.default()
    svc = RagService(cfg)
    hits = [FakeHit()]
    assert svc.context_block(hits=hits) == render_rag(hits)
    assert svc.context_block(hits=hits, block_renderer=None) == render_rag(hits)


def test_service_uses_block_renderer():
    """context_block с block_renderer использует переданный шаблон (DI)."""
    from rag.config import RagConfig
    from rag.service import RagService

    svc = RagService(RagConfig.default())
    hits = [FakeHit()]
    block = svc.context_block(hits=hits,
                              block_renderer=lambda h, q="": render_local_rag_template(h))
    assert LOCAL_RAG_INSTRUCTIONS in block
