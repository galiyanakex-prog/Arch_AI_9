# migr_plan_5.md — Этап 5. Индекс и персистентность (R3)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (Ревизия 6, §4 «Этап 5»).
> Контур: **R (реализация)**. Метка цели: **R3**. Зависимости: **этап 3** (чанки),
> **этап 4** (эмбеддинги). Порядок: **пошагово с оператором**.
> **Коммиты — только за оператором** (текст предложен в ШАГЕ 5.8).

## Цель этапа

Реализовать `rag/index.py` (плоский индекс BM25 + dense, персистентность) и
`rag/corpus.py` (обход корпуса + дельта-индексация). Артефакты — в `rag/index/`.
Добавить в `storage/store.py` доступ к глобальному RAG-корню.

## Предусловия (выполнено)

- `rag/chunking.py` — чанки с `sha1` (этап 3);
- `rag/embedding.py` — `Embedder`, `EmbeddingCache` (этап 4);
- `rag/types.py` — `Chunk`, `DocMeta`, `IngestReport` (этап 0);
- `rag/config.py` — `CorpusConfig`, `Bm25Config`, `index_dir="rag/index"`;
- `rag/datasets/corpus.list` — 9 файлов (этап 2);
- `.gitignore` — `rag/index/` уже игнорируется.

## Границы этапа

- **Не** реализуем ретривер/фьюжн (этап 6) — только `search_bm25`/`search_dense`.
- **Не** трогаем `Kod.py`, `core/`, `memory/`, `integrations/`.
- **Не** добавляем pip-зависимостей (только stdlib: `json`, `array`, `os`, `math`).
- **Не** ходим во внешнюю сеть.

---

## Шаги

### ШАГ 5.1 — `rag/corpus.py` (агент)

- `discover(paths, cfg)` — обход `corpus.list` + явных путей; фильтр `deny`;
  детект типа по расширению (`.py`→code, `.md`→text); `sha1` содержимого;
  возврат `list[dict]` (`doc_id`, `source`, `title`, `text`, `sha1`, `mtime`,
  `content_type`).
- `delta(docs, known_docs)` — `{added, updated, removed, skipped}` по `sha1`.

### ШАГ 5.2 — `rag/index.py` (агент)

`RagIndex`:
- `build(chunks, embedder, cache=None)` — полная сборка (BM25 + векторы);
- `ingest(docs, cfg, embedder, cache=None)` — инкрементальная сборка через
  `corpus.delta`; неизменённые документы не переэмбедятся;
- `save(path)` / `load(path)` — `postings.json`, `vectors.bin`, `chunks.json`,
  `meta.json`; запись только `tmp + os.replace`;
- `search_bm25(query, k)` / `search_dense(vector, k)`;
- `stats()` — `n_docs`, `n_chunks`, размер на диске.

### ШАГ 5.3 — Устойчивость (агент)

- при загрузке — сверка `meta.json` с `RagConfig` (`model_id`, `dim`,
  `chunker_version`, `strategy`) → расхождение = полный ребилд;
- битый `postings.json` → ребилд с предупреждением;
- пустой индекс не роняет поиск.

### ШАГ 5.4 — `storage/store.py` (агент)

`rag_root()`, `rag_index_dir()`, `read_rag_config(default)`, `write_rag_config(data)`
— глобальный RAG-корень вне `users/` (по образцу `scheduler_dir`).

### ШАГ 5.5 — `test_rag_index.py` (агент)

Проверки: round-trip (сохранить → загрузить → идентичная выдача BM25);
инкрементальность (изменён 1 файл из N → пересчитан только он, по счётчику
эмбеддингов); ребилд при смене `model_id`; пустой индекс не роняет поиск;
`stats()` заполнен.

### ШАГ 5.6 — Живой прогон (агент)

Индексация реального корпуса (9 файлов) → `stats()`; повторный `ingest` без
изменений → `embed_calls == 0`; транскрипт в `stages/rag_index_live.txt`.

### ШАГ 5.7 — Регрессия (агент)

L2/L3/L4/гейт.

### ШАГ 5.8 — Запись в журнал + перечитывание плана

---

## Выход этапа

- `rag/index.py`, `rag/corpus.py` — реализованы;
- `storage/store.py` — +4 метода RAG-корня;
- `dev/tests_debug/unit/test_rag_index.py` — создан;
- `dev/logs_reports/stages/rag_index_live.txt` — транскрипт;
- запись «Этап 5» в `dev/migr_log.md`;
- `requirements.txt`, `Kod.py`, `core/`, `memory/` — **не изменены**.

## Гейт 5→6 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `unit_runner.py test_rag_index` | все зелёные |
| 2 | round-trip: BM25-выдача идентична после перезапуска | да |
| 3 | повторный `ingest` без изменений | `embed_calls == 0` |
| 4 | смена `model_id` → ребилд | да |
| 5 | пустой индекс не роняет поиск | да |
| 6 | `stats()`: `n_docs`, `n_chunks`, размер | заполнены |
| 7 | L2/L3/L4/гейт | без регрессии |
| 8 | `git diff --stat requirements.txt` | пусто |
| 9 | запись «Этап 5» + перечитывание `migr_plan.md` | ✅ |

## Откат

```bash
git checkout -- rag/index.py rag/corpus.py storage/store.py
rm -f dev/tests_debug/unit/test_rag_index.py
rm -rf rag/index/
```

## Что передаём дальше

- **Этапу 6 (R4):** `search_bm25`/`search_dense` — компоненты гибрида; `chunks.json`
  — метаданные для `Hit`.
- **Этапу 7 (R5):** индекс — база для метрик на golden-датасете.
- **Этапу 8 (R6):** `storage/store.py` — путь к индексу для `Kod.py`.
