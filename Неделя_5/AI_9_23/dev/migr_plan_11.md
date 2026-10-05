# Этап 11 — Финал: живой прогон, гейт, синхронизация (Ф)

> Мастер-план: `dev/migr_plan.md` §4 «Этап 11», §5 границы, §6, §8 (DoD).
> Цель: доказать, что Ревизия 6 работает целиком, и синхронизировать документацию
> с кодом. Финальный гейт — **33/33**.

## Что уже есть (этапы 0–10)

- `rag/` полностью реализован: chunking (2 стратегии), embedding (Ollama bge-m3 +
  Hashing-фолбэк), index (плоский, инкрементальный), retrieval (bm25/dense/hybrid),
  rerank, eval, compare, cache, grounding, service (фасад).
- Интеграция: `--rag`, `/rag …`, блок `[rag]` в промпте, grounding strict.
- Транскрипты: `stages/rag_chunking_compare.md`, `rag_grounding_live.md`,
  `rag_cache_live.md`.
- Гейт 25/25; L2 244 OK; `requirements.txt` не тронут.

## Шаги

| # | Шаг | Файл | Содержание |
|---|---|---|---|
| 11.1 | Живые прогоны | `dev/logs_reports/stages/rag_*` | индексация корпуса на bge-m3; `--rag-search` (5 запросов); REPL-демо «вопрос → источники → ответ со ссылками»; `--rag-eval`; `--rag-compare` — транскрипты |
| 11.2 | Сценарий | `dev/tests_debug/scenario/scen_rag.md` | ручная демонстрация RAG (шаги, ожидаемый вывод) |
| 11.3 | Гейт | `dev/tests_debug/check_acceptance.sh` | **+8 проверок** (25 → 33): импорт `rag`; индекс строится; поиск отдаёт ≥1 хит с метаданными; обе стратегии чанкинга; отчёт сравнения существует; без `--rag` промпт без `[rag]`; RAG не меняет `TaskStage`; `--rag-eval` hit-rate@5 ≥ 0.80 |
| 11.4 | README | `README.md` | раздел «RAG-индексация и поиск по документам» (назначение, запуск Ollama, команды, примеры вывода) |
| 11.5 | arch | `arch.md` | слой `rag/` в дереве модулей, направление зависимостей, конвейер, границы |
| 11.6 | Итог | `dev/migr_log.md` | «Итог Ревизии 6» + предложить коммит |
| 11.7 | Регрессия | — | L2/L3/L4 + гейт 33/33; `requirements.txt` пуст |

## Гейт (финальный) — 33/33

| # | Проверка | Критерий |
|---|---|---|
| 1–25 | прежние проверки | без регрессии |
| 26 | импорт `rag` | `import rag` работает |
| 27 | индекс строится | `--rag-ingest` → чанки > 0 |
| 28 | поиск отдаёт ≥1 хит с метаданными | `source`/`section`/`chunk_id` |
| 29 | обе стратегии чанкинга | `fixed` и `structural` дают разное разбиение |
| 30 | отчёт сравнения существует | `stages/rag_chunking_compare.md` |
| 31 | без `--rag` промпт без `[rag]` | байт-в-байт прежний |
| 32 | RAG не меняет `TaskStage` | стадии не затронуты |
| 33 | `--rag-eval` hit-rate@5 ≥ 0.80 | да |

## Границы (не нарушаем)

- `rag/` не импортирует `core/`; `core/` не импортирует `rag/`.
- `TaskStage` не меняется; RAG off по умолчанию; сеть — только localhost.
- Новых pip-зависимостей нет; `requirements.txt` не меняется.
- Юниты зелёные **без** Ollama (фолбэк Hashing).
- Коммит выполняет **только** оператор.

## Откат

```bash
git checkout -- dev/tests_debug/check_acceptance.sh README.md arch.md dev/migr_log.md
rm -f dev/tests_debug/scenario/scen_rag.md dev/migr_plan_11.md
```
