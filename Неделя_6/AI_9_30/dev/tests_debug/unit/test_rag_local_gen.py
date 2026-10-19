# -*- coding: utf-8 -*-
"""Юнит-тесты локальной генерации в RAG (Ревизия 8, этап 5).

Без сети: генератор подменяется фейковым callable (счётчик вызовов). Проверяем
контракты: явный `llm`-инжект в `RagService`; `answer` использует инжектированный
генератор; блок `[rag]` и источники/цитаты сохраняются как с облаком; пустой
индекс → «не знаю» без падения; секция `generation` в конфиге (JSON + env);
`_build_gen_llm` строит локального клиента из реестра и падает понятно при
неизвестном сервисе.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

# Kod.py парсит argv при импорте — подставляем «пустой» argv.
sys.argv = [os.path.join(BASE_DIR, "Kod.py")]
import Kod  # noqa: E402

from rag.config import RagConfig, GenerationConfig, RagConfigError  # noqa: E402
from rag.corpus import discover  # noqa: E402
from rag.embedding import HashingEmbedder  # noqa: E402
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


# --- секция generation в конфиге -------------------------------------------------

def test_generation_config_defaults():
    cfg = RagConfig.default()
    assert isinstance(cfg.generation, GenerationConfig)
    assert cfg.generation.provider == "cloud"
    assert cfg.generation.model is None
    assert cfg.generation.profile is None


def test_generation_config_loaded_from_json():
    cfg = RagConfig.load(os.path.join(BASE_DIR, "rag/config.json"))
    assert cfg.generation.provider == "cloud"
    assert cfg.generation.model is None


def test_generation_config_env_override():
    os.environ["AI9_GEN_PROVIDER"] = "lmstudio"
    os.environ["AI9_GEN_MODEL"] = "lmstudio:test"
    try:
        cfg = RagConfig.default().from_env()
        assert cfg.generation.provider == "lmstudio"
        assert cfg.generation.model == "lmstudio:test"
    finally:
        os.environ.pop("AI9_GEN_PROVIDER", None)
        os.environ.pop("AI9_GEN_MODEL", None)


def test_generation_config_invalid_provider():
    try:
        RagConfig.default().from_dict({"generation": {"provider": "bogus"}}).validate()
    except RagConfigError:
        return
    raise AssertionError("невалидный генератор должен давать RagConfigError")


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


# --- _build_gen_llm (сборка генератора из реестра) ------------------------------

def test_build_gen_llm_cloud_without_key_returns_none():
    """cloud без API_KEY → None (заглушка), без падения."""
    cfg = RagConfig.default()
    saved = os.environ.pop("API_KEY", None)
    try:
        assert Kod._build_gen_llm(cfg) is None
    finally:
        if saved is not None:
            os.environ["API_KEY"] = saved


def test_build_gen_llm_local_builds_client():
    """lmstudio → клиент из реестра (callable.complete)."""
    cfg = RagConfig.default().from_dict({"generation": {"provider": "lmstudio"}})
    llm = Kod._build_gen_llm(cfg)
    assert callable(llm)


def test_build_gen_llm_unknown_service_raises():
    """Сервис без chat-модели в реестре → понятная ошибка."""
    cfg = RagConfig.default().from_dict({"generation": {"provider": "ollama"}})
    try:
        Kod._build_gen_llm(cfg)
    except ValueError as error:
        assert "chat-модели" in str(error)
        return
    raise AssertionError("ожидался ValueError для сервиса без chat-модели")


# --- команда /gen (одна точка: agent.llm и rag_service.llm) ---------------------

def _agent_with_rag(tmp_path):
    """Агент на MockClient с подключённым RagService (без сети)."""
    from core.agent import Agent
    from core.llm_client import MockClient
    from core.prompt_builder import PromptBuilder
    from memory.manager import MemoryManager, default_layers
    from storage.store import Store

    store = Store(str(tmp_path / "store"))
    memory = MemoryManager(default_layers(store), log=lambda line: None)
    agent = Agent(MockClient(name="Mock"), memory, PromptBuilder("sys"), store,
                  user_id="t")
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
    assert agent.rag_service.cfg.generation.provider == "lmstudio"
    assert agent.rag_service.llm is not None
    # Основной LLM агента — тот же локальный клиент (одна точка).
    assert agent.llm is not None
    assert "lmstudio" in agent.model_label()


def test_gen_status_reports_provider(tmp_path):
    """`/gen status` печатает провайдера и наличие LLM-инжекта."""
    import io
    from contextlib import redirect_stdout
    agent = _agent_with_rag(tmp_path)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        Kod.handle_gen_command(agent, "/gen status")
    out = buffer.getvalue()
    assert "provider=cloud" in out
    assert "LLM-инжект" in out
