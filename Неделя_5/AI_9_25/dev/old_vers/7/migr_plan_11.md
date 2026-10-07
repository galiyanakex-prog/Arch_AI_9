# migr_plan_11.md — Этап 11. Часть 4: RAG в каждом обмене + память задачи + 2 сценария (R9)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (Ревизия 7, §4 «Этап 11»).
> Контур: **R (RAG-ядро)**. Метка цели: **R9**. Зависимости: **этапы 9–10**.
> Порядок: **пошагово с оператором**. **Коммиты — только за оператором** (ШАГ 11.7).

## Цель этапа

**Часть 4 `Задание.txt`:** **существующий CLI-агент** хранит историю диалога, при
**каждом** вопросе ищет контекст через RAG, отвечает с учётом найденного, **всегда выводит
источники**; усиление — **память задачи** (цель диалога, уточнения, ограничения, термины);
проверка на **2 длинных сценариях** по 10–15 сообщений.

> **Ключевое (оператор):** AI_9 — это **и есть** полноценный чат-агент, **не «мини»**.
> Часть 4 — **инкрементальное улучшение** существующего агента: **никаких** `core/chat.py`,
> `core/task_state.py`, `--chat*`, `/chat*`.

> **Фундамент есть (Ревизия 6):** `ShortTermMemory`/`session.json` (история, окно 10);
> `core/agent.py._rag_retrieve` — **один поиск на обмен** с `_rag_turn`-кэшем (RAG уже
> в каждом обмене); `_grounding_guard`; `last_rag_hits`.
> **Новое:** расширение `WorkingMemory` (память задачи) + 2 длинных сценария + тест.

## Предусловия

- `memory/working.py` — `WorkingMemory` (поля `description`, `refs`, `decisions`,
  `constraints`, `facts`, `open_questions`, `current_state`, `lifecycle_summary`).
- `core/agent.py._rag_retrieve` — поиск на каждый обмен (этап 10 закрыт).
- `Answer` с источниками/цитатами (этап 9).
- `dev/tests_debug/scenario/scen_rag.md` — есть; `scenario.py` — движок автопрогонов.

## Границы этапа

- **Не** создаём новых подсистем (`core/chat.py`, `core/task_state.py` — запрещены).
- **Не** дублируем историю: переиспользуем `ShortTermMemory`/`session.json`.
- **Не** меняем `TaskStage`/`ALLOWED_TRANSITIONS` от RAG.
- **Не** меняем `requirements.txt`.

---

## Шаги

### ШАГ 11.1 — Аудит RAG-на-каждый-обмен (агент)

```bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
grep -nE "_rag_retrieve|_rag_turn|message_counter|last_rag_hits" core/agent.py | head
```

Подтвердить: `_rag_retrieve` вызывается в сборке контекста на **каждый** обмен; кэш
`_rag_turn == message_counter` исключает дубль-поиск в рамках одного обмена; ошибки RAG
не роняют ответ.

### ШАГ 11.2 — Расширение `WorkingMemory` полями памяти задачи (агент)

Добавить в `memory/working.py` поля: `goal` (цель диалога), `clarifications[]` (что уточнил
пользователь), `constraints[]` (ограничения), `terms{}` (зафиксированные термины).
Обновление — **merge** (не перезапись); детерминированно по триггерам-фразам
(«цель: …», «уточняю: …», «ограничение: …», «термин X — это …»), опционально через LLM
(фолбэк — эвристика). Хранение — в существующем `working_memory.json`; вывод — в блок
`[working]` (`as_prompt_block`).

```python
# merge-обновление в WorkingMemory.write:
for key, value in updates.items():
    if key == "goal":
        data["goal"] = value
    elif key in ("clarifications", "constraints"):
        data.setdefault(key, []).append({"text": value, "source_message_id": item.source_message_id})
    elif key == "terms":
        data.setdefault("terms", {}).update(value if isinstance(value, dict) else {})
    # ... существующие ветки ...
```

И в `as_prompt_block` — строки «Цель: …», «Уточнения: …», «Термины: …».

### ШАГ 11.3 — Обогащение поискового запроса памятью задачи (агент)

```bash
grep -nE "def _rag_retrieve|search\(|search_multi\(" core/agent.py | head
```

В `_rag_retrieve` (или перед вызовом) строить `query = вопрос ⊕ goal ⊕ terms`
(при наличии), чтобы поиск учитывал контекст диалога. Замер: не ухудшает hit-rate@5.

### ШАГ 11.4 — Тест `test_rag_working_memory.py` (агент)

Создать `dev/tests_debug/unit/test_rag_working_memory.py`:
- `WorkingMemory` расширена, сериализуется round-trip;
- `goal`/`terms` пополняются merge-ом и сохраняются к концу диалога;
- история (`ShortTermMemory`) растёт и переживает перезапуск;
- RAG вызывается на каждом сообщении при включённом слое;
- `len(sources) ≥ 1` в каждом ответе (при непустом индексе);
- `TaskStage` не затронут;
- без `--rag` промпт байт-в-байт прежний.

```bash
API_KEY=test-key .venv/bin/python dev/tests_debug/unit_runner.py 2>&1 | grep -iE "rag_working_memory|memory|Итого"
```

### ШАГ 11.5 — 2 длинных сценария (агент)

Создать `dev/tests_debug/scenario/scen_dialog_A.md` и `scen_dialog_B.md` — по **10–15
сообщений** каждый. Критерии: ассистент **не теряет цель** (`goal` учитывается в каждом
ответе), **источники в каждом ответе**.

Автопрогон через существующий `scenario.py` → `dev/logs_reports/stages/dialog_scenarios.md`:

```bash
API_KEY=test-key .venv/bin/python dev/tests_debug/scenario.py 2>&1 | tail -20
```

Ожидаемо: таблица «цель / источники / уточнения» по каждому сценарию.

### ШАГ 11.6 — Разделение сущностей (проверка) (агент)

```bash
.venv/bin/python - <<'EOF'
# история диалога — session.json (append-only, окно 10)
# память задачи  — working_memory.json (пересчитываемое состояние)
# очистка одного не сбрасывает другое
print("OK: ShortTermMemory ≠ WorkingMemory; RAG ≠ переход TaskStage")
EOF
```

### ШАГ 11.7 — Запись в журнал + коммит (оператор)

Запись «Этап 11» в `dev/migr_log.md`. **Предлагаемый коммит:**

```
feat(agent): RAG в каждом обмене + память задачи (расширение WorkingMemory) + 2 сценария
(этап 11, Ревизия 7)

Причина: часть 4 Задание.txt — история диалога + RAG на каждый обмен + память задачи
(цель/уточнения/ограничения/термины) + 2 длинных сценария. AI_9 — полноценный агент;
никаких core/chat.py, core/task_state.py, --chat*, /chat*.
```

---

## Выход этапа

- `memory/working.py` — поля `goal`/`clarifications`/`constraints`/`terms` (merge);
- `core/agent.py` — enrichment запроса памятью задачи;
- `dev/tests_debug/scenario/scen_dialog_A.md`, `scen_dialog_B.md` (10–15 сообщений);
- `dev/logs_reports/stages/dialog_scenarios.md` — прогон;
- `dev/tests_debug/unit/test_rag_working_memory.py` — зелёный;
- запись «Этап 11» в `dev/migr_log.md`.

## Гейт 11→12 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | RAG вызывается на каждом сообщении (при `--rag`) | ✅ |
| 2 | `len(sources) ≥ 1` в каждом ответе (непустой индекс) | ✅ |
| 3 | `goal` учитывается в каждом ответе | ✅ |
| 4 | `goal`/`terms` пополняются merge-ом и сохраняются | round-trip OK |
| 5 | история растёт и переживает перезапуск | ✅ |
| 6 | 2 сценария по 10–15 сообщений | созданы |
| 7 | `TaskStage` не затронут | ✅ |
| 8 | без `--rag` промпт байт-в-байт прежний | ✅ |
| 9 | `test_rag_working_memory.py` + `unit_runner.py` | зелёные, без регрессии |
| 10 | `git diff --stat requirements.txt` | пусто |
| 11 | запись «Этап 11» + перечитывание `migr_plan.md` | ✅ |

## Откат

`git checkout -- memory/working.py core/agent.py dev/tests_debug/unit/test_rag_working_memory.py`;
удалить `scen_dialog_A.md`/`scen_dialog_B.md` и отчёт. Запись ❌.

## Что передаём дальше

- **Этапу 12 (Ф):** сценарии и прогон — в `dev/Проверка.md`; память задачи — в `README.md`.
- **Финалу:** живой прогон 2 сценариев + гейт 33/33.
