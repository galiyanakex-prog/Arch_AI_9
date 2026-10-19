# migr_plan_6.md — рабочий план этапа M6 «CLI: DI + /mcp + --mcp-probe»

> **Роль документа.** Рабочий план-алгоритм **одного этапа** миграции проекта `den_16`
> на целевую архитектуру `Nedela_4/den_16/arch_den_16.md`. Разворачивает этап **M6** из
> `migr_plan.md` §4. Закрывает рабочие команды и флаги результата задания
> (`arch_den_16.md` §2.6).
> **Конец этого этапа — автоматический гейт в этап M7** (`migr_plan_7.md`).
> Источники: `migr_plan.md` (эталон), `arch_den_16.md` §2.6, §2.8,
> `Задание_d16.txt` (результат: «код, который подключается к MCP и выводит список
> доступных инструментов»), `Рекомендации_MCP_d16.txt` (DI-композиция;
> mcp_enabled=False по умолчанию).

---

## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **M6** — CLI: DI + `/mcp` + `--mcp-probe` |
| Рабочий план | `dev/migr_plan_6.md` (этот файл) |
| Зависит от | **M1–M5** (контракты, реестр, MCP-слой, хранение) |
| Открывает | `dev/migr_plan_7.md` (M7 — Тесты и отладка) |
| Закрывает | `arch_den_16.md` §2.6 (DI-композиция, /mcp-семейство, флаги) |
| Основные артефакты | `Kod.py` (расширение) |
| Живой ключ | **Не нужен** (REPL-смоук на FakeMCPTransport; LLM не участвует) |
| Меняет поведение | **Да, опционально**: без `--mcp` поведение = den_15 (MCP off по умолчанию) |

**Цель этапа.** Результат задания становится рабочим кодом: `--mcp-probe`
(one-shot: подключиться → handshake → tools/list → вывести список → закрыться) и
семейство `/mcp` в REPL (status/servers/tools/refresh/connect/disconnect) — один
кодовый путь `MCPGateway → MCPToolProvider → ToolRegistry`. DI собирает MCP-слой
только при `mcp_enabled`.

---

## 1. Вход и предусловия

- `core/tools.py`, `core/tool_registry.py`, `integrations/mcp/*`,
  `storage/store.py` (M1–M5) — готовы.
- `Kod.py` текущий: `build_agent()` (DI дней 11–15), REPL, 12 флагов.
- M1–M5 зелёные (L2 91/0).

**Предусловия:** прежние команды REPL не тронуты; `/mcp`-команды токенов LLM не
тратят; `--mcp-probe` не требует идентификации пользователя (one-shot, без REPL);
REPL-режим требует `--user`/интервью как раньше.

---

## 2. Шаги этапа (исполняемый алгоритм)

### Шаг 6.1 — DI-композиция (`build_agent`)
1. Параметр `mcp_enabled: bool = False` (из флага `--mcp`).
2. При `mcp_enabled=True`: `servers = store.read_mcp_servers(user_id)` →
   `gateway = MCPGatewaySync(servers)` → `provider = MCPToolProvider(gateway)` →
   `tool_registry.add_provider(provider)` → `registry.refresh()` →
   `store.save_tool_catalog(user_id, snapshot)`; gateway хранится в агенте/контексте
   для `/mcp status|connect|disconnect`.
3. При `mcp_enabled=False`: реестр пуст, gateway не создаётся — поведение ровно
   как den_15.
4. **Ожидаемый результат:** MCP-слой опционален; циклов зависимостей нет
   (gateway не знает об агенте; агент — только о реестре/фасаде gateway).

### Шаг 6.2 — Семейство `/mcp` (6 форм)
1. `/mcp status` — состояние подключения по серверам (`MCPConnectionState`),
   версия каталога, счётчик тулов; без MCP — «MCP выключен (включите: --mcp)».
2. `/mcp servers` — список сконфигурированных серверов (server_id, transport,
   enabled, trust_level, allowed/denied).
3. `/mcp tools` — **результат задания**: таблица доступных инструментов из
   `registry.snapshot()` (квалифицированное имя, description, input-схема —
   компактно); пустой каталог → подсказка «/mcp refresh».
4. `/mcp refresh` — `gateway.discover()` → `registry.refresh()` (атомарный swap) →
   `store.save_tool_catalog(...)`; отчёт: сколько тулов, какие серверы живы.
5. `/mcp connect <id>` — включить/поднять соединение с сервером (по умолчанию —
   все из servers.json при старте); неизвестный id → подсказка.
6. `/mcp disconnect <id>` — закрыть соединение (тулы сервера покидают каталог при
   следующем refresh).
7. **Ожидаемый результат:** 6 форм; без активной задачи не требуют её; ошибки
   серверов не роняют REPL (деградация: память/профили/автомат работают).

### Шаг 6.3 — Флаги `--mcp` и `--mcp-probe`
1. `--mcp` — включить MCP-слой в REPL (см. 6.1).
2. `--mcp-probe` — one-shot результат задания: `load servers.json` →
   `gateway.start()` → handshake → `discover()` → вывод списка (имя, description,
   input-схема каждого тула) → `gateway.stop()` → exit 0; недоступный сервер →
   понятная ошибка в stderr, exit 1; **не входит в REPL** (взаимоисключаем с
   обычным запуском).
3. Итого флагов **14** (12 прежних + 2); `/help` — обновлён (семейство `/mcp`,
   флаги).
4. **Ожидаемый результат:** `python Kod.py --mcp-probe` (на fake-транспорте в
   тестах; на stdio — с demo_server) печатает список тулов.

### Шаг 6.4 — REPL-смоук этапа (инлайн, `.tmp/`, FakeMCPTransport)
```bash
python - <<'EOF'
# Ветка A (--mcp-probe, fake):
#   probe → READY → 3 тула выведены → exit 0
# Ветка B (REPL --mcp, fake):
#   /mcp connect → READY
#   /mcp tools → 3 тула (имя/description/схема)
#   /mcp refresh → «3 тулов, каталог сохранён» (catalog.json на диске)
#   /mcp status → READY + version каталога
#   /mcp disconnect → DISCONNECTED
# Ветка C (без --mcp):
#   /mcp status → «MCP выключен»; /plan → /approve → /run → done (как den_15)
# Ветка D (недоступный сервер):
#   /mcp connect bad → FAILED, REPL жив, /memory и /state работают
EOF
```
**Ожидаемый результат:** все ветки OK; временные файлы — только в `.tmp/`.

### Шаг 6.5 — Проверка границ и наследия
1. `grep -n "import mcp\|from mcp" Kod.py` → пусто (CLI не импортирует SDK —
   только через integrations).
2. Наследие: `/memory`, `/profile list`, `/deliver`, `/invariants`, `/check`,
   `/summary`, `/tokens`, `/cost`, `/plan`, `/approve`, `/goto`, `/transitions`,
   `/state` — работают (прогон в `.tmp/m6_heritage/`).
3. **Ожидаемый результат:** границы чистые; наследие не регрессирует.

### Шаг 6.6 — Регрессия
1. L1 → ok; L2 → **91 OK, 0 FAIL**; L3 → SMOKE OK; L4 → 9/9; гейт → 13+2⚠
   (без новых красных).
**Ожидаемый результат:** полная нерегрессия.

---

## 3. Выход этапа

- `Kod.py` — DI с `mcp_enabled`, семейство `/mcp` (6 форм), флаги `--mcp`/
  `--mcp-probe`, обновлённый `/help`.
- REPL-смоук этапа (4 ветки).
- Запись этапа **M6** в `dev/migr_log.md`.

---

## 4. Автоматический гейт M6→M7

Гейт считается **зелёным**, если одновременно:
- [ ] `--mcp-probe` выводит список тулов и завершается exit 0 (fake);
      недоступный сервер → exit 1 с понятной ошибкой;
- [ ] `/mcp` — 6 форм работают (connect/tools/refresh/status/disconnect/servers);
- [ ] `/mcp tools` показывает имя/description/схему каждого тула (результат задания);
- [ ] `/mcp refresh` делает атомарный swap и сохраняет catalog.json через Store;
- [ ] без `--mcp` поведение = den_15 (ветка C смоука);
- [ ] недоступный сервер не роняет REPL (деградация);
- [ ] `Kod.py` не импортирует `mcp` SDK (grep);
- [ ] наследие дней 11–15 не регрессирует (смоук наследия);
- [ ] L1 зелёный; L2 **91 OK, 0 FAIL**; L3 OK; L4 9/9; гейт 13+2⚠.

**Зелёный** → запись M6 в `migr_log.md` (✅) → **перечитать `migr_plan.md`** →
создать `migr_plan_7.md`.
**Красный** → карточка ошибки, этап M6 открыт.

---

## 5. Запись в `migr_log.md` (форма §6.4)

```text
## Этап M6 — CLI: DI + /mcp + --mcp-probe
- Статус: ✅ завершён | ⚠️ обход | ❌ открыт
- Было: MCP-слой готов, но не подключён к CLI; флагов 12
- Стало: <DI mcp_enabled; /mcp 6 форм; --mcp/--mcp-probe; /help обновлён;
  флагов 14>
- Проверка: <REPL-смоук (4 ветки); grep; наследие; L1/L2/L3/L4/гейт>
- Артефакты: Kod.py
- Спорное/риски: <если есть>
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (дата/время)
- Гейт M6→M7: ✅ пройден | ❌ не пройден
```

---

## 6. Следующий шаг

Перечитать актуальный `dev/migr_plan.md`, затем приступить к **M7** по
`dev/migr_plan_7.md` (тесты: `unit/test_mcp.py` на FakeMCPTransport;
`scenario_mcp_discovery`; smoke + MCP; гейт 15 → 18 проверок).
