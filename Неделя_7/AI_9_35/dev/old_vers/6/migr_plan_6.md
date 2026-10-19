# migr_plan_6.md — Этап 6. Ретривер (R4)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (Ревизия 6, §4 «Этап 6»).
> Контур: **R (реализация)**. Метка цели: **R4**. Зависимости: **этап 4** (эмбеддинги),
> **этап 5** (индекс). Порядок: **пошагово с оператором**.
> **Коммиты — только за оператором** (текст предложен в ШАГЕ 6.7).

## Цель этапа

Реализовать `rag/retrieval.py` (три режима + честный фьюжн) и `rag/rerank.py`
(`LexicalReranker`). Гибрид: BM25 top-50 ⊕ dense top-50 → **RRF k=60** → реранк →
**MMR λ=0.7** → top-k с ≤2 чанка на документ.

## Предусловия (выполнено)

- `rag/index.py` — `search_bm25`, `search_dense`, `chunks`, `vectors` (этап 5);
- `rag/embedding.py` — `Embedder.embed` (этап 4);
- `rag/config.py` — `RetrievalConfig` (`mode=hybrid`, `candidate_k=50`, `final_k=5`,
  `rrf_k=60`, `mmr_lambda=0.7`, `max_chunks_per_doc=2`, `multi_query=False`),
  `RerankConfig` (`provider=lexical`, `candidates=20`);
- `rag/types.py` — `Hit` (со `scores`, `source_query`, `parent_text`);
- `rag/datasets/queries.jsonl` — 24 golden-запроса (этап 2).

## Границы этапа

- **Не** считаем метрики/сравнение (этап 7) — только поиск.
- **Не** трогаем `Kod.py`, `core/`, `storage/`, `memory/`, `integrations/`.
- **Не** добавляем pip-зависимостей (только stdlib).
- **Не** включаем multi-query (за флагом, этап 10).

---

## Шаги

### ШАГ 6.1 — `rag/rerank.py` (агент)

`Reranker` (протокол) + `LexicalReranker`: пересечение токенов запроса и чанка
(стемминг + стоп-слова) как добавочный скор; стабильная сортировка.

### ШАГ 6.2 — `rag/retrieval.py` (агент)

`Retriever(index, cfg, embedder=None)`:
- `search(query, k, mode, filters)` — три режима:
  - `bm25` — `index.search_bm25` → top-k;
  - `dense` — `embedder.embed([query])` → `index.search_dense` → top-k;
  - `hybrid` — BM25 top-50 ⊕ dense top-50 → **RRF** → реранк → **MMR** → top-k;
- `_rrf(rank_lists, rrf_k, weights=None)` — `score = Σ w_i/(rrf_k + rank)`;
  веса `w_bm25=0.3`, `w_dense=1.0` (dense — основной bi-encoder, BM25 — вспомогательный;
  уточнено на этапе 7, см. `migr_plan_7.md`);
- `_mmr(candidates, k, λ)` — отбор с штрафом за близость к уже выбранным;
- `_apply_filters(hits, filters)` — glob по `source`, `content_type`, `section`-префикс;
- `_limit_per_doc(hits, max_per_doc)` — ≤2 чанка на документ;
- `Hit.scores` — `bm25_rank`, `dense_rank`, `rrf`, `rerank`, `source_query`.

### ШАГ 6.3 — CLI-точка входа (агент)

`python -m rag.retrieval --query "…" --mode hybrid --k 5` — печатает top-k с
метаданными и скорами (требование гейта 6→7).

### ШАГ 6.4 — `test_rag_retrieval.py` (агент)

Проверки: точное совпадение идентификатора (`build_agent`) в top-3; гибрид не хуже
каждой компоненты по recall@5 на golden-датасете; MMR уменьшает долю повторов
документа; фильтр `content_type="code"` не отдаёт прозу; пустой запрос → понятная
ошибка, не падение.

### ШАГ 6.5 — Живой прогон (агент)

`python -m rag.retrieval` на реальном индексе (этап 5) для трёх режимов; транскрипт
в `stages/rag_retrieval_live.txt`.

### ШАГ 6.6 — Регрессия (агент)

L2/L3/L4/гейт.

### ШАГ 6.7 — Запись в журнал + перечитывание плана

---

## Выход этапа

- `rag/retrieval.py`, `rag/rerank.py` — реализованы;
- `dev/tests_debug/unit/test_rag_retrieval.py` — создан;
- `dev/logs_reports/stages/rag_retrieval_live.txt` — транскрипт;
- запись «Этап 6» в `dev/migr_log.md`;
- `requirements.txt`, `Kod.py`, `core/`, `storage/` — **не изменены**.

## Гейт 6→7 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `unit_runner.py test_rag_retrieval` | все зелёные |
| 2 | `build_agent` в top-3 | да |
| 3 | гибрид ≥ каждой компоненты по recall@5 (HashingEmbedder) | да |
| 4 | MMR снижает долю повторов документа | да |
| 5 | фильтр `content_type="code"` не отдаёт прозу | да |
| 6 | пустой запрос → понятная ошибка | да |
| 7 | `python -m rag.retrieval` — три режима | работают |
| 8 | L2/L3/L4/гейт | без регрессии |
| 9 | `git diff --stat requirements.txt` | пусто |
| 10 | запись «Этап 6» + перечитывание `migr_plan.md` | ✅ |

## Откат

```bash
git checkout -- rag/retrieval.py rag/rerank.py
rm -f dev/tests_debug/unit/test_rag_retrieval.py
```

## Что передаём дальше

- **Этапу 7 (R5):** `Retriever.search` — предмет метрик на golden-датасете.
- **Этапу 8 (R6):** `Retriever` — источник `Hit` для блока `[rag]`.
- **Этапу 10 (R8):** multi-query и кэш поиска.
