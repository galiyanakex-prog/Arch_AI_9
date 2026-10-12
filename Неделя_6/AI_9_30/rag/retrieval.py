# -*- coding: utf-8 -*-
"""Гибридный ретривер (этап 6, R4).

Три режима:
  * `bm25`   — лексический поиск (BM25);
  * `dense`  — косинус по векторам;
  * `hybrid` — BM25 top-50 ⊕ dense top-50 → RRF (k=60) → лексический реранк →
               MMR (λ=0.7) → top-k с ограничением ≤2 чанка на документ.

Объяснимость: в `Hit.scores` лежат `bm25_rank`, `dense_rank`, `rrf`, `rerank` —
видно, почему чанк попал в выдачу.
"""
from __future__ import annotations

import argparse
import math

from rag.rerank import LexicalReranker
from rag.types import Hit


class Retriever:
    def __init__(self, index, cfg, embedder=None):
        self.index = index
        self.cfg = cfg
        self.embedder = embedder
        self.reranker = LexicalReranker()

    # ---------- вспомогательное ----------
    def _make_hit(self, chunk_idx, score, scores, source_query=""):
        chunk = self.index.chunks[chunk_idx]
        parent_text = ""
        if chunk.parent_id:
            for other in self.index.chunks:
                if other.chunk_id == chunk.parent_id:
                    parent_text = other.text
                    break
        return Hit(
            chunk_id=chunk.chunk_id, doc_id=chunk.doc_id, source=chunk.source,
            title=chunk.title, section=chunk.section, text=chunk.text,
            score=score, scores=scores, source_query=source_query,
            parent_text=parent_text)

    def _apply_filters(self, hits, filters):
        if not filters:
            return hits
        import fnmatch
        result = []
        for hit in hits:
            if "source" in filters and not fnmatch.fnmatch(hit.source, filters["source"]):
                continue
            if "content_type" in filters:
                chunk = self._chunk_of(hit)
                if chunk is None or chunk.content_type != filters["content_type"]:
                    continue
            if "section" in filters and not hit.section.startswith(filters["section"]):
                continue
            result.append(hit)
        return result

    def _chunk_of(self, hit):
        for chunk in self.index.chunks:
            if chunk.chunk_id == hit.chunk_id:
                return chunk
        return None

    def _limit_per_doc(self, hits, max_per_doc):
        counts = {}
        result = []
        for hit in hits:
            count = counts.get(hit.doc_id, 0)
            if count >= max_per_doc:
                continue
            counts[hit.doc_id] = count + 1
            result.append(hit)
        return result

    def _apply_threshold(self, hits, threshold):
        """Отсечь кандидатов ниже порога (часть 2 Задание.txt).

        Порог — по **косинусной близости** запроса и чанка (`scores["sim"]`,
        0..1, абсолютная и сопоставимая между запросами). Если dense-сигнала нет
        (режим `bm25`), нормируем RRF-скор на лучший кандидат. threshold <= 0 →
        фильтр выключен. Значение близости дублируется в `scores["norm"]`.
        """
        if not hits or threshold <= 0:
            return hits
        top = max(hit.score for hit in hits) or 1.0
        kept = []
        for hit in hits:
            sim = hit.scores.get("sim")
            if sim is None:
                sim = hit.score / top
            hit.scores["norm"] = round(sim, 4)
            if sim >= threshold:
                kept.append(hit)
        return kept

    def _annotate_sim(self, hits, vector):
        """Записать косинусную близость каждого хита к запросу в scores["sim"]."""
        for hit in hits:
            idx = self._index_of(hit)
            if idx is None or not self.index.vectors:
                continue
            hit.scores["sim"] = round(self._cosine(vector, self.index.vectors[idx]), 4)
        return hits

    @staticmethod
    def _cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(x * x for x in b)) or 1.0
        return dot / (na * nb)

    # ---------- фьюжн ----------
    def _rrf(self, rank_lists, rrf_k, weights=None):
        """Reciprocal Rank Fusion: score = Σ w_i / (rrf_k + rank).

        Веса отражают надёжность ретриверов (этап 7): dense — основной bi-encoder,
        BM25 — вспомогательный. Без весов (weights=None) — классический RRF.
        """
        weights = weights or [1.0] * len(rank_lists)
        fused = {}
        for weight, ranks in zip(weights, rank_lists):
            for rank, chunk_idx in enumerate(ranks):
                fused[chunk_idx] = fused.get(chunk_idx, 0.0) + weight / (rrf_k + rank + 1)
        return sorted(fused.items(), key=lambda kv: kv[1], reverse=True)

    def _mmr(self, hits, k, lam):
        """Maximal Marginal Relevance: штраф за близость к уже выбранным.

        Релевантность берётся из ПОРЯДКА списка (он уже отсортирован реранком),
        а не из RRF-скора: иначе MMR затирает выигрыш реранка. Позиционная
        релевантность нормирована к [0,1] и сопоставима с косинусом (0..1).
        """
        if not hits:
            return []
        n = len(hits)
        relevance = {id(hit): (n - pos) / n for pos, hit in enumerate(hits)}
        selected = []
        candidates = list(hits)
        while candidates and len(selected) < k:
            best, best_score = None, -math.inf
            for hit in candidates:
                rel = relevance[id(hit)]
                if selected:
                    max_sim = max(self._similarity(hit, s) for s in selected)
                else:
                    max_sim = 0.0
                score = lam * rel - (1 - lam) * max_sim
                if score > best_score:
                    best, best_score = hit, score
            selected.append(best)
            candidates.remove(best)
        return selected

    def _similarity(self, a, b):
        """Косинус по векторам чанков (если есть), иначе — по токенам."""
        idx_a = self._index_of(a)
        idx_b = self._index_of(b)
        if idx_a is not None and idx_b is not None and self.index.vectors:
            va, vb = self.index.vectors[idx_a], self.index.vectors[idx_b]
            dot = sum(x * y for x, y in zip(va, vb))
            na = math.sqrt(sum(x * x for x in va)) or 1.0
            nb = math.sqrt(sum(x * x for x in vb)) or 1.0
            return dot / (na * nb)
        return 0.0

    def _index_of(self, hit):
        for i, chunk in enumerate(self.index.chunks):
            if chunk.chunk_id == hit.chunk_id:
                return i
        return None

    # ---------- поиск ----------
    def search(self, query: str, k: int = 5, mode: str = None, filters=None,
               threshold: float = None) -> list:
        if not query or not query.strip():
            raise ValueError("пустой запрос: нечего искать")
        mode = mode or self.cfg.retrieval.mode
        candidate_k = self.cfg.retrieval.candidate_k
        rrf_k = self.cfg.retrieval.rrf_k
        lam = self.cfg.retrieval.mmr_lambda
        max_per_doc = self.cfg.retrieval.max_chunks_per_doc
        if threshold is None:
            threshold = self.cfg.retrieval.threshold

        if mode == "bm25":
            ranked = self.index.search_bm25(query, candidate_k)
            hits = [self._make_hit(i, s, {"bm25_rank": r}) for r, (i, s) in enumerate(ranked)]
        elif mode == "dense":
            if self.embedder is None:
                raise ValueError("режим dense требует embedder")
            vector = self.embedder.embed([query])[0]
            ranked = self.index.search_dense(vector, candidate_k)
            hits = [self._make_hit(i, s, {"dense_rank": r}) for r, (i, s) in enumerate(ranked)]
            self._annotate_sim(hits, vector)
        elif mode == "hybrid":
            bm25 = self.index.search_bm25(query, candidate_k)
            if self.embedder is None:
                raise ValueError("режим hybrid требует embedder")
            vector = self.embedder.embed([query])[0]
            dense = self.index.search_dense(vector, candidate_k)
            bm25_rank = {i: r for r, (i, _) in enumerate(bm25)}
            dense_rank = {i: r for r, (i, _) in enumerate(dense)}
            weights = [self.cfg.retrieval.rrf_weight_bm25, self.cfg.retrieval.rrf_weight_dense]
            fused = self._rrf([[i for i, _ in bm25], [i for i, _ in dense]], rrf_k, weights)
            hits = [self._make_hit(i, s, {
                "bm25_rank": bm25_rank.get(i), "dense_rank": dense_rank.get(i),
                "rrf": s}) for i, s in fused]
            self._annotate_sim(hits, vector)
            hits = self.reranker.rerank(query, hits)
            for r, hit in enumerate(hits):
                hit.scores["rerank"] = r
            # Дедуп ДО MMR: иначе MMR выбирает k из пула, где один документ занимает
            # несколько слотов, и релевантный чанк вытесняется повторами (проверено
            # на golden-датасете: 0.708 → 0.792).
            pool = self._limit_per_doc(hits[:self.cfg.rerank.candidates], max_per_doc)
            hits = self._mmr(pool, k, lam)
        else:
            raise ValueError(f"неизвестный режим ретривера: {mode}")

        hits = self._apply_filters(hits, filters)
        hits = self._limit_per_doc(hits, max_per_doc)
        hits = self._apply_threshold(hits, threshold)
        return hits[:k]


def _main():
    from rag.config import RagConfig
    from rag.embedding import make_embedder
    from rag.index import RagIndex

    parser = argparse.ArgumentParser(description="RAG-поиск (этап 6)")
    parser.add_argument("--query", required=True)
    parser.add_argument("--mode", default="hybrid", choices=["bm25", "dense", "hybrid"])
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--index", default=None)
    args = parser.parse_args()

    cfg = RagConfig.default()
    index_dir = args.index or cfg.index_dir
    index = RagIndex.load(index_dir, cfg)
    embedder = make_embedder(cfg.embedding) if args.mode in ("dense", "hybrid") else None
    retriever = Retriever(index, cfg, embedder)
    hits = retriever.search(args.query, k=args.k, mode=args.mode)
    print(f"Запрос: {args.query!r}  режим={args.mode}  k={args.k}  хитов={len(hits)}")
    for rank, hit in enumerate(hits, 1):
        print(f"\n[{rank}] {hit.source}  section={hit.section!r}")
        print(f"    chunk_id={hit.chunk_id}  score={hit.score:.4f}  scores={hit.scores}")
        print(f"    {hit.text[:160].replace(chr(10), ' ')}…")


if __name__ == "__main__":
    _main()