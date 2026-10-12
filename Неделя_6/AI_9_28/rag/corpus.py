# -*- coding: utf-8 -*-
"""Обход корпуса и дельта-индексация (этап 5, R3).

`discover` собирает документы из `corpus.list` (+ явные пути), отсеивая `deny`.
`delta` сравнивает sha1 содержимого с известными документами индекса и говорит,
что добавить/обновить/удалить/пропустить — это основа инкрементальной индексации.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

_CODE_EXT = {".py", ".js", ".ts", ".sh", ".go", ".rs", ".java", ".c", ".cpp", ".h"}
_TEXT_EXT = {".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini"}


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _content_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in _CODE_EXT:
        return "code"
    return "text"


def _denied(path: str, deny) -> bool:
    """Путь под запретом, если содержит запрещённый сегмент или совпал с glob."""
    import fnmatch
    normalized = path.replace("\\", "/")
    for pattern in deny:
        if fnmatch.fnmatch(normalized, pattern) or fnmatch.fnmatch(os.path.basename(normalized), pattern):
            return True
        if f"/{pattern}/" in f"/{normalized}/":
            return True
    return False


def _read_list(list_file: str) -> list:
    try:
        lines = Path(list_file).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [ln.strip() for ln in lines
            if ln.strip() and not ln.strip().startswith("#")]


def discover(paths, cfg) -> list:
    """Собрать документы корпуса. `paths` — список путей или None (тогда corpus.list).

    `cfg` — CorpusConfig (или RagConfig: тогда берётся cfg.corpus).
    """
    root = Path(".")
    corpus_cfg = getattr(cfg, "corpus", cfg)
    if paths is None:
        paths = _read_list(corpus_cfg.list_file)
    docs = []
    for rel in paths:
        rel = rel.strip()
        if not rel or _denied(rel, corpus_cfg.deny):
            continue
        full = root / rel
        if not full.is_file():
            continue
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        stat = full.stat()
        docs.append({
            "doc_id": _sha1(rel),
            "source": rel,
            "title": full.stem,
            "text": text,
            "sha1": _sha1(text),
            "mtime": stat.st_mtime,
            "content_type": _content_type(rel),
        })
        if len(docs) >= corpus_cfg.max_docs:
            break
    return docs


def delta(docs, known_docs) -> dict:
    """Сравнить документы с известными (по sha1). known_docs: {doc_id: sha1}."""
    added, updated, skipped = [], [], []
    seen = set()
    for doc in docs:
        seen.add(doc["doc_id"])
        known = known_docs.get(doc["doc_id"])
        if known is None:
            added.append(doc)
        elif known != doc["sha1"]:
            updated.append(doc)
        else:
            skipped.append(doc)
    removed = [doc_id for doc_id in known_docs if doc_id not in seen]
    return {"added": added, "updated": updated, "removed": removed, "skipped": skipped}