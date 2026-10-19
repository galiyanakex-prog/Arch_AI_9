# -*- coding: utf-8 -*-
"""Юнит-тесты секции `rewrite` в конфиге RAG (Ревизия 7.1, этап 1, решение №4).

Проверяем, что rewrite настраивается из `rag/config.json` (единообразно с
`unknown`/`retrieval`): класс `RewriteConfig`, поле в `RagConfig`, слияние из JSON
и env (`AI9_RAG_REWRITE_MODE`), валидация режима. Флаг `--rag-rewrite` имеет
приоритет над конфигом (проверяется в Kod.py, здесь — только конфиг).
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from rag.config import RagConfig, RewriteConfig, RagConfigError


def test_rewrite_config_defaults():
    cfg = RagConfig.default()
    assert isinstance(cfg.rewrite, RewriteConfig)
    assert cfg.rewrite.enabled is False
    assert cfg.rewrite.mode == "heuristic"


def test_rewrite_config_loaded_from_json():
    cfg = RagConfig.load(os.path.join(BASE_DIR, "rag/config.json"))
    assert cfg.rewrite.mode == "heuristic"
    assert cfg.rewrite.enabled is False


def test_rewrite_config_env_override(monkeypatch=None):
    os.environ["AI9_RAG_REWRITE_MODE"] = "llm"
    try:
        cfg = RagConfig.default().from_env()
        assert cfg.rewrite.mode == "llm"
    finally:
        os.environ.pop("AI9_RAG_REWRITE_MODE", None)


def test_rewrite_config_invalid_mode():
    try:
        RagConfig.default().from_dict({"rewrite": {"mode": "bogus"}}).validate()
    except RagConfigError:
        return
    raise AssertionError("невалидный режим rewrite должен давать RagConfigError")


def test_rewrite_config_from_dict():
    cfg = RagConfig.default().from_dict({"rewrite": {"enabled": True, "mode": "llm"}})
    assert cfg.rewrite.enabled is True
    assert cfg.rewrite.mode == "llm"
