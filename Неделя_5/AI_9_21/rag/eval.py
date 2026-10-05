# -*- coding: utf-8 -*-
"""Метрики качества retrieval (этап 7, R5).

Метрики: recall@k, precision@k, hit-rate@k, MRR, nDCG@k + латентность p50/p95.
Релевантность: golden-запись `<path>::<symbol>` считается найденной, если в выдаче
есть `Hit` с тем же `source` и вхождением `symbol` в `text`/`section`.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from rag.types import EvalReport


def load_queries(path: str) -> list:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _is_relevant(hit, relevant) -> bool:
    for entry in relevant:
        path, _, symbol = entry.partition("::")
        if hit.source == path and (not symbol or symbol in hit.text or symbol in hit.section):
            return True
    return False


def _dcg(gains) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def evaluate(index, dataset, k: int = 5, retriever=None, mode: str = "hybrid",
             candidate_k: int = 20) -> EvalReport:
    """Прогнать golden-датасет и посчитать метрики.

    `k` — финальная выдача (после реранка); `candidate_k` — стадия retrieval
    («bi-encoder Top-20» по модели куратора N5_audio). Recall на стадии кандидатов
    показывает, не теряет ли ретривер релевантное ДО реранка.
    """
    from rag.retrieval import Retriever

    queries = dataset if isinstance(dataset, list) else load_queries(dataset)
    retriever = retriever or Retriever(index, index.cfg, None)

    recalls, precisions, hit_rates, mrrs, ndcgs = [], [], [], [], []
    recalls_cand = []
    latencies = []
    per_query = []

    for q in queries:
        started = time.time()
        hits = retriever.search(q["query"], k=k, mode=mode)
        latencies.append((time.time() - started) * 1000)

        relevant = q.get("relevant", [])
        flags = [1 if _is_relevant(h, relevant) else 0 for h in hits]
        n_rel = len(relevant) or 1
        # Несколько чанков одного документа могут быть релевантны — recall не > 1.
        found = min(sum(flags), n_rel)

        recall = found / n_rel
        precision = found / len(hits) if hits else 0.0
        hit_rate = 1.0 if found else 0.0
        mrr = next((1.0 / (i + 1) for i, f in enumerate(flags) if f), 0.0)
        ideal = _dcg([1] * min(n_rel, k))
        ndcg = _dcg(flags) / ideal if ideal else 0.0

        # Стадия retrieval: сколько golden-записей попало в top-candidate_k.
        cand_hits = retriever.search(q["query"], k=candidate_k, mode=mode)
        cand_found = sum(1 for e in relevant if any(_is_relevant(h, [e]) for h in cand_hits))
        recall_cand = min(cand_found, n_rel) / n_rel

        recalls.append(recall)
        precisions.append(precision)
        hit_rates.append(hit_rate)
        mrrs.append(mrr)
        ndcgs.append(ndcg)
        recalls_cand.append(recall_cand)
        per_query.append({"id": q.get("id", ""), "recall": recall, "hit_rate": hit_rate,
                          "mrr": mrr, "ndcg": ndcg, "recall_cand": recall_cand})

    def _mean(values):
        return sum(values) / len(values) if values else 0.0

    def _pct(values, p):
        if not values:
            return 0.0
        ordered = sorted(values)
        idx = min(len(ordered) - 1, int(round((p / 100) * (len(ordered) - 1))))
        return ordered[idx]

    return EvalReport(
        k=k,
        metrics={
            "recall@k": round(_mean(recalls), 4),
            "precision@k": round(_mean(precisions), 4),
            "hit_rate@k": round(_mean(hit_rates), 4),
            "mrr": round(_mean(mrrs), 4),
            "ndcg@k": round(_mean(ndcgs), 4),
            f"recall@{candidate_k}": round(_mean(recalls_cand), 4),
        },
        latency_ms={"p50": round(_pct(latencies, 50), 2), "p95": round(_pct(latencies, 95), 2)},
        per_query=tuple(per_query),
        dataset=str(dataset) if not isinstance(dataset, list) else "inline")


def main(argv=None) -> int:
    from rag.config import RagConfig
    from rag.embedding import make_embedder
    from rag.index import RagIndex

    parser = argparse.ArgumentParser(description="RAG-метрики (этап 7)")
    parser.add_argument("--queries", default="rag/datasets/queries.jsonl")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--mode", default="hybrid", choices=["bm25", "dense", "hybrid"])
    parser.add_argument("--index", default=None)
    args = parser.parse_args(argv)

    cfg = RagConfig.default()
    index = RagIndex.load(args.index or cfg.index_dir, cfg)
    embedder = make_embedder(cfg.embedding) if args.mode in ("dense", "hybrid") else None
    report = evaluate(index, args.queries, k=args.k, mode=args.mode)
    print(f"Датасет: {report.dataset}  k={report.k}  mode={args.mode}")
    for name, value in report.metrics.items():
        print(f"  {name:14s} = {value}")
    print(f"  latency p50={report.latency_ms['p50']}ms  p95={report.latency_ms['p95']}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())