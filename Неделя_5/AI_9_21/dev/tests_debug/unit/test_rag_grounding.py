# -*- coding: utf-8 -*-
"""Юнит-тесты grounding (этап 9, R7): вердикты, числа, ссылки, авто-перегенерация.

Тесты НЕ зависят от Ollama/индекса: ground() работает на строках Hit, а
авто-перегенерация проверяется скриптованным LLM-клиентом (счётчик вызовов).
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

import dataclasses

from rag.config import RagConfig
from rag.grounding import ground, extract_citations, feedback_prompt, render_report
from rag.types import Hit
from storage.store import Store
from storage.db import ProfileRepository
from memory.manager import MemoryManager, default_layers
from core.prompt_builder import PromptBuilder
from core.agent import Agent


HIT1_TEXT = ("BM25 использует функцию ранжирования с параметрами k1=1.2 и b=0.75 "
             "и учитывает длину документа.")
HIT2_TEXT = ("Dense-ретривер строит векторы через модель bge-m3 размером 1024 "
             "измерения и ищет ближайших соседей.")


def hit1():
    return Hit(chunk_id="d1#1", doc_id="d1", source="docs/a.md", title="Ретривер",
               section="BM25", text=HIT1_TEXT, score=0.02, scores={"rrf": 0.02})


def hit2():
    return Hit(chunk_id="d2#3", doc_id="d2", source="docs/b.md", title="Dense",
               section="", text=HIT2_TEXT, score=0.01, scores={"rrf": 0.01})


def cfg(mode="strict", **kw):
    base = RagConfig.default()
    return dataclasses.replace(
        base, grounding=dataclasses.replace(base.grounding, mode=mode, **kw))


# --- вердикты ---------------------------------------------------------------------
def test_supported_answer_is_ok():
    report = ground(
        "BM25 использует функцию ранжирования с параметрами k1=1.2 и b=0.75 [d1#d1#1]. "
        "Параметры учитывают длину документа [d1#d1#1].",
        [hit1()], cfg())
    assert report.verdict == "ok", report.to_dict()
    assert report.citations_ok
    assert report.stats["n_unsupported"] == 0
    assert report.stats["n_numbers_missing"] == 0


def test_invented_number_is_hallucination():
    report = ground(
        "BM25 использует функцию ранжирования с параметрами k1=1.2 [d1#d1#1]. "
        "Метод предложили в 1994 году в университете Монпелье [d1#d1#1].",
        [hit1()], cfg())
    assert report.verdict == "hallucination", report.to_dict()
    assert report.stats["n_numbers_missing"] >= 1
    assert "1994" in report.stats["missing_preview"]


def test_invented_date_is_hallucination():
    report = ground("Индекс собран 2027-13-45 [d1#d1#1] по правилам BM25.",
                    [hit1()], cfg())
    assert report.verdict == "hallucination"


def test_answer_without_citations_is_partial():
    report = ground("BM25 использует функцию ранжирования с параметрами k1=1.2.",
                    [hit1()], cfg())
    assert report.verdict == "partial"
    assert not report.citations_ok
    assert report.stats["n_citations"] == 0


def test_bad_citation_reference_is_partial():
    # Ссылка есть, но указывает на чанк, которого нет среди найденных.
    report = ground("BM25 использует функцию ранжирования [d9#d9#9].",
                    [hit1()], cfg())
    assert report.citations_ok is False
    assert report.verdict == "partial"
    assert report.stats["n_bad_citations"] == 1


def test_numbers_from_other_cited_chunk_are_not_hallucination():
    report = ground(
        "Dense-ретривер строит векторы через модель bge-m3 размером 1024 измерения "
        "[d2#d2#3]; BM25 использует параметры k1=1.2 [d1#d1#1].",
        [hit1(), hit2()], cfg())
    assert report.verdict == "ok", report.to_dict()
    assert report.stats["n_numbers_missing"] == 0


# --- устойчивость оценки ----------------------------------------------------------
def test_case_and_word_forms_do_not_break_coverage():
    # Верхний регистр + падежные формы: normalize+stem обязаны сохранить покрытие.
    report = ground(
        "BM25 ИСПОЛЬЗУЕТ Функцией Ранжирования с параметрами k1=1.2 и b=0.75 [d1#d1#1].",
        [hit1()], cfg())
    assert report.verdict == "ok", report.to_dict()
    assert report.stats["coverage_avg"] >= 0.45


def test_citation_markers_do_not_count_as_numbers():
    # hex-хвосты ссылок не должны рождать «числа вне источников».
    long_id = "a" * 40 + "1234"
    hit = Hit(chunk_id=f"{long_id}#7", doc_id=long_id, source="x.md", title="",
              section="", text=HIT1_TEXT, score=0.1, scores={})
    report = ground(f"BM25 использует функцию ранжирования с k1=1.2 [{long_id}#{long_id}#7].",
                    [hit], cfg())
    assert report.verdict == "ok", report.to_dict()


def test_off_mode_checks_nothing():
    report = ground("Вовсе не про это, 12345 [d1#d1#1].", [hit1()], cfg("off"))
    assert report.verdict == "unchecked"
    assert report.sentences == ()
    assert report.stats["n_sentences"] == 0


def test_numbers_strict_off_ignores_numbers():
    report = ground("BM25 использует функцию ранжирования с параметрами k1=1.2 [d1#d1#1]. "
                    "Метод предложили в 1994 году в университете Монпелье [d1#d1#1].",
                    [hit1()], cfg(numbers_strict=False))
    assert report.verdict != "hallucination"
    assert report.stats["n_numbers_missing"] == 0


def test_extract_citations_only_ref_shape():
    assert extract_citations("см. [d1#d1#1] и [d2#d2#3], но не [1] или [текст](url)") \
        == ["d1#d1#1", "d2#d2#3"]


def test_feedback_prompt_and_render():
    report = ground("Метод предложили в 1994 году [d1#d1#1].", [hit1()], cfg())
    prompt = feedback_prompt(report, "Метод предложили в 1994 году", n_sources=1)
    assert "1994" in prompt and "источник" in prompt.lower()
    text = render_report(report)
    assert report.verdict in text and "Предложений" in text


# --- агент: авто-перегенерация (strict) --------------------------------------------
class ScriptedClient:
    """LLM-заглушка по скрипту ответов; считает вызовы (для проверки лимита 1)."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0

    def complete(self, messages, **params):
        self.calls += 1
        return self.answers.pop(0) if self.answers else "(нет ответа)"


class GroundedFakeRag:
    """Фасад с реальным grounding-ядром, но без индекса (поиск — фиксированные hits)."""

    def __init__(self, hits, mode="strict"):
        self.hits = hits
        self.search_calls = 0
        base = RagConfig.default()
        self.cfg = dataclasses.replace(
            base, grounding=dataclasses.replace(base.grounding, mode=mode))

    def search(self, query, k=None, mode=None, filters=None):
        self.search_calls += 1
        return self.hits

    def context_block(self, query="", k=None, budget=None, hits=None, mode=None):
        return "1. [d1#d1#1] docs/a.md\n    " + HIT1_TEXT

    def ground(self, answer, hits=None, mode=None):
        return ground(answer, hits if hits is not None else self.hits, self.cfg)

    def grounding_feedback(self, report, answer, n_sources):
        return feedback_prompt(report, answer, n_sources)

    def grounding_render(self, report):
        return render_report(report)


BAD_ANSWER = "BM25 использует функцию ранжирования с параметрами k1=1.2 [d1#d1#1]. " \
             "Метод предложили в 1994 году в университете Монпелье [d1#d1#1]."
GOOD_ANSWER = "BM25 использует функцию ранжирования с параметрами k1=1.2 и b=0.75 [d1#d1#1]."


def make_agent(tmp_path, client, mode="strict"):
    repo = ProfileRepository(str(tmp_path / "profiles.db"))
    store = Store(str(tmp_path / "users"), profile_repo=repo)
    memory = MemoryManager(default_layers(store))
    agent = Agent(client, memory, PromptBuilder("Ты ассистент"), store, user_id="g1")
    agent.initialize_user("g1", "Тест", {"style": "a", "constraints": "b", "context": "c"})
    agent.rag_service = GroundedFakeRag([hit1()], mode=mode)
    agent.rag_enabled = True
    agent.rag_block_enabled = True
    agent.deliver.add("rag")
    return agent


def test_strict_regenerates_once_and_accepts_fix(tmp_path):
    agent = make_agent(tmp_path, ScriptedClient([BAD_ANSWER, GOOD_ANSWER]))
    answer = agent.respond("Как ранжирует BM25?")
    assert answer == GOOD_ANSWER
    assert agent.llm.calls == 2                       # ответ + ровно 1 перегенерация
    assert agent.last_grounding_extra_tokens > 0      # доп. обмен учтён в оценках


def test_strict_marks_answer_when_fix_fails(tmp_path):
    agent = make_agent(tmp_path, ScriptedClient([BAD_ANSWER, BAD_ANSWER]))
    answer = agent.respond("Как ранжирует BM25?")
    assert agent.llm.calls == 2                       # цикла нет: максимум одна попытка
    assert "не полностью подтверждён" in answer


def test_warn_mode_does_not_regenerate(tmp_path):
    agent = make_agent(tmp_path, ScriptedClient([BAD_ANSWER]), mode="warn")
    answer = agent.respond("Как ранжирует BM25?")
    assert answer == BAD_ANSWER
    assert agent.llm.calls == 1


def test_off_mode_does_not_regenerate(tmp_path):
    agent = make_agent(tmp_path, ScriptedClient([BAD_ANSWER]), mode="off")
    answer = agent.respond("Как ранжирует BM25?")
    assert answer == BAD_ANSWER
    assert agent.llm.calls == 1


def test_no_rag_block_skips_grounding(tmp_path):
    # --no-rag-block: ищем и логируем, но цитировать не из чего → провер нет.
    agent = make_agent(tmp_path, ScriptedClient([BAD_ANSWER]))
    agent.rag_block_enabled = False
    answer = agent.respond("Как ранжирует BM25?")
    assert answer == BAD_ANSWER
    assert agent.llm.calls == 1


def test_check_grounding_without_hits_returns_none(tmp_path):
    agent = make_agent(tmp_path, ScriptedClient([GOOD_ANSWER]))
    agent.last_rag_hits = []
    assert agent.check_grounding(GOOD_ANSWER) is None
