# -*- coding: utf-8 -*-
"""L4 сценарные тесты задания: маршрутизация, дозированная доставка, интервью, resume.

Запуск: API_KEY=test-key $PY $TST/scenario.py
Использует MockClient и временный каталог — живых вызовов нет.
Сценарии (из задания недели и Суть_N3 §4.3):
  1. интервью-инициализация нового ID → создано дерево;
  2. «какие данные попадают в каждый слой» (маршрутизация remember);
  3. дозированная доставка (deliver без long_term);
  4. влияние памяти на ответы (сравнение с/без слоя);
  5. resume «с того же места»;
  6. персонализация: два профиля → разный состав промта + авто-роутинг;
  7. пауза/продолжение задачи: снимок task_state.json по канону Дня 15,
     «перезапуск» → resume с того же шага без повторного плана → run → done;
  8. конфликт запроса и инварианта (День 14): отказ + изменение правила;
  9. контролируемые переходы (День 15): отказы /goto, флоу /approve,
     пауза → перезапуск → resume (канон «Проверьте» из Задание_Д15.txt).
"""
import json
import os
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


def build(tmp):
    repo = ProfileRepository(os.path.join(tmp, "profiles.db"))
    store = Store(os.path.join(tmp, "users"), profile_repo=repo)
    memory = MemoryManager(default_layers(store))
    builder = PromptBuilder("Ты ассистент")
    client = MockClient()
    return Agent(client, memory, builder, store, user_id="u")


def scenario_interview(tmp):
    """1. Новый ID → интервью → дерево users/<id>/... со всеми файлами."""
    agent = build(tmp)
    agent.initialize_user("alice", "Аня", {"style": "краткий",
                                           "constraints": "Python",
                                           "context": "магазин"})
    base = os.path.join(tmp, "users", "alice")
    assert os.path.isfile(os.path.join(base, "profile.json"))
    assert os.path.isfile(os.path.join(base, "long_term_memory.json"))
    assert os.path.isdir(os.path.join(base, "tasks", "Основная_задача", "sessions"))
    print("[scenario] интервью-инициализация OK")


def scenario_routing(tmp):
    """2. Какие данные в какой слой (явная маршрутизация)."""
    agent = build(tmp)
    agent.initialize_user("bob", "Боб", {"style": "x", "constraints": "y", "context": "z"})
    import storage.store as _s
    _s.safe_name  # noqa
    agent.respond("Мой стек — Python")
    ctx = MemoryContext("bob", agent.task, agent.session_id)
    short = agent.memory.layers["short_term"].read(ctx)
    longt = agent.memory.layers["long_term"].read(MemoryContext("bob"))
    work = agent.memory.layers["working"].read(ctx)
    prof = agent.memory.layers["profile"].read(MemoryContext("bob"))
    # Сообщение — в краткосрочной, профиль — отдельно, рабочая/долговременная — структура.
    assert len(short["messages"]) >= 2
    assert "name" in prof
    assert "tasks" in longt
    assert "current_state" in work
    print("[scenario] маршрутизация «какие данные куда» OK")


def scenario_dosed_delivery(tmp):
    """3. Дозированная доставка: без long_term слой не подмешивается."""
    agent = build(tmp)
    agent.initialize_user("carol", "К", {"style": "a", "constraints": "b", "context": "c"})
    agent.deliver = {"profile", "working", "short_term"}  # long_term опущен осознанно
    pctx = agent.build_context("вопрос")
    joined = " ".join(pctx.memory_blocks.keys())
    assert "long_term" not in joined
    messages = agent.prompts.build(pctx, agent.deliver)
    all_text = " ".join(m["content"] for m in messages)
    assert "long_term" not in all_text
    print("[scenario] дозированная доставка OK")


def scenario_influence(tmp):
    """4. Влияние памяти на ответы: с long_term и без (сравнение доставки слоя)."""
    agent = build(tmp)
    agent.initialize_user("dave", "Д", {"style": "a", "constraints": "b", "context": "c"})
    # Решение попадает в долговременную память пользователя dave.
    agent.memory.remember("long_term", MemoryContext("dave"),
                          content={"decisions": "PostgreSQL"}, source="system")
    q = "Какая СУБД выбрана?"
    # С long_term: блок долговременной памяти подмешивается в промт.
    agent.deliver = {"profile", "long_term", "working", "short_term"}
    block_full = agent.build_context(q).memory_blocks.get("long_term", "")
    # Без long_term: блок отсутствует (дозированная доставка).
    agent.deliver = {"profile", "working", "short_term"}
    block_cut = agent.build_context(q).memory_blocks.get("long_term", "")
    assert "PostgreSQL" in block_full
    assert "PostgreSQL" not in block_cut
    print("[scenario] влияние памяти на ответы OK")


def scenario_resume(tmp):
    """5. Resume: перезапуск продолжает «с того же места»."""
    agent1 = build(tmp)
    agent1.initialize_user("eve", "Е", {"style": "a", "constraints": "b", "context": "c"})
    agent1.save_state()
    task1 = agent1.task

    agent2 = build(tmp)
    agent2.load_state("eve")
    assert agent2.task == task1
    assert agent2.initialized
    print("[scenario] resume OK")


def scenario_personalization(tmp):
    """6. Персонализация: профили «Химик» и «Экономист» → разный состав промта.

    Один и тот же запрос даёт разный блок профиля (MockClient отражает блоки);
    auto_route переключает профиль по запросу — лог содержит «[Роутер]» и
    «[Агент] активный профиль».
    """
    logs = []
    repo = ProfileRepository(os.path.join(tmp, "profiles.db"))
    store = Store(os.path.join(tmp, "users"), profile_repo=repo, log=logs.append)
    memory = MemoryManager(default_layers(store, log=logs.append), log=logs.append)
    agent = Agent(MockClient(), memory, PromptBuilder("Ты ассистент"), store,
                  user_id="frank", log=logs.append)
    agent.initialize_user("frank", "Ф", {"style": "a", "constraints": "b", "context": "c"})

    chemist = {"id": "frank", "name": "Химик", "domain": "химия",
               "triggers": ["химия", "реактив", "реакция"],
               "style": {"answers": "строго по формулам"}, "constraints": {}, "context": {},
               "skills": [{"name": "spec", "instructions": "составь спеку ответа"}]}
    economist = {"id": "frank", "name": "Экономист", "domain": "экономика",
                 "triggers": ["бюджет", "цена"],
                 "style": {"answers": "считай выгоду"}, "constraints": {}, "context": {}}
    store.save_profile("frank", chemist, "chemist")
    store.save_profile("frank", economist, "economist")

    # Один и тот же запрос — разный состав промта для разных активных профилей.
    q = "расскажи про это"
    agent.switch_profile("chemist")
    block_chem = agent.build_context(q).memory_blocks.get("profile", "")
    answer_chem = agent.respond(q)
    agent.switch_profile("economist")
    block_eco = agent.build_context(q).memory_blocks.get("profile", "")
    answer_eco = agent.respond(q)
    assert "Химик" in block_chem and "Пайплайн скиллов:" in block_chem
    assert "Экономист" in block_eco
    assert block_chem != block_eco
    assert answer_chem != answer_eco

    # Авто-роутинг: запрос с триггером переключает профиль до сборки промта.
    agent.auto_route = True
    agent.respond("какая реакция идёт с реактивом?")
    assert agent.active_profile == "chemist"

    joined = "\n".join(logs)
    assert "[Роутер]" in joined
    assert "[Агент] активный профиль" in joined
    print("[scenario] персонализация (профили + роутер) OK")


def build_fsm(tmp, logs=None):
    """Агент с детерминированным StubExecutor (без сети) для сценария автомата."""
    log = logs.append if logs is not None else None
    repo = ProfileRepository(os.path.join(tmp, "profiles.db"))
    store = Store(os.path.join(tmp, "users"), profile_repo=repo, log=log)
    memory = MemoryManager(default_layers(store, log=log), log=log)
    return Agent(MockClient(), memory, PromptBuilder("Ты ассистент"), store,
                 user_id="u", log=log, executor=StubExecutor(),
                 validator=default_validator)


def scenario_pause_resume(tmp):
    """7. Пауза/продолжение задачи (канон Дня 15, arch §2.9).

    /plan → план построен (planning, ожидает /approve) → /approve → /step
    (шаг 0 выполнен) → /pause → снимок task_state.json по канону задания →
    «перезапуск» (новый Agent, тот же memory-dir) → /resume с того же шага без
    повторного плана → /run → done. Лог содержит «[Автомат]».
    """
    logs = []
    agent1 = build_fsm(tmp, logs)
    agent1.initialize_user("gina", "Г", {"style": "a", "constraints": "b", "context": "c"})

    # /plan «Найди три Python-фреймворка и сравни их» → new → planning (план из 3 шагов).
    agent1.start_task("Найди три Python-фреймворка и сравни их")
    agent1.step_task()                 # new → planning (план построен, ожидает /approve)
    assert agent1.task_state.stage == TaskStage.PLANNING
    assert len(agent1.task_state.steps) == 3
    agent1.approve_plan()              # planning → plan_approved
    assert agent1.task_state.stage == TaskStage.PLAN_APPROVED
    agent1.step_task()                 # plan_approved → implementation, шаг 0 выполнен
    assert agent1.task_state.stage == TaskStage.IMPLEMENTATION
    assert agent1.task_state.current_step == 1 and len(agent1.task_state.results) == 1

    # /pause → снимок на диске.
    assert agent1.pause() is True
    task_name = agent1.task
    snap_path = agent1.store.task_state_path("gina", task_name)
    assert os.path.isfile(snap_path)
    with open(snap_path, encoding="utf-8") as file:
        raw = json.load(file)
    # Канон снимка: paused, previous_stage=implementation, шаг 1, 1 результат, журнал.
    assert raw["stage"] == "paused"
    assert raw["previous_stage"] == "implementation"
    assert raw["current_step"] == 1
    assert len(raw["results"]) == 1
    assert isinstance(raw["transition_log"], list) and raw["transition_log"]

    # «Перезапуск»: новый Agent поверх того же memory-dir читает снимок.
    agent2 = build_fsm(tmp, logs)
    agent2.load_state("gina")
    assert agent2.task_state is not None
    assert agent2.task_state.stage == TaskStage.PAUSED
    assert agent2.task_state.current_step == 1

    # /resume → продолжение с шага 1, план НЕ перестроен, задача НЕ переспрошена.
    assert agent2.resume() is True
    assert agent2.task_state.stage == TaskStage.IMPLEMENTATION
    assert agent2.task_state.current_step == 1
    assert len(agent2.task_state.steps) == 3

    # /run → done; завершённый шаг 0 не повторяется (results без дублей).
    agent2.run_to_end()
    assert agent2.task_state.stage == TaskStage.DONE
    assert len(agent2.task_state.results) == 3 == len(set(agent2.task_state.results))

    assert "[Автомат]" in "\n".join(logs)
    print("[scenario] пауза/продолжение задачи (task_state.json + перезапуск) OK")



def scenario_invariant_conflict(tmp):
    """8. Конфликт запроса и инварианта (День 14): отказ, объяснение, изменение правила.

    /invariant add framework.django → запрос «перепиши API на FastAPI» → агент
    ОТКАЗЫВАЕТ, называет framework.django и предлагает альтернативу; /check показывает
    нарушение; /invariant set --yes меняет правило; повторный запрос проходит. Лог
    содержит строки «[Инварианты]».
    """
    from core.invariants import Invariant
    logs = []
    repo = ProfileRepository(os.path.join(tmp, "profiles.db"))
    store = Store(os.path.join(tmp, "users"), profile_repo=repo, log=logs.append)
    memory = MemoryManager(default_layers(store, log=logs.append), log=logs.append)
    agent = Agent(MockClient(), memory, PromptBuilder("Ты ассистент"), store,
                  user_id="ivan", log=logs.append, executor=StubExecutor())
    agent.initialize_user("ivan", "И", {"style": "a", "constraints": "b", "context": "c"})

    # /invariant add framework.django architecture "Использовать Django"
    agent.add_invariant(Invariant(id="framework.django", category="architecture",
                                  description="Использовать Django, а не FastAPI"))

    # Запрос конфликтует с инвариантом → отказ с объяснением и альтернативой.
    before = agent.tool_calls
    result = agent.propose_and_check("перепиши API на FastAPI")
    assert result["allowed"] is False
    assert agent.tool_calls == before                    # инструмент не вызван
    assert "framework.django" in result["message"]
    assert "альтернатив" in result["message"].lower()

    # /check "перейти на FastAPI" → нарушение видно без исполнения.
    action = agent.propose_action("перейти на FastAPI")
    assert agent.check_invariants(action)

    # Инвариант попадает в промт (явный учёт в рассуждениях).
    joined = "\n".join(m["content"] for m in agent.prompts.build(agent.build_context("q"), agent.deliver))
    assert "[invariants]" in joined and "framework.django" in joined

    # /invariant set framework.django "..." --yes → правило изменено (требует подтверждения);
    # без --yes — PermissionError (критерий 30).
    try:
        agent.update_invariant("framework.django", "Использовать FastAPI", authorized=False)
        assert False, "ожидался PermissionError"
    except PermissionError:
        pass
    agent.update_invariant("framework.django", "Использовать FastAPI", authorized=True)
    assert agent.constraints.by_id("framework.django").description == "Использовать FastAPI"

    # Чтобы запрос «перейти на FastAPI» прошёл, правило меняется явно: прежнее
    # отключается, добавляется новое (архитектурное решение не меняется обычной фразой).
    agent.toggle_invariant("framework.django", False)
    agent.add_invariant(Invariant(id="framework.fastapi", category="architecture",
                                  description="Использовать FastAPI"))
    result2 = agent.propose_and_check("перейти на FastAPI")
    assert result2["allowed"] is True

    assert "[Инварианты]" in "\n".join(logs)
    print("[scenario] конфликт запроса и инварианта (отказ + изменение) OK")


def scenario_controlled_transitions(tmp):
    """9. Контролируемые переходы (канон «Проверьте» из `Задание_Д15.txt`).

    Ветка 1: /plan → план построен (planning) → /goto implementation → ОТКАЗ
    («нельзя реализацию до утверждённого плана», состояние не изменилось,
    запись в transition_log) → /approve → /goto done → ОТКАЗ («нельзя финал
    без валидации») → /run → done → /goto new → ОТКАЗ (терминальная).
    Ветка 2: /plan → /approve → /step → /pause → «перезапуск» (новый Agent,
    тот же memory-dir) → /resume → /run → done (шаг не повторён). Лог содержит
    «[Автомат] … ОТКАЗАНО».
    """
    logs = []
    agent = build_fsm(tmp, logs)
    agent.initialize_user("kate", "К", {"style": "a", "constraints": "b", "context": "c"})

    # --- Ветка 1: отказы /goto + флоу /approve + терминальная done -------------
    agent.start_task("Сделать REST API")
    agent.step_task()                                  # new → planning (план)
    assert agent.task_state.stage == TaskStage.PLANNING

    # /goto implementation из planning: отказ, состояние не изменилось.
    result = agent.attempt_transition("implementation")
    assert "ОТКАЗАНО" in result
    assert "нельзя делать реализацию до утверждённого плана" in result.lower()
    assert agent.task_state.stage == TaskStage.PLANNING   # не изменилось
    refused = [e for e in agent.task_state.transition_log if not e["allowed"]]
    assert refused and refused[-1]["to"] == "implementation"

    # /approve → plan_approved; /goto done → отказ («нельзя финал без валидации»).
    agent.approve_plan()
    assert agent.task_state.stage == TaskStage.PLAN_APPROVED
    result2 = agent.attempt_transition("done")
    assert "ОТКАЗАНО" in result2
    assert "валидаци" in result2.lower()
    assert agent.task_state.stage == TaskStage.PLAN_APPROVED

    # /run → done (через implementation → validation); /goto new → отказ.
    agent.run_to_end()
    assert agent.task_state.stage == TaskStage.DONE
    result3 = agent.attempt_transition("new")
    assert "ОТКАЗАНО" in result3 and "терминальная" in result3.lower()
    assert agent.task_state.stage == TaskStage.DONE

    # /transitions: журнал с 3 отказами.
    report = agent.transitions_report()
    assert "отказов: 3" in report
    print("[scenario] контролируемые переходы: отказы /goto + /approve OK")

    # --- Ветка 2: пауза → перезапуск → resume → done (шаг не повторён) ---------
    logs2 = []
    agent1 = build_fsm(tmp, logs2)
    agent1.initialize_user("lena", "Л", {"style": "a", "constraints": "b", "context": "c"})
    agent1.start_task("Тестовая цель")
    agent1.step_task()                                 # → planning
    agent1.approve_plan()                              # → plan_approved
    agent1.step_task()                                 # → implementation, шаг 0
    assert agent1.task_state.current_step == 1
    assert agent1.pause() is True

    # «Перезапуск»: новый Agent поверх того же memory-dir.
    agent2 = build_fsm(tmp, logs2)
    agent2.load_state("lena")
    assert agent2.task_state.stage == TaskStage.PAUSED
    assert agent2.resume() is True
    assert agent2.task_state.stage == TaskStage.IMPLEMENTATION
    assert agent2.task_state.current_step == 1          # тот же шаг
    agent2.run_to_end()
    assert agent2.task_state.stage == TaskStage.DONE
    assert len(agent2.task_state.results) == 3
    assert len(agent2.task_state.results) == len(set(agent2.task_state.results))

    joined = "\n".join(logs + logs2)
    assert "ОТКАЗАНО" in joined
    assert "[Автомат]" in joined
    print("[scenario] контролируемые переходы: пауза → перезапуск → resume OK")


def build_mcp(tmp, logs=None, fail_initialize=False):
    """Агент с MCP-слоем на FakeMCPTransport (без сети и подпроцессов).

    FakeSync повторяет контракт MCPGatewaySync, но без фонового loop'а:
    сценарий не тянет mcp SDK (быстро и детерминированно).
    """
    import integrations.mcp.gateway as mcp_gateway_mod
    from integrations.mcp.config import MCPServerConfig
    from integrations.mcp.transport import FakeMCPTransport
    from integrations.mcp.provider import MCPToolProvider
    from core.tool_registry import ToolRegistry

    log = logs.append if logs is not None else None
    repo = ProfileRepository(os.path.join(tmp, "profiles.db"))
    store = Store(os.path.join(tmp, "users"), profile_repo=repo, log=log)
    memory = MemoryManager(default_layers(store, log=log), log=log)
    agent = Agent(MockClient(), memory, PromptBuilder("Ты ассистент"), store,
                  user_id="u", log=log, executor=StubExecutor())

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
    transport = FakeMCPTransport(fake_tools, fail_initialize=fail_initialize,
                                 server_id="demo")
    servers = [MCPServerConfig(server_id="demo", transport="stdio",
                               command="python", enabled=True, trust_level="low")]

    class FakeSync(mcp_gateway_mod.MCPGatewaySync):
        """Фасад без фонового loop'а: каждый вызов — свой asyncio.run.

        Наследование от MCPGatewaySync обязательно: MCPToolProvider.discover()
        проверяет isinstance (иначе уйдёт в asyncio.run над корутиной,
        которую вернул бы настоящий async-шлюз).
        """

        def __init__(self, srvs, transports=None):
            # НЕ зовём родительский __init__ (он стартует фоновый loop).
            self._gateway = mcp_gateway_mod.MCPGateway(srvs, {"demo": transport})

        def _run(self, coro):
            return mcp_gateway_mod.asyncio.run(coro)

    gateway = FakeSync(servers)
    registry = ToolRegistry()
    registry.add_provider(MCPToolProvider(gateway))
    agent.mcp_gateway = gateway
    agent.tool_registry = registry
    return agent


def _attach_tool_use(agent, tools, results):
    """Включает полный tool-use на fake-транспорте (policy + executor + [tools])."""
    import integrations.mcp.gateway as mcp_gateway_mod
    from integrations.mcp.config import MCPServerConfig
    from integrations.mcp.transport import FakeMCPTransport
    from integrations.mcp.provider import MCPToolProvider
    from core.tool_registry import ToolRegistry
    from core.tool_policy import ToolPolicy
    from core.tool_executor import ToolExecutor
    from core.invariants import RuleBasedChecker

    transport = FakeMCPTransport(tools, server_id="demo", tool_results=results)
    servers = [MCPServerConfig(server_id="demo", transport="stdio",
                               command="python", enabled=True, trust_level="low")]

    class FakeSync(mcp_gateway_mod.MCPGatewaySync):
        def __init__(self, srvs, transports=None):
            self._gateway = mcp_gateway_mod.MCPGateway(srvs, {"demo": transport})

        def _run(self, coro):
            return mcp_gateway_mod.asyncio.run(coro)

    gateway = FakeSync(servers)
    registry = ToolRegistry()
    registry.add_provider(MCPToolProvider(gateway))
    agent.mcp_gateway = gateway
    agent.tool_registry = registry
    gateway.start()
    registry.refresh()
    agent.tool_executor = ToolExecutor(registry, ToolPolicy(), gateway,
                                       store=agent.store, checker=RuleBasedChecker())
    agent.deliver.add("tools")
    return gateway


def scenario_llm_tool_use(tmp):
    """11. LLM tool-use (День 16, Ревизия 2): намерение → вызов тула → ответ.

    MockClient детерминированно предлагает вызов search_locations по «Москва»;
    ToolExecutor исполняет на fake-транспорте; результат возвращается в ответ;
    запись — в tool_audit.jsonl; TaskStage не меняется (инструмент ≠ переход).
    """
    agent = build(tmp)
    agent.initialize_user("u", "Иван", {"style": "a", "constraints": "b", "context": "c"})
    tools = [{"name": "search_locations", "description": "city search",
              "inputSchema": {"type": "object",
                              "properties": {"query": {"type": "string"}},
                              "required": ["query"]}}]
    _attach_tool_use(agent, tools, {"search_locations": '{"results":[{"name":"Moscow"}]}'})
    agent.start_task("Найти город")
    agent.step_task()  # new → planning
    stage_before = agent.task_state.stage
    answer = agent.respond("найди город Москва")
    assert "Moscow" in answer, answer
    audit = agent.store.load_tool_audit("u", agent.task)
    assert audit and audit[0]["tool"] == "mcp.demo.search_locations"
    assert audit[0]["status"] == "succeeded"
    # инструмент ≠ переход: стадия и журнал автомата не изменились
    assert agent.task_state.stage == stage_before
    print("[scenario] LLM tool-use: намерение → вызов → ответ (аудит) OK")


def scenario_tool_denied(tmp):
    """12. Policy/инвариант отклоняет вызов инструмента (День 16)."""
    from core.invariants import Invariant, add_invariant
    agent = build(tmp)
    agent.initialize_user("u2", "Пётр", {"style": "a", "constraints": "b", "context": "c"})
    tools = [{"name": "search_locations", "description": "city search",
              "inputSchema": {"type": "object",
                              "properties": {"query": {"type": "string"}},
                              "required": ["query"]}}]
    _attach_tool_use(agent, tools, {"search_locations": '{"results":[{"name":"Moscow"}]}'})
    add_invariant(agent.constraints,
                  Invariant(id="tool.deny.mcp.demo.search_locations",
                            category="technical", description="инструмент запрещён"))
    answer = agent.respond("найди город Москва")
    assert "Нарушен инвариант" in answer, answer
    audit = agent.store.load_tool_audit("u2", agent.task)
    assert audit and audit[0]["status"] == "denied"
    print("[scenario] tool denied: вызов отклонён инвариантом (аудит denied) OK")


def scenario_mcp_discovery(tmp):
    """10. MCP discovery (День 16, канон arch_den_16.md §2.4/§3.2).

    Ветка 1: one-shot probe (fake): READY → 3 тула (имя/description/схема) →
    чистое закрытие (DISCONNECTED).
    Ветка 2: REPL-флоу: connect → tools (пустой каталог) → refresh (3 тула,
    catalog.json на диске) → tools (имена) → status (ready + версия) →
    disconnect (DISCONNECTED).
    Ветка 3: деградация: fail_initialize → connect не роняет REPL, каталог
    пуст, память/автомат продолжают работать.
    """
    import io
    from contextlib import redirect_stdout

    # handle_mcp_command живёт в Kod.py; Kod парсит argv при импорте —
    # очищаем (сценарий не передаёт флаги), как в m6_smoke.py.
    sys.argv = [os.path.join(BASE_DIR, "Kod.py")]
    import Kod
    handle_mcp_command = Kod.handle_mcp_command

    def run_cmd(agent, line):
        buf = io.StringIO()
        with redirect_stdout(buf):
            handle_mcp_command(agent, line)
        return buf.getvalue()

    # --- Ветка 1: one-shot probe (fake) --------------------------------------
    agent = build_mcp(tmp)
    out = run_cmd(agent, "/mcp connect demo")
    assert "READY" in out.upper(), out
    tools = agent.tool_registry.refresh()
    assert len(tools.tools) == 3
    names = {t.name for t in tools.tools}
    assert names == {"mcp.demo.get_time", "mcp.demo.echo", "mcp.demo.weather_stub"}
    for t in tools.tools:
        assert t.description and isinstance(t.input_schema, dict)
        assert t.input_schema.get("type") == "object"
        assert t.source == "mcp" and t.provider == "demo"
    run_cmd(agent, "/mcp disconnect")
    assert agent.mcp_gateway.status()["overall"] == "disconnected"
    print("[scenario] MCP: probe-флоу (READY → 3 тула → DISCONNECTED) OK")

    # --- Ветка 2: REPL connect → tools → refresh → status → disconnect -------
    agent2 = build_mcp(tmp)
    out = run_cmd(agent2, "/mcp connect demo")
    assert "READY" in out.upper(), out
    out = run_cmd(agent2, "/mcp tools")
    assert "refresh" in out                      # пустой каталог → подсказка
    out = run_cmd(agent2, "/mcp refresh")
    assert "3 тулов" in out and "catalog.json" in out
    catalog_path = agent2.store.tool_catalog_path("u")
    assert os.path.isfile(catalog_path)
    with open(catalog_path, encoding="utf-8") as file:
        saved = json.load(file)
    assert saved["schema_version"] == 1 and len(saved["tools"]) == 3
    saved_names = {t["name"] for t in saved["tools"]}
    assert saved_names == names
    out = run_cmd(agent2, "/mcp tools")
    assert "mcp.demo.get_time" in out and "Повтор текста" in out
    out = run_cmd(agent2, "/mcp status")
    assert "ready" in out and "версия" in out.lower()
    out = run_cmd(agent2, "/mcp disconnect")
    assert "DISCONNECTED" in out
    assert agent2.mcp_gateway.status()["overall"] == "disconnected"
    print("[scenario] MCP: REPL-флоу (connect→tools→refresh→status→disconnect) OK")

    # --- Ветка 3: деградация (fail_initialize) -------------------------------
    logs = []
    agent3 = build_mcp(tmp, logs, fail_initialize=True)
    out = run_cmd(agent3, "/mcp connect demo")
    assert "FAILED" in out.upper() or "не удалось" in out.lower(), out
    out = run_cmd(agent3, "/mcp refresh")
    assert "0 тулов" in out                      # каталог честен: тулов нет
    # Память и автомат продолжают работать при деградации MCP.
    ctx = MemoryContext(agent3.user_id, agent3.task, agent3.session_id)
    assert agent3.memory.report(ctx)
    agent3.start_task("Цель при деградации MCP")
    agent3.step_task()
    assert agent3.task_state.stage == TaskStage.PLANNING
    print("[scenario] MCP: деградация (FAILED не роняет REPL, каталог честен) OK")


def scenario_multiserver_flow(tmp):
    """13. D3 (День 20): длинный флоу с инструментами РАЗНЫХ MCP-серверов.

    Программируемый многошаговый клиент (скрипт вызовов) прогоняет цепочку
    time → pipeline(search) → pipeline(summarize) → pipeline(saveToFile) →
    scheduler(schedule_reminder). Проверяем: выбор инструмента по имени,
    МАРШРУТИЗАЦИЮ по `provider` (у каждого сервера — свой транспорт), строгий
    ПОРЯДОК вызовов, отсутствие лишних вызовов, что `TaskStage` не изменился и
    аудит содержит ровно N записей.
    """
    import integrations.mcp.gateway as mcp_gateway_mod
    from integrations.mcp.config import MCPServerConfig
    from integrations.mcp.transport import FakeMCPTransport
    from integrations.mcp.provider import MCPToolProvider
    from core.llm_client import LLMClient, LLMReply
    from core.tool_registry import ToolRegistry
    from core.tool_policy import ToolPolicy
    from core.tool_executor import ToolExecutor
    from core.invariants import RuleBasedChecker

    # Серверы и их каталоги (квалифицированно: mcp.<server>.<tool>).
    catalogs = {
        "time": [{"name": "get_time", "description": "Текущее время",
                  "inputSchema": {"type": "object", "properties":
                                  {"timezone_name": {"type": "string"}},
                                  "required": []}}],
        "pipeline": [
            {"name": "search", "description": "Получить данные (шаг 1)",
             "inputSchema": {"type": "object",
                             "properties": {"query": {"type": "string"}},
                             "required": ["query"]}},
            {"name": "summarize", "description": "Обработать данные (шаг 2)",
             "inputSchema": {"type": "object",
                             "properties": {"text": {"type": "string"}},
                             "required": ["text"]}},
            {"name": "saveToFile", "description": "Сохранить результат (шаг 3)",
             "inputSchema": {"type": "object",
                             "properties": {"name": {"type": "string"},
                                            "content": {"type": "string"}},
                             "required": ["name", "content"]}},
        ],
        "scheduler": [
            {"name": "schedule_reminder", "description": "Напоминание",
             "inputSchema": {"type": "object",
                             "properties": {"text": {"type": "string"},
                                            "delay_seconds": {"type": "number"}},
                             "required": ["text"]}},
        ],
    }
    results = {
        "time": {"get_time": "2026-10-01T09:00:00+03:00"},
        "pipeline": {
            "search": "Python — язык.\nPython быстр.",
            "summarize": "Сводка (2 предложений): Python — язык.; Python быстр.",
            "saveToFile": '{"saved":"digest.txt","chars":52}',
        },
        "scheduler": {"schedule_reminder": '{"job_id":"j1","at":"+0s"}'},
    }
    # Запись порядка вызовов (server, tool) на общий список.
    order: list[tuple[str, str]] = []
    transports = {}
    for sid in catalogs:
        base = FakeMCPTransport(catalogs[sid], tool_results=results[sid], server_id=sid)

        class _Recorder(type(base)):
            def __init__(self, inner, sid, order):
                self._inner, self._sid, self._order = inner, sid, order

            async def initialize(self):
                return await self._inner.initialize()

            async def list_tools(self):
                return await self._inner.list_tools()

            async def call_tool(self, name, arguments):
                self._order.append((self._sid, name))
                return await self._inner.call_tool(name, arguments)

            async def close(self):
                return await self._inner.close()

        transports[sid] = _Recorder(base, sid, order)

    servers = [MCPServerConfig(server_id=sid, transport="stdio",
                               command="python", enabled=True, trust_level="low")
               for sid in catalogs]

    class FakeSync(mcp_gateway_mod.MCPGatewaySync):
        def __init__(self, srvs, trs):
            self._gateway = mcp_gateway_mod.MCPGateway(srvs, trs)

        def _run(self, coro):
            return mcp_gateway_mod.asyncio.run(coro)

    # Программируемый многошаговый клиент: выдаёт вызовы по сценарию (по имени из
    # каталога), затем — финальный ответ. Имена берёт из фактически доступных tools.
    class ScriptedClient(LLMClient):
        def __init__(self):
            self._step = 0
            self.seen_tools: list[str] = []

        def complete(self, messages, **params):
            return "[scripted] финальный ответ"

        def complete_with_tools(self, messages, tools=None, **params):
            names = {t["function"]["name"] for t in (tools or [])}
            self.seen_tools = sorted(names)
            # Пока есть tool-результаты в истории — идём к финалу.
            for m in messages:
                if m.get("role") in ("tool", "function"):
                    # продолжаем цепочку до конца скрипта
                    break
            script = [
                ("mcp.time.get_time", {"timezone_name": "Europe/Moscow"}),
                ("mcp.pipeline.search", {"query": "python"}),
                ("mcp.pipeline.summarize", {"text": "Python — язык. Python быстр."}),
                ("mcp.pipeline.saveToFile", {"name": "digest",
                                             "content": "Сводка (2 предложений): Python — язык."}),
                ("mcp.scheduler.schedule_reminder", {"text": "свежая сводка",
                                                     "delay_seconds": 0}),
            ]
            if self._step < len(script):
                name, args = script[self._step]
                if name not in names:
                    # Каталог не содержит запрошенный тул — не выдумываем вызов.
                    return LLMReply(content=f"[scripted] тул {name} недоступен")
                self._step += 1
                return LLMReply(tool_calls=[{"id": f"call_{self._step}",
                                             "name": name, "arguments": args}])
            return LLMReply(content="[scripted] длинный флоу завершён: digest готов")

    repo = ProfileRepository(os.path.join(tmp, "ms_profiles.db"))
    store = Store(os.path.join(tmp, "ms_users"), profile_repo=repo)
    memory = MemoryManager(default_layers(store))
    client = ScriptedClient()
    agent = Agent(client, memory, PromptBuilder("Ты ассистент"), store,
                  user_id="ums", executor=StubExecutor())

    gateway = FakeSync(servers, transports)
    registry = ToolRegistry()
    registry.add_provider(MCPToolProvider(gateway))
    agent.mcp_gateway = gateway
    agent.tool_registry = registry
    gateway.start()
    registry.refresh()
    assert len(registry.snapshot().tools) == 5, "каталог: 1+3+1"
    agent.tool_executor = ToolExecutor(registry, ToolPolicy(), gateway,
                                       store=store, checker=RuleBasedChecker())
    agent.deliver.add("tools")
    # Длинный флоу: 5 вызовов + финал → лимит итераций выше дефолтных 5.
    agent.max_tool_iterations = 8

    agent.initialize_user("ums", "Ирина", {"style": "a", "constraints": "b",
                                           "context": "c"})
    agent.start_task("Собрать и сохранить сводку")
    agent.step_task()  # new → planning
    stage_before = agent.task_state.stage
    answer = agent.respond("собери свежие данные, обработай, сохрани и напомни")

    expected = [
        ("time", "get_time"),
        ("pipeline", "search"),
        ("pipeline", "summarize"),
        ("pipeline", "saveToFile"),
        ("scheduler", "schedule_reminder"),
    ]
    assert order == expected, f"порядок вызовов неверен:\n факт={order}\n ожид={expected}"
    assert "digest" in answer, answer
    # Инструмент ≠ переход: стадия и журнал автомата не изменились.
    assert agent.task_state.stage == stage_before
    # Аудит: ровно N записей, маршрутизация по provider зафиксирована в tool-имени.
    audit = store.load_tool_audit("ums", agent.task)
    invoked = [r for r in audit if r.get("phase") == "invoked"]
    assert len(invoked) == len(expected), f"аудит: {len(invoked)} != {len(expected)}"
    providers = [r["tool"].split(".")[1] for r in invoked]
    assert providers == ["time", "pipeline", "pipeline", "pipeline", "scheduler"], providers
    print("[scenario] D3: мультисерверный длинный флоу "
          "(5 вызовов, порядок, маршрутизация, аудит) OK")


def main():
    os.makedirs(TMP_ROOT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="scn_", dir=TMP_ROOT)
    scenario_interview(tmp)
    scenario_routing(tmp)
    scenario_dosed_delivery(tmp)
    scenario_influence(tmp)
    scenario_resume(tmp)
    scenario_personalization(tmp)
    scenario_pause_resume(tmp)
    scenario_invariant_conflict(tmp)
    scenario_controlled_transitions(tmp)
    scenario_mcp_discovery(tmp)
    scenario_llm_tool_use(tmp)
    scenario_tool_denied(tmp)
    scenario_multiserver_flow(tmp)
    print("SCENARIO OK: exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())