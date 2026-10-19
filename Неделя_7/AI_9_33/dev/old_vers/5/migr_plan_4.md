# migr_plan_4.md — Этап 4. Базовая линия Ревизии 5 (M0)

> Рабочий план-алгоритм **одного этапа** на основе `dev/migr_plan.md` (Ревизия 5).
> Контур: **D (правки продукта)**. Метка: **M0** (зафиксировать «как есть»).
> Коммиты — только за оператором.

## Цель этапа
Зафиксировать фактическое состояние перед правками: счётчики регрессии и
**красные** проверки дефектов D1–D6. Это точка отсчёта «падало → проходит» для
этапов 5–10. Ничего не чиним.

## Предусловия (выполнено)
- Этапы 0–3 ✅: VPS-контур живой (time/scheduler/pipeline), `dev/vps/` готов.
- D1 воспроизведён живьём (этап 2); при всех живых серверах probe даёт exit 0
  (этап 3) — значит D1 зависит от состава `enabled`/доступности.

## Границы этапа
Только фиксация. Код не меняется. `migr_log.md` уже обнулён под Ревизию 5 (этап 0).

---

## Шаги

### ШАГ 4.1 — базовая линия (счётчики)
bash
.venv/bin/python -m py_compile Kod.py core/*.py memory/*.py storage/*.py \
  integrations/mcp/*.py integrations/scheduler/*.py
.venv/bin/python dev/tests_debug/unit_runner.py
API_KEY=test-key .venv/bin/python dev/tests_debug/smoke.py
API_KEY=test-key .venv/bin/python dev/tests_debug/scenario.py
API_KEY=test-key bash dev/tests_debug/check_acceptance.sh

**Зафиксировано:** L1 OK · L2 **122 OK / 0 FAIL** · L3 **SMOKE OK** ·
L4 **SCENARIO OK** · гейт **21/21 FAIL=0**.

### ШАГ 4.2 — красные проверки дефектов
| Дефект | Команда | Красный результат |
|---|---|---|
| **D1** | `Kod.py --mcp-probe` при недоступном сервере | `overall: degraded` → exit 1 (этап 2) |
| **D2** | REPL `--mcp` → `[Режим] Доставка слоёв` | `tools` **отсутствует** в списке (затёрт `--deliver`) |
| **D3** | `grep multiserver dev/tests_debug/scenario*` | пусто; `.tmp/m4_check.py` нет |
| **D4** | `/mcp route найди погоду в Москве` | печатает **весь каталог** (15 тулов), не кандидата |
| **D5** | `grep wait_for integrations/mcp/transport.py` | пусто (таймаут не применяется) |
| **D6** | `/mcp connect time` → `/mcp status` | поднимает **все** 4 сервера, не только `time`; `summary=text[:500]` |

### ШАГ 4.3 — запись в журнал
Запись «Этап 4» в `dev/migr_log.md` (счётчики + таблица красных проверок).

---

## Гейт 4→5
| # | Проверка | Ожидаемо |
|---|---|---|
| 1 | L1/L2/L3/L4/гейт | зелёные (счётчики выше) |
| 2 | D1–D6 воспроизведены | каждая — командой, с выводом |
| 3 | код продукта не изменён | `git diff` пуст по `Kod.py`, `core/`, `integrations/` |

## Перечитывание
После гейта — перечитать `dev/migr_plan.md` (§4 «Этап 5», §6) и создать
`dev/migr_plan_5.md`.
