# -*- coding: utf-8 -*-
"""Юнит-тесты инвариантов (День 14): проверка, конфликт, изменение, персистентность.

Все на заглушках, без живого ключа. Базовые тесты — канон `Задание_Д14.txt`
(test_allowed_action / test_forbidden_framework / test_forbidden_dependency).
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from storage.store import Store
from storage.db import ProfileRepository
from memory.manager import MemoryManager, default_layers
from core.llm_client import MockClient
from core.prompt_builder import PromptBuilder
from core.agent import Agent, StubExecutor
from core.invariants import (
    Invariant, ConstraintSet, ProposedAction, RuleBasedChecker,
    update_invariant, toggle_invariant, example_constraints,
)


def make_agent(tmp_path, user_id="u"):
    repo = ProfileRepository(str(tmp_path / "profiles.db"))
    store = Store(str(tmp_path / "users"), profile_repo=repo)
    memory = MemoryManager(default_layers(store))
    agent = Agent(MockClient(), memory, PromptBuilder("Ты ассистент"), store,
                  user_id=user_id, executor=StubExecutor())
    agent.initialize_user(user_id, "Тест", {"style": "a", "constraints": "b", "context": "c"})
    return agent


# --- Базовые тесты из задания --------------------------------------------------------
def test_allowed_action(tmp_path):
    constraints = example_constraints()
    action = ProposedAction(description="Добавить новый endpoint", technology="django")
    assert RuleBasedChecker().check(action, constraints) == []


def test_forbidden_framework(tmp_path):
    constraints = example_constraints()
    action = ProposedAction(description="Перейти на FastAPI", technology="fastapi")
    violations = RuleBasedChecker().check(action, constraints)
    assert len(violations) == 1
    assert "framework.django" in violations[0]


def test_forbidden_dependency(tmp_path):
    constraints = example_constraints()
    action = ProposedAction(description="Установить библиотеку", adds_dependency=True)
    assert len(RuleBasedChecker().check(action, constraints)) == 1


# --- Расширенные кейсы ---------------------------------------------------------------
def test_multiple_violations_at_once(tmp_path):
    constraints = example_constraints()
    action = ProposedAction(description="Накатить FastAPI и либу", technology="fastapi",
                            adds_dependency=True)
    violations = RuleBasedChecker().check(action, constraints)
    assert len(violations) == 2


def test_invariants_survive_restart(tmp_path):
    agent = make_agent(tmp_path)
    agent.add_invariant(Invariant(id="framework.django", category="architecture",
                                  description="Использовать Django"))
    agent.save_state()
    agent2 = make_agent(tmp_path)
    agent2.load_state("u")
    assert agent2.constraints.by_id("framework.django") is not None


def test_clearing_session_keeps_invariants(tmp_path):
    agent = make_agent(tmp_path)
    agent.add_invariant(Invariant(id="framework.django", category="architecture",
                                  description="Django"))
    agent.remember_message("user", "привет", "M1")
    session_path = agent.store.session_path("u", agent.task, agent.session_id)
    assert os.path.isfile(session_path)
    os.remove(session_path)   # очистка истории диалога
    assert os.path.isfile(agent.store.invariants_path("u", agent.task))
    agent.load_constraints()
    assert agent.constraints.by_id("framework.django") is not None


def test_forbidden_action_does_not_call_tool(tmp_path):
    agent = make_agent(tmp_path)
    agent.add_invariant(Invariant(id="framework.django", category="architecture",
                                  description="Django"))
    before = agent.tool_calls
    result = agent.propose_and_check("перепиши API на FastAPI")
    assert result["allowed"] is False
    assert agent.tool_calls == before


def test_refusal_names_invariant(tmp_path):
    agent = make_agent(tmp_path)
    agent.add_invariant(Invariant(id="framework.django", category="architecture",
                                  description="Django"))
    result = agent.propose_and_check("перейти на FastAPI")
    assert "framework.django" in result["message"]


def test_refusal_offers_alternative(tmp_path):
    agent = make_agent(tmp_path)
    agent.add_invariant(Invariant(id="framework.django", category="architecture",
                                  description="Django"))
    result = agent.propose_and_check("перейти на FastAPI")
    assert "альтернатив" in result["message"].lower()


def test_update_requires_confirmation(tmp_path):
    constraints = example_constraints()
    try:
        update_invariant(constraints, "framework.django", "x", authorized=False)
        assert False, "ожидался PermissionError"
    except PermissionError:
        pass
    update_invariant(constraints, "framework.django", "новое", authorized=True)
    assert constraints.by_id("framework.django").description == "новое"


def test_active_false_lifts_block(tmp_path):
    constraints = example_constraints()
    toggle_invariant(constraints, "framework.django", False)
    action = ProposedAction(description="x", technology="fastapi")
    assert RuleBasedChecker().check(action, constraints) == []


def test_warning_severity(tmp_path):
    agent = make_agent(tmp_path)
    agent.add_invariant(Invariant(id="framework.django", category="architecture",
                                  description="Django", severity="warning"))
    logs = []
    agent.log = logs.append
    result = agent.propose_and_check("перейти на FastAPI")
    assert result["allowed"] is True          # warning не блокирует
    assert result["warnings"]
    assert any("warning" in line for line in logs)


def test_invariants_block_in_prompt(tmp_path):
    agent = make_agent(tmp_path)
    agent.add_invariant(Invariant(id="framework.django", category="architecture",
                                  description="Использовать Django"))
    pctx = agent.build_context("вопрос")
    messages = agent.prompts.build(pctx, agent.deliver)
    joined = "\n".join(m["content"] for m in messages)
    assert "[invariants]" in joined and "framework.django" in joined
