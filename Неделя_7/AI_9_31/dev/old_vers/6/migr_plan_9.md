# Этап 9 — Цитирование и grounding (R7)

> Мастер-план: `dev/migr_plan.md` §4 «Этап 9», §5 границы, §6.1/§6.4/§6.5.
> Цель: решение №4 — при активном RAG ответ **обязан** опираться на источники,
> и это проверяется **кодом** (`rag/grounding.py`), а не только промптом.

## Что уже есть (этап 8)

- `agent.last_rag_hits` — чанки последнего поиска (вход для проверки).
- `RagService.ground(...)` — заглушка `NotImplementedError` (заменим).
- `GroundingReport` в `rag/types.py`: `verdict` (ok | partial | hallucination |
  unchecked), `sentences`, `citations_ok`, `regenerated`, `stats`.
- `rag/text.py`: `split_sentences`, `tokenize`, `stem`, `normalize` — переиспользуем.
- `RagConfig.grounding`: `mode` (off|warn|strict, default strict), `coverage_min=0.45`,
  `numbers_strict=True`, `max_regenerations=1`.

## Шаги (по зависимостям)

| # | Шаг | Файл | Содержание |
|---|---|---|---|
| 9.1 | Ядро проверки | `rag/grounding.py` | `ground(answer, hits, cfg) -> GroundingReport`: ответ → предложения → для каждого лучший чанк по (а) покрытию стем-токенов, (б) пересечению сущностей (заглавные словосочетания, латинские идентификаторы, `snake_case`), (в) строгому совпадению чисел/дат. Статусы: `supported` / `weak` / `unsupported`. Числа в ответе, отсутствующие в выбранном чанке → `unsupported` (главный тип галлюцинаций). Регистр/опечатки не ломают оценку (normalize+stem). |
| 9.2 | Вердикт | `rag/grounding.py` | нет ни одной ссылки → `partial`; ссылки есть, но доля `unsupported` > порога или провалены числа → `hallucination`; иначе `ok`. `citations_ok` = есть ≥1 ссылка и они указывают на реальные `chunk_id` из hits. `stats`: n_sentences, n_supported, coverage_avg, n_numbers, n_numbers_missing, n_citations, n_bad_citations |
| 9.3 | Фасад | `rag/service.py` | `ground(answer, hits=None, mode=None)` → `rag.grounding.ground(...)`; режим из `cfg.grounding.mode` (переопределение аргументом); `off` → `verdict="unchecked"` без работы |
| 9.4 | Агент | `core/agent.py` | `check_grounding(answer)` — тонкий вызов фасада на `last_rag_hits`; `regenerate_with_feedback(report)` — **одна** авто-перегенерация (strict, `max_regenerations=1`) с фидбэк-промптом («оперись на N источников, убери неподтверждённое»), повторная проверка, при провале — явная пометка в ответе; счётчик токенов обмена не ломается |
| 9.5 | Kod.py | `Kod.py` | `/rag check <ответ>` — проверка по `agent.last_rag_hits` (LLM не тратит); после обычного ответа при `strict` — авто-перегенерация/пометка; `[RAG] grounding: verdict=… coverage=…` в лог; `--rag-grounding` уже проброшен в конфиг (этап 8) |
| 9.6 | Тесты | `dev/tests_debug/unit/test_rag_grounding.py` | синтетический корректный ответ → `ok`; выдуманная дата/число → `hallucination`; ответ без единой ссылки → `partial`; регистр/падеж не ломают; `off` → `unchecked`; ссылки на несуществующий chunk → `citations_ok=False`; авто-перегенерация ровно 1 раз (Mock-клиент со счётчиком) |
| 9.7 | Регрессия | — | L2 (211 + новые) / L3 / L4 / гейт 25; `requirements.txt` пуст |
| 9.8 | Живой прогон гейта | `dev/logs_reports/stages/rag_grounding_live.md` | 3 запроса из `queries.jsonl`, реальный LLM: в каждом ответе есть ссылки, `verdict ≠ hallucination`; транскрипт |
| 9.9 | Журнал | `dev/migr_log.md` | запись «Этап 9» + перечитать `migr_plan.md` + текст коммита |

## Гейт 9→10

| # | Проверка | Критерий |
|---|---|---|
| 1 | `unit_runner.py test_rag_grounding` | все зелёные |
| 2 | корректный ответ → `ok` | да |
| 3 | выдуманное число/дата → `hallucination` | да |
| 4 | ответ без ссылок → `partial` | да |
| 5 | `off` ничего не проверяет | `verdict=unchecked`, 0 обращений к индексам |
| 6 | регистр/опечатки/падеж не ломают оценку | да |
| 7 | `strict`: одна авто-перегенерация, не больше | счётчик вызовов LLM = 2 (ответ + 1) |
| 8 | `/rag check` не тратит LLM | да |
| 9 | живой прогон 3 запроса: ссылки есть, `verdict ≠ hallucination` | транскрипт `stages/rag_grounding_live.md` |
| 10 | L2/L3/L4/гейт 25 без регрессии | да |
| 11 | `git diff --stat requirements.txt` пусто; запись «Этап 9» + перечитывание | да |

## Границы (не нарушаем)

- `rag/` не импортирует `core/`; `core/` не импортирует `rag/` (связь через DI-фасад).
- Grounding **не** вводит новых стадий `TaskStage` и не меняет переходы.
- Без `--rag` поведение и промпт байт-в-байт прежние (grounding не вызывается).
- Авто-перегенерация — максимум `max_regenerations` (1), затем пометка, а не цикл.
- Новые pip-зависимости запрещены (только stdlib + уже используемое).

## Откат

```bash
git checkout -- rag/grounding.py rag/service.py core/agent.py Kod.py
rm -f dev/tests_debug/unit/test_rag_grounding.py
```
