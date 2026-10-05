# migr_plan_7.md — Этап 7. D5: таймауты транспорта

> Рабочий план-алгоритм **одного этапа** на основе `dev/migr_plan.md` (Ревизия 5).
> Контур: **D (правки продукта)**. Метка: **D5**. Коммиты — только за оператором.

## Цель этапа
`asyncio.wait_for` в `initialize`/`list_tools`/`call_tool`; таймаут →
`MCPConnectionError("таймаут …")`, состояние `FAILED`, процесс жив.

## Предусловия (выполнено)
- Этап 4 ✅: D5 воспроизведён (`grep wait_for` пусто).
- Этап 5 ✅: D1 закрыт.

## Границы этапа
Не меняем сигнатуры транспортов и `MCPConnectionError`. Правки — только
`integrations/mcp/transport.py` + тест.

---

## Шаги

### ШАГ 7.1 — `_with_timeout` в `_SessionTransport`
Обёртка `asyncio.wait_for(coro, timeout=self._timeout)`; `TimeoutError` →
`MCPConnectionError(server_id, "таймаут <что> (<N> с)")`.

### ШАГ 7.2 — применить в трёх методах
`list_tools`, `call_tool`, `initialize` (stdio и HTTP: подключение/сессия/initialize).

### ШАГ 7.3 — юнит-тест + живая регрессия
`dev/tests_debug/unit/test_d5_timeout.py` (зависшая сессия → таймаут; быстрая →
проходит). Живой прогон: реальные серверы не режутся ложно.

---

## Гейт 7→8
| # | Проверка | Ожидаемо |
|---|---|---|
| 1 | unit-тест таймаута | 3 OK |
| 2 | `--mcp-probe` (живой) | READY, exit 0, без ложных FAILED |
| 3 | `SCHEDULER/PIPELINE_MCP_ENABLED=1` | 4 READY, 15 тулов, exit 0 |
| 4 | регрессия L2/L3/L4/гейт | 131 OK · SMOKE OK · SCENARIO OK · 21/21 |

## Перечитывание
После гейта — перечитать `dev/migr_plan.md` (§4 «Этап 8», §6) и создать
`dev/migr_plan_8.md`.
