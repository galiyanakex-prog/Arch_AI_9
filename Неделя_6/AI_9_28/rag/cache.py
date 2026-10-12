# -*- coding: utf-8 -*-
"""Кэш результатов поиска (этап 10, R8).

Зачем: dense-поиск платит вызовом эмбеддера (Ollama), а один и тот же запрос в
сессии повторяется часто (пересборка контекста, повторные вопросы). Кэш убирает
повторную работу, но обязан быть КОРРЕКТНЫМ: устаревшая выдача хуже её отсутствия.

Ключ: sha256(model_id | index_version | norm_query | params | filters).
Значение: список Hit + `expires` (TTL) + `mtimes` затронутых документов. Запись
считается невалидной, если:
  * истёк TTL (`ttl_seconds`);
  * изменился `mtime` любого документа, чьи чанки попали в выдачу (правка файла
    ДО истечения TTL — самый частый источник «протухшего» кэша).

Вытеснение — LRU по `max_entries`. Только stdlib: OrderedDict + hashlib + json.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict

from rag.text import normalize


def make_key(model_id: str, index_version: str, query: str, params: dict,
             filters: dict = None) -> str:
    """Стабильный ключ кэша. norm_query — normalize (регистр/пунктуация не важны)."""
    payload = json.dumps({
        "model_id": model_id,
        "index_version": index_version,
        "query": normalize(query or ""),
        "params": params or {},
        "filters": filters or {},
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SearchCache:
    """LRU + TTL кэш выдач поиска. Потокобезопасность не требуется (один процесс)."""

    def __init__(self, cfg=None, log=None):
        cache_cfg = getattr(cfg, "cache", cfg)
        self.enabled = getattr(cache_cfg, "enabled", True)
        self.max_entries = getattr(cache_cfg, "max_entries", 256)
        self.ttl_seconds = getattr(cache_cfg, "ttl_seconds", 900)
        self.log = log or (lambda line: None)
        self._store: "OrderedDict[str, dict]" = OrderedDict()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.invalidations = 0

    # ---------- доступ ----------
    def get(self, key: str, mtimes: dict = None):
        """Вернуть список Hit или None. Проверяет TTL и mtime затронутых документов."""
        if not self.enabled:
            return None
        entry = self._store.get(key)
        if entry is None:
            self.misses += 1
            return None
        if time.time() > entry["expires"]:
            self._drop(key)
            self.invalidations += 1
            self.misses += 1
            return None
        if mtimes and self._stale(entry, mtimes):
            self._drop(key)
            self.invalidations += 1
            self.misses += 1
            return None
        self._store.move_to_end(key)          # LRU: свежий доступ — в конец
        self.hits += 1
        return entry["hits"]

    def put(self, key: str, hits: list, mtimes: dict = None):
        """Положить выдачу. mtimes — {doc_id: mtime} затронутых документов."""
        if not self.enabled:
            return
        self._store[key] = {
            "hits": list(hits),
            "expires": time.time() + self.ttl_seconds,
            "mtimes": dict(mtimes or {}),
        }
        self._store.move_to_end(key)
        while len(self._store) > self.max_entries:
            self._store.popitem(last=False)   # вытесняем самый старый
            self.evictions += 1

    def clear(self):
        self._store.clear()

    # ---------- вспомогательное ----------
    def _stale(self, entry: dict, mtimes: dict) -> bool:
        """Изменился ли mtime хотя бы одного документа из выдачи."""
        for doc_id, mtime in entry["mtimes"].items():
            current = mtimes.get(doc_id)
            if current is not None and current != mtime:
                return True
        return False

    def _drop(self, key: str):
        self._store.pop(key, None)

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "enabled": self.enabled,
            "entries": len(self._store),
            "max_entries": self.max_entries,
            "ttl_seconds": self.ttl_seconds,
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "invalidations": self.invalidations,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
        }