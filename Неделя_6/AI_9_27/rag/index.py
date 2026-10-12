# -*- coding: utf-8 -*-
"""Плоский индекс BM25 + dense и персистентность (этап 5, R3).

Артефакты в `rag/index/`:
  * `postings.json` — термин → [[chunk_idx, tf], …] + df;
  * `vectors.bin`   — array('f'), row-major, dim фиксирован;
  * `chunks.json`   — метаданные чанков;
  * `meta.json`     — версии/параметры/docs (для дельты и ребилда).

Запись — только `tmp + os.replace` (атомарно). При загрузке meta сверяется с
конфигом: расхождение model_id/dim/chunker_version/strategy → полный ребилд.
"""
from __future__ import annotations

import array
import hashlib
import json
import math
import os
import time
from pathlib import Path

from rag import corpus as corpus_mod
from rag.chunking import chunk_document
from rag.text import STOPWORDS, stem, tokenize
from rag.types import Chunk, DocMeta, IngestReport

CHUNKER_VERSION = "chunk-v1"


def _sha1(text: str) -> str:
    import hashlib
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


class RagIndex:
    """Индекс: BM25-постинги + dense-векторы + метаданные чанков."""

    def __init__(self, cfg=None):
        self.cfg = cfg
        self.chunks: list = []                 # list[Chunk]
        self.postings: dict = {}               # term -> [[chunk_idx, tf], ...]
        self.df: dict = {}                     # term -> document frequency
        self.vectors: list = []                # list[list[float]]
        self.dim: int = 0
        self.meta: dict = {}                   # {model_id, dim, chunker_version, strategy, docs}
        self._doc_data: dict = {}              # doc_id -> {"chunks": [...], "vectors": [...]}
        self._avgdl: float = 0.0

    # ---------- сборка ----------
    def _tokenize_chunk(self, text: str) -> list:
        return [stem(t) for t in tokenize(text) if t not in STOPWORDS]

    def _rebuild_postings(self):
        self.postings = {}
        self.df = {}
        total_len = 0
        for idx, chunk in enumerate(self.chunks):
            tokens = self._tokenize_chunk(chunk.text)
            total_len += len(tokens)
            tf = {}
            for token in tokens:
                tf[token] = tf.get(token, 0) + 1
            for term, count in tf.items():
                self.postings.setdefault(term, []).append([idx, count])
                self.df[term] = self.df.get(term, 0) + 1
        self._avgdl = (total_len / len(self.chunks)) if self.chunks else 0.0

    def _embed_chunks(self, chunks, embedder, cache):
        """Вернуть (vectors, embed_calls). Кэш по sha1 избавляет от повторных вызовов."""
        vectors = [None] * len(chunks)
        pending, pending_idx = [], []
        for i, chunk in enumerate(chunks):
            cached = cache.get(chunk.sha1) if cache else None
            if cached is not None:
                vectors[i] = cached
            else:
                pending.append(chunk.text)
                pending_idx.append(i)
        embed_calls = len(pending)
        if pending:
            fresh = embedder.embed(pending)
            for i, vector in zip(pending_idx, fresh):
                vectors[i] = vector
                if cache:
                    cache.put(chunks[i].sha1, vector)
        return vectors, embed_calls

    def build(self, chunks, embedder, cache=None):
        """Полная сборка из готовых чанков."""
        self.chunks = list(chunks)
        self.vectors, _ = self._embed_chunks(self.chunks, embedder, cache)
        self.dim = embedder.dim
        self._rebuild_postings()
        self._doc_data = {}
        for chunk, vector in zip(self.chunks, self.vectors):
            entry = self._doc_data.setdefault(chunk.doc_id, {"chunks": [], "vectors": []})
            entry["chunks"].append(chunk)
            entry["vectors"].append(vector)
        self.meta = {
            "model_id": embedder.model_id,
            "dim": self.dim,
            "chunker_version": CHUNKER_VERSION,
            "strategy": self.cfg.chunking.strategy if self.cfg else "",
            "docs": {},
        }
        return self

    def ingest(self, docs, cfg, embedder, cache=None):
        """Инкрементальная сборка: неизменённые документы не переэмбедятся."""
        started = time.time()
        self.cfg = cfg
        known = {doc_id: d["sha1"] for doc_id, d in self.meta.get("docs", {}).items()}
        diff = corpus_mod.delta(docs, known)

        # Сохраняем данные неизменённых документов.
        kept = {doc["doc_id"]: self._doc_data[doc["doc_id"]]
                for doc in diff["skipped"] if doc["doc_id"] in self._doc_data}

        embed_calls = 0
        new_doc_data = dict(kept)
        for doc in diff["added"] + diff["updated"]:
            chunks = chunk_document(doc, cfg.chunking, cfg.chunking.strategy)
            vectors, calls = self._embed_chunks(chunks, embedder, cache)
            embed_calls += calls
            new_doc_data[doc["doc_id"]] = {"chunks": chunks, "vectors": vectors}

        # Собираем плоские списки.
        self.chunks, self.vectors = [], []
        docs_meta = {}
        for doc in docs:
            doc_id = doc["doc_id"]
            if doc_id not in new_doc_data:
                continue
            entry = new_doc_data[doc_id]
            self.chunks.extend(entry["chunks"])
            self.vectors.extend(entry["vectors"])
            docs_meta[doc_id] = DocMeta(
                doc_id=doc_id, source=doc["source"], sha1=doc["sha1"],
                mtime=doc["mtime"], n_chunks=len(entry["chunks"]),
                content_type=doc["content_type"]).to_dict()

        self._doc_data = new_doc_data
        self.dim = embedder.dim
        self._rebuild_postings()
        self.meta = {
            "model_id": embedder.model_id,
            "dim": self.dim,
            "chunker_version": CHUNKER_VERSION,
            "strategy": cfg.chunking.strategy,
            "docs": docs_meta,
        }
        return IngestReport(
            added=len(diff["added"]), updated=len(diff["updated"]),
            removed=len(diff["removed"]), skipped=len(diff["skipped"]),
            chunks=len(self.chunks), seconds=round(time.time() - started, 3),
            embed_calls=embed_calls)

    # ---------- поиск ----------
    def search_bm25(self, query: str, k: int) -> list:
        """BM25 (k1, b из конфига). Возврат: [(chunk_idx, score), …] по убыванию."""
        if not self.chunks:
            return []
        k1 = self.cfg.retrieval.bm25.k1 if self.cfg else 1.2
        b = self.cfg.retrieval.bm25.b if self.cfg else 0.75
        n = len(self.chunks)
        scores = {}
        for term in self._tokenize_chunk(query):
            if term not in self.postings:
                continue
            df = self.df[term]
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            for chunk_idx, tf in self.postings[term]:
                dl = len(self._tokenize_chunk(self.chunks[chunk_idx].text))
                denom = tf + k1 * (1 - b + b * dl / (self._avgdl or 1))
                scores[chunk_idx] = scores.get(chunk_idx, 0.0) + idf * tf * (k1 + 1) / denom
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return ranked[:k]

    def search_dense(self, vector, k: int) -> list:
        """Косинус по vectors (плоский перебор). Возврат: [(chunk_idx, score), …]."""
        if not self.vectors:
            return []
        norm_q = math.sqrt(sum(x * x for x in vector)) or 1.0
        scored = []
        for idx, vec in enumerate(self.vectors):
            dot = sum(a * b for a, b in zip(vector, vec))
            norm_v = math.sqrt(sum(x * x for x in vec)) or 1.0
            scored.append((idx, dot / (norm_q * norm_v)))
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored[:k]

    # ---------- персистентность ----------
    def save(self, path: str):
        directory = Path(path)
        directory.mkdir(parents=True, exist_ok=True)
        self._atomic_write(directory / "postings.json",
                           json.dumps({"postings": self.postings, "df": self.df}))
        self._atomic_write(directory / "chunks.json",
                           json.dumps([c.to_dict() for c in self.chunks], ensure_ascii=False))
        self._atomic_write(directory / "meta.json",
                           json.dumps(self.meta, ensure_ascii=False))
        flat = array.array("f")
        for vec in self.vectors:
            flat.extend(vec)
        tmp = directory / "vectors.bin.tmp"
        with open(tmp, "wb") as handle:
            flat.tofile(handle)
        os.replace(tmp, directory / "vectors.bin")
        return str(directory)

    def _atomic_write(self, path: Path, text: str):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str, cfg=None):
        """Загрузить индекс. Битый postings.json → пустой индекс (ребилд вызывающим)."""
        directory = Path(path)
        index = cls(cfg)
        try:
            meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
            chunks_raw = json.loads((directory / "chunks.json").read_text(encoding="utf-8"))
            postings_raw = json.loads((directory / "postings.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            print(f"[RAG] индекс {path} повреждён ({error}) — требуется ребилд")
            return index
        index.meta = meta
        index.dim = meta.get("dim", 0)
        index.chunks = [Chunk(**c) for c in chunks_raw]
        index.postings = postings_raw.get("postings", {})
        index.df = postings_raw.get("df", {})
        # Векторы.
        try:
            flat = array.array("f")
            with open(directory / "vectors.bin", "rb") as handle:
                flat.fromfile(handle, os.path.getsize(directory / "vectors.bin") // 4)
            dim = index.dim or 1
            index.vectors = [list(flat[i:i + dim]) for i in range(0, len(flat), dim)]
        except (OSError, ValueError):
            index.vectors = []
        # Восстанавливаем _doc_data и _avgdl.
        index._doc_data = {}
        for chunk, vector in zip(index.chunks, index.vectors):
            entry = index._doc_data.setdefault(chunk.doc_id, {"chunks": [], "vectors": []})
            entry["chunks"].append(chunk)
            entry["vectors"].append(vector)
        total = sum(len(index._tokenize_chunk(c.text)) for c in index.chunks)
        index._avgdl = (total / len(index.chunks)) if index.chunks else 0.0
        return index

    def needs_rebuild(self, cfg, embedder) -> bool:
        """Расхождение версий/параметров → полный ребилд."""
        if not self.meta:
            return True
        return (self.meta.get("model_id") != embedder.model_id
                or self.meta.get("dim") != embedder.dim
                or self.meta.get("chunker_version") != CHUNKER_VERSION
                or self.meta.get("strategy") != cfg.chunking.strategy)

    def stats(self) -> dict:
        size = 0
        if self.cfg:
            directory = Path(self.cfg.index_dir)
            if directory.is_dir():
                size = sum(f.stat().st_size for f in directory.glob("*") if f.is_file())
        return {
            "n_docs": len(self.meta.get("docs", {})),
            "n_chunks": len(self.chunks),
            "dim": self.dim,
            "model_id": self.meta.get("model_id", ""),
            "size_bytes": size,
        }

    # ---------- версия и mtime (для кэша поиска, этап 10) ----------
    def version(self) -> str:
        """Отпечаток состояния индекса: параметры сборки + sha1 всех документов.

        Меняется при ребилде, смене модели/стратегии или правке любого документа —
        ключ кэша поиска обязан включать его, иначе выдача «протухает».
        """
        parts = [
            str(self.meta.get("model_id", "")),
            str(self.meta.get("dim", "")),
            str(self.meta.get("chunker_version", "")),
            str(self.meta.get("strategy", "")),
        ]
        for doc_id in sorted(self.meta.get("docs", {})):
            parts.append(f"{doc_id}:{self.meta['docs'][doc_id].get('sha1', '')}")
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    def mtimes(self) -> dict:
        """{doc_id: mtime} — для инвалидации кэша по времени правки файлов."""
        return {doc_id: meta.get("mtime", 0.0)
                for doc_id, meta in self.meta.get("docs", {}).items()}