# -*- coding: utf-8 -*-
"""Юнит-тесты субагентов (Ревизия 8, этап 4).

Без сети: дочерний процесс подменяется фейковым `subprocess.Popen`. Проверяем
контракты: запуск → непустой результат → лог создан; таймаут → статус
`timed_out` и kill; неизвестный сервис → отказ до запуска; облачный сервис при
`local_only` → отказ; лимит одновременных; детектор фразы; `TaskStage` основной
задачи не изменён.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from core.subagents import (  # noqa: E402
    SubagentRunner, SubagentError, detect_local_subagent_request, LOCAL_SERVICES,
)
from core.model_registry import ModelRegistry  # noqa: E402

MODELS_PATH = os.path.join(BASE_DIR, "models.json")
LMSTUDIO_ID = "lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K"


class FakePopen:
    """Фейковый дочерний процесс: пишет лог и возвращает заданный код."""

    def __init__(self, command, cwd=None, shell=None, stdout=None, stderr=None,
                 text=None, start_new_session=None, returncode=0, timeout=False,
                 running=False, output="[lmstudio/test] Агент: готово\n"):
        self.command = command
        self.pid = 4242
        self.returncode = returncode
        self._timeout = timeout
        self._running = running
        self._output = output
        self._killed = False
        # Эмулируем запись лога субагентом (--log — предпоследний аргумент).
        log_path = command[command.index("--log") + 1]
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as handle:
            handle.write("[Сессия] модель: lmstudio/test\n")

    def communicate(self, timeout=None):
        if self._timeout and not self._killed:
            import subprocess
            raise subprocess.TimeoutExpired(self.command, timeout)
        return self._output, None

    def poll(self):
        return None if self._running else self.returncode

    def kill(self):
        self._killed = True
        self.returncode = -9


def _runner(tmp_path, monkeypatch_popen=None):
    registry = ModelRegistry(MODELS_PATH)
    return SubagentRunner(BASE_DIR, registry=registry,
                          stages_dir=str(tmp_path / "stages"),
                          python="/usr/bin/python3")


def test_detect_local_subagent_request():
    """Фраза «сделай локально в <service>: <задача>» распознаётся."""
    assert detect_local_subagent_request("сделай локально в LM Studio: посчитай 2+2") \
        == ("lmstudio", "посчитай 2+2")
    assert detect_local_subagent_request("сделай локально в ollama: переведи текст") \
        == ("ollama", "переведи текст")
    assert detect_local_subagent_request("обычный вопрос") is None


def test_resolve_model_defaults_to_registry(tmp_path):
    """Без --model берётся первый chat-спек сервиса из реестра."""
    runner = _runner(tmp_path)
    assert runner.resolve_model("lmstudio") == LMSTUDIO_ID


def test_unknown_service_rejected(tmp_path):
    """Неизвестный сервис → SubagentError до запуска."""
    runner = _runner(tmp_path)
    try:
        runner.resolve_model("openai")
        assert False, "ожидался SubagentError"
    except SubagentError as error:
        assert "недопустим" in str(error)


def test_cloud_service_rejected_when_local_only(tmp_path):
    """Облачный сервис при local_only → отказ до запуска."""
    runner = _runner(tmp_path)
    try:
        runner.run("задача", service="cloud", local_only=True)
        assert False, "ожидался SubagentError"
    except SubagentError as error:
        assert "локальный" in str(error)


def test_run_ok_creates_log(tmp_path):
    """Запуск → статус ok, непустой вывод, лог создан с подписью модели."""
    import core.subagents as mod
    original = mod.subprocess.Popen
    mod.subprocess.Popen = FakePopen
    try:
        runner = _runner(tmp_path)
        result = runner.run("посчитай 2+2", service="lmstudio")
    finally:
        mod.subprocess.Popen = original
    assert result["status"] == "ok"
    assert result["output"].strip()
    assert os.path.exists(result["log"])
    with open(result["log"], encoding="utf-8") as handle:
        assert "lmstudio/test" in handle.read()


def test_run_timeout_kills_process(tmp_path):
    """Таймаут → статус timed_out, процесс убит."""
    import core.subagents as mod
    original = mod.subprocess.Popen
    mod.subprocess.Popen = lambda *a, **k: FakePopen(*a, timeout=True, **k)
    try:
        runner = _runner(tmp_path)
        result = runner.run("долгая задача", service="lmstudio", timeout=1)
    finally:
        mod.subprocess.Popen = original
    assert result["status"] == "timed_out"


def test_run_failed_status(tmp_path):
    """Ненулевой код возврата → статус failed."""
    import core.subagents as mod
    original = mod.subprocess.Popen
    mod.subprocess.Popen = lambda *a, **k: FakePopen(*a, returncode=1, **k)
    try:
        runner = _runner(tmp_path)
        result = runner.run("задача", service="lmstudio")
    finally:
        mod.subprocess.Popen = original
    assert result["status"] == "failed"


def test_max_parallel_limit(tmp_path):
    """Лимит одновременных субагентов соблюдается."""
    import core.subagents as mod
    original = mod.subprocess.Popen
    mod.subprocess.Popen = lambda *a, **k: FakePopen(*a, running=True, **k)
    try:
        runner = _runner(tmp_path)
        runner.max_parallel = 1
        runner.run("задача 1", service="lmstudio", wait=False)
        try:
            runner.run("задача 2", service="lmstudio", wait=False)
            assert False, "ожидался SubagentError"
        except SubagentError as error:
            assert "лимит" in str(error)
    finally:
        mod.subprocess.Popen = original


def test_empty_task_rejected(tmp_path):
    """Пустая задача → SubagentError."""
    runner = _runner(tmp_path)
    try:
        runner.run("   ", service="lmstudio")
        assert False, "ожидался SubagentError"
    except SubagentError as error:
        assert "Пустая" in str(error)


def test_subagent_does_not_touch_main_task(tmp_path):
    """Запуск субагента не меняет TaskStage/память основной задачи."""
    import core.subagents as mod
    from core.agent import Agent
    from core.llm_client import MockClient
    from core.prompt_builder import PromptBuilder
    from memory.manager import MemoryManager, default_layers
    from storage.store import Store

    original = mod.subprocess.Popen
    mod.subprocess.Popen = FakePopen
    try:
        store = Store(str(tmp_path / "store"))
        memory = MemoryManager(default_layers(store), log=lambda line: None)
        agent = Agent(MockClient(name="Mock"), memory, PromptBuilder("sys"), store,
                      user_id="main")
        stage_before = agent.task_state
        task_before = agent.task
        runner = _runner(tmp_path)
        runner.run("вспомогательная задача", service="lmstudio")
    finally:
        mod.subprocess.Popen = original
    assert agent.task_state is stage_before
    assert agent.task == task_before
