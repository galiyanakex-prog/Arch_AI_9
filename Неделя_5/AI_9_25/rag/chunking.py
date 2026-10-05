# -*- coding: utf-8 -*-
"""Стратегии чанкинга (этап 3, R1).

Две обязательные стратегии (требование Задание_d21.txt) дают РАЗНОЕ разбиение:
  * S1 `fixed`      — скользящее окно по токенам, граница по концу предложения;
  * S2 `structural` — границы по markdown-заголовкам и блокам кода/таблиц,
                      parent-child (дочерний индексируется, родитель в контекст).
S3 `semantic` — задел (не в гейте).

Контракт `doc` — dict: {doc_id, source, title, text}. Возврат — list[Chunk].
"""
from __future__ import annotations

import hashlib
import re

from rag.text import est_tokens, split_sentences
from rag.types import Chunk

STRATEGIES = ("fixed", "structural")

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_RE = re.compile(r"^\s*```")
_TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _make_chunk(doc, index, text, section, content_type, start_line, end_line,
                strategy, parent_id=""):
    return Chunk(
        chunk_id=f"{doc['doc_id']}#{index}",
        doc_id=doc["doc_id"],
        source=doc["source"],
        title=doc.get("title", ""),
        section=section,
        text=text,
        strategy=strategy,
        content_type=content_type,
        start_line=start_line,
        end_line=end_line,
        tokens=est_tokens(text),
        sha1=_sha1(text),
        parent_id=parent_id,
    )


def _split_by_sentences(text, size_tokens, overlap_tokens):
    """Скользящее окно по предложениям: граница — конец предложения, хвост < 40 → назад."""
    sentences = split_sentences(text) or [text]
    windows = []
    current = []
    current_tokens = 0
    for sentence in sentences:
        st = est_tokens(sentence)
        if current and current_tokens + st > size_tokens:
            windows.append(" ".join(current))
            # overlap: оставляем хвост предложений на ~overlap_tokens
            tail = []
            tail_tokens = 0
            for s in reversed(current):
                if tail_tokens + est_tokens(s) > overlap_tokens:
                    break
                tail.insert(0, s)
                tail_tokens += est_tokens(s)
            current = tail
            current_tokens = tail_tokens
        current.append(sentence)
        current_tokens += st
    if current:
        tail_text = " ".join(current)
        # хвост < 40 токенов присоединяем к предыдущему окну
        if windows and est_tokens(tail_text) < 40:
            windows[-1] = f"{windows[-1]} {tail_text}"
        else:
            windows.append(tail_text)
    return windows


def _chunk_fixed(doc, cfg):
    """S1: фиксированное окно по токенам с перекрытием."""
    text = doc["text"]
    size = cfg.fixed_size_tokens
    overlap = cfg.fixed_overlap_tokens
    windows = _split_by_sentences(text, size, overlap)
    chunks = []
    for i, window in enumerate(windows):
        chunks.append(_make_chunk(doc, i, window, "", "text", 0, 0, "fixed"))
    return chunks


def _parse_structural_blocks(text):
    """Разбор на блоки: (section, content_type, start_line, end_line, text)."""
    lines = text.splitlines()
    blocks = []
    section_stack = []
    current_lines = []
    current_type = "text"
    start = 0
    in_fence = False

    def flush(end):
        if current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                section = " > ".join(section_stack)
                blocks.append((section, current_type, start, end, content))

    for i, line in enumerate(lines):
        if _FENCE_RE.match(line):
            if not in_fence:
                flush(i - 1)
                current_lines = [line]
                current_type = "code"
                start = i
                in_fence = True
            else:
                current_lines.append(line)
                flush(i)
                current_lines = []
                current_type = "text"
                in_fence = False
            continue
        if in_fence:
            current_lines.append(line)
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            flush(i - 1)
            current_lines = []
            level = len(heading.group(1))
            title = heading.group(2).strip()
            section_stack = section_stack[: level - 1]
            section_stack.append(title)
            current_lines = [line]
            current_type = "text"
            start = i
            continue
        if _TABLE_RE.match(line):
            if current_type != "table":
                flush(i - 1)
                current_lines = []
                current_type = "table"
                start = i
            current_lines.append(line)
            continue
        if current_type == "table" and not _TABLE_RE.match(line):
            flush(i - 1)
            current_lines = []
            current_type = "text"
            start = i
        if not current_lines:
            start = i
        current_lines.append(line)
    flush(len(lines) - 1)
    return blocks


def _chunk_structural(doc, cfg):
    """S2: границы по заголовкам/коду/таблицам; код и таблицы не режутся."""
    text = doc["text"]
    size = cfg.size_tokens
    overlap = int(size * cfg.overlap_ratio)
    blocks = _parse_structural_blocks(text)
    chunks = []
    index = 0
    for section, content_type, start, end, content in blocks:
        if content_type in ("code", "table") or est_tokens(content) <= size:
            chunks.append(_make_chunk(doc, index, content, section, content_type,
                                      start, end, "structural"))
            index += 1
            continue
        # Большая текстовая секция — допил по предложениям с перекрытием.
        for window in _split_by_sentences(content, size, overlap):
            chunks.append(_make_chunk(doc, index, window, section, "text",
                                      start, end, "structural"))
            index += 1
    return chunks


def chunk_document(doc, cfg, strategy: str) -> list:
    """Разбить документ на чанки выбранной стратегией."""
    if not (doc.get("text") or "").strip():
        return []
    if strategy == "fixed":
        return _chunk_fixed(doc, cfg)
    if strategy == "structural":
        return _chunk_structural(doc, cfg)
    raise ValueError(f"неизвестная стратегия чанкинга: {strategy}")