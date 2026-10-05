# migr_plan_10.md — Этап 10. D6: пакет мелких исправлений

> Рабочий план-алгоритм **одного этапа** на основе `dev/migr_plan.md` (Ревизия 5).
> Контур: **D (правки продукта)**. Метка: **D6**. Коммиты — только за оператором.

## Цель этапа
Устранить 4 мелких дефекта продукта, найденных на этапе 4:
1. `/mcp connect <id>` поднимал ВСЕ серверы (а не целевой);
2. `summary=text[:500]` терял данные при передаче между шагами пайплайна;
3. терминальные стадии (done/failed/paused) не блокировали мутирующие инструменты;
4. assistant-сообщение в tool-use цикле было текстовым (`tool_call: …`) без
   валидного `tool_calls` (несовместимо с OpenAI-форматом).

## Предусловия (выполнено)
- Этап 4 ✅: D6 воспроизведён.
- Этапы 5–9 ✅: D1/D2/D5/D3/D4 закрыты; регрессия зелёная.

## Границы этапа
Правки: `integrations/mcp/gateway.py`, `Kod.py`, `core/tools.py`,
`core/tool_executor.py`, `core/tool_pipeline.py`, `core/tool_policy.py`,
`core/agent.py`. Инварианты: `overall_state()` не менять; инструмент ≠ переход;
SDK не протекает в `core`.

---

## Шаги

### ШАГ 10.1 — `/mcp connect <id>` только целевой сервер
`MCPGateway.start(only_server=None)` + фасад `MCPGatewaySync.start(only_server)`;
`Kod.py` передаёт `target`; печать состояния целевого сервера.

### ШАГ 10.2 — полный текст результата
`ToolExecutionResult.text` (полный) рядом с `summary` (≤500, для логов/аудита);
`gateway.call_tool` заполняет `text`; `tool_executor` пробрасывает;
`run_pipeline` несёт `text` между шагами; `agent._respond_with_tools` кладёт
`text` в tool-сообщение.

### ШАГ 10.3 — терминальные стадии read-only
`core/tools.py`: `TERMINAL_STAGES`, `infer_read_only(name)`; `tool_policy`:
на терминальной стадии разрешены только read-only (проверка ДО стадийного фильтра).

### ШАГ 10.4 — валидный tool_calls
`agent._respond_with_tools`: assistant-сообщение с `tool_calls` (id/type/function),
`tool_call_id` в tool-сообщении; `call_id` с fallback.

### ШАГ 10.5 — тесты + живой прогон
`dev/tests_debug/unit/test_d6_fixes.py` (5 функций); живой `/mcp connect time`
(только time READY, scheduler/pipeline disconnected); проверка 34 в гейте.

---

## Гейт 10→11 (живой)
| # | Проверка | Ожидаемо |
|---|---|---|
| 1 | unit `test_d6_fixes` | 5 OK |
| 2 | живой `/mcp connect time` | time READY; scheduler/pipeline disconnected |
| 3 | регрессия L2/L3/L4/гейт | 142 OK · SMOKE OK · SCENARIO OK · 24/24 |

## Перечитывание
После гейта — перечитать `dev/migr_plan.md` (§4 «Этап 11», §6) и создать
`dev/migr_plan_11.md`.
