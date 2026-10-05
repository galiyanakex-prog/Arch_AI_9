# migr_plan_3.md — рабочий план этапа M3 «tools/call (инвентарь вызова)»

> Рабочий план этапа **M3** миграции `den_16` (Ревизия 2). **Конец — гейт в M4**.

---
## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **M3** — `tools/call` (настоящий вызов инструмента) |
| Зависит от | M2 |
| Открывает | `migr_plan_4.md` (M4 — `ToolExecutor`/`ToolPolicy`/аудит) |
| Тип изменений | `integrations/mcp/{transport,client,gateway}.py`, `core/tools.py` |
| Живой прогон | **Да** (`search_locations({"query":"Москва"})`) |
| Точка отката | Гейт M2→M3 |

**Цель.** Реализовать настоящий вызов инструмента на всех транспортах и нормализацию
результата; контракт `ToolExecutionResult`.

---

## 1. Шаги этапа

### Шаг 3.1 — `call_tool` в транспортах (`transport.py`)
- `MCPTransport.call_tool(name, arguments) -> object` (убрать `NotImplementedError`).
- `FakeMCPTransport.call_tool` — программируемые ответы: `tool_results: dict[name→result]`,
  флаги `fail_call`, `error_call` (`isError=True`).
- `StdioMCPTransport.call_tool` / `HttpMCPTransport.call_tool`:
  `result = await self._session.call_tool(name, arguments)`; нормализация →
  `{"isError": bool, "text": <агрегат текстовых content>, "raw": <result>}`.

### Шаг 3.2 — `MCPClient.call_tool` (`client.py`)
- `call_tool(name, arguments)` — делегирует транспорту, сбой → `MCPConnectionError`;
  нормализованный dict результата.

### Шаг 3.3 — `MCPGateway.call_tool` (`gateway.py`)
- `call_tool(provider, tool_name, arguments)`: находит сервер по `provider`; сервер не
  READY → понятная ошибка; делегирует `client.call_tool`; возвращает `ToolExecutionResult`
  (id, tool=квалифицированное имя, status=succeeded/failed, summary=краткий текст, raw).

### Шаг 3.4 — Контракт результата (`core/tools.py`)
- Уточнить `ToolCallRequest` (name, arguments) и `ToolExecutionResult`
  (execution_id, tool, status, summary, raw); добавить `ToolExecutionState` (requested/
  denied/waiting_confirmation/running/succeeded/failed/timed_out/cancelled).
- `execution_id` — детерминированный формат (напр. `exec-<n>`/uuid-хелпер).

### Шаг 3.5 — Проверка
- Примитив-тест (fake): успешный вызов, `isError`, исключение.
- **Живой** вызов: `search_locations({"query":"Москва"})` → текст содержит `Moscow`,
  `55.75…`, `37.61…`.

---

## 2. Выход этапа
- `call_tool` работает на fake/stdio/http; нормализованный результат; контракт зафиксирован.
- Живой вызов реального тула с аргументом-городом.
- Запись M3 в `migr_log.md`.

## 3. Гейт M3→M4
- [ ] `call_tool` (fake) — успех/`isError`/исключение (не молчит);
- [ ] живой `search_locations({"query":"Москва"})` → координаты Москвы;
- [ ] `ToolExecutionResult`/`ToolExecutionState` зафиксированы в `core/tools.py`;
- [ ] SDK — только в `integrations/mcp/`; L1/L2 без регрессии.

**Зелёный** → запись ✅ → перечитать `migr_plan.md` → `migr_plan_4.md`.

## 4. Запись в `migr_log.md`
По форме §6.4; в «Проверка» — живой вывод вызова (координаты Москвы).

## 5. Следующий шаг
Перечитать `dev/migr_plan.md` → M4 (`migr_plan_4.md`): `ToolExecutor` + `ToolPolicy` +
аудит.