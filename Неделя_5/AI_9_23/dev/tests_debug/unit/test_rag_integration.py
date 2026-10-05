# -*- coding: utf-8 -*-
"""Интеграция RAG в AI_9 (этап 8, Ревизия 6): регрессия промпта, порядок блоков,
фасад RagService на пустом/живом индексе, деградация ошибок, инварианты границ.

Главная регрессия этапа: БЕЗ активного RAG промпт байт-в-байт прежний.
Юниты НЕ зависят от живого Ollama (bm25/hashing).
"""
import dataclasses
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from core.prompt_builder import (PromptBuilder, BLOCK_ORDER, DELIVERABLE,
                                 RAG_INSTRUCTIONS, render_rag)
from core.agent import Agent, PromptContext
from core.llm_client import MockClient
from core.state_machine import TaskStage, ALLOWED_TRANSITIONS
from storage.store import Store
from storage.db import ProfileRepository
from memory.manager import MemoryManager, default_layers
from rag.config import RagConfig
from rag.service import RagService
from rag.types import Hit


def make_builder():
    return PromptBuilder("Ты ассистент", token_estimator=lambda t: max(1, len(t) // 4))


def make_agent(tmp_path, user_id="u1"):
    repo = ProfileRepository(str(tmp_path / "profiles.db"))
    store = Store(str(tmp_path / "users"), profile_repo=repo)
    memory = MemoryManager(default_layers(store))
    agent = Agent(MockClient(), memory, PromptBuilder("Ты ассистент"), store,
                  user_id=user_id)
    agent.initialize_user(user_id, "Тест", {"style": "a", "constraints": "b", "context": "c"})
    return agent


def hit(num, text="текст источника", source="docs/a.md", doc="d1", section=""):
    return Hit(chunk_id=f"c{num}", doc_id=doc, source=source, title="Заголовок",
               section=section, text=text, score=0.5 - num / 100,
               scores={"rrf": 0.01})


class FakeRag:
    """Мини-фасад: тот же контракт, что у RagService (DI в Agent)."""

    def __init__(self, hits=None, error=None):
        self.hits = hits if hits is not None else [hit(1), hit(2)]
        self.error = error
        self.search_calls = 0
        self.cfg = RagConfig.default()

    def search(self, query, k=None, mode=None, filters=None):
        self.search_calls += 1
        if self.error:
            raise self.error
        return self.hits

    def context_block(self, query="", k=None, budget=None, hits=None, mode=None):
        return render_rag(hits if hits is not None else self.hits)

    def stats(self):
        return {"n_chunks": len(self.hits), "n_docs": 1, "dim": 8, "model_id": "fake",
                "size_bytes": 0, "index_dir": "-", "mode": "bm25", "strategy": "fixed",
                "embedding_provider": "hashing", "ollama_url": "http://127.0.0.1:11434",
                "ollama_ready": False}


# --- 1. Главная регрессия: без RAG промпт байт-в-байт прежний ----------------------
def test_prompt_identical_without_rag():
    builder = make_builder()
    ctx = PromptContext("вопрос", {"long_term": "Факт"}, rag_block="")
    # rag в deliver, но блок пуст → список сообщений совпадает с набором без rag.
    with_rag = builder.build(ctx, {"long_term", "rag"})
    without_rag = builder.build(ctx, {"long_term"})
    assert with_rag == without_rag
    # Непустой блок и rag НЕ в deliver → тоже не попадает в промт.
    ctx2 = PromptContext("вопрос", {"long_term": "Факт"}, rag_block="1. [d#c] текст")
    assert builder.build(ctx2, {"long_term"}) == without_rag


def test_rag_block_absent_when_no_hits():
    builder = make_builder()
    ctx = PromptContext("вопрос", {"long_term": "Факт"}, rag_block=render_rag([]))
    messages = builder.build(ctx, {"long_term", "rag"})
    assert all("[rag]" not in m["content"] for m in messages)


# --- 2. Порядок блоков: rag после tools, до long_term ------------------------------
def test_rag_block_position_after_tools_before_memory():
    assert BLOCK_ORDER.index("rag") == BLOCK_ORDER.index("tools") + 1
    assert BLOCK_ORDER.index("rag") < BLOCK_ORDER.index("long_term")
    assert "rag" in DELIVERABLE

    builder = make_builder()
    ctx = PromptContext("вопрос", {"long_term": "Факт"},
                        tools_block="инструмент demo", rag_block="1. [d1#c1] источник")
    messages = builder.build(ctx, {"tools", "rag", "long_term"})
    texts = [m["content"] for m in messages]
    idx_tools = next(i for i, t in enumerate(texts) if t.startswith("[tools]"))
    idx_rag = next(i for i, t in enumerate(texts) if t.startswith("[rag]"))
    idx_lt = next(i for i, t in enumerate(texts) if t.startswith("[long_term]"))
    assert idx_tools < idx_rag < idx_lt
    assert "1. [d1#c1] источник" in texts[idx_rag]


def test_rag_budget_trims_block_first():
    # Бюджет не вытесняет invariants/profile: rag идёт последним из необязательных.
    builder = make_builder()
    ctx = PromptContext("вопрос", {"profile": "Имя: Аня"},
                        invariants="Правило: только Python",
                        rag_block="1. [d1#c1] " + "длинный источник " * 60)
    messages = builder.build(ctx, {"profile", "invariants", "rag"}, budget=120)
    joined = "\n".join(m["content"] for m in messages)
    assert "Правило: только Python" in joined
    assert "[rag]" not in joined


# --- 3. render_rag: нумерация, ссылки, бюджет --------------------------------------
def test_render_rag_numbering_and_links():
    block = render_rag([hit(1, section="Раздел"), hit(2, source="docs/b.md", doc="d2")])
    lines = block.splitlines()
    assert lines[0].startswith("Найденные источники")
    assert "1. [d1#c1] docs/a.md · Заголовок · раздел: Раздел" in block
    assert "2. [d2#c2] docs/b.md" in block
    assert RAG_INSTRUCTIONS in block
    assert render_rag([]) == ""


def test_render_rag_budget_drops_whole_sources():
    hits = [hit(i, text="содержание " * 20) for i in range(1, 6)]
    small = render_rag(hits, budget=200)      # влезает не всё: 2 источника из 5
    big = render_rag(hits, budget=100000)
    n_small = len([l for l in small.splitlines() if re.match(r"^\d+\. \[", l)])
    n_big = len([l for l in big.splitlines() if re.match(r"^\d+\. \[", l)])
    assert 0 < n_small < n_big
    # Рваных цитат нет: каждый размещённый источник — целая запись.
    assert small.count("\n    ") >= n_small
    # Слишком малый бюджет → блока нет вовсе (а не полублок).
    assert render_rag(hits, budget=1) == ""


def test_service_block_format_matches_core():
    """Единый вид блока: rag/service._render_block == core.render_rag (без импорта core)."""
    service = RagService(RagConfig.default())
    hits = [hit(1), hit(2)]
    assert service.context_block(hits=hits) == render_rag(hits)


# --- 4. RagService: пустой индекс и живой прогон (bm25 + hashing, без Ollama) -------
def test_service_empty_index_degrades(tmp_path):
    # Индекс — в tmp_path: тест не должен видеть реальный rag/index репозитория.
    cfg = dataclasses.replace(RagConfig.default(), index_dir=str(tmp_path / "no_index"))
    service = RagService(cfg)
    assert service.search("что-то") == []
    assert service.context_block("что-то") == ""
    stats = service.stats()
    assert stats["n_chunks"] == 0 and stats["n_docs"] == 0


def test_service_ingest_search_roundtrip(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.md").write_text("# Основы\nКриптография изучает методы защиты информации.",
                               encoding="utf-8")
    (docs / "b.md").write_text("# Быт\nРецепт борща с свёклой и капустой.", encoding="utf-8")

    cfg = dataclasses.replace(
        RagConfig.default(),
        index_dir=str(tmp_path / "index"),
        embedding=dataclasses.replace(RagConfig.default().embedding, provider="hashing"),
        retrieval=dataclasses.replace(RagConfig.default().retrieval, mode="bm25"),
    )
    service = RagService(cfg)
    report = service.ingest([str(docs / "a.md"), str(docs / "b.md")])
    assert report.chunks > 0 and report.added == 2

    hits = service.search("Криптография защита информации")
    assert hits and hits[0].source.endswith("a.md")
    block = service.context_block(hits=hits)
    assert f"[{hits[0].doc_id}#{hits[0].chunk_id}]" in block

    # Индекс переживает перезапуск (тот же каталог → новый фасад).
    reloaded = RagService(cfg)
    assert reloaded.stats()["n_chunks"] == service.stats()["n_chunks"]
    assert reloaded.search("Криптография защита информации")


# --- 5. Агент: DI RAG, один поиск на обмен, деградация ошибок -----------------------
def test_agent_rag_off_context_has_no_block(tmp_path):
    agent = make_agent(tmp_path)
    ctx = agent.build_context("вопрос")
    assert ctx.rag_block == ""
    assert agent.last_rag_hits == []


def test_agent_rag_injects_block_and_one_search(tmp_path):
    agent = make_agent(tmp_path)
    fake = FakeRag()
    agent.rag_service = fake
    agent.rag_enabled = True
    agent.deliver.add("rag")

    answer = agent.respond("Что делать?")
    assert answer is not None
    assert fake.search_calls == 1
    assert len(agent.last_rag_hits) == 2

    messages = agent.prompts.build(agent.build_context("Что делать?"), agent.deliver)
    assert any(m["content"].startswith("[rag]") for m in messages)
    # Повторная сборка контекста того же обмена (Kod.py: оценка токенов) — без 2-го поиска.
    agent.build_context("Что делать?")
    assert fake.search_calls == 1


def test_agent_rag_block_disabled_still_searches(tmp_path):
    agent = make_agent(tmp_path)
    fake = FakeRag()
    agent.rag_service = fake
    agent.rag_enabled = True
    agent.rag_block_enabled = False          # --no-rag-block
    agent.deliver.add("rag")

    agent.respond("Что делать?")
    assert fake.search_calls == 1 and agent.last_rag_hits
    ctx = agent.build_context("Что делать?")
    assert ctx.rag_block == ""


def test_agent_rag_error_does_not_break_answer(tmp_path):
    agent = make_agent(tmp_path)
    agent.rag_service = FakeRag(error=RuntimeError("Ollama недоступна"))
    agent.rag_enabled = True
    agent.deliver.add("rag")

    answer = agent.respond("Что делать?")
    assert answer is not None
    assert agent.last_rag_hits == []
    assert agent.build_context("Что делать?").rag_block == ""


# --- 6. Границы модулей (мастер-план §5) -------------------------------------------
_IMPORT_CORE = re.compile(r"^\s*(from\s+core[\w.]*\s+import|import\s+core\b)")
_IMPORT_RAG = re.compile(r"^\s*(from\s+rag[\w.]*\s+import|import\s+rag\b)")


def test_rag_does_not_import_core():
    for name in sorted(os.listdir(os.path.join(BASE_DIR, "rag"))):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(BASE_DIR, "rag", name), encoding="utf-8") as handle:
            for line in handle:
                assert not _IMPORT_CORE.match(line), f"rag/{name}: {line.strip()}"


def test_core_does_not_import_rag():
    for name in sorted(os.listdir(os.path.join(BASE_DIR, "core"))):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(BASE_DIR, "core", name), encoding="utf-8") as handle:
            for line in handle:
                assert not _IMPORT_RAG.match(line), f"core/{name}: {line.strip()}"


def test_task_stage_contract_unchanged():
    """TaskStage не меняется: канон 8 стадий + переходы (этап 8 их не трогает)."""
    assert {s.value for s in TaskStage} == {
        "new", "planning", "plan_approved", "implementation", "validation",
        "done", "paused", "failed"}
    assert len(TaskStage) == 8
    assert set(ALLOWED_TRANSITIONS) == set(TaskStage)