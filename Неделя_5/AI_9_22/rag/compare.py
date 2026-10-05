# -*- coding: utf-8 -*-
"""Сравнение стратегий чанкинга (этап 7, R5).

Прямое требование Задание_d21.txt: минимум две стратегии и их сравнение.
Прогоняем S×{bm25,dense,hybrid} на одном корпусе и одном golden-датасете, считаем
метрики, выбираем лучшую конфигурацию и разбираем запросы, где стратегии разошлись.
"""
from __future__ import annotations

import argparse
import dataclasses
from pathlib import Path

from rag.config import RagConfig
from rag.corpus import discover
from rag.embedding import make_embedder
from rag.eval import evaluate, load_queries
from rag.index import RagIndex
from rag.retrieval import Retriever
from rag.types import CompareReport


def _build_index(cfg, strategy, embedder):
    """Собрать индекс для конкретной стратегии чанкинга."""
    local = dataclasses.replace(
        cfg, chunking=dataclasses.replace(cfg.chunking, strategy=strategy))
    index = RagIndex(local)
    index.ingest(discover(None, local.corpus), local, embedder)
    return index


def compare(cfg, strategies, modes, queries, k: int = 5) -> CompareReport:
    """Прогнать все конфигурации и вернуть CompareReport."""
    query_list = queries if isinstance(queries, list) else load_queries(queries)
    embedder = make_embedder(cfg.embedding)

    rows = []
    indexes = {}
    for strategy in strategies:
        index = _build_index(cfg, strategy, embedder)
        indexes[strategy] = index
        for mode in modes:
            retriever = Retriever(index, index.cfg, embedder)
            report = evaluate(index, query_list, k=k, retriever=retriever, mode=mode)
            rows.append({
                "strategy": strategy, "mode": mode,
                "n_chunks": len(index.chunks),
                **report.metrics,
            })

    # Лучшая конфигурация по hit_rate@k, затем по recall@k.
    best_row = max(rows, key=lambda r: (r.get("hit_rate@k", 0), r.get("recall@k", 0)))
    best = f"{best_row['strategy']}/{best_row['mode']}"

    # Разбор расхождений: запросы, где стратегии дали разный hit_rate.
    divergences = _find_divergences(cfg, indexes, embedder, query_list, k)

    verdict = _make_verdict(rows, best_row)
    return CompareReport(
        rows=tuple(rows), best=best, verdict=verdict,
        divergences=tuple(divergences), k=k, model_id=embedder.model_id)


def _find_divergences(cfg, indexes, embedder, queries, k, limit=3):
    """Найти запросы, где стратегии разошлись по попаданию в top-k."""
    from rag.eval import _is_relevant
    divergences = []
    strategies = list(indexes)
    if len(strategies) < 2:
        return divergences
    for q in queries:
        outcomes = {}
        for strategy in strategies:
            index = indexes[strategy]
            retriever = Retriever(index, index.cfg, embedder)
            hits = retriever.search(q["query"], k=k, mode="hybrid")
            outcomes[strategy] = any(_is_relevant(h, q.get("relevant", [])) for h in hits)
        if len(set(outcomes.values())) > 1:
            divergences.append({
                "id": q.get("id", ""), "query": q["query"],
                "outcomes": outcomes,
                "reason": _reason(outcomes),
            })
        if len(divergences) >= limit:
            break
    return divergences


def _reason(outcomes) -> str:
    winners = [s for s, ok in outcomes.items() if ok]
    losers = [s for s, ok in outcomes.items() if not ok]
    return (f"стратегия {winners} нашла релевантный чанк, {losers} — нет "
            "(разное разбиение: обрывок кода / склейка разделов / потеря заголовка)")


def _make_verdict(rows, best_row) -> str:
    hybrid_rows = [r for r in rows if r["mode"] == "hybrid"]
    best_hybrid = max(hybrid_rows, key=lambda r: r.get("hit_rate@k", 0)) if hybrid_rows else None
    parts = [f"Лучшая конфигурация: {best_row['strategy']}/{best_row['mode']} "
             f"(hit-rate@k={best_row.get('hit_rate@k')}, recall@k={best_row.get('recall@k')})."]
    if best_hybrid:
        parts.append(f"Среди гибридных режимов лучшая стратегия — {best_hybrid['strategy']}.")
        # Проверка «гибрид ≥ каждой компоненты» на обеих стадиях (гейт 7→8).
        # Проверяем КАЖДУЮ стратегию, а не только лучшую: иначе проигрыш гибрида
        # на другой стратегии остался бы незамеченным.
        for strategy in dict.fromkeys(r["strategy"] for r in rows):
            hybrid = next((r for r in rows
                           if r["strategy"] == strategy and r["mode"] == "hybrid"), None)
            if hybrid is None:
                continue
            for stage in ("recall@20", "hit_rate@k"):
                comps = [r.get(stage, 0) for r in rows
                         if r["strategy"] == strategy and r["mode"] != "hybrid"]
                if comps:
                    ok = hybrid.get(stage, 0) >= max(comps)
                    parts.append(f"[{strategy}] {stage}: hybrid={hybrid.get(stage)} vs "
                                 f"max(компоненты)={max(comps)} — {'✅' if ok else '❌'}.")
    return " ".join(parts)


def render_report(report: CompareReport) -> str:
    """Markdown-отчёт: таблица «метрика × конфигурация» + вердикт + расхождения."""
    lines = ["# Сравнение стратегий чанкинга (RAG, этап 7)", ""]
    lines.append(f"Модель эмбеддингов: `{report.model_id}`  ·  k = {report.k}")
    lines.append("")
    lines.append("## Таблица «метрика × конфигурация»")
    lines.append("")
    lines.append("| Стратегия | Режим | Чанков | recall@20 | recall@k | precision@k | hit-rate@k | MRR | nDCG@k |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for row in report.rows:
        lines.append(
            f"| {row['strategy']} | {row['mode']} | {row['n_chunks']} | "
            f"{row.get('recall@20')} | {row.get('recall@k')} | {row.get('precision@k')} | "
            f"{row.get('hit_rate@k')} | {row.get('mrr')} | {row.get('ndcg@k')} |")
    lines.append("")
    lines.append("> `recall@20` — стадия retrieval («bi-encoder Top-20» по модели куратора);")
    lines.append("> `hit-rate@k` — стадия после реранка. Гибрид обязан быть не хуже каждой")
    lines.append("> компоненты на обеих стадиях.")
    lines.append("")
    lines.append("## Эффект реранкинга (top-20 → top-k)")
    lines.append("")
    lines.append("| Стратегия | Режим | recall@20 | hit-rate@k | Δ |")
    lines.append("|---|---|---|---|---|")
    for row in report.rows:
        r20 = row.get("recall@20") or 0.0
        hk = row.get("hit_rate@k") or 0.0
        lines.append(f"| {row['strategy']} | {row['mode']} | {r20} | {hk} | {round(hk - r20, 4)} |")
    lines.append("")
    lines.append("## Вердикт")
    lines.append("")
    lines.append(report.verdict)
    lines.append("")
    lines.append("## Разбор расхождений")
    lines.append("")
    if report.divergences:
        for div in report.divergences:
            lines.append(f"- **{div['id']}** «{div['query']}» — {div['reason']}")
    else:
        lines.append("Расхождений между стратегиями не обнаружено.")
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Сравнение стратегий чанкинга (этап 7)")
    parser.add_argument("--corpus", default="rag/datasets/corpus.list")
    parser.add_argument("--queries", default="rag/datasets/queries.jsonl")
    parser.add_argument("--strategies", default="fixed,structural")
    parser.add_argument("--modes", default="bm25,dense,hybrid")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--report", default="dev/logs_reports/stages/rag_chunking_compare.md")
    args = parser.parse_args(argv)

    cfg = RagConfig.default()
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    report = compare(cfg, strategies, modes, args.queries, k=args.k)
    text = render_report(report)
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(text, encoding="utf-8")
    print(text)
    print(f"\nОтчёт записан: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())