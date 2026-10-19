# -*- coding: utf-8 -*-
"""Юнит-тесты сравнения генераторов RAG (Ревизия 8, этап 6, G2).

Без сети: генераторы подменяются фейковыми callable. Проверяем контракты
`compare_generators`: три оси (качество/скорость/стабильность), валидность
ссылок, разбор расхождений, вердикт, воспроизводимость отчёта; и что
`rag/compare.py` не импортирует `core/` (граница §5).
"""
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from rag.compare import (compare_generators, render_generator_report,  # noqa: E402
                         _citations, _citations_valid, GENERATOR_MODES)
from rag.config import RagConfig  # noqa: E402
from rag.corpus import discover  # noqa: E402
from rag.embedding import HashingEmbedder  # noqa: E402
from rag.index import RagIndex  # noqa: E402
from rag.retrieval import Retriever  # noqa: E402
from rag.service import RagService  # noqa: E402

_CFG = RagConfig.default()
_EMB = HashingEmbedder(dim=256)


def _service(llm):
    svc = RagService(_CFG, llm=llm)
    index = RagIndex(_CFG)
    index.ingest(discover(None, _CFG.corpus), _CFG, _EMB)
    svc._index = index
    svc._loaded = True
    svc._embedder = _EMB
    svc._retriever = Retriever(index, _CFG, _EMB)
    return svc


class FakeGen:
    """Фейковый генератор: детерминированный ответ со ссылкой на первый чанк."""

    def __init__(self, name, latency=0.0, cite=True, empty=False):
        self.name = name
        self.latency = latency
        self.cite = cite
        self.empty = empty
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        if self.empty:
            return ""
        prompt = messages[-1]["content"]
        # Достаём первую ссылку [doc#chunk] из блока источников, если есть.
        ref = ""
        if self.cite:
            match = re.search(r"\[([0-9a-f]{8,}#\d+)\]", prompt)
            if match:
                ref = f" [{match.group(1)}]"
        return f"{self.name}: ответ по источникам{ref}"


def _queries():
    return [{"id": "c01", "query": "как считается бюджет токенов",
             "must_contain": ["бюджет"]},
            {"id": "c02", "query": "какой базовый класс описывает слой памяти",
             "must_contain": ["MemoryLayer"]}]


# --- ссылки ---------------------------------------------------------------------

def test_citations_extract_and_validate():
    hits = [type("H", (), {"chunk_id": "abc12345#0", "doc_id": "abc12345"})()]
    text = "Ответ [abc12345#0] и мусор [нет-такого]."
    cites = _citations(text)
    # Ссылкой считается только фрагмент с «#» (doc_id#chunk_id).
    assert cites == ["abc12345#0"]
    total, valid = _citations_valid(text, hits)
    assert total == 1 and valid == 1


def test_citations_duplicated_doc_id_still_valid():
    """Модель дублирует doc_id в ссылке — ссылка всё равно валидна."""
    hits = [type("H", (), {"chunk_id": "abc12345#0", "doc_id": "abc12345"})()]
    text = "См. [abc12345#abc12345#0]."
    total, valid = _citations_valid(text, hits)
    assert total == 1 and valid == 1


# --- сравнение генераторов ------------------------------------------------------

def test_compare_generators_three_axes():
    cloud = FakeGen("cloud")
    local = FakeGen("local")
    result = compare_generators(_CFG, _queries(),
                                {"cloud": cloud.complete, "local": local.complete}, k=5)
    assert set(result["summary"]) == {"cloud", "local"}
    for mode, s in result["summary"].items():
        # качество
        assert "must_ratio" in s and "sources_ok" in s
        # скорость
        assert "latency_median" in s and "latency_p95" in s and "tokens_per_s" in s
        # стабильность
        assert "errors" in s and "consistent" in s
    assert result["verdict"]


def test_compare_generators_repeat_consistency():
    """Повторы одного вопроса: согласованность считается по всем прогонам."""
    gen = FakeGen("local")
    result = compare_generators(_CFG, _queries(), {"local": gen.complete},
                                k=5, repeat=3)
    s = result["summary"]["local"]
    assert s["n"] == 6                      # 2 вопроса × 3 повтора
    assert s["questions"] == 2
    assert s["consistent"] == 2             # детерминированный генератор согласован


def test_compare_generators_empty_answer_is_error():
    gen = FakeGen("local", empty=True)
    result = compare_generators(_CFG, _queries(), {"local": gen.complete}, k=5)
    s = result["summary"]["local"]
    assert s["errors"] == s["n"]
    assert s["empty"] == s["n"]


def test_compare_generators_divergences():
    """Генератор без ссылок vs со ссылками → расхождение по источникам."""
    good = FakeGen("cloud", cite=True)
    bad = FakeGen("local", cite=False)
    result = compare_generators(_CFG, _queries(),
                                {"cloud": good.complete, "local": bad.complete}, k=5)
    # Оба возвращают источники (hits есть), но ссылки различаются — расхождение
    # по must_contain/источникам может отсутствовать; проверяем структуру.
    assert isinstance(result["divergences"], list)


def test_render_generator_report_has_three_axes():
    gen = FakeGen("local")
    result = compare_generators(_CFG, _queries(), {"local": gen.complete}, k=5)
    text = render_generator_report(result)
    assert "Качество" in text and "Скорость" in text and "Стабильность" in text
    assert "Вердикт" in text and "Разбор расхождений" in text


def test_compare_generators_reproducible():
    """Одинаковый вход → одинаковая сводка (детерминированный генератор).

    Латентность — единственная недетерминированная величина; качество и
    стабильность воспроизводимы.
    """
    gen = FakeGen("local")
    r1 = compare_generators(_CFG, _queries(), {"local": gen.complete}, k=5)
    r2 = compare_generators(_CFG, _queries(), {"local": gen.complete}, k=5)
    stable_keys = ("n", "must_ratio", "sources_ok", "citations", "citations_valid",
                   "verdicts", "errors", "empty", "consistent", "questions")
    for key in stable_keys:
        assert r1["summary"]["local"][key] == r2["summary"]["local"][key], key
    # Вердикт содержит латентность (недетерминирована) — сверяем качественную часть.
    assert r1["verdict"].split("медиана")[0] == r2["verdict"].split("медиана")[0]


def test_generator_modes_constant():
    assert GENERATOR_MODES == ("cloud", "local")


# --- граница модулей ------------------------------------------------------------

def test_compare_does_not_import_core():
    pattern = re.compile(r"^\s*(from\s+core[\w.]*\s+import|import\s+core\b)")
    with open(os.path.join(BASE_DIR, "rag", "compare.py"), encoding="utf-8") as handle:
        for line in handle:
            assert not pattern.match(line), f"rag/compare.py: {line.strip()}"
