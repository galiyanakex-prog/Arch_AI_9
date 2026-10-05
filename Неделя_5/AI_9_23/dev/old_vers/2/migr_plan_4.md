# migr_plan_4.md — рабочий план этапа M4 «MCP-слой: gateway / provider / demo_server»

> **Роль документа.** Рабочий план-алгоритм **одного этапа** миграции проекта `den_16`
> на целевую архитектуру `Nedela_4/den_16/arch_den_16.md`. Разворачивает этап **M4** из
> `migr_plan.md` §4. Закрывает шлюз, провайдер и локальный демо-сервер
> (`arch_den_16.md` §2.4, часть 2).
> **Конец этого этапа — автоматический гейт в этап M5** (`migr_plan_5.md`).
> Источники: `migr_plan.md` (эталон), `arch_den_16.md` §2.4, §2.8,
> `Рекомендации_MCP_d16.txt` (gateway — адаптер, не контролёр; не знает о стадиях/
> профилях/памяти), `Суть_N4.md` §3.3 (изоляция прав через тулинг), §3.7 (погодный
> пример: units Celsius|Kelvin + location).

> **Синхронизировано с фактом реализации: 2026-09-24.** Правки внесены строго по
> `README.md` (факт реализации) и `dev/migr_log.md` (история процесса) — оба
> равноправные источники истины. `dev/migr_log.md` не изменялся; исходная версия —
> в `dev/old_vers/`.

---
## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **M4** — MCP-слой: gateway / provider / demo_server |
| Рабочий план | `dev/migr_plan_4.md` (этот файл) |
| Зависит от | **M3** (config/transport/client) |
| Открывает | `dev/migr_plan_5.md` (M5 — Хранение: servers.json + catalog.json) |
| Закрывает | `arch_den_16.md` §2.4 (gateway.py, provider.py, demo_server.py), §2.8 (механика discovery) |
| Основные артефакты | `integrations/mcp/{gateway,provider,demo_server}.py` |
| Живой ключ | **Не нужен** (fake — гейт; stdio-подпроцесс — интеграционный прогон) |
| Меняет поведение | **Нет** (слой не подключён к агенту до M6) |

**Цель этапа.** `MCPGateway` — адаптер внешних возможностей: состояние подключения
(`MCPConnectionState`), start/stop, discovery с фильтром прав
(allowed/denied_tools); `MCPToolProvider` — нормализация mcp-тулов во внутреннюю
модель `ToolDescriptor`; `demo_server.py` — минимальный локальный stdio MCP-сервер
(3 тула) для демо и интеграционного прогона. Gateway **не знает** о TaskStage/
профилях/памяти.

---

## 1. Вход и предусловия

- `integrations/mcp/{config,transport,client}.py` после M3 (SDK, fake, дефолты).
- M1–M3 зелёные (L2 91/0).

**Предусловия:** gateway/provider не импортируют `state_machine`, `agent`,
`memory`, `storage`; async внутри, синхронный фасад наружу (`MCPGatewaySync`);
demo_server — самостоятельный модуль, запускаемый `python -m`.

---

## 2. Шаги этапа (исполняемый алгоритм)

### Шаг 4.1 — `gateway.py`: состояние подключения + шлюз
1. `class MCPConnectionState(str, Enum)`: `DISCONNECTED`, `CONNECTING`, `READY`,
   `DEGRADED` (задел: часть серверов недоступна), `FAILED`.
2. `class MCPGateway`: конструктор `(servers: list[MCPServerConfig])`; поля —
   клиенты по `server_id`, состояния по серверам.
3. `async start()`: для каждого включённого сервера — `CONNECTING` →
   `client.initialize()` → `READY`; сбой → `FAILED` (не падение; остальные
   серверы продолжают); все упали → общий статус `FAILED`.
4. `async stop()`: закрытие транспортов → `DISCONNECTED` (чистое отключение).
5. `status() -> dict`: по серверам — состояние, версия протокола/capabilities
   (из initialize), счётчик тулов.
6. `async discover() -> list[ToolDescriptor]`: `list_tools()` у каждого сервера в
   `READY` → фильтр прав (`allowed_tools` — если непусто, только перечисленные;
   `denied_tools` — всегда исключаются) → нормализация: `name=f"mcp.{server_id}.
   {original_name}"`, `source="mcp"`, `provider=server_id`, `original_name`,
   `description`, `input_schema`; сервер в `FAILED` → его тулы не попадают
   (каталог честен: нет соединения — нет тулов).
7. `class MCPGatewaySync`: синхронный фасад над `start`/`stop`/`discover`/`status`
   на **постоянном фоновом event loop** (`threading.Thread` +
   `run_coroutine_threadsafe`; сессии `mcp` SDK привязаны к loop'у initialize,
   поэтому `asyncio.run` на каждый вызов несовместим) — для REPL и `--mcp-probe`
   (REPL остаётся синхронным; полный async core — задел).
8. **Ожидаемый результат:** gateway по arch §2.4/§2.8; изоляция прав через тулинг.

### Шаг 4.2 — `provider.py`: MCPToolProvider
1. `class MCPToolProvider(ToolProvider)`: конструктор `(gateway: MCPGateway)`;
   `provider_id() -> "mcp"`.
2. `discover() -> list[ToolDescriptor]`: `gateway.discover()` (синхронная обёртка
   над async — провайдер синхронный по контракту `ToolProvider`); тулы уже
   нормализованы gateway'ем.
3. **Ожидаемый результат:** провайдер — тонкий адаптер над gateway; без своей
   логики нормализации (она в gateway).

### Шаг 4.3 — `demo_server.py`: локальный stdio MCP-сервер
1. Минимальный сервер на `mcp` SDK (stdio): 3 тула —
   `get_time` (текущее время, без аргументов), `echo` (текст → текст),
   `weather_stub` (аргументы: `location` — required, `units` — enum
   Celsius|Kelvin; ответ — заглушка «Погода в <location>: …»).
2. Описание каждого тула: `description` (что возвращает) + `inputSchema`
   (что передать, что обязательно) — канон лекции (§3.5 Суть_N4).
3. Запуск: `python -m integrations.mcp.demo_server` (блокирующий stdio-режим).
4. **Ожидаемый результат:** сервер стартует и отвечает по протоколу; тулы
   соответствуют канону описания.

### Шаг 4.4 — Примитив-смоук этапа (инлайн, `.tmp/`, fake)
```bash
python - <<'EOF'
# 1. Gateway([demo-config], transport=fake): start → READY; status → demo/READY
# 2. discover() → 3 тула mcp.demo.get_time / mcp.demo.echo / mcp.demo.weather_stub
#    (source="mcp", provider="demo", original_name корректен)
# 3. фильтр прав: denied_tools={"get_time"} → get_time отсутствует в discovery;
#    allowed_tools={"echo"} → только echo
# 4. сервер с fail_initialize → FAILED; discover → его тулов нет, остальные живы;
#    общий статус DEGRADED (один из двух)
# 5. stop() → DISCONNECTED; discover после stop → пусто (каталог честен)
# 6. MCPToolProvider: provider_id()=="mcp"; discover() == gateway.discover()
# 7. MCPGatewaySync: start/discover/status/stop — синхронно, без ручного event loop
EOF
```
**Ожидаемый результат:** все блоки OK, EXIT 0.

### Шаг 4.5 — Интеграционный прогон (stdio → demo_server, не гейт)
```bash
python - <<'EOF'
# StdioMCPTransport(command=(sys.executable, "-m", "integrations.mcp.demo_server"))
# → initialize → list_tools → 3 тула (get_time, echo, weather_stub) → close
EOF
```
**Ожидаемый результат:** живой stdio-прогон даёт 3 тула; подпроцесс корректно
завершается (нет висящих процессов); таймаут срабатывает при зависании.

### Шаг 4.6 — Проверка границ
1. `grep -n "state_machine\|StateMachine\|TaskStage\|memory\|profile" integrations/mcp/gateway.py integrations/mcp/provider.py` → пусто.
2. `grep -rn "import mcp\|from mcp" integrations/` → только `transport.py` и
   `demo_server.py`.
3. **Ожидаемый результат:** gateway — адаптер, не контролёр; SDK — в двух
   разрешённых местах.

### Шаг 4.7 — Регрессия
1. L1 → ok; L2 → **91 OK, 0 FAIL**; L3/L4/гейт — без изменений (13+2⚠).
**Ожидаемый результат:** полная нерегрессия.

---

## 3. Выход этапа

- `integrations/mcp/{gateway,provider,demo_server}.py`.
- Примитив-смоук + интеграционный stdio-прогон.
- Запись этапа **M4** в `dev/migr_log.md`.

---

## 4. Автоматический гейт M4→M5

Гейт считается **зелёным**, если одновременно:
- [ ] `MCPConnectionState` — 5 состояний; gateway start/stop/status/discover
      работают (fake);
- [ ] discovery нормализует в `ToolDescriptor` с квалифицированными именами
      `mcp.<server>.<tool>`;
- [ ] фильтр прав: denied исключается всегда; allowed (непустой) сужает список;
- [ ] сервер в FAILED → тулов нет, остальные живы; общий статус DEGRADED/FAILED;
- [ ] после stop() discovery пуст (каталог честен);
- [ ] `MCPGatewaySync` — синхронный фасад работает;
- [ ] **интеграционный прогон**: stdio → demo_server → initialize → list_tools →
      3 тула → чистое закрытие;
- [ ] gateway/provider не знают о стадиях/профилях/памяти (grep);
- [ ] L1 зелёный; L2 **91 OK, 0 FAIL**; L3/L4/гейт — без изменений.

**Зелёный** → запись M4 в `migr_log.md` (✅) → **перечитать `migr_plan.md`** →
создать `migr_plan_5.md`.
**Красный** → карточка ошибки, этап M4 открыт.

---

## 5. Запись в `migr_log.md` (форма §6.4)

```text
## Этап M4 — MCP-слой: gateway / provider / demo_server
- Статус: ✅ завершён | ⚠️ обход | ❌ открыт
- Было: config/transport/client готовы; шлюза, провайдера и демо-сервера нет
- Стало: <MCPConnectionState; MCPGateway (start/stop/status/discover + фильтр прав);
  MCPGatewaySync; MCPToolProvider; demo_server (get_time/echo/weather_stub)>
- Проверка: <примитив-смоук (7 блоков); интеграционный stdio-прогон (3 тула);
  grep-границы; L1/L2/L3/L4/гейт>
- Артефакты: integrations/mcp/{gateway,provider,demo_server}.py
- Спорное/риски: <если есть>
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (дата/время)
- Гейт M4→M5: ✅ пройден | ❌ не пройден
```

---

## 6. Следующий шаг

Перечитать актуальный `dev/migr_plan.md`, затем приступить к **M5** по
`dev/migr_plan_5.md` (хранение: `storage/store.py` — `mcp_servers_path`/
`read/write_mcp_servers`, `tool_catalog_path`/`read/save_tool_catalog`, аудит
`append_tool_audit`; round-trip и битые файлы).
