# -*- coding: utf-8 -*-
"""L3 смоук-тест: полный цикл память→prompt→agent→CLI на MockClient.

Запуск: API_KEY=test-key $PY $TST/smoke.py
Выход 0 — цикл отработал; 1 — падение.
Не использует сеть: прогон через MockClient и подпроцесс CLI в --mock.
"""
import os
import subprocess
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Все временные артефакты прогонов — только в dev/tests_debug/.tmp (не в /tmp и не в users/ дня).
TMP_ROOT = os.path.join(BASE_DIR, "dev", "tests_debug", ".tmp")
sys.path.insert(0, BASE_DIR)

from storage.store import Store
from storage.db import ProfileRepository
from memory.base import MemoryContext
from memory.manager import MemoryManager, default_layers
from core.llm_client import MockClient
from core.prompt_builder import PromptBuilder
from core.agent import Agent, StubExecutor, default_validator
from core.state_machine import TaskStage


def test_full_cycle_in_process():
    """Память → промт → агент → ответ на MockClient (in-process)."""
    os.makedirs(TMP_ROOT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="smoke_", dir=TMP_ROOT)
    repo = ProfileRepository(os.path.join(tmp, "profiles.db"))
    store = Store(os.path.join(tmp, "users"), profile_repo=repo)
    memory = MemoryManager(default_layers(store))
    builder = PromptBuilder("Ты ассистент")
    agent = Agent(MockClient(), memory, builder, store, user_id="smoke_user")
    agent.initialize_user("smoke_user", "Т", {"style": "краткий",
                                              "constraints": "Python",
                                              "context": "тест"})
    answer = agent.respond("Привет, как дела?")
    assert answer is not None
    assert "вижу" in answer  # MockClient отражает контекст
    # Сообщение ушло в краткосрочную память.
    session = memory.layers["short_term"].read(
        MemoryContext("smoke_user", "Основная_задача", agent.session_id))
    assert len(session["messages"]) >= 2
    print("[smoke] in-process цикл OK")


def test_cli_subprocess():
    """Полный цикл через Kod.py --mock: интервью → обмен → /memory → exit.

    Использует изолированный --memory-dir (tests_debug/.tmp) — прогон идемпотентен и
    не трогает рабочие users/ дня (§7.1, §2.1: тестовые артефакты — только .tmp).
    Логи тоже изолированы (--log/--token-log в tmp): дефолты Kod.py пишут в корень проекта.
    """
    os.makedirs(TMP_ROOT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="smoke_cli_", dir=TMP_ROOT)
    stdin = "cli_user\nИван\nкраткий\nPython\nобучение\nПривет!\n/memory\n/exit\n"
    env = dict(os.environ)
    env["API_KEY"] = "test-key"  # гарантируем MockClient-ветку
    proc = subprocess.run(
        [sys.executable, os.path.join(BASE_DIR, "Kod.py"),
         "--mock", "--memory-dir", os.path.join(tmp, "users"),
         "--log", os.path.join(tmp, "log.md"),
         "--token-log", os.path.join(tmp, "tokens.csv")],
        input=stdin, capture_output=True, text=True, timeout=60, env=env,
        cwd=BASE_DIR,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "Инициализация" in out, out
    assert "вижу" in out, out
    assert "[Память]" in out, out
    print("[smoke] CLI subprocess цикл OK (exit 0)")


def test_fsm_in_process():
    """Жизненный цикл автомата in-process (День 15): plan → approve → step →
    pause → resume → run → done (утверждение плана — контрольный пункт)."""
    os.makedirs(TMP_ROOT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="smoke_fsm_", dir=TMP_ROOT)
    repo = ProfileRepository(os.path.join(tmp, "profiles.db"))
    store = Store(os.path.join(tmp, "users"), profile_repo=repo)
    memory = MemoryManager(default_layers(store))

    def build():
        return Agent(MockClient(), memory, PromptBuilder("Ты ассистент"), store,
                     user_id="fsm_user", executor=StubExecutor(),
                     validator=default_validator)

    agent = build()
    agent.initialize_user("fsm_user", "Ф", {"style": "a", "constraints": "b", "context": "c"})
    agent.start_task("Найди три Python-фреймворка и сравни их")
    agent.step_task()                       # new → planning (план, ожидает /approve)
    assert agent.task_state.stage == TaskStage.PLANNING
    agent.approve_plan()                    # planning → plan_approved
    agent.step_task()                       # plan_approved → implementation, шаг 0
    assert agent.task_state.stage == TaskStage.IMPLEMENTATION
    assert agent.pause() is True
    assert agent.task_state.stage == TaskStage.PAUSED

    restarted = build()                     # «перезапуск» — тот же memory-dir
    restarted.load_state("fsm_user")
    assert restarted.task_state.stage == TaskStage.PAUSED
    assert restarted.resume() is True
    assert restarted.task_state.current_step == 1   # продолжение с того же шага
    restarted.run_to_end()
    assert restarted.task_state.stage == TaskStage.DONE
    assert len(restarted.task_state.results) == 3
    print("[smoke] жизненный цикл автомата in-process OK")


def test_cli_fsm_subprocess():
    """CLI-прогон команд жизненного цикла: /plan /approve /step /pause /resume
    /run /state (новый поток Дня 15 — с утверждением плана)."""
    os.makedirs(TMP_ROOT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="smoke_cli_fsm_", dir=TMP_ROOT)
    stdin = ("cli_user\nИван\nкраткий\nPython\nобучение\n"
             "/plan Тестовая цель\n/approve\n/step\n/pause\n/resume\n/run\n"
             "/state\n/exit\n")
    env = dict(os.environ)
    env["API_KEY"] = "test-key"
    proc = subprocess.run(
        [sys.executable, os.path.join(BASE_DIR, "Kod.py"),
         "--mock", "--memory-dir", os.path.join(tmp, "users"),
         "--log", os.path.join(tmp, "log.md"),
         "--token-log", os.path.join(tmp, "tokens.csv")],
        input=stdin, capture_output=True, text=True, timeout=60, env=env,
        cwd=BASE_DIR,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    for marker in ("[План]", "[Шаг]", "[Пауза]", "[Продолжение]", "[Прогон]",
                   "[Состояние задачи]"):
        assert marker in out, (marker, out)
    assert "утверждён" in out, out
    assert "Этап: done" in out, out
    print("[smoke] CLI команды жизненного цикла OK (exit 0)")


def test_mcp_in_process():
    """MCP-слой in-process (День 16): fake-транспорт → READY → 3 тула →
    каталог сохраняется (catalog.json) → чистое закрытие (DISCONNECTED)."""
    os.makedirs(TMP_ROOT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="smoke_mcp_", dir=TMP_ROOT)
    import integrations.mcp.gateway as mcp_gateway_mod
    from integrations.mcp.config import MCPServerConfig
    from integrations.mcp.transport import FakeMCPTransport
    from integrations.mcp.provider import MCPToolProvider
    from core.tool_registry import ToolRegistry

    fake_tools = [
        {"name": "get_time", "description": "Текущее время",
         "inputSchema": {"type": "object", "properties": {}, "required": []}},
        {"name": "echo", "description": "Повтор текста",
         "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}},
                         "required": ["text"]}},
        {"name": "weather_stub", "description": "Погода (заглушка)",
         "inputSchema": {"type": "object",
                         "properties": {"location": {"type": "string"},
                                        "units": {"type": "string"}},
                         "required": ["location"]}},
    ]
    transport = FakeMCPTransport(fake_tools, server_id="demo")
    servers = [MCPServerConfig(server_id="demo", transport="stdio",
                               command="python", enabled=True, trust_level="low")]

    class FakeSync(mcp_gateway_mod.MCPGatewaySync):
        """Фасад без фонового loop'а (isinstance для MCPToolProvider)."""

        def __init__(self, srvs, transports=None):
            self._gateway = mcp_gateway_mod.MCPGateway(srvs, {"demo": transport})

        def _run(self, coro):
            return mcp_gateway_mod.asyncio.run(coro)

    repo = ProfileRepository(os.path.join(tmp, "profiles.db"))
    store = Store(os.path.join(tmp, "users"), profile_repo=repo)
    memory = MemoryManager(default_layers(store))
    agent = Agent(MockClient(), memory, PromptBuilder("Ты ассистент"), store,
                  user_id="mcp_user", executor=StubExecutor())
    gateway = FakeSync(servers)
    registry = ToolRegistry()
    registry.add_provider(MCPToolProvider(gateway))
    agent.mcp_gateway = gateway
    agent.tool_registry = registry

    gateway.start()
    assert gateway.status()["overall"] == "ready"
    snap = registry.refresh()
    assert len(snap.tools) == 3
    assert {t.name for t in snap.tools} == {
        "mcp.demo.get_time", "mcp.demo.echo", "mcp.demo.weather_stub"}
    # Каталог переживает перезапуск — сохранение через Store.
    store.save_tool_catalog("mcp_user", {
        "schema_version": 1, "version": snap.version,
        "tools": [{"name": t.name, "description": t.description,
                   "input_schema": t.input_schema, "source": t.source,
                   "provider": t.provider, "original_name": t.original_name,
                   "risk_level": t.risk_level,
                   "allowed_stages": sorted(t.allowed_stages),
                   "requires_confirmation": t.requires_confirmation,
                   "enabled": t.enabled} for t in snap.tools],
        "created_at": snap.created_at})
    saved = store.read_tool_catalog("mcp_user")
    assert saved is not None and len(saved["tools"]) == 3
    gateway.stop()
    assert gateway.status()["overall"] == "disconnected"
    print("[smoke] MCP in-process (fake → READY → 3 тула → DISCONNECTED) OK")


def test_mcp_probe_subprocess():
    """CLI one-shot --mcp-probe через подпроцесс с подменой модулей (fake).

    Обёртка-скрипт (по образцу m6_smoke.py) подменяет load_servers_config и
    MCPGatewaySync на fake-транспорт ДО вызова Kod.run_mcp_probe() и
    запускается как подпроцесс: проверяется реальный CLI-путь (argv →
    --mcp-probe → exit 0/1), но без сети и подпроцессов stdio-сервера.
    """
    os.makedirs(TMP_ROOT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="smoke_probe_", dir=TMP_ROOT)
    wrapper = os.path.join(tmp, "probe_wrapper.py")
    with open(wrapper, "w", encoding="utf-8") as file:
        file.write(PROBE_WRAPPER_SRC)
    env = dict(os.environ)
    env["API_KEY"] = "test-key"
    proc = subprocess.run(
        [sys.executable, wrapper, "--mcp-probe",
         "--memory-dir", os.path.join(tmp, "users"),
         "--log", os.path.join(tmp, "log.md"),
         "--token-log", os.path.join(tmp, "tokens.csv")],
        capture_output=True, text=True, timeout=60, env=env, cwd=BASE_DIR,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "[MCP] Соединение установлено (READY" in out, out
    assert "mcp.demo.get_time" in out and "mcp.demo.echo" in out, out
    assert "mcp.demo.weather_stub" in out, out
    assert "Всего инструментов: 3" in out, out
    print("[smoke] CLI --mcp-probe (fake, exit 0) OK")


def test_mcp_tool_use_in_process():
    """Полный LLM tool-use in-process (Ревизия 2): намерение → вызов тула →
    результат → ответ; аудит записан; TaskStage не меняется."""
    os.makedirs(TMP_ROOT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="smoke_tooluse_", dir=TMP_ROOT)
    import integrations.mcp.gateway as mcp_gateway_mod
    from integrations.mcp.config import MCPServerConfig
    from integrations.mcp.transport import FakeMCPTransport
    from integrations.mcp.provider import MCPToolProvider
    from core.tool_registry import ToolRegistry
    from core.tool_policy import ToolPolicy
    from core.tool_executor import ToolExecutor
    from core.invariants import RuleBasedChecker

    tools = [{"name": "search_locations", "description": "city search",
              "inputSchema": {"type": "object",
                              "properties": {"query": {"type": "string"}},
                              "required": ["query"]}}]
    transport = FakeMCPTransport(tools, server_id="weather",
                                 tool_results={"search_locations": '{"results":[{"name":"Moscow"}]}'})
    servers = [MCPServerConfig(server_id="weather", transport="http",
                               endpoint="https://x/mcp/", enabled=True, trust_level="low")]

    class FakeSync(mcp_gateway_mod.MCPGatewaySync):
        def __init__(self, srvs, transports=None):
            self._gateway = mcp_gateway_mod.MCPGateway(srvs, {"weather": transport})

        def _run(self, coro):
            return mcp_gateway_mod.asyncio.run(coro)

    repo = ProfileRepository(os.path.join(tmp, "profiles.db"))
    store = Store(os.path.join(tmp, "users"), profile_repo=repo)
    memory = MemoryManager(default_layers(store))
    agent = Agent(MockClient(), memory, PromptBuilder("Ты ассистент"), store,
                  user_id="tool_user", executor=StubExecutor())
    agent.initialize_user("tool_user", "Т", {"style": "a", "constraints": "b", "context": "c"})
    gateway = FakeSync(servers)
    registry = ToolRegistry()
    registry.add_provider(MCPToolProvider(gateway))
    agent.mcp_gateway = gateway
    agent.tool_registry = registry
    gateway.start()
    registry.refresh()
    agent.tool_executor = ToolExecutor(registry, ToolPolicy(), gateway, store=store,
                                       checker=RuleBasedChecker())
    agent.deliver.add("tools")
    answer = agent.respond("найди город Москва")
    assert "Moscow" in answer, answer
    audit = store.load_tool_audit("tool_user", agent.task)
    assert audit and audit[0]["status"] == "succeeded", audit
    print("[smoke] LLM tool-use in-process (Москва → вызов → ответ) OK")


# Обёртка для test_mcp_probe_subprocess: подмена модулей до run_mcp_probe().
# Kod.py парсит argv при импорте — argv передаётся как есть (флаг --mcp-probe
# обрабатывает сам wrapper, вызывая run_mcp_probe напрямую).
PROBE_WRAPPER_SRC = '''\
# -*- coding: utf-8 -*-
# probe_wrapper.py — обёртка --mcp-probe на fake-транспорте (без сети).
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, BASE)
os.chdir(BASE)
sys.argv = [os.path.join(BASE, "Kod.py")]  # Kod парсит argv при импорте

import Kod  # noqa: E402
from integrations.mcp.config import MCPServerConfig  # noqa: E402
from integrations.mcp.transport import FakeMCPTransport  # noqa: E402
import integrations.mcp.config as mcp_config  # noqa: E402
import integrations.mcp.gateway as mcp_gateway_mod  # noqa: E402

FAKE_TOOLS = [
    {"name": "get_time", "description": "Текущее время",
     "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "echo", "description": "Повтор текста",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}},
                     "required": ["text"]}},
    {"name": "weather_stub", "description": "Погода (заглушка)",
     "inputSchema": {"type": "object",
                     "properties": {"location": {"type": "string"},
                                    "units": {"type": "string"}},
                     "required": ["location"]}},
]


def fake_servers():
    return [MCPServerConfig(server_id="demo", transport="stdio",
                            command="python", enabled=True, trust_level="low")]


class FakeSync(mcp_gateway_mod.MCPGatewaySync):
    def __init__(self, servers, transports=None):
        self._gateway = mcp_gateway_mod.MCPGateway(
            servers, {"demo": FakeMCPTransport(FAKE_TOOLS, server_id="demo")})

    def _run(self, coro):
        return mcp_gateway_mod.asyncio.run(coro)


# run_mcp_probe импортирует load_servers_config/MCPGatewaySync локально —
# подменяем в исходных модулях до вызова.
mcp_config.load_servers_config = lambda path: fake_servers()
mcp_gateway_mod.MCPGatewaySync = FakeSync

sys.exit(Kod.run_mcp_probe())
'''


def main():
    test_full_cycle_in_process()
    test_cli_subprocess()
    test_fsm_in_process()
    test_cli_fsm_subprocess()
    test_mcp_in_process()
    test_mcp_tool_use_in_process()
    test_mcp_probe_subprocess()
    print("SMOKE OK: exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
