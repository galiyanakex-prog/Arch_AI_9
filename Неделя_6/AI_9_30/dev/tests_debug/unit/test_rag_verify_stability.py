# -*- coding: utf-8 -*-
"""Юнит-тесты метрики стабильности verify (Ревизия 7.1, этап 2, решение №13).

Проверяем агрегацию N прогонов: `runs=1` — прежний отчёт; `runs>1` — таблица
среднее/min–max/σ; σ ≥ 0; пустой набор не роняет. Живой LLM не нужен — формат
источников/цитат проверяется на заглушке (llm=None).
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from rag.config import RagConfig
from rag.verify import verify_answers, verify_stability, render_report, render_stability, _aggregate

_CFG = RagConfig.default()
_QUERIES = [{"id": "c01", "query": "как считается бюджет токенов"},
            {"id": "c02", "query": "что такое инвариант"}]


def test_aggregate_basic():
    agg = _aggregate([1, 2, 3])
    assert agg["mean"] == 2.0
    assert agg["min"] == 1 and agg["max"] == 3
    assert agg["std"] >= 0


def test_aggregate_single():
    agg = _aggregate([5])
    assert agg["mean"] == 5 and agg["std"] == 0.0


def test_verify_runs_one_is_plain_report():
    result = verify_answers(_CFG, _QUERIES, k=3, llm=None, limit=2)
    text = render_report(result)
    assert "Проверка формата ответа" in text
    assert "Стабильность" not in text


def test_verify_stability_runs_three():
    result = verify_stability(_CFG, _QUERIES, k=3, llm=None, limit=2, runs=3)
    assert result["runs"] == 3
    assert len(result["per_run"]) == 3
    for key in ("sources_ok", "quotes_ok", "meaning_ok", "insufficient"):
        assert result["metrics"][key]["std"] >= 0
    text = render_stability(result)
    assert "Стабильность" in text
    assert "σ" in text


def test_verify_stability_empty_queries():
    result = verify_stability(_CFG, [], k=3, llm=None, limit=2, runs=2)
    assert result["n"] == 0
    assert result["metrics"]["sources_ok"]["mean"] == 0.0
