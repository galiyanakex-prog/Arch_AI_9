# -*- coding: utf-8 -*-
"""Юнит-тесты rag/chunking.py (этап 3, R1)."""
import hashlib
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from rag.chunking import chunk_document
from rag.config import RagConfig

CFG = RagConfig.default().chunking

SAMPLE = """# Заголовок A

Первый абзац текста. Второе предложение здесь. Третье предложение тоже есть.

## Подраздел B

Ещё немного текста для проверки разбиения по структуре документа.

```python
def foo():
    return 42
```

| col1 | col2 |
|------|------|
| a    | b    |
"""


def _doc(text=SAMPLE, source="sample.md"):
    return {
        "doc_id": hashlib.sha1(source.encode()).hexdigest(),
        "source": source,
        "title": "Заголовок A",
        "text": text,
    }


def test_both_strategies_produce_chunks():
    for strategy in ("fixed", "structural"):
        chunks = chunk_document(_doc(), CFG, strategy)
        assert chunks, f"{strategy} не дал чанков"


def test_metadata_filled():
    for strategy in ("fixed", "structural"):
        for chunk in chunk_document(_doc(), CFG, strategy):
            assert chunk.chunk_id and chunk.doc_id and chunk.source
            assert chunk.title and chunk.strategy == strategy
            assert chunk.tokens > 0 and chunk.sha1


def test_strategies_differ():
    fixed = chunk_document(_doc(), CFG, "fixed")
    structural = chunk_document(_doc(), CFG, "structural")
    assert len(fixed) != len(structural), "стратегии дали одинаковое число чанков"


def test_code_block_not_split():
    chunks = chunk_document(_doc(), CFG, "structural")
    code = [c for c in chunks if c.content_type == "code"]
    assert code, "код-блок не найден"
    assert any("def foo" in c.text and "return 42" in c.text for c in code)


def test_section_for_nested_headings():
    chunks = chunk_document(_doc(), CFG, "structural")
    sections = {c.section for c in chunks}
    assert any("Заголовок A > Подраздел B" in s for s in sections)


def test_empty_and_broken_input():
    for strategy in ("fixed", "structural"):
        assert chunk_document(_doc(text=""), CFG, strategy) == []
        assert chunk_document(_doc(text="   \n  \n"), CFG, strategy) == []


def test_crlf_and_bom_survive():
    text = "\ufeff# Заголовок\r\n\r\nТекст с CRLF.\r\n"
    for strategy in ("fixed", "structural"):
        chunks = chunk_document(_doc(text=text), CFG, strategy)
        assert chunks, f"{strategy} упал на CRLF/BOM"


def test_unknown_strategy_raises():
    try:
        chunk_document(_doc(), CFG, "semantic")
    except ValueError:
        return
    raise AssertionError("неизвестная стратегия не подняла ValueError")
