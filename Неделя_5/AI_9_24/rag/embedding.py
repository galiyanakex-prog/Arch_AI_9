# -*- coding: utf-8 -*-
"""Эмбеддеры (этап 4, R2).

Протокол `Embedder`: `dim`, `model_id`, `embed(texts) -> list[list[float]]`.

Реализации:
  * `HashingEmbedder` — дефолт, 0 зависимостей: char 3–5-граммы → blake2b → dim 256
    → L2-норма. Детерминирован между запусками и машинами.
  * `OllamaEmbedder` — живой: POST /api/embed, только localhost, батчи, retry.
  * `FakeEmbedder` — детерминированный по хэшу текста (тесты).
  * `SentenceTransformerEmbedder` — заглушка: бросает RagDependencyError.

Деградация: Ollama недоступен → предупреждение + HashingEmbedder (не падение).
"""
from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.error
import urllib.request
from pathlib import Path

from rag.config import RagDependencyError

_ALLOWED_URL_PREFIXES = ("http://127.0.0.1", "http://localhost")


class Embedder:
    """Протокол эмбеддера."""

    dim: int = 0
    model_id: str = ""

    def embed(self, texts: list) -> list:
        raise NotImplementedError


def _l2_normalize(vector: list) -> list:
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0:
        return vector
    return [x / norm for x in vector]


class HashingEmbedder(Embedder):
    """Хэширующий эмбеддер: char n-граммы → подписанный blake2b-хэш → L2-норма."""

    def __init__(self, dim: int = 256, ngrams=(3, 4, 5)):
        self.dim = dim
        self.ngrams = ngrams
        self.model_id = f"hashing-{dim}"

    def _embed_one(self, text: str) -> list:
        vector = [0.0] * self.dim
        text = (text or "").lower()
        for n in self.ngrams:
            for i in range(len(text) - n + 1):
                gram = text[i:i + n]
                digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
                value = int.from_bytes(digest, "big")
                index = value % self.dim
                sign = 1.0 if (value >> 63) & 1 else -1.0
                vector[index] += sign
        return _l2_normalize(vector)

    def embed(self, texts: list) -> list:
        return [self._embed_one(t) for t in texts]


class FakeEmbedder(Embedder):
    """Детерминированный эмбеддер для тестов: вектор из хэша текста."""

    def __init__(self, dim: int = 16):
        self.dim = dim
        self.model_id = f"fake-{dim}"

    def _embed_one(self, text: str) -> list:
        digest = hashlib.sha256((text or "").encode("utf-8")).digest()
        raw = [digest[i % len(digest)] / 255.0 for i in range(self.dim)]
        return _l2_normalize(raw)

    def embed(self, texts: list) -> list:
        return [self._embed_one(t) for t in texts]


class OllamaEmbedder(Embedder):
    """Живой эмбеддер через локальный сервис Ollama (только localhost)."""

    def __init__(self, url: str, model: str, dim: int, batch_size: int = 32,
                 timeout: int = 30, retries: int = 2, keep_alive: str = "10m",
                 log=None):
        if not url.lower().startswith(_ALLOWED_URL_PREFIXES):
            raise ValueError(
                f"OllamaEmbedder: url обязан быть локальным {_ALLOWED_URL_PREFIXES}, "
                f"получено: {url}")
        self.url = url.rstrip("/")
        self.model = model
        self.dim = dim
        self.batch_size = batch_size
        self.timeout = timeout
        self.retries = retries
        self.keep_alive = keep_alive
        self.model_id = f"ollama:{model}"
        self.log = log or (lambda line: None)

    def _post(self, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.url}/api/embed", data=data,
            headers={"Content-Type": "application/json"})
        last_error = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                    return json.load(resp)
            except (urllib.error.URLError, OSError, json.JSONDecodeError) as error:
                last_error = error
                if attempt < self.retries:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"OllamaEmbedder: не удалось получить эмбеддинги: {last_error}")

    def embed(self, texts: list) -> list:
        vectors = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            data = self._post({"model": self.model, "input": batch,
                               "keep_alive": self.keep_alive})
            vectors.extend(data["embeddings"])
        return vectors


class SentenceTransformerEmbedder(Embedder):
    """Заглушка: sentence-transformers сознательно не устанавливаем в этой ревизии."""

    def __init__(self, *args, **kwargs):
        raise RagDependencyError(
            "требуется pip install sentence-transformers — в этой ревизии "
            "сознательно не устанавливаем")


class EmbeddingCache:
    """Кэш эмбеддингов: sha1(text) → vector. Перестроение не переэмбедит неизменное."""

    def __init__(self, path: str, log=None):
        self.path = Path(path)
        self.log = log or (lambda line: None)
        self._data = {}
        self._load()

    def _load(self):
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._data = {}

    def get(self, sha1: str):
        return self._data.get(sha1)

    def put(self, sha1: str, vector: list):
        self._data[sha1] = vector

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data), encoding="utf-8")

    def stats(self) -> dict:
        return {"entries": len(self._data), "path": str(self.path)}


def make_embedder(cfg, log=None):
    """Выбор эмбеддера по cfg.provider с деградацией на HashingEmbedder."""
    log = log or (lambda line: None)
    provider = cfg.provider
    if provider == "hashing":
        return HashingEmbedder(dim=cfg.hashing_dim)
    if provider == "fake":
        return FakeEmbedder()
    if provider == "sentence-transformers":
        return SentenceTransformerEmbedder()
    if provider == "ollama":
        embedder = OllamaEmbedder(
            url=cfg.url, model=cfg.model, dim=cfg.dim, batch_size=cfg.batch_size,
            timeout=cfg.timeout_seconds, retries=cfg.retries, keep_alive=cfg.keep_alive,
            log=log)
        try:
            embedder.embed(["проверка доступности"])
            return embedder
        except RuntimeError as error:
            log(f"[RAG] Ollama недоступен ({error}) — деградация на HashingEmbedder")
            return HashingEmbedder(dim=cfg.hashing_dim)
    raise ValueError(f"неизвестный провайдер эмбеддингов: {provider}")