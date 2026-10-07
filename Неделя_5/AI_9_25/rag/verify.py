# -*- coding: utf-8 -*-
"""Проверка формата ответа на 10 вопросах (часть 3 Задание.txt, этап 9, R7).

Требование части 3: ответ обязан возвращать (1) текст, (2) источники, (3) цитаты;
проверить на 10 вопросах — есть ли источники/цитаты в каждом ответе и совпадает
ли смысл ответа с цитатами. `verify_answers` прогоняет вопросы через
`RagService.answer`, считает метрики и пишет Markdown-отчёт.

CLI:
  python -m rag.verify --queries rag/datasets/queries.jsonl --k 5 \
      --report dev/logs_reports/stages/rag_verify_10q.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag.config import RagConfig


def verify_answers(cfg, queries, k: int = 5, llm=None, limit: int = 10) -> dict:
    """Прогнать вопросы, собрать метрики формата (источники/цитаты/смысл).

    Возвращает dict: {"rows": [...], "summary": {...}}.
    llm — callable(messages)->str (DI); без LLM текст ответа — заглушка, но
    формат источников/цитат проверяется по-настоящему.
    """
    from rag.service import RagService
    from rag.grounding import ground
    query_list = queries if isinstance(queries, list) else _load(queries)
    query_list = query_list[:limit]
    svc = RagService(cfg)
    rows = []
    for q in query_list:
        ans = svc.answer(q["query"], use_rag=True, k=k, llm=llm)
        # Смысл ответа vs цитаты: grounding по цитатам (если они есть).
        quote_hits = _quote_hits(ans)
        report = ground(ans.text, quote_hits, cfg) if quote_hits else None
        rows.append({
            "id": q.get("id", ""),
            "query": q["query"],
            "verdict": ans.verdict,
            "n_sources": len(ans.sources),
            "n_quotes": len(ans.quotes),
            "has_sources": len(ans.sources) > 0,
            "has_quotes": len(ans.quotes) > 0,
            "meaning_match": (report.verdict in ("ok", "partial")) if report else False,
            "answer_len": len(ans.text or ""),
        })
    n = len(rows)
    summary = {
        "n": n,
        "sources_ok": sum(r["has_sources"] for r in rows),
        "quotes_ok": sum(r["has_quotes"] for r in rows),
        "meaning_ok": sum(r["meaning_match"] for r in rows),
        "insufficient": sum(r["verdict"] == "insufficient" for r in rows),
    }
    return {"rows": rows, "summary": summary}


def _quote_hits(ans):
    """Превратить цитаты Answer в лёгкие объекты с .text/.chunk_id/.doc_id/.source."""
    from rag.types import Hit
    hits = []
    for q in ans.quotes:
        hits.append(Hit(chunk_id=q.chunk_id, doc_id=q.chunk_id.split("#")[0],
                        source=q.source, title="", section="", text=q.text, score=0.0))
    return hits


# ---------------------------------------------------------------------------
# Метрика стабильности (Ревизия 7.1, этап 2, решение №13): N прогонов одного
# набора вопросов → среднее / разброс (min–max, σ). Недетерминизм LLM (разный
# «смысл» на одних и тех же вопросах) становится виден явно, а не как
# противоречие между двумя отчётами.
# ---------------------------------------------------------------------------
def verify_stability(cfg, queries, k: int = 5, llm=None, limit: int = 10,
                     runs: int = 1) -> dict:
    """Прогнать `verify_answers` `runs` раз и агрегировать метрики.

    Возвращает {"runs": N, "per_run": [...], "metrics": {имя: {mean,min,max,std}}}.
    При `runs=1` — один прогон (обратная совместимость).
    """
    runs = max(1, int(runs))
    per_run = [verify_answers(cfg, queries, k=k, llm=llm, limit=limit)
               for _ in range(runs)]
    keys = ("sources_ok", "quotes_ok", "meaning_ok", "insufficient")
    metrics = {}
    for key in keys:
        values = [r["summary"][key] for r in per_run]
        metrics[key] = _aggregate(values)
    return {"runs": runs, "per_run": per_run, "metrics": metrics,
            "n": per_run[0]["summary"]["n"]}


def _aggregate(values: list) -> dict:
    """Среднее / min–max / σ по списку чисел (σ — генеральное, по совокупности)."""
    n = len(values)
    mean = sum(values) / n if n else 0.0
    variance = sum((v - mean) ** 2 for v in values) / n if n else 0.0
    return {"mean": mean, "min": min(values) if values else 0,
            "max": max(values) if values else 0, "std": variance ** 0.5}


def render_stability(result: dict) -> str:
    """Отчёт стабильности: метрика × (среднее / min–max / σ)."""
    n = result["n"]
    lines = ["# Стабильность формата ответа RAG (N прогонов, часть 3)", ""]
    lines.append(f"Прогонов: **{result['runs']}** · вопросов: **{n}**")
    lines.append("")
    lines.append("| Метрика | Среднее | min–max | σ |")
    lines.append("|---|---|---|---|")
    labels = {"sources_ok": "Источники", "quotes_ok": "Цитаты",
              "meaning_ok": "Смысл=цитаты", "insufficient": "«не знаю»"}
    for key, label in labels.items():
        m = result["metrics"][key]
        lines.append(f"| {label} | {m['mean']:.2f}/{n} | {m['min']}–{m['max']} | "
                     f"{m['std']:.2f} |")
    lines.append("")
    return "\n".join(lines)



def render_report(result: dict) -> str:
    s = result["summary"]
    lines = ["# Проверка формата ответа RAG на 10 вопросах (часть 3)", ""]
    lines.append(f"Источники: **{s['sources_ok']}/{s['n']}** · "
                 f"Цитаты: **{s['quotes_ok']}/{s['n']}** · "
                 f"Смысл совпадает с цитатами: **{s['meaning_ok']}/{s['n']}** · "
                 f"«не знаю»: {s['insufficient']}")
    lines.append("")
    lines.append("| Вопрос | verdict | Источники | Цитаты | Смысл=цитаты | Длина |")
    lines.append("|---|---|---|---|---|---|")
    for r in result["rows"]:
        lines.append(f"| {r['id']} | {r['verdict']} | {r['n_sources']} | "
                     f"{r['n_quotes']} | {'✅' if r['meaning_match'] else '—'} | "
                     f"{r['answer_len']} |")
    lines.append("")
    return "\n".join(lines)


def _load(path) -> list:
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Проверка формата ответа RAG (этап 9)")
    parser.add_argument("--queries", default="rag/datasets/queries.jsonl")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--runs", type=int, default=1,
                        help="число прогонов для метрики стабильности (по умолчанию 1)")
    parser.add_argument("--report", default="dev/logs_reports/stages/rag_verify_10q.md")
    args = parser.parse_args(argv)

    cfg = RagConfig.load("rag/config.json")
    # Живой LLM сюда не пробрасываем: rag/ НЕ импортирует core/ (граница §5).
    # Живой прогон делается внешним скриптом, который передаёт llm=... в verify_answers.
    queries = [q for q in _load(args.queries) if q.get("id", "").startswith("c")]
    if args.runs > 1:
        result = verify_stability(cfg, queries, k=args.k, llm=None,
                                  limit=args.limit, runs=args.runs)
        text = render_stability(result)
    else:
        result = verify_answers(cfg, queries, k=args.k, llm=None, limit=args.limit)
        text = render_report(result)
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(text, encoding="utf-8")
    print(text)
    print(f"Отчёт записан: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
