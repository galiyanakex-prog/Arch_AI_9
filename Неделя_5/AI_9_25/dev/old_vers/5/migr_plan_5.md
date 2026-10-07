# migr_plan_5.md — Этап 5. D1: порог probe + `enabled`-политика

> Рабочий план-алгоритм **одного этапа** на основе `dev/migr_plan.md` (Ревизия 5).
> Контур: **D (правки продукта)**. Метка: **D1**. Коммиты — только за оператором.

## Цель этапа
`--mcp-probe` = «≥1 READY-сервер и непустой список» → `exit 0`; опция
`--mcp-probe-server <id>`; `scheduler`/`pipeline` `enabled=False` по умолчанию
(но зарегистрированы) + env-переопределение. `overall_state()` не меняется.

## Предусловия (выполнено)
- Этап 2 ✅: D1 воспроизведён живьём (`degraded` → exit 1).
- Этап 3 ✅: scheduler/pipeline подняты (для проверки env-флагов).
- Этап 4 ✅: базовая линия (122 OK · 21/21).

## Границы этапа
Не трогаем `overall_state()` (инвариант). Не меняем `MCPConnectionState`. Правки —
`Kod.py` (probe), `config.py` (enabled-политика), тесты.

---

## Шаги

### ШАГ 5.1 — `config.py`: `enabled`-политика
`_env_flag(name, default=False)`; `SCHEDULER_MCP_ENABLED`/`PIPELINE_MCP_ENABLED`
(по умолчанию False); в `DEFAULT_SERVERS` — `enabled=SCHEDULER_MCP_ENABLED` и т.д.

### ШАГ 5.2 — `Kod.py`: порог probe + `--mcp-probe-server`
`run_mcp_probe(only_server=None)`: успех = ≥1 READY + непустой список; печать
`READY: …; overall: …`; пустой каталог → exit 1; фильтр по `only_server`.

### ШАГ 5.3 — совместимость тестов
`check_acceptance.sh:211`, `smoke.py:237`: `(READY)` → `(READY`.

### ШАГ 5.4 — новый юнит-тест
`dev/tests_debug/unit/test_d1_probe.py` (3 функции): политика enabled, env-флаги,
неизменность `overall_state()`.

### ШАГ 5.5 — регрессия + запись
L2/L3/L4/гейт; запись «Этап 5» в `dev/migr_log.md`.

---

## Гейт 5→6 (живой)
| # | Проверка | Ожидаемо |
|---|---|---|
| 1 | `--mcp-probe` без env | `READY: time, weather`, exit 0 |
| 2 | `--mcp-probe-server time` | `READY: time`, 1 тул, exit 0 |
| 3 | env `SCHEDULER/PIPELINE_MCP_ENABLED=1` | 4 READY, 15 тулов, exit 0 |
| 4 | все адреса мёртвые | exit 1 |
| 5 | регрессия L2/L3/L4/гейт | 125 OK · SMOKE OK · SCENARIO OK · 21/21 |
| 6 | `overall_state()` не изменён | тест `test_overall_state_semantics_unchanged` OK |

## Перечитывание
После гейта — перечитать `dev/migr_plan.md` (§4 «Этап 6», §6) и создать
`dev/migr_plan_6.md`.
