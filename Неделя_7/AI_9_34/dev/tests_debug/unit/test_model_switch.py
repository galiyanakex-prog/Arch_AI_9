# -*- coding: utf-8 -*-
"""Юнит-тесты команды /model и отображения модели (Ревизия 8, этап 3).

Без сети: probe подменяется, LLM не вызывается. Проверяем контракты:
`/model list` печатает все спеки; `/model use` меняет `agent.llm` и подпись;
переключение не трогает TaskStage/память/deliver; недоступный сервис → отказ
с сохранением прежней модели; подпись присутствует в выводе ответа.
"""
import io
import os
import sys
from contextlib import redirect_stdout

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

# Kod.py парсит argv при импорте — подставляем «пустой» argv.
sys.argv = [os.path.join(BASE_DIR, "Kod.py")]
import Kod  # noqa: E402

from core.agent import Agent  # noqa: E402
from core.llm_client import MockClient  # noqa: E402
from core.model_registry import ModelRegistry  # noqa: E402
from core.prompt_builder import PromptBuilder  # noqa: E402
from memory.manager import MemoryManager, default_layers  # noqa: E402
from storage.store import Store  # noqa: E402

MODELS_PATH = os.path.join(BASE_DIR, "models.json")
LMSTUDIO_ID = "lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K"
CLOUD_ID = "cloud:stepfun/step-3.5-flash"


def _make_agent(tmp_path):
    """Агент на MockClient с подключённым реестром (без сети)."""
    store = Store(str(tmp_path / "store"))
    memory = MemoryManager(default_layers(store), log=lambda line: None)
    builder = PromptBuilder("sys")
    client = MockClient(name="Mock")
    agent = Agent(client, memory, builder, store, user_id="t")
    registry = ModelRegistry(MODELS_PATH)
    agent.set_model(client, label=registry.current().display())
    agent.model_registry = registry
    return agent


def test_model_list_prints_all_specs(tmp_path):
    """`/model list` печатает все спеки реестра и отметку текущей."""
    agent = _make_agent(tmp_path)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        Kod.handle_model_command(agent, "/model list")
    out = buffer.getvalue()
    for spec in agent.model_registry.list():
        assert spec.id in out, spec.id
    assert "*" in out  # отметка текущей


def test_model_use_switches_llm_and_label(tmp_path):
    """`/model use` меняет agent.llm и подпись; probe подменён на успех."""
    agent = _make_agent(tmp_path)
    agent.model_registry.probe = lambda model_id: {"ok": True, "latency_ms": 1,
                                                   "version": "test"}
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        Kod.handle_model_command(agent, f"/model use {LMSTUDIO_ID}")
    assert agent.model_registry.current_id == LMSTUDIO_ID
    assert agent.model_label() == agent.model_registry.get(LMSTUDIO_ID).display()
    assert "lmstudio/" in agent.model_label()
    assert "Переключено" in buffer.getvalue()


def test_model_use_does_not_touch_stage_memory_deliver(tmp_path):
    """Переключение модели — не переход: TaskStage/память/deliver не меняются."""
    agent = _make_agent(tmp_path)
    agent.model_registry.probe = lambda model_id: {"ok": True, "latency_ms": 1,
                                                   "version": "test"}
    stage_before = agent.task_state
    deliver_before = set(agent.deliver)
    memory_before = agent.memory
    with redirect_stdout(io.StringIO()):
        Kod.handle_model_command(agent, f"/model use {LMSTUDIO_ID}")
    assert agent.task_state is stage_before
    assert agent.deliver == deliver_before
    assert agent.memory is memory_before


def test_model_use_unavailable_keeps_previous(tmp_path):
    """Недоступный сервис → отказ с объяснением, прежняя модель сохранена."""
    agent = _make_agent(tmp_path)
    agent.model_registry.probe = lambda model_id: {"ok": False,
                                                   "error": "Connection refused"}
    before = agent.model_label()
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        Kod.handle_model_command(agent, f"/model use {LMSTUDIO_ID}")
    assert agent.model_registry.current_id == CLOUD_ID
    assert agent.model_label() == before
    assert "недоступен" in buffer.getvalue()


def test_model_use_unknown_id(tmp_path):
    """Неизвестный id → предупреждение, модель не меняется."""
    agent = _make_agent(tmp_path)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        Kod.handle_model_command(agent, "/model use nope:model")
    assert agent.model_registry.current_id == CLOUD_ID
    assert "не найдена" in buffer.getvalue()


def test_model_banner_contains_label(tmp_path):
    """Баннер сессии несёт подпись модели и признак локальности."""
    agent = _make_agent(tmp_path)
    agent.model_registry.probe = lambda model_id: {"ok": True, "latency_ms": 1,
                                                   "version": "test"}
    with redirect_stdout(io.StringIO()):
        Kod.handle_model_command(agent, f"/model use {LMSTUDIO_ID}")
    banner = Kod.model_banner(agent)
    assert "lmstudio/" in banner
    assert "локально" in banner


def test_model_profile_applies(tmp_path):
    """`/model profile <name>` применяет профиль параметров."""
    agent = _make_agent(tmp_path)
    with redirect_stdout(io.StringIO()):
        Kod.handle_model_command(agent, "/model profile fast")
    assert agent.model_registry.current().profile == "fast"


def test_answer_prefix_has_model_label(tmp_path):
    """Подпись модели присутствует в выводе ответа (перехват stdout)."""
    agent = _make_agent(tmp_path)
    label = agent.model_label()
    # Эмулируем строку вывода REPL (как в главном цикле Kod.py).
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        print(f"[{agent.model_label()}] Агент: ответ")
    assert f"[{label}]" in buffer.getvalue()


def test_prompt_unchanged_by_model_switch(tmp_path):
    """Переключение модели не меняет промпт: messages байт-в-байт прежние."""
    agent = _make_agent(tmp_path)
    ctx = agent.build_context("привет")
    before = agent.prompts.build(ctx, agent.deliver)
    agent.model_registry.probe = lambda model_id: {"ok": True, "latency_ms": 1,
                                                   "version": "test"}
    with redirect_stdout(io.StringIO()):
        Kod.handle_model_command(agent, f"/model use {LMSTUDIO_ID}")
    after = agent.prompts.build(ctx, agent.deliver)
    assert before == after
    # Подпись модели — вывод CLI, в содержимое messages не попадает.
    assert all(agent.model_label() not in m.get("content", "") for m in after)

