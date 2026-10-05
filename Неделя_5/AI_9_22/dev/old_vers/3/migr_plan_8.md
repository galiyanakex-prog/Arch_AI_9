# migr_plan_8.md — рабочий план этапа M8 «CLI/DI: tool-use, /mcp call, env»

> Рабочий план этапа **M8** миграции `den_16` (Ревизия 2). **Конец — гейт в M9**.

---
## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **M8** — пользователь запускает tool-use из REPL и вызывает тул вручную |
| Зависит от | M7 |
| Открывает | `migr_plan_9.md` (M9 — живой прогон «найди город Москва») |
| Тип изменений | `Kod.py` (DI, флаги, `/mcp call`, env) |
| Живой ключ | Для гейта не нужен (`--mock`); живой прогон — M9 |
| Точка отката | Гейт M7→M8 |

**Цель.** Включить полный tool-use в REPL и дать ручной вызов инструмента.

---

## 1. Шаги этапа

### Шаг 8.1 — DI при `--mcp` (`Kod.py::build_agent`)
- При `mcp_enabled`: добавить `ToolPolicy`, `ToolExecutor` (с `gateway`, `registry`,
  `store`, `checker`); `agent.tool_executor = executor`; доставка включает `tools`
  (`agent.deliver.add("tools")`); задать `ToolPromptPolicy` (лимиты).
- `catalog.refresh()` при старте (`--mcp`) — чтобы каталог был готов к tool-use
  (реальный discovery к `weatherapi`); при недоступности — деградация, REPL жив.
- Endpoint берётся из env `MCP_WEATHER_URL` (иначе дефолт `config.py`).

### Шаг 8.2 — Команда `/mcp call <tool> <json>`
- Ручной вызов: `tool_executor.execute(ToolCallRequest(name, arguments))` → печать
  `ToolExecutionResult` (status, summary, при желании — фрагмент raw).
- Обновить `/help` и строку команд в README.

### Шаг 8.3 — Совместимость
- Без `--mcp`: `agent.tool_executor = None`, каталог не строится, поведение = den_15.
- `/mcp`-команды без `--mcp` — прежнее сообщение «MCP-слой выключен».

### Шаг 8.4 — Проверка
- `--mcp --mock`: намерение «найди город Москва» → тул (fake) → ответ;
- `/mcp call search_locations {"query":"Москва"}` (fake) → результат;
- без `--mcp` — регрессия.

---

## 2. Выход этапа
- tool-use доступен в REPL под `--mcp`; ручной `/mcp call`; env-endpoint; совместимость.
- Запись M8 в `migr_log.md`.

## 3. Гейт M8→M9
- [ ] `--mcp --mock` + «найди город Москва» → вызов тула → ответ;
- [ ] `/mcp call` работает (fake);
- [ ] без `--mcp` — поведение = den_15 (регрессия зелёная);
- [ ] `MCP_WEATHER_URL` учитывается;
- [ ] L1/L2/L3/L4 без регрессии.

**Зелёный** → запись ✅ → перечитать `migr_plan.md` → `migr_plan_9.md`.

## 4. Запись в `migr_log.md`
По форме §6.4.

## 5. Следующий шаг
Перечитать `dev/migr_plan.md` → M9 (`migr_plan_9.md`): живой прогон «найди город Москва».