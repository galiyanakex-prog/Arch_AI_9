# Этап 10 — Кэш, multi-query, реранк, статистика (R8)

> Мастер-план: `dev/migr_plan.md` §4 «Этап 10», §5 границы, §6.1/§6.3/§6.4.
> Цель: не платить за повторные поиски (кэш), уметь расширять запрос
> (multi-query), показать состояние контура (`/rag stats`).

## Что уже есть (этапы 6–9)

- `Retriever.search(query, k, mode, filters)` — гибридный поиск; `_rrf` — фьюжн.
- `RagIndex.meta` = `{model_id, dim, chunker_version, strategy, docs}`; `docs[doc_id]`
  хранит `mtime` и `sha1` — основа инвалидации кэша.
- `RagService.search(...)` — точка входа; `stats()` уже отдаёт индекс/модель/Ollama.
- `RagConfig.cache`: `enabled=True`, `max_entries=256`, `ttl_seconds=900`.
- `RagConfig.retrieval.multi_query=False`; `--rag-multi-query` пока no-op (этап 8).
- `LexicalReranker` (этап 7) — уже реализован; интерфейс `Reranker` оставлен под
  будущий cross-encoder (в этой ревизии НЕ реализуем — тяжёлые зависимости).

## Шаги (по зависимостям)

| # | Шаг | Файл | Содержание |
|---|---|---|---|
| 10.1 | Кэш поиска | `rag/cache.py` | `SearchCache(cfg, log)`: ключ `sha256(model_id \| index_version \| norm_query \| params \| filters)`; значение хранит `expires` (TTL) и `mtimes` затронутых документов → запись невалидна при изменении документа **до** истечения TTL; LRU `max_entries`; счётчики `hits/misses/evictions`; `stats()` |
| 10.2 | Версия индекса | `rag/index.py` | `version()` — sha256 от `model_id/dim/chunker_version/strategy` + sha1 всех документов; `mtimes()` — `{doc_id: mtime}` (для инвалидации) |
| 10.3 | Интеграция кэша | `rag/service.py` | `search()`: ключ → `cache.get` (проверка TTL+mtime) → при промахе реальный поиск → `cache.put`; латентность (p50/p95) в кольцевом буфере; `stats()` дополняется `cache`/`latency` |
| 10.4 | Multi-query | `rag/service.py` | `rephrase(query, llm, n)` — 2–4 переформулировки через LLM (парсинг строк), при отсутствии LLM — детерминированная эвристика (контент-слова/стемы); `search_multi(query, variants, k, mode, filters)` — поиск по каждой + склейка через RRF (`Retriever._rrf`), дедуп, top-k |
| 10.5 | Агент | `core/agent.py` | при `cfg.retrieval.multi_query`: `rephrase` через `self.llm` → `search_multi`; доп. токены в `last_grounding_extra_tokens` (учёт в `tokens.csv`); по умолчанию выключено |
| 10.6 | Kod.py | `Kod.py` | убрать no-op предупреждение `--rag-multi-query`; `/rag stats` показывает кэш-хиты, p50/p95, RAM, Ollama; `--rag-multi-query` реально включает |
| 10.7 | Тесты | `dev/tests_debug/unit/test_rag_cache.py` | N одинаковых запросов → 1 реальный поиск (счётчик эмбеддера/ретривера); инвалидация по `mtime`; TTL; LRU-вытеснение; ключ чувствителен к params/filters; multi-query recall@5 ≥ базового (детерминированная эвристика) |
| 10.8 | Регрессия | — | L2 (229 + новые) / L3 / L4 / гейт 25; `requirements.txt` пуст |
| 10.9 | Живой прогон | `dev/logs_reports/stages/rag_cache_live.md` | реальный индекс: повторные запросы → кэш-хиты; `/rag stats`; multi-query recall@5 vs базового |
| 10.10 | Журнал | `dev/migr_log.md` | запись «Этап 10» + перечитать `migr_plan.md` + текст коммита |

## Гейт 10→11

| # | Проверка | Критерий |
|---|---|---|
| 1 | `unit_runner.py test_rag_cache` | все зелёные |
| 2 | N одинаковых запросов → 1 реальный поиск | счётчик = 1 |
| 3 | инвалидация по `mtime` | изменение документа → промах |
| 4 | TTL истекает | промах после TTL |
| 5 | LRU-вытеснение при `max_entries` | старейший вытеснен |
| 6 | ключ чувствителен к `params`/`filters` | разные ключи |
| 7 | multi-query recall@5 ≥ базового | да (иначе выключено, зафиксировано) |
| 8 | `/rag stats` показывает кэш/p50-p95/RAM/Ollama | да |
| 9 | L2/L3/L4/гейт 25 без регрессии | да |
| 10 | `git diff --stat requirements.txt` пусто | да |
| 11 | запись «Этап 10» + перечитывание `migr_plan.md` | да |

## Границы (не нарушаем)

- `rag/` не импортирует `core/`; LLM для multi-query передаётся как callable (DI).
- Кэш — только stdlib (OrderedDict + hashlib + json); новых pip-зависимостей нет.
- Multi-query по умолчанию **выключен**; без флага поведение прежнее.
- Кэш не меняет `TaskStage` и не влияет на промпт (только ускоряет поиск).
- Cross-encoder НЕ реализуем (тяжёлые зависимости) — интерфейс `Reranker` остаётся.

## Откат

```bash
git checkout -- rag/index.py rag/service.py core/agent.py Kod.py
rm -f rag/cache.py dev/tests_debug/unit/test_rag_cache.py
```
