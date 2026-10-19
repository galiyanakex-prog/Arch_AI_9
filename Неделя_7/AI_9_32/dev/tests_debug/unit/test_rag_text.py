# -*- coding: utf-8 -*-
"""Юнит-тесты rag/text.py (этап 3, R1)."""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from rag import text as T


def test_normalize_strips_case_and_punct():
    assert T.normalize("Привет, МИР!") == "привет мир"
    assert T.normalize("  a-b_c  ") == "a b c"


def test_tokenize_words_and_numbers():
    assert T.tokenize("Python 3.13 — это круто!") == ["python", "3", "13", "это", "круто"]


def test_stem_collapses_forms():
    assert T.stem("инвариантами") == T.stem("инвариант")
    assert T.stem("правила") == T.stem("правило")


def test_split_sentences_keeps_abbrev():
    sents = T.split_sentences("Это т. е. пример. Второе предложение!")
    assert len(sents) == 2
    assert sents[0].startswith("Это")


def test_est_tokens_approx():
    assert T.est_tokens("") == 0
    assert T.est_tokens("a" * 40) == 10


def test_normalize_code_keeps_case_and_splits_snake():
    out = T.normalize_code("def load_servers_config(MCPServerConfig):")
    assert "load" in out and "servers" in out and "config" in out
    assert "mcp" in out and "server" in out


def test_stopwords_loaded():
    assert "и" in T.STOPWORDS
    assert "the" in T.STOPWORDS
