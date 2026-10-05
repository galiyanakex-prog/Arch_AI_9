# -*- coding: utf-8 -*-
"""Фасад модуля для Kod.py (этап 8, R6) — публичный API §6.1 мастер-плана.

RagService — единственная точка входа для ядра агента: Kod.py/Agent работают
только с этим классом и не лезут в index/retrieval/embedding напрямую.

Границы (мастер-план §5):
  * rag/ НЕ импортирует core/ — форматирование блока живёт здесь, в rag/;
  * индекс и эмбеддер грузятся ЛЕНИВО (первый поиск/индексация), чтобы `--rag`
    без прогона не платил за загрузку;
  * любая ошибка RAG — деградация (пустая выдача), а не падение ответа агента.
"""
from __future__ import annotations

import dataclasses
import time

from rag.cache import SearchCache, make_key
from rag.config import RagConfig
from rag.types import IngestReport


class RagService:
    """Фасад: ingest / search / context_block / stats / compare / evaluate / ground."""

    def __init__(self, cfg: RagConfig = None, log=None):
        self.cfg = (cfg or RagConfig.default()).validate()
        self.log = log or (lambda line: None)
        self._index = None
        self._embedder = None
        self._retriever = None
        self._loaded = False
        self._cache = SearchCache(self.cfg, log=self.log)
        self._latencies: list = []          # кольцевой буфер латентностей поиска (мс)

    # ---------- ленивая загрузка ----------
    def _ensure_index(self):
        """Загрузить индекс с диска (один раз). Пустой/битый → пустой индекс."""
        if self._loaded:
            return self._index
        from rag.index import RagIndex
        self._index = RagIndex.load(self.cfg.index_dir, self.cfg)
        self._loaded = True
        return self._index

    def _ensure_embedder(self):
        if self._embedder is None:
            from rag.embedding import make_embedder
            self._embedder = make_embedder(self.cfg.embedding, log=self.log)
        return self._embedder

    def _ensure_retriever(self):
        if self._retriever is None:
            from rag.retrieval import Retriever
            index = self._ensure_index()
            # Эмбеддер нужен только dense/hybrid; для bm25 не поднимаем Ollama.
            embedder = (self._ensure_embedder()
                        if self.cfg.retrieval.mode in ("dense", "hybrid") else None)
            self._retriever = Retriever(index, self.cfg, embedder)
        return self._retriever

    @property
    def index(self):
        return self._ensure_index()

    # ---------- индексация ----------
    def ingest(self, paths=None) -> IngestReport:
        """Проиндексировать пути (дельтой) и сохранить индекс. paths=None → corpus.list."""
        from rag import corpus as corpus_mod
        from rag.index import RagIndex
        index = self._ensure_index()
        embedder = self._ensure_embedder()
        docs = corpus_mod.discover(paths, self.cfg)
        if index.needs_rebuild(self.cfg, embedder):
            # Расхождение версий/параметров — полный ребилд (инкрементация невалидна).
            index.meta = {}
        report = index.ingest(docs, self.cfg, embedder)
        index.save(self.cfg.index_dir)
        self._retriever = None          # сбросить ретривер: индекс изменился
        self.log(f"[RAG] ingest: +{report.added} ~{report.updated} "
                 f"-{report.removed} ={report.skipped}, чанков {report.chunks} "
                 f"за {report.seconds}s")
        return report

    # ---------- поиск ----------
    def search(self, query: str, k: int = None, mode: str = None,
               filters=None) -> list:
        """Топ-k чанков по запросу. Пустой индекс/ошибка → [] (деградация).

        Кэш (этап 10): ключ включает model_id, версию индекса, нормализованный
        запрос, параметры и фильтры; запись невалидна при истечении TTL или
        изменении mtime затронутых документов. Промах → реальный поиск.
        """
        if not query or not query.strip():
            return []
        k = k or self.cfg.retrieval.final_k
        index = self._ensure_index()
        params = {"k": k, "mode": mode or self.cfg.retrieval.mode}
        key = make_key(index.meta.get("model_id", ""), index.version(), query,
                       params, filters)
        cached = self._cache.get(key, index.mtimes())
        if cached is not None:
            self.log(f"[RAG] кэш: попадание по запросу «{query[:50]}» "
                     f"({len(cached)} ист.)")
            return cached
        started = time.time()
        try:
            retriever = self._ensure_retriever()
            hits = retriever.search(query, k=k, mode=mode, filters=filters)
        except Exception as error:            # RAG не роняет ответ агента
            self.log(f"[RAG] поиск не удался ({type(error).__name__}: {error}) — блок опущен")
            return []
        self._record_latency((time.time() - started) * 1000)
        # В кэш кладём mtime только затронутых документов (по выдаче).
        touched = {h.doc_id: index.mtimes().get(h.doc_id, 0.0) for h in hits}
        self._cache.put(key, hits, touched)
        return hits

    def _record_latency(self, ms: float):
        self._latencies.append(ms)
        if len(self._latencies) > 200:        # кольцевой буфер
            self._latencies = self._latencies[-200:]

    def latency_stats(self) -> dict:
        if not self._latencies:
            return {"p50": 0.0, "p95": 0.0, "n": 0}
        ordered = sorted(self._latencies)
        def pct(p):
            idx = min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1))))
            return round(ordered[idx], 1)
        return {"p50": pct(50), "p95": pct(95), "n": len(ordered)}

    # ---------- multi-query (этап 10) ----------
    def rephrase(self, query: str, llm=None, n: int = 3) -> list:
        """2–4 переформулировки запроса. llm — callable(messages)->str (DI).

        Без LLM (или при ошибке) — детерминированная эвристика: исходный запрос +
        варианты из значимых слов (стемы), чтобы multi-query не падал без модели.
        """
        n = max(2, min(4, n))
        variants = [query]
        if llm is not None:
            try:
                prompt = (
                    f"Переформулируй поисковый запрос {n - 1} разными способами "
                    f"(синонимы, уточнения), по одному на строку, без нумерации:\n{query}")
                text = llm([{"role": "user", "content": prompt}]) or ""
                for line in text.splitlines():
                    line = line.strip(" -•\t")
                    if line and line.lower() != query.lower():
                        variants.append(line)
            except Exception as error:
                self.log(f"[RAG] multi-query: LLM не ответил ({type(error).__name__}) — "
                         "эвристика")
        if len(variants) < 2:
            variants.extend(_heuristic_variants(query, n))
        # Дедуп с сохранением порядка, ограничение n.
        seen, result = set(), []
        for v in variants:
            key = v.strip().lower()
            if key and key not in seen:
                seen.add(key)
                result.append(v.strip())
        return result[:n]

    def search_multi(self, query: str, variants: list = None, k: int = None,
                     mode: str = None, filters=None, llm=None) -> list:
        """Поиск по нескольким переформулировкам + склейка через RRF.

        Каждый вариант ищется отдельно (с кэшем), затем списки сливаются RRF
        (тот же фьюжн, что в гибриде). В Hit.source_query — какая формулировка
        нашла чанк. Дедуп по chunk_id, top-k.
        """
        k = k or self.cfg.retrieval.final_k
        variants = variants or self.rephrase(query, llm=llm)
        retriever = self._ensure_retriever()
        rank_lists, by_id = [], {}
        for variant in variants:
            hits = self.search(variant, k=k, mode=mode, filters=filters)
            for hit in hits:
                if hit.chunk_id not in by_id:
                    # Hit — frozen: помечаем источник формулировки через replace.
                    by_id[hit.chunk_id] = dataclasses.replace(hit, source_query=variant)
            rank_lists.append([hit.chunk_id for hit in hits])
        if not rank_lists:
            return []
        fused = retriever._rrf(rank_lists, self.cfg.retrieval.rrf_k)
        result = []
        for chunk_id, score in fused:
            hit = by_id.get(chunk_id)
            if hit is None:
                continue
            scores = dict(hit.scores)
            scores["multi_rrf"] = round(score, 6)
            result.append(dataclasses.replace(hit, scores=scores))
        return result[:k]

    # ---------- блок промпта ----------
    def context_block(self, query: str = "", k: int = None, budget: int = None,
                      hits: list = None, mode: str = None) -> str:
        """Готовый текст блока [rag] (нумерованные источники + инструкция).

        `hits` передаются извне, чтобы на один запрос был ОДИН поиск (агент уже
        нашёл чанки и кладёт их в last_rag_hits). Иначе — ищем по `query`.
        """
        if hits is None:
            hits = self.search(query, k=k, mode=mode)
        if not hits:
            return ""
        budget = budget or self.cfg.budget.max_rag_tokens
        return _render_block(hits, budget)

    # ---------- статистика ----------
    def stats(self) -> dict:
        """Состояние индекса/модели/эмбеддера/кэша (для /rag stats)."""
        index = self._ensure_index()
        data = index.stats()
        data.update({
            "index_dir": self.cfg.index_dir,
            "strategy": self.cfg.chunking.strategy,
            "mode": self.cfg.retrieval.mode,
            "multi_query": self.cfg.retrieval.multi_query,
            "embedding_provider": self.cfg.embedding.provider,
            "ollama_url": self.cfg.embedding.url,
            "ollama_ready": _ollama_ready(self.cfg.embedding.url),
            "cache": self._cache.stats(),
            "latency": self.latency_stats(),
            "ram_estimate_bytes": _ram_estimate(index),
        })
        return data

    # ---------- метрики и сравнение (тонкие обёртки) ----------
    def evaluate(self, dataset: str = "rag/datasets/queries.jsonl", k: int = 5,
                 mode: str = None):
        from rag.eval import evaluate
        index = self._ensure_index()
        retriever = self._ensure_retriever()
        return evaluate(index, dataset, k=k, retriever=retriever,
                        mode=mode or self.cfg.retrieval.mode)

    def compare(self, strategies=("fixed", "structural"),
                modes=("bm25", "dense", "hybrid"),
                queries: str = "rag/datasets/queries.jsonl", k: int = 5):
        from rag.compare import compare
        return compare(self.cfg, list(strategies), list(modes), queries, k=k)

    # ---------- grounding (этап 9) ----------
    def ground(self, answer: str, hits: list = None, mode: str = None):
        """Проверить опору ответа на источники (решение №4). → GroundingReport.

        hits — чанки, по которым проверяем (агент передаёт last_rag_hits); mode —
        переопределение cfg.grounding.mode (off|warn|strict). mode=off →
        verdict=unchecked без вычислений.
        """
        from rag.grounding import ground
        if hits is None:
            hits = []
        cfg = self.cfg
        if mode and mode != cfg.grounding.mode:
            import dataclasses
            cfg = dataclasses.replace(
                cfg, grounding=dataclasses.replace(cfg.grounding, mode=mode))
        report = ground(answer, hits, cfg)
        self.log(f"[RAG] grounding: verdict={report.verdict} "
                 f"coverage={report.stats.get('coverage_avg', 0)} "
                 f"ссылок={report.stats.get('n_citations', 0)} "
                 f"чисел вне={report.stats.get('n_numbers_missing', 0)}")
        return report

    def grounding_feedback(self, report, answer: str, n_sources: int) -> str:
        """Фидбэк-промпт для ОДНОЙ авто-перегенерации (core/ не импортирует rag/)."""
        from rag.grounding import feedback_prompt
        return feedback_prompt(report, answer, n_sources)

    def grounding_render(self, report) -> str:
        """Человекочитаемый вывод GroundingReport (для /rag check)."""
        from rag.grounding import render_report
        return render_report(report)


# ---------------------------------------------------------------------------
# Форматирование блока [rag] живёт в rag/ (граница: rag/ не импортирует core/).
# Формат совпадает с core.prompt_builder.render_rag — единый вид блока в промте.
# ---------------------------------------------------------------------------
_BLOCK_INSTRUCTIONS = (
    "Инструкции:\n"
    "1. Отвечай по возможности по этим источникам; каждое утверждение помечай "
    "ссылкой вида [doc_id#chunk_id] из списка выше.\n"
    "2. Если в источниках ответа нет — прямо скажи об этом, не выдумывай.\n"
    "3. Источники могут противоречить друг другу — укажи это."
)


def _render_block(hits, budget: int = 1400, max_chars: int = 700) -> str:
    header = "Найденные источники (используй их и ставь ссылки на них):"
    lines = [header]
    used = max(1, len(header) // 4)
    placed = 0
    for num, hit in enumerate(hits, 1):
        ref = f"[{getattr(hit, 'doc_id', '')}#{getattr(hit, 'chunk_id', '')}]"
        where = getattr(hit, "source", "") or ""
        section = getattr(hit, "section", "") or ""
        title = getattr(hit, "title", "") or ""
        fragment = " ".join((getattr(hit, "text", "") or "").split())[:max_chars]
        entry = (f"{num}. {ref} {where}" + (f" · {title}" if title else "")
                 + (f" · раздел: {section}" if section else "")
                 + "\n    " + fragment)
        cost = max(1, len(entry) // 4)
        if used + cost > budget:
            continue
        lines.append(entry)
        used += cost
        placed += 1
    if not placed:
        return ""
    lines.append("")
    lines.append(_BLOCK_INSTRUCTIONS)
    return "\n".join(lines)


def _heuristic_variants(query: str, n: int) -> list:
    """Детерминированные переформулировки без LLM: значимые слова (стемы).

    Нужны, чтобы multi-query работал и без модели (тесты, офлайн). Варианты —
    подмножества значимых слов запроса: расширяют лексический охват BM25.
    """
    from rag.text import STOPWORDS, stem, tokenize
    words = [w for w in tokenize(query) if len(w) >= 3 and w not in STOPWORDS]
    variants = []
    if len(words) >= 2:
        variants.append(" ".join(words))                 # без стоп-слов
        variants.append(" ".join(words[:max(2, len(words) // 2)]))  # ядро запроса
    return variants[:max(0, n - 1)]


def _ram_estimate(index) -> int:
    """Грубая оценка RAM индекса: векторы (float32) + тексты чанков."""
    vectors = len(index.vectors) * (index.dim or 0) * 4
    texts = sum(len(c.text.encode("utf-8")) for c in index.chunks)
    return vectors + texts


def _ollama_ready(url: str) -> bool:
    """Доступен ли локальный Ollama (для /rag stats; не поднимает сервис)."""
    import json
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/tags", timeout=2) as resp:
            json.load(resp)
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False