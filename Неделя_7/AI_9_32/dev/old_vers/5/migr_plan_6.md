# migr_plan_6.md — Этап 6. D2: каталог реально в промте

> Рабочий план-алгоритм **одного этапа** на основе `dev/migr_plan.md` (Ревизия 5).
> Контур: **D (правки продукта)**. Метка: **D2**. Коммиты — только за оператором.

## Цель этапа
При `--mcp` в промте появляется блок `[tools]` с `mcp.*`; `render_tool_protocol`
перечисляет имена + обязательные аргументы; при MCP off блока нет.

## Предусловия (выполнено)
- Этап 4 ✅: D2 воспроизведён (`tools` затёрт `--deliver`).
- Этап 5 ✅: D1 закрыт (probe зелёный).

## Границы этапа
Не меняем `PromptBuilder.build` (блок `[tools]` уже поддержан). Правки — `Kod.py`
(порядок deliver), `core/llm_client.py` (протокол от каталога), `core/agent.py`
(использование), тесты.

---

## Шаги

### ШАГ 6.1 — `Kod.py`: `tools` не затирается
После `agent.deliver = deliver & set(DELIVERABLE)` — при `--mcp` (и без
`--no-tools-block`) добавить `agent.deliver.add("tools")`. Новый флаг
`--no-tools-block` (диагностика).

### ШАГ 6.2 — `render_tool_protocol(tools)`
В `core/llm_client.py`: протокол от каталога (имена + обязательные аргументы);
пустой каталог → `TOOL_PROTOCOL_PROMPT`.

### ШАГ 6.3 — `core/agent.py`
`_respond_with_tools` использует `render_tool_protocol(tools)` вместо статичной
строки.

### ШАГ 6.4 — юнит-тест + регрессия
`dev/tests_debug/unit/test_d2_tools_prompt.py` (3 функции); L2/L3/L4/гейт; запись
«Этап 6» в `dev/migr_log.md`.

---

## Гейт 6→7 (живой)
| # | Проверка | Ожидаемо |
|---|---|---|
| 1 | `--mcp` → `[Режим] Доставка слоёв` | содержит `tools` |
| 2 | `--mcp --no-tools-block` | `tools` отсутствует |
| 3 | без `--mcp` | `tools` отсутствует (регрессия) |
| 4 | `render_tool_protocol` | имена + обязательные аргументы |
| 5 | регрессия L2/L3/L4/гейт | 128 OK · SMOKE OK · SCENARIO OK · 21/21 |

## Перечитывание
После гейта — перечитать `dev/migr_plan.md` (§4 «Этап 7», §6) и создать
`dev/migr_plan_7.md`.
