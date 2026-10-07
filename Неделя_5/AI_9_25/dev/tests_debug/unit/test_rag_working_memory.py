# -*- coding: utf-8 -*-
"""Юнит-тесты памяти задачи + RAG в каждом обмене (часть 4, этап 11, R9).

Проверяем: WorkingMemory расширена (goal/clarifications/constraints/terms) и
merge-сериализуется round-trip; история (ShortTermMemory) растёт и переживает
перезапуск; RAG вызывается на каждом сообщении; источники ≥1 в каждом ответе;
TaskStage не затронут; без --rag промпт прежний.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from core.agent import Agent
from core.llm_client import MockClient
from core.prompt_builder import PromptBuilder, render_rag
from core.state_machine import TaskStage, ALLOWED_TRANSITIONS
from storage.store import Store
from storage.db import ProfileRepository
from memory.base import MemoryContext, MemoryItem
from memory.manager import MemoryManager, default_layers
from memory.working import WorkingMemory
from rag.config import RagConfig
from rag.types import Hit


def make_agent(tmp_path, user_id="u1"):
    repo = ProfileRepository(str(tmp_path / "profiles.db"))
    store = Store(str(tmp_path / "users"), profile_repo=repo)
    memory = MemoryManager(default_layers(store))
    agent = Agent(MockClient(), memory, PromptBuilder("Ты ассистент"), store,
                  user_id=user_id)
    agent.initialize_user(user_id, "Тест", {"style": "a", "constraints": "b", "context": "c"})
    return agent


class FakeRag:
    def __init__(self):
        self.search_calls = 0
        self.cfg = RagConfig.default()

    def search(self, query, k=None, mode=None, filters=None, threshold=None):
        self.search_calls += 1
        return [Hit(chunk_id="d1#0", doc_id="d1", source="docs/a.md", title="",
                    section="", text="бюджет токенов", score=0.5, scores={"rrf": 0.01})]

    def context_block(self, query="", k=None, budget=None, hits=None, mode=None):
        return render_rag(hits or [])

    def sources_for(self, hits):
        from rag.sources import build_sources
        return build_sources(hits or [])

    def quotes_for(self, answer_text, hits):
        from rag.citations import build_quotes
        return build_quotes(answer_text or "", hits or [])

    def verdict_for(self, answer_text, hits, mode=None):
        return "partial" if hits else "unchecked"


# --- WorkingMemory: расширение полей ----------------------------------------------
def test_working_memory_goal_terms_roundtrip(tmp_path):
    repo = ProfileRepository(str(tmp_path / "profiles.db"))
    store = Store(str(tmp_path / "users"), profile_repo=repo)
    memory = MemoryManager(default_layers(store))
    ctx = MemoryContext("u1", "task1", "s1")
    wm = memory.layers["working"]

    memory.remember("working", ctx, content={"goal": "разобраться с бюджетом токенов"},
                    source="system")
    memory.remember("working", ctx, content={"terms": {"бюджет": "лимит токенов промпта"}},
                    source="system")
    memory.remember("working", ctx, content={"clarifications": "именно про промпт"},
                    source="system")
    memory.remember("working", ctx, content={"constraints": "только Python"}, source="system")

    data = store.read_working("u1", "task1")
    assert data["goal"] == "разобраться с бюджетом токенов"
    assert data["terms"]["бюджет"] == "лимит токенов промпта"
    assert any("промпт" in c["text"] for c in data["clarifications"])
    assert any("Python" in c["text"] for c in data["constraints"])

    # Новый менеджер читает те же данные (round-trip переживает перезапуск).
    memory2 = MemoryManager(default_layers(store))
    block = memory2.layers["working"].as_prompt_block(ctx)
    assert "Цель диалога:" in block
    assert "Термины:" in block
    assert "Уточнения:" in block


def test_working_memory_merge_terms_not_overwrite(tmp_path):
    repo = ProfileRepository(str(tmp_path / "profiles.db"))
    store = Store(str(tmp_path / "users"), profile_repo=repo)
    memory = MemoryManager(default_layers(store))
    ctx = MemoryContext("u1", "t", "s")
    memory.remember("working", ctx, content={"terms": {"a": "1"}}, source="system")
    memory.remember("working", ctx, content={"terms": {"b": "2"}}, source="system")
    terms = store.read_working("u1", "t")["terms"]
    assert terms == {"a": "1", "b": "2"}      # merge, не перезапись


# --- агент: извлечение памяти задачи ----------------------------------------------
def test_agent_extracts_goal_from_message(tmp_path):
    agent = make_agent(tmp_path)
    agent.respond("цель: понять, как считается бюджет токенов")
    data = agent.store.read_working("u1", agent.task)
    assert "бюджет" in data.get("goal", "")


def test_agent_extracts_term(tmp_path):
    agent = make_agent(tmp_path)
    agent.respond("термин «RRF» — это reciprocal rank fusion")
    data = agent.store.read_working("u1", agent.task)
    assert data["terms"].get("RRF") == "reciprocal rank fusion"


# --- RAG в каждом обмене ----------------------------------------------------------
def test_rag_called_every_message(tmp_path):
    agent = make_agent(tmp_path)
    fake = FakeRag()
    agent.rag_service = fake
    agent.rag_enabled = True
    agent.deliver.add("rag")

    for _ in range(3):
        agent.respond("вопрос про бюджет")

    assert fake.search_calls == 3             # поиск на КАЖДОМ обмене
    assert len(agent.last_answer_sources) >= 1


def test_sources_in_every_answer(tmp_path):
    agent = make_agent(tmp_path)
    agent.rag_service = FakeRag()
    agent.rag_enabled = True
    agent.deliver.add("rag")

    for _ in range(3):
        agent.respond("вопрос")
        assert len(agent.last_answer_sources) >= 1


def test_history_grows_and_survives_restart(tmp_path):
    agent = make_agent(tmp_path)
    for i in range(4):
        agent.respond(f"сообщение {i}")
    ctx = MemoryContext("u1", agent.task, agent.session_id)
    recent = agent.memory.layers["short_term"].recent(ctx)
    assert len(recent) >= 4

    # Новый агент читает ту же историю (session.json).
    agent2 = make_agent(tmp_path)
    ctx2 = MemoryContext("u1", agent2.task, agent.session_id)
    recent2 = agent2.memory.layers["short_term"].recent(ctx2)
    assert len(recent2) >= 4


# --- границы ----------------------------------------------------------------------
def test_task_stage_unchanged():
    assert {s.value for s in TaskStage} == {
        "new", "planning", "plan_approved", "implementation", "validation",
        "done", "paused", "failed"}
    assert set(ALLOWED_TRANSITIONS) == set(TaskStage)


def test_prompt_without_rag_unchanged(tmp_path):
    from core.agent import PromptContext
    builder = PromptBuilder("Ты ассистент", token_estimator=lambda t: max(1, len(t) // 4))
    ctx = PromptContext("вопрос", {"long_term": "Факт"}, rag_block="")
    assert builder.build(ctx, {"long_term", "rag"}) == builder.build(ctx, {"long_term"})
