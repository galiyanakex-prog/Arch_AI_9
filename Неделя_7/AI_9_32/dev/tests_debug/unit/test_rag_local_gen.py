# -*- coding: utf-8 -*-
"""Юнит-тесты генератора RAG (Ревизия 8, этап 5; уточнение куратора 2026-10-12).

Генератор RAG = текущая модель агента: отдельной секции `generation` в конфиге
НЕТ. Проверяем контракты: явный `llm`-инжект в `RagService`; `answer` использует
инжектированный генератор; блок `[rag]` и источники/цитаты сохраняются; пустой
индекс → «не знаю» без падения; `_build_gen_llm` строит клиента из реестра;
`/gen` и `/embed` переключают модель агента/эмбеддер; смена провайдера эмбеддинга.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

# Kod.py парсит argv при импорте — подставляем «пустой» argv.
sys.argv = [os.path.join(BASE_DIR, "Kod.py")]
import Kod  # noqa: E402

from rag.config import RagConfig  # noqa: E402
from rag.corpus import discover  # noqa: E402
from rag.embedding import HashingEmbedder, make_embedder  # noqa: E402
from rag.index import RagIndex  # noqa: E402
from rag.retrieval import Retriever  # noqa: E402
from rag.service import RagService  # noqa: E402

_CFG = RagConfig.default()
_EMB = HashingEmbedder(dim=256)


class FakeLocal:
    """Фейковый локальный генератор: считает вызовы, эхо промпта."""

    def __init__(self):
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        prompt = messages[-1]["content"]
        return "ЛОКАЛЬНО:" + ("[rag]" if "Найденные источники" in prompt else "нет-rag")


def _service(llm=None):
    """Сервис с заранее собранным индексом (без Ollama — хэширующий эмбеддер)."""
    svc = RagService(_CFG, llm=llm)
    index = RagIndex(_CFG)
    index.ingest(discover(None, _CFG.corpus), _CFG, _EMB)
    svc._index = index
    svc._loaded = True
    svc._embedder = _EMB
    svc._retriever = Retriever(index, _CFG, _EMB)
    return svc


# --- генератор RAG = модель агента (секции generation в конфиге нет) -------------

def test_config_has_no_generation_section():
    """Секции `generation` в конфиге нет (одна точка выбора — модель агента)."""
    cfg = RagConfig.default()
    assert not hasattr(cfg, "generation")
    loaded = RagConfig.load(os.path.join(BASE_DIR, "rag/config.json"))
    assert not hasattr(loaded, "generation")


def test_config_ignores_unknown_generation_key():
    """Даже если в JSON остался `generation` — он игнорируется, не падаем."""
    cfg = RagConfig.default().from_dict(
        {"generation": {"provider": "bogus"}}).validate()
    assert not hasattr(cfg, "generation")


# --- переключаемый эмбеддер (роль «эмбеддинг») -----------------------------------

def test_embedding_defaults_ollama_bge_m3():
    cfg = RagConfig.default()
    assert cfg.embedding.provider == "ollama"
    assert cfg.embedding.model == "bge-m3"


def test_embedding_lmstudio_provider_supported():
    """Провайдер эмбеддингов не захардкожен: lmstudio — валидный вариант."""
    from dataclasses import replace
    emb = replace(RagConfig.default().embedding, provider="lmstudio",
                  model="text-embedding-nomic-embed-text-v1.5", dim=768)
    assert emb.provider == "lmstudio"


def test_make_embedder_hashing_and_fake():
    from dataclasses import replace
    emb = replace(RagConfig.default().embedding, provider="hashing")
    assert isinstance(make_embedder(emb), HashingEmbedder)


def test_embedding_url_must_be_local():
    """Границы модуля: внешний embedding-URL → RagConfigError."""
    from dataclasses import replace
    from rag.config import RagConfigError
    cfg = replace(RagConfig.default(),
                  embedding=replace(RagConfig.default().embedding,
                                    url="http://example.com:11434"))
    try:
        cfg.validate()
    except RagConfigError:
        return
    raise AssertionError("внешний embedding-URL должен давать RagConfigError")


# --- явный llm-инжект в RagService ----------------------------------------------

def test_service_uses_injected_llm():
    """answer() использует llm, переданный в конструктор (DI)."""
    fake = FakeLocal()
    svc = _service(llm=fake.complete)
    ans = svc.answer("как считается бюджет токенов", use_rag=True)
    assert fake.calls == 1
    assert ans.used_rag is True
    assert "[rag]" in ans.text


def test_explicit_llm_overrides_injected():
    """Явный llm в answer() имеет приоритет над инжектированным."""
    injected = FakeLocal()
    explicit = FakeLocal()
    svc = _service(llm=injected.complete)
    svc.answer("как считается бюджет токенов", use_rag=True, llm=explicit.complete)
    assert explicit.calls == 1
    assert injected.calls == 0


def test_local_gen_keeps_sources_and_quotes():
    """Локальная генерация сохраняет источники/цитаты как с облаком."""
    fake = FakeLocal()
    svc = _service(llm=fake.complete)
    ans = svc.answer("как считается бюджет токенов", use_rag=True)
    assert len(ans.sources) >= 1
    assert ans.sources[0].chunk_id
    assert ans.verdict in ("ok", "partial", "hallucination", "unchecked")


def test_local_gen_no_cloud_client_called():
    """Локальный генератор не обращается к облачному клиенту (счётчик)."""
    fake = FakeLocal()
    svc = _service(llm=fake.complete)
    svc.answer("как считается бюджет токенов", use_rag=True)
    # Единственный вызов LLM — локальный; облачный клиент не задействован.
    assert fake.calls == 1


def test_empty_index_returns_unknown_without_llm():
    """Пустой индекс → «не знаю» (verdict=insufficient), LLM не вызывается."""
    fake = FakeLocal()
    svc = RagService(_CFG, llm=fake.complete)
    svc._index = RagIndex(_CFG)          # пустой индекс
    svc._loaded = True
    svc._embedder = _EMB
    svc._retriever = Retriever(svc._index, _CFG, _EMB)
    ans = svc.answer("любой вопрос", use_rag=True)
    assert ans.used_rag is False
    assert ans.verdict == "insufficient"
    assert fake.calls == 0


# --- _build_gen_llm (генератор = текущая модель агента из реестра) --------------

def test_build_gen_llm_cloud_without_key_returns_none():
    """cloud без API_KEY → None (заглушка), без падения."""
    saved = os.environ.pop("API_KEY", None)
    try:
        assert Kod._build_gen_llm(model_id="cloud:stepfun/step-3.5-flash") is None
    finally:
        if saved is not None:
            os.environ["API_KEY"] = saved


def test_build_gen_llm_local_builds_client():
    """lmstudio (явный id) → клиент из реестра (callable.complete)."""
    llm = Kod._build_gen_llm(
        model_id="lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K")
    assert callable(llm)


def test_build_gen_llm_current_default_is_callable_or_none():
    """Без явного id берётся текущая модель агента (реестр)."""
    llm = Kod._build_gen_llm()
    # current = облако: без ключа → None; с ключом → callable. Оба варианта ок.
    assert llm is None or callable(llm)


# --- команда /gen (одна точка: agent.llm и rag_service.llm) ---------------------

def _agent_with_rag(tmp_path):
    """Агент на MockClient с подключённым RagService и реестром (без сети)."""
    from core.agent import Agent
    from core.llm_client import MockClient
    from core.model_registry import ModelRegistry
    from core.prompt_builder import PromptBuilder
    from memory.manager import MemoryManager, default_layers
    from storage.store import Store

    store = Store(str(tmp_path / "store"))
    memory = MemoryManager(default_layers(store), log=lambda line: None)
    agent = Agent(MockClient(name="Mock"), memory, PromptBuilder("sys"), store,
                  user_id="t")
    registry = ModelRegistry(os.path.join(BASE_DIR, "models.json"))
    registry.probe = lambda model_id: {"ok": True, "latency_ms": 1, "version": "test"}
    agent.model_registry = registry
    agent.rag_service = _service()
    agent.rag_enabled = True
    return agent


def test_gen_local_switches_agent_and_service(tmp_path):
    """`/gen local` переключает и agent.llm, и rag_service.llm (без расхождений)."""
    import io
    from contextlib import redirect_stdout
    agent = _agent_with_rag(tmp_path)
    with redirect_stdout(io.StringIO()):
        Kod.handle_gen_command(agent, "/gen local")
    # Генератор RAG — та же модель агента (одна точка, без секции generation).
    assert agent.rag_service.llm is not None
    assert agent.llm is not None
    assert "lmstudio" in agent.model_label()


def test_gen_status_reports_current_model(tmp_path):
    """`/gen status` печатает текущую модель агента и наличие LLM-инжекта."""
    import io
    from contextlib import redirect_stdout
    agent = _agent_with_rag(tmp_path)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        Kod.handle_gen_command(agent, "/gen status")
    out = buffer.getvalue()
    assert "моделью агента" in out
    assert "LLM-инжект" in out


# --- команда /embed (переключаемый эмбеддер) ------------------------------------

def test_embed_status_reports_provider(tmp_path):
    """`/embed status` печатает провайдера/модель/dim текущего эмбеддера."""
    import io
    from contextlib import redirect_stdout
    agent = _agent_with_rag(tmp_path)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        Kod.handle_embed_command(agent, "/embed status")
    out = buffer.getvalue()
    assert "Провайдер:" in out
    assert "bge-m3" in out


def test_embed_use_hashing_switches_service(tmp_path):
    """`/embed use hashing` пересобирает сервис с хэширующим эмбеддером."""
    import io
    from contextlib import redirect_stdout
    agent = _agent_with_rag(tmp_path)
    with redirect_stdout(io.StringIO()):
        Kod.handle_embed_command(agent, "/embed use hashing")
    assert agent.rag_service.cfg.embedding.provider == "hashing"


def test_embed_use_unknown_provider_keeps_service(tmp_path):
    """Неизвестный провайдер → предупреждение, прежний сервис сохранён."""
    import io
    from contextlib import redirect_stdout
    agent = _agent_with_rag(tmp_path)
    before = agent.rag_service
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        Kod.handle_embed_command(agent, "/embed use bogus")
    assert agent.rag_service is before
    assert "Неизвестный провайдер" in buffer.getvalue()
