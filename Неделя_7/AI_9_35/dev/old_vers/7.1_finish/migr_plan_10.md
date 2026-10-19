# migr_plan_10.md — Этап 10. Интеграция в AI_9 (R8)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (Ревизия 7, §4 «Этап 10»).
> Контур: **R (RAG-ядро)**. Метка цели: **R8**. Зависимости: **этапы 6, 9**.
> Порядок: **пошагово с оператором**. **Коммиты — только за оператором** (ШАГ 10.7).

## Цель этапа

**Проверить/адаптировать** интеграцию RAG в агента (большая часть сделана в Ревизии 6) и
**довести формат ответа** до части 3: агент при активном RAG отдаёт **источники/цитаты**
и «не знаю» (из этапа 9). **Контракты агента не меняются**; без `--rag` промпт байт-в-байт
прежний.

> **Фундамент есть (Ревизия 6):** `Kod.py` — `--rag`, `--rag-ingest/-search/-eval/-compare`,
> `--no-rag-block`, REPL `/rag …`; `core/prompt_builder.py` — `BLOCK_ORDER` содержит `"rag"`
> **после** `"tools"` до `"long_term"`, `DELIVERABLE` содержит `"rag"`, есть `render_rag`;
> `core/agent.py` — DI (`rag_service`, `rag_enabled`, `rag_block_enabled`, `rag_top_k`,
> `rag_mode`), `_rag_retrieve` (один поиск на обмен + строка `[RAG]`), `_grounding_guard`
> (авто-перегенерация), `last_rag_hits`; `storage/store.py` — RAG-корень.
> **Новое:** подключить к пути ответа `Answer` (sources/quotes/verdict) из этапа 9.

## Предусловия

- `rag/sources.py`, `rag/citations.py`, `rag/verify.py`, расширенный `Answer` — этап 9 закрыт.
- `RagService.answer`, `context_block`, `ground` — этапы 6–9.
- `core/prompt_builder.py`, `core/agent.py`, `Kod.py`, `storage/store.py` — как в Ревизии 6.

## Границы этапа

- **Не** создаём `core/chat.py`, `core/task_state.py`, флагов `--chat*`, команд `/chat*`.
- **Не** меняем `BLOCK_ORDER` (rag уже на месте); `invariants`/`profile` не вытесняются.
- **Не** меняем `requirements.txt`.

---

## Шаги

### ШАГ 10.1 — Аудит DI и промпта (агент)

```bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
grep -nE "BLOCK_ORDER|DELIVERABLE|def render_rag" core/prompt_builder.py
grep -nE "rag_service|rag_enabled|rag_block_enabled|_rag_retrieve|last_rag_hits" core/agent.py | head
grep -nE "rag_root|rag_index|read_rag|write_rag" storage/store.py
grep -nE "\-\-rag|/rag|build_agent" Kod.py | head
```

Сверить с §6: `BLOCK_ORDER = (..., "tools", "rag", "long_term", ...)`; `DELIVERABLE`
содержит `"rag"`; DI-поля на месте; `--rag`/`/rag` есть.

### ШАГ 10.2 — Проверка «без --rag промпт идентичен» (агент) — главная регрессия

```bash
API_KEY=test-key .venv/bin/python dev/tests_debug/unit_runner.py 2>&1 | grep -iE "rag_integration|prompt|Итого"
```

Ожидаемо: `test_rag_integration.py` и `test_prompt.py` зелёные; при `rag_enabled=False`
собранный промпт **байт-в-байт** равен прежнему.

### ШАГ 10.3 — `RagService.answer` в пути ответа агента (агент)

Связать формат `Answer` (этап 9) с ответом агента: при активном RAG ответ должен нести
`sources`/`quotes` и `verdict`; при `insufficient` — «не знаю» + уточнение **без вызова LLM**.
Правка — в `core/agent.py` (в районе `_rag_retrieve`/`_grounding_guard`), **без** изменения
публичных контрактов.

```bash
grep -nE "answer\(|sources|quotes|verdict|insufficient" core/agent.py | head
```

### ШАГ 10.4 — Проверка блока `[rag]` в бюджете промпта (агент)

```bash
.venv/bin/python - <<'EOF'
from core.prompt_builder import BLOCK_ORDER, DELIVERABLE
assert "rag" in BLOCK_ORDER and "rag" in DELIVERABLE
i_tools, i_rag, i_lt = BLOCK_ORDER.index("tools"), BLOCK_ORDER.index("rag"), BLOCK_ORDER.index("long_term")
assert i_tools < i_rag < i_lt, "rag должен стоять после tools и до long_term"
print("OK: порядок блоков корректен:", BLOCK_ORDER)
EOF
```

Бюджет: блок `[rag]` усекается **первым**; `invariants`/`profile` не вытесняются.

### ШАГ 10.5 — Наблюдаемость `[RAG]` (агент)

```bash
grep -nE "\[RAG\]" core/agent.py | head
```

Ожидаемо: на каждый поиск — строка `[RAG]` (запрос, режим, k, `chunk_id`, скоры,
латентность) в `Den_log.md`; токены multi-query/grounding — в `tokens.csv`.

### ШАГ 10.6 — Smoke RAG-режима (агент)

```bash
API_KEY=test-key .venv/bin/python Kod.py --rag --mock </dev/null 2>&1 | head -20
```

Ожидаемо: поднимается, печатает `[RAG]`; без ошибок сборки агента.

### ШАГ 10.7 — Запись в журнал + коммит (оператор)

Запись «Этап 10» в `dev/migr_log.md`. **Предлагаемый коммит:**

```
feat(rag): интеграция Answer (источники/цитаты/«не знаю») в ответ агента (этап 10, Ревизия 7)

Причина: часть 3/4 Задание.txt — ответ агента обязан нести источники и цитаты.
Фундамент Ревизии 6 (DI, BLOCK_ORDER, /rag, [RAG]-лог) подтверждён; добавлена связка
формата Answer с путём ответа; без --rag промпт байт-в-байт прежний.
```

---

## Выход этапа

- подтверждено: DI, `BLOCK_ORDER` (`rag` после `tools`), `DELIVERABLE`, `/rag`, `[RAG]`-лог;
- ответ агента при активном RAG несёт источники/цитаты/`verdict`;
- `test_rag_integration.py`/`test_prompt.py` — зелёные; без `--rag` промпт идентичен;
- запись «Этап 10» в `dev/migr_log.md`.

## Гейт 10→11 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `BLOCK_ORDER` | `tools < rag < long_term` |
| 2 | `DELIVERABLE` содержит `rag` | ✅ |
| 3 | без `--rag` промпт | байт-в-байт прежний |
| 4 | с `--rag` | блок `[rag]` есть, в бюджете |
| 5 | пустой индекс | блока нет, агент отвечает |
| 6 | RAG не меняет `TaskStage`/`transition_log` | ✅ |
| 7 | `python Kod.py --rag --mock` | поднимается, печатает `[RAG]` |
| 8 | `test_rag_integration.py`/`test_prompt.py`/`unit_runner.py` | зелёные, без регрессии |
| 9 | `git diff --stat requirements.txt` | пусто |
| 10 | запись «Этап 10» + перечитывание `migr_plan.md` | ✅ |

## Откат

`git checkout -- core/agent.py core/prompt_builder.py Kod.py storage/store.py
dev/tests_debug/unit/test_rag_integration.py`. Запись ❌.

## Что передаём дальше

- **Этапу 11 (R9):** рабочий RAG-слой в агентском цикле + память задачи + 2 сценария.
- **Этапу 12 (Ф):** `--rag`/`/rag` — в документацию и проверки приёмки.
