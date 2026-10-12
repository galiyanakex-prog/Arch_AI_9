# -*- coding: utf-8 -*-
"""Сравнение стратегий чанкинга (этап 7, R5).

Прямое требование Задание_d21.txt: минимум две стратегии и их сравнение.
Прогоняем S×{bm25,dense,hybrid} на одном корпусе и одном golden-датасете, считаем
метрики, выбираем лучшую конфигурацию и разбираем запросы, где стратегии разошлись.
"""
from __future__ import annotations

import argparse
import dataclasses
import re
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


# ---------------------------------------------------------------------------
# Сравнение РЕЖИМОВ ОТВЕТА (часть 1, этап 7): no_rag | rag | rag_filter |
# rag_filter_rewrite. Отличается от сравнения стратегий чанкинга: здесь метрики
# про ОТВЕТ (попадание must_contain, наличие источников), а не про retrieval.
# ---------------------------------------------------------------------------
ANSWER_MODES = ("no_rag", "rag", "rag_filter", "rag_filter_rewrite")

# Порог отсечения по умолчанию для режимов с фильтром (часть 2). Скор — косинус
# запрос-чанк (см. Retriever._apply_threshold). 0.45 подобран замером: сохраняет
# hit-rate@5 = 0.8824 (как без фильтра) и отсекает «хвост» нерелевантного
# (см. migr_log.md, этап 8). Совпадает с rag/config.json → retrieval.threshold.
DEFAULT_FILTER_THRESHOLD = 0.45


def _mode_flags(mode: str) -> dict:
    """Режим ответа → что делать: RAG, порог, rewrite."""
    return {
        "use_rag": mode != "no_rag",
        "threshold": DEFAULT_FILTER_THRESHOLD if mode in
                     ("rag_filter", "rag_filter_rewrite") else 0.0,
        "rewrite": mode == "rag_filter_rewrite",
    }


def compare_answers(cfg, modes, queries, k: int = 5, llm=None,
                    threshold: float = None, rewrite_mode: str = "heuristic"):
    """Прогнать контрольные вопросы в разных режимах ответа (части 1–2).

    Возвращает dict: {"rows": [...], "verdict": str, "divergences": [...]}.
    llm — callable(messages)->str (DI). Колонки top-K до/после: `candidate_k`
    (пул до фильтра) и `n_sources` (после фильтра).
    """
    from rag.rewrite import rewrite as _rewrite
    from rag.service import RagService
    query_list = queries if isinstance(queries, list) else load_queries(queries)
    svc = RagService(cfg)
    candidate_k = cfg.retrieval.candidate_k
    rows = []
    for mode in modes:
        flags = _mode_flags(mode)
        thr = threshold if threshold is not None else flags["threshold"]
        for q in query_list:
            query = q["query"]
            used_query = query
            if flags["rewrite"]:
                used_query = _rewrite(query, llm=llm, mode=rewrite_mode)
            hits = svc.search(used_query, k=k, threshold=thr) if flags["use_rag"] else []
            ans = svc.answer(used_query, use_rag=flags["use_rag"], k=k,
                             threshold=thr, llm=llm)
            text = ans.text or ""
            must = q.get("must_contain", [])
            hit_must = sum(1 for m in must if m.lower() in text.lower())
            rows.append({
                "id": q.get("id", ""), "mode": mode,
                "used_query": used_query,
                "candidate_k": candidate_k if flags["use_rag"] else 0,
                "has_sources": bool(ans.hits),
                "n_sources": len(ans.hits),
                "must_hit": hit_must, "must_total": len(must),
                "answer_len": len(text),
                "latency_ms": ans.latency_ms,
            })
    divergences = _answer_divergences(rows)
    verdict = _answer_verdict(rows)
    return {"rows": rows, "verdict": verdict, "divergences": divergences}


def _answer_divergences(rows, limit=3):
    """Вопросы, где режимы разошлись по наличию источников/попаданию must_contain."""
    by_id = {}
    for r in rows:
        by_id.setdefault(r["id"], []).append(r)
    out = []
    for qid, group in by_id.items():
        sig = {(r["has_sources"], r["must_hit"]) for r in group}
        if len(sig) > 1:
            out.append({"id": qid,
                        "detail": "; ".join(
                            f"{r['mode']}: ист.={r['n_sources']}, must={r['must_hit']}/{r['must_total']}"
                            for r in group)})
        if len(out) >= limit:
            break
    return out


def _answer_verdict(rows) -> str:
    modes = list(dict.fromkeys(r["mode"] for r in rows))
    parts = []
    for mode in modes:
        group = [r for r in rows if r["mode"] == mode]
        n = len(group)
        src = sum(1 for r in group if r["has_sources"])
        must = sum(r["must_hit"] for r in group)
        total = sum(r["must_total"] for r in group)
        lat = round(sum(r["latency_ms"] for r in group) / n, 1) if n else 0
        parts.append(f"{mode}: источники {src}/{n}, must_contain {must}/{total}, "
                     f"латентность ~{lat} мс")
    rag_rows = [r for r in rows if r["mode"] != "no_rag"]
    no_rag_rows = [r for r in rows if r["mode"] == "no_rag"]
    if rag_rows and no_rag_rows:
        rag_src = sum(1 for r in rag_rows if r["has_sources"])
        no_src = sum(1 for r in no_rag_rows if r["has_sources"])
        parts.append(f"RAG добавляет источники: {no_src} → {rag_src}.")
    # Часть 2: режим с фильтром не хуже режима без фильтра (по попаданию must_contain).
    def must_ratio(mode):
        g = [r for r in rows if r["mode"] == mode]
        total = sum(r["must_total"] for r in g)
        return (sum(r["must_hit"] for r in g) / total) if total else 0.0
    if any(r["mode"] == "rag_filter" for r in rows) and any(r["mode"] == "rag" for r in rows):
        base, filt = must_ratio("rag"), must_ratio("rag_filter")
        ok = filt >= base
        parts.append(f"фильтр vs без фильтра (must_contain): {round(base, 3)} → "
                     f"{round(filt, 3)} — {'✅ не хуже' if ok else '❌ хуже'}.")
    return " · ".join(parts)


def render_answer_report(result, k: int = 5) -> str:
    """Markdown-отчёт сравнения режимов ответа (части 1–2)."""
    lines = ["# Сравнение режимов ответа RAG (части 1–2)", ""]
    lines.append(f"k = {k}  ·  вопросов = "
                 f"{len({r['id'] for r in result['rows']})}")
    lines.append("")
    lines.append("## Таблица «вопрос × режим»")
    lines.append("")
    lines.append("| Вопрос | Режим | top-K до | top-K после | must_contain | Длина | Латентность, мс |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in result["rows"]:
        lines.append(
            f"| {r['id']} | {r['mode']} | {r.get('candidate_k', 0)} | "
            f"{r['n_sources']} | {r['must_hit']}/{r['must_total']} | "
            f"{r['answer_len']} | {r['latency_ms']} |")
    lines.append("")
    lines.append("## Вердикт")
    lines.append("")
    lines.append(result["verdict"])
    lines.append("")
    lines.append("## Разбор расхождений")
    lines.append("")
    if result["divergences"]:
        for div in result["divergences"]:
            lines.append(f"- **{div['id']}** — {div['detail']}")
    else:
        lines.append("Расхождений между режимами не обнаружено.")
    lines.append("")
    return "\n".join(lines)



# ---------------------------------------------------------------------------
# Сравнение ГЕНЕРАТОРОВ (часть 3, этап 6): локальная vs облачная модель.
# Отличается ТОЛЬКО генератор (retrieval и индекс — общие). Три оси: качество,
# скорость, стабильность ответов. Генераторы приходят как DI (callable), чтобы
# rag/ не импортировал core/ (граница §5): клиентов строит Kod.py.
# ---------------------------------------------------------------------------
GENERATOR_MODES = ("cloud", "local")

_CITATION_RE = re.compile(r"\[([^\[\]]+)\]")


def _citations(text: str) -> list:
    """Ссылки вида [doc_id#chunk_id] в тексте ответа (модель может дублировать doc_id)."""
    return [m for m in _CITATION_RE.findall(text or "") if "#" in m]


def _citations_valid(text: str, hits: list) -> tuple:
    """(всего ссылок, валидных). Валидна, если указывает на doc_id/chunk_id выдачи."""
    cites = _citations(text)
    if not cites:
        return 0, 0
    chunk_ids = {h.chunk_id for h in hits}
    doc_ids = {h.doc_id for h in hits}
    valid = sum(1 for c in cites
                if any(cid in c for cid in chunk_ids) or any(did in c for did in doc_ids))
    return len(cites), valid


def compare_generators(cfg, queries, generators, k: int = 5, repeat: int = 1,
                       threshold: float = None, block_renderers: dict = None,
                       resource_hooks: dict = None) -> dict:
    """Прогнать контрольные вопросы разными генераторами (часть 3, этап 6).

    `generators` — dict {имя: callable(messages)->str} (DI). Различается только
    генератор: retrieval/индекс общие. `repeat` — число повторов на вопрос (для
    оси «стабильность»). `block_renderers` (часть 4, этап 7) — dict
    {имя: callable(hits, query)->str} для сборки блока [rag] иным шаблоном
    (напр. строгий локальный); отсутствие имени → общий шаблон.
    `resource_hooks` (часть 4, этап 8) — dict {имя: {"start": callable,
    "stop": callable}} для снятия ресурсов вокруг прогона генератора; `stop`
    возвращает dict-сводку, которая кладётся в `result["resources"][имя]`.
    Возвращает {"rows", "summary", "divergences", "verdict", "resources"}.
    """
    from rag.service import RagService
    query_list = queries if isinstance(queries, list) else load_queries(queries)
    repeat = max(1, int(repeat))
    block_renderers = block_renderers or {}
    resource_hooks = resource_hooks or {}
    rows = []
    resources = {}
    for name, llm in generators.items():
        svc = RagService(cfg, llm=llm)
        renderer = block_renderers.get(name)
        hook = resource_hooks.get(name)
        if hook and hook.get("start"):
            hook["start"]()
        for q in query_list:
            for run in range(repeat):
                ans = svc.answer(q["query"], use_rag=True, k=k, threshold=threshold,
                                 block_renderer=renderer)
                text = ans.text or ""
                must = q.get("must_contain", [])
                hit_must = sum(1 for m in must if m.lower() in text.lower())
                n_cites, n_valid = _citations_valid(text, list(ans.hits))
                error = (not text) or ("(ошибка вызова LLM)" in text) \
                    or ("(LLM недоступен" in text)
                rows.append({
                    "id": q.get("id", ""), "mode": name, "run": run,
                    "must_hit": hit_must, "must_total": len(must),
                    "n_sources": len(ans.sources), "has_sources": bool(ans.sources),
                    "n_citations": n_cites, "n_citations_valid": n_valid,
                    "verdict": ans.verdict, "answer_len": len(text),
                    "latency_ms": ans.latency_ms, "error": error,
                })
        if hook and hook.get("stop"):
            resources[name] = hook["stop"]()
    summary = _generator_summary(rows)
    divergences = _generator_divergences(rows)
    verdict = _generator_verdict(summary)
    return {"rows": rows, "summary": summary, "divergences": divergences,
            "verdict": verdict, "k": k, "repeat": repeat, "resources": resources}


def _median(values: list) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[mid], 1)
    return round((ordered[mid - 1] + ordered[mid]) / 2, 1)


def _p95(values: list) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    return round(ordered[idx], 1)


def _std(values: list) -> float:
    n = len(values)
    if not n:
        return 0.0
    mean = sum(values) / n
    return (sum((v - mean) ** 2 for v in values) / n) ** 0.5


def _count(values) -> dict:
    out = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return out


def _generator_summary(rows) -> dict:
    """Сводка по трём осям для каждого генератора."""
    modes = list(dict.fromkeys(r["mode"] for r in rows))
    out = {}
    for mode in modes:
        group = [r for r in rows if r["mode"] == mode]
        n = len(group)
        lat = [r["latency_ms"] for r in group]
        must = sum(r["must_hit"] for r in group)
        total = sum(r["must_total"] for r in group)
        by_id = {}
        for r in group:
            by_id.setdefault(r["id"], []).append(r["must_hit"])
        consistent = sum(1 for v in by_id.values() if len(set(v)) == 1)
        total_lat = sum(lat)
        out[mode] = {
            "n": n,
            "must_ratio": round(must / total, 4) if total else 0.0,
            "sources_ok": sum(1 for r in group if r["has_sources"]),
            "citations": sum(r["n_citations"] for r in group),
            "citations_valid": sum(r["n_citations_valid"] for r in group),
            "verdicts": _count(r["verdict"] for r in group),
            "latency_median": _median(lat),
            "latency_p95": _p95(lat),
            "latency_std": round(_std(lat), 1),
            "tokens_per_s": round((sum(r["answer_len"] for r in group) / 4)
                                  / (total_lat / 1000), 2) if total_lat else 0.0,
            "errors": sum(1 for r in group if r["error"]),
            "empty": sum(1 for r in group if not r["answer_len"]),
            "consistent": consistent, "questions": len(by_id),
        }
    return out


def _generator_divergences(rows, limit: int = 3) -> list:
    """Вопросы, где генераторы разошлись по наличию источников/попаданию must_contain."""
    by_id = {}
    for r in rows:
        by_id.setdefault(r["id"], {}).setdefault(r["mode"], []).append(r)
    out = []
    for qid, modes in by_id.items():
        if len(modes) < 2:
            continue
        sig = {m: (any(r["has_sources"] for r in g), max(r["must_hit"] for r in g))
               for m, g in modes.items()}
        if len(set(sig.values())) > 1:
            detail = "; ".join(
                f"{m}: ист.={'да' if v[0] else 'нет'}, must={v[1]}" for m, v in sig.items())
            out.append({"id": qid, "detail": detail})
        if len(out) >= limit:
            break
    return out


def _generator_verdict(summary) -> str:
    parts = []
    for mode, s in summary.items():
        parts.append(
            f"{mode}: must_contain {s['must_ratio']}, источники {s['sources_ok']}/{s['n']}, "
            f"медиана {s['latency_median']} мс / p95 {s['latency_p95']} мс, "
            f"ошибок {s['errors']}, согласованность {s['consistent']}/{s['questions']}")
    if "cloud" in summary and "local" in summary:
        c, l = summary["cloud"], summary["local"]
        parts.append("Локальная не хуже облачной по must_contain."
                     if l["must_ratio"] >= c["must_ratio"]
                     else "Локальная уступает облачной по must_contain.")
        if c["latency_median"]:
            parts.append(f"Локальная медленнее в "
                         f"{round(l['latency_median'] / c['latency_median'], 1)}× (медиана).")
    return " · ".join(p for p in parts if p)


def render_generator_report(result, title: str = None) -> str:
    """Markdown-отчёт сравнения генераторов (три оси + вердикт + расхождения).

    `title` — заголовок отчёта (этап 6 — сравнение cloud/local; этап 7 — замер
    «до/после» оптимизации). По умолчанию — заголовок этапа 6.
    """
    lines = [title or "# Сравнение локальной и облачной генерации RAG (этап 6, G2)", ""]
    lines.append(f"k = {result['k']} · повторов на вопрос = {result['repeat']} · "
                 f"вопросов = {len({r['id'] for r in result['rows']})}")
    lines.append("")
    lines.append("## Таблица «вопрос × генератор»")
    lines.append("")
    lines.append("| Вопрос | Генератор | must_contain | Источники | Ссылки (валид.) | "
                 "verdict | Длина | Латентность, мс |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in result["rows"]:
        lines.append(
            f"| {r['id']} | {r['mode']} | {r['must_hit']}/{r['must_total']} | "
            f"{r['n_sources']} | {r['n_citations_valid']}/{r['n_citations']} | "
            f"{r['verdict']} | {r['answer_len']} | {r['latency_ms']} |")
    lines.append("")
    lines.append("## Сводка по трём осям")
    lines.append("")
    lines.append("| Генератор | Качество: must_contain | Источники | Ссылки валид. | "
                 "Скорость: медиана, мс | p95, мс | ток/с | Стабильность: ошибки | "
                 "согласованность |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for mode, s in result["summary"].items():
        lines.append(
            f"| {mode} | {s['must_ratio']} | {s['sources_ok']}/{s['n']} | "
            f"{s['citations_valid']}/{s['citations']} | {s['latency_median']} | "
            f"{s['latency_p95']} | {s['tokens_per_s']} | {s['errors']} | "
            f"{s['consistent']}/{s['questions']} |")
    lines.append("")
    lines.append("## Вердикт")
    lines.append("")
    lines.append(result["verdict"])
    lines.append("")
    lines.append("## Разбор расхождений")
    lines.append("")
    if result["divergences"]:
        for d in result["divergences"]:
            lines.append(f"- **{d['id']}** — {d['detail']}")
    else:
        lines.append("Расхождений между генераторами не обнаружено.")
    lines.append("")
    resources = result.get("resources") or {}
    if resources:
        lines.append("## Ресурсы по генераторам")
        lines.append("")
        lines.append("| Генератор | RSS пик, МБ | RSS среднее, МБ | CPU среднее, % | "
                     "Размер модели | RAM до (used/avail) | RAM после (used/avail) |")
        lines.append("|---|---|---|---|---|---|---|")
        for name, r in resources.items():
            before = r.get("free_before", {})
            after = r.get("free_after", {})
            lines.append(
                f"| {name} | {r.get('rss_peak_mb', 0)} | {r.get('rss_avg_mb', 0)} | "
                f"{r.get('cpu_avg', 0)} | {r.get('model_size', '—') or '—'} | "
                f"{before.get('used_mb', 0)}/{before.get('available_mb', 0)} | "
                f"{after.get('used_mb', 0)}/{after.get('available_mb', 0)} |")
        lines.append("")
        lines.append("**GPU:** дискретного GPU нет, inference по CPU, VRAM неприменим.")
        lines.append("")
    return "\n".join(lines)


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
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]

    # Сравнение генераторов (этап 6): клиентов строит Kod.py (граница §5 —
    # rag/ не импортирует core/). Здесь только подсказка.
    if any(m in GENERATOR_MODES for m in modes):
        print("Сравнение генераторов (cloud/local) запускается из Kod.py "
              "(клиентов строит реестр):\n"
              "  python Kod.py --rag-gen-compare --gen-modes cloud,local --repeat 3")
        return 2

    # Режимы ответа (части 1–2) — отдельный отчёт сравнения ответов.
    if any(m in ANSWER_MODES for m in modes):
        result = compare_answers(cfg, modes, args.queries, k=args.k)
        text = render_answer_report(result, k=args.k)
    else:
        strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
        report = compare(cfg, strategies, modes, args.queries, k=args.k)
        text = render_report(report)
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(text, encoding="utf-8")
    print(text)
    print(f"\nОтчёт записан: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())