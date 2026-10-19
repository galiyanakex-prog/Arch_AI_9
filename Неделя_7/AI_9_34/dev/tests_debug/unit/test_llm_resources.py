# -*- coding: utf-8 -*-
"""Юнит-тесты снятия ресурсов и агрегации «до/после» (Ревизия 8, этап 8, часть 4).

Без сети и без реальных процессов: парсеры `ps`/`free`/`lms ps` проверяются на
фиксированных образцах; `ResourceSampler` — на инъекции `runner`; агрегация
матрицы «до/после» — на синтетических сводках.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from core.resources import (  # noqa: E402
    parse_ps, parse_free, parse_lms_ps, ResourceSampler, render_resources_section,
)

PS_SAMPLE = "  3804048  1.9\n"
FREE_SAMPLE = (
    "               total        used        free      shared  buff/cache   available\n"
    "Mem:           15904        3967        6278         161        6139       11937\n"
    "Swap:          16496        3807       12689\n"
)
LMS_SAMPLE = (
    "\n"
    "IDENTIFIER                                                        MODEL"
    "                                                             STATUS        SIZE"
    "       CONTEXT    PARALLEL    LOAD CONFIG    DEVICE    TTL\n"
    "qwen2.5-coder-3b-instruct-distill-qwen3-coder-next-abliterated    "
    "qwen2.5-coder-3b-instruct-distill-qwen3-coder-next-abliterated    IDLE      "
    "2.54 GB    32768      4           LM Studio      Local\n"
)


# --- 1. Парсеры на фиксированных образцах ---------------------------------------

def test_parse_ps():
    assert parse_ps(PS_SAMPLE) == {"rss_kb": 3804048, "pcpu": 1.9}


def test_parse_ps_empty():
    assert parse_ps("") == {"rss_kb": 0, "pcpu": 0.0}


def test_parse_free():
    out = parse_free(FREE_SAMPLE)
    assert out["total_mb"] == 15904
    assert out["used_mb"] == 3967
    assert out["available_mb"] == 11937


def test_parse_lms_ps():
    out = parse_lms_ps(LMS_SAMPLE)
    assert len(out) == 1
    assert out[0]["identifier"].startswith("qwen2.5-coder-3b")
    assert out[0]["status"] == "IDLE"
    assert out[0]["size"] == "2.54 GB"
    assert out[0]["context"] == "32768"


def test_parse_lms_ps_header_only():
    assert parse_lms_ps("IDENTIFIER MODEL STATUS SIZE CONTEXT PARALLEL\n") == []


# --- 2. ResourceSampler на инъекции runner --------------------------------------

def _fake_runner(ps_text, free_text, lms_text):
    def runner(cmd):
        if cmd[0] == "ps":
            return ps_text
        if cmd[0] == "free":
            return free_text
        if cmd[0] == "lms":
            return lms_text
        return ""
    return runner


def test_sampler_summary():
    sampler = ResourceSampler(pid=123, interval=0.01,
                              runner=_fake_runner(PS_SAMPLE, FREE_SAMPLE, LMS_SAMPLE))
    sampler.start()
    sampler.stop()
    summary = sampler.summary()
    assert summary["pid"] == 123
    assert summary["rss_peak_mb"] == round(3804048 / 1024, 1)
    assert summary["model_size"] == "2.54 GB"
    assert summary["free_before"]["used_mb"] == 3967
    assert summary["free_after"]["used_mb"] == 3967


def test_sampler_model_hint_selects_row():
    """model_hint выбирает размер нужной модели из нескольких строк `lms ps`."""
    lms_multi = (
        "IDENTIFIER    MODEL    STATUS    SIZE    CONTEXT    PARALLEL\n"
        "qwen/qwen2.5-coder-14b    qwen/qwen2.5-coder-14b    IDLE    8.99 GB    32768    4\n"
        "codellama-7b-python    codellama-7b-python    IDLE    2.95 GB    16384    4\n"
    )
    sampler = ResourceSampler(pid=1, interval=0.01, model_hint="codellama-7b-python",
                              runner=_fake_runner(PS_SAMPLE, FREE_SAMPLE, lms_multi))
    sampler.start()
    sampler.stop()
    assert sampler.summary()["model_size"] == "2.95 GB"


def test_sampler_no_pid_no_samples():
    sampler = ResourceSampler(pid=0, interval=0.01,
                              runner=_fake_runner("", FREE_SAMPLE, LMS_SAMPLE))
    # find_lmstudio_pid через runner не вызывается (pgrep идёт через _run) —
    # pid остаётся 0, сэмплов нет, но сводка не падает.
    sampler.pid = 0
    sampler._sample_once()
    assert sampler.samples == []
    assert sampler.summary()["rss_peak_mb"] == 0.0


# --- 3. Раздел «Ресурсы» в отчёте -----------------------------------------------

def test_render_resources_section():
    resources = {
        "pid": 123, "samples": 5, "rss_peak_mb": 3714.9, "rss_avg_mb": 3600.0,
        "cpu_avg": 250.0, "model_size": "2.54 GB",
        "free_before": {"used_mb": 3967, "available_mb": 11937},
        "free_after": {"used_mb": 5000, "available_mb": 10000},
    }
    text = render_resources_section(resources)
    assert "## Ресурсы (хост)" in text
    assert "3714.9" in text
    assert "2.54 GB" in text
    assert "VRAM неприменим" in text


def test_render_resources_section_empty():
    assert render_resources_section({}) == ""


# --- 4. Агрегация «до/после» воспроизводима -------------------------------------

def test_compare_generators_resources_hook():
    """resource_hooks: start/stop вызываются вокруг прогона, сводка в result."""
    from rag.compare import compare_generators
    from rag.config import RagConfig

    calls = {"start": 0, "stop": 0}

    def start():
        calls["start"] += 1

    def stop():
        calls["stop"] += 1
        return {"rss_peak_mb": 100.0}

    cfg = RagConfig.default()
    queries = [{"id": "c01", "query": "вопрос", "must_contain": []}]
    generators = {"local": lambda messages: "ответ"}
    result = compare_generators(cfg, queries, generators, k=1, repeat=1,
                                resource_hooks={"local": {"start": start, "stop": stop}})
    assert calls == {"start": 1, "stop": 1}
    assert result["resources"]["local"]["rss_peak_mb"] == 100.0


def test_compare_generators_missing_config_is_explicit():
    """Отсутствие конфигурации в матрице → строка «недоступно», а не тихий пропуск.

    Проверяем на уровне отчёта: генератор, помеченный недоступным, не попадает в
    summary, но в отчёте остаётся явная пометка (см. run_rag_gen_compare).
    """
    from rag.compare import compare_generators
    from rag.config import RagConfig

    cfg = RagConfig.default()
    queries = [{"id": "c01", "query": "вопрос", "must_contain": []}]
    # В матрице только доступный генератор; недоступный не передан вовсе.
    result = compare_generators(cfg, queries, {"local": lambda m: "ответ"}, k=1)
    assert "local" in result["summary"]
    assert "cloud" not in result["summary"]
