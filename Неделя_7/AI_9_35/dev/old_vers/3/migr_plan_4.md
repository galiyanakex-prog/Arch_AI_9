# migr_plan_4.md — рабочий план этапа M4 «ToolExecutor + ToolPolicy + аудит»

> Рабочий план этапа **M4** миграции `den_16` (Ревизия 2). **Конец — гейт в M5**.

---
## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **M4** — процедура контролируемого вызова в `core` |
| Зависит от | M3 |
| Открывает | `migr_plan_5.md` (M5 — LLM-клиент с tool-use) |
| Тип изменений | Новые `core/tool_policy.py`, `core/tool_executor.py`; задействование Store audit |
| Живой прогон | Не требуется (сеть — на M9); фейк/примитивы |
| Точка отката | Гейт M3→M4 |

**Цель.** Обернуть вызов инструмента проверками (policy) и аудитом, **не меняя**
`StateMachine`: «инструмент ≠ переход».

---

## 1. Шаги этапа

### Шаг 4.1 — `core/tool_policy.py` (минимал)
- Функция/класс `ToolPolicy` со ступенями (порядок канона рекомендаций):
  1. инструмент существует (`registry.get`);
  2. инструмент включён (`descriptor.enabled`);
  3. аргументы соответствуют схеме (`input_schema`: required/properties — мягкая проверка);
  4. стадия разрешает (`task_stage ∈ descriptor.allowed_stages`);
  5. инварианты разрешают (существующий `InvariantChecker` поверх `ProposedAction` с
     `action_type`/`tool_name`/`arguments` — расширение задел-совместимое);
  6. требуется подтверждение (`descriptor.requires_confirmation`).
- Возврат: `allowed` + причина/категория (`denied`).

### Шаг 4.2 — `core/tool_executor.py`
- `ToolExecutor(registry, policy, gateway, store, invariant_checker, log)`.
- `execute(request, context) -> ToolExecutionResult`:
  policy → при отказе: status=`denied`, аудит, возврат; при разрешении: `gateway.call_tool`
  → status=succeeded/failed → **аудит** `store.append_tool_audit(user_id, task, record)`.
- Аудит-запись: execution_id, tool, provider, status, `arguments_hash` (хэш, не сырые
  аргументы), duration_ms, error, at.
- **Никаких** вызовов `StateMachine`/`try_transition`.

### Шаг 4.3 — Расширение `ProposedAction` (задел-совместимо, `core/invariants.py`)
- Добавить **опциональные** поля `action_type: str = ""`, `tool_name: str | None = None`,
  `arguments: dict | None = None` (обратно совместимо: старые конструирования не ломаются).
- Правило «нельзя менять схему БД» работает и для MCP-тула (по `tool_name`/аргументам).

### Шаг 4.4 — Проверка
- Примитив: разрешённый вызов (fake gateway) исполняется и аудируется;
- отказ по стадии/инварианту/confirmation → не исполняется, аудит `denied`;
- после вызова `TaskStage` не изменился, `transition_log` пуст.

---

## 2. Выход этапа
- `ToolExecutor` + `ToolPolicy` + аудит; `ProposedAction` расширен обратно совместимо.
- Проверки: исполнение/отказ/аудит; «инструмент ≠ переход».
- Запись M4 в `migr_log.md`.

## 3. Гейт M4→M5
- [ ] `ToolExecutor` исполняет разрешённый вызов и пишет `tool_audit.jsonl`;
- [ ] отказ policy (стадия/инвариант/confirmation) не исполняет, аудирует `denied`;
- [ ] `TaskStage` не меняется; `transition_log` пуст;
- [ ] `ProposedAction` расширен обратно совместимо (старые тесты инвариантов зелёные);
- [ ] L1/L2 без регрессии; `state_machine` не тронут.

**Зелёный** → запись ✅ → перечитать `migr_plan.md` → `migr_plan_5.md`.

## 4. Запись в `migr_log.md`
По форме §6.4.

## 5. Следующий шаг
Перечитать `dev/migr_plan.md` → M5 (`migr_plan_5.md`): LLM-клиент с поддержкой tool-use.