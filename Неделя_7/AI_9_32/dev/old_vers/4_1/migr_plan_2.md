# migr_plan_2.md — рабочий план этапа M2 (MCP-сервер планировщика)

> Рабочий план-алгоритм одного этапа миграции `den_18` (Ревизия 4). Подчинён
> плану-эталону `dev/migr_plan.md` §4 «Этап M2» (задание 1). Один этап = один
> рабочий план = один гейт. Результат — в `dev/migr_log.md`.
> `migr_plan.md` перечитан перед созданием файла (правило §1.1).

---

## 0. Цель и границы

**Цель** — MCP-инструмент с отложенным/периодическим выполнением, который
**сохраняет данные (JSON)**, **выполняется по расписанию**, **возвращает
агрегированный результат** — по образцу `doc/mcp/mcp-time-server/time_server_http.py`.

**Границы**: сервер использует ядро M1 (JSON-хранилище + агрегатор) через фасад
`Store`; SDK — только в `integrations/mcp/`; сводка отдаётся **без нового запроса
к модели** (возврат уже сохранённого текста).

---

## 1. Артефакты

| Файл | Назначение |
|---|---|
| `integrations/mcp/scheduler_server.py` | MCP-сервер: `schedule_reminder`, `record_observation`, `run_due`, `latest_summary`/`get_summary`, `list_jobs` |
| `integrations/mcp/config.py` | сервер `scheduler` в `DEFAULT_SERVERS` (endpoint из env `SCHEDULER_MCP_URL`) |

---

## 2. Шаги

1. `scheduler_server.py` на `mcp.server.mcpserver.MCPServer` (образец
   `time_server_http.py`): тулы над ядром M1; `configure(memory_dir, user_id)` — для
   тестов; `get_scheduler()` — ленивая сборка `Store → SchedulerStore → Scheduler`.
   Возврат — агрегированный результат (текст/структура).
2. `config.py` — `SCHEDULER_MCP_URL = os.getenv("SCHEDULER_MCP_URL", "http://127.0.0.1:8010/mcp")`;
   сервер `scheduler` (`transport="http"`, `enabled=True`); `time`/`weather`/`demo` — без изменений.
3. Запуск сервера (по образцу): `streamable_http_app` + `uvicorn.run(port=8010)`.
4. Детерминированная проверка: тулы `mcp.scheduler.*` видны через discovery
   (`FakeMCPTransport`); `record_observation` пишет наблюдение в JSON; `get_summary`
   возвращает агрегат; `schedule_reminder` + `run_due` выполняются по расписанию.
5. Живой прогон (не гейт): поднять `scheduler_server`, `--mcp-probe` → тулы;
   `/mcp call` → запись и сводка.

---

## 3. Гейт M2→M3 (критерии)

- [ ] MCP-сервер планировщика поднимается (или fake-эквивалент);
- [ ] discovery возвращает тулы `mcp.scheduler.*`;
- [ ] данные сохраняются в JSON; `get_summary` возвращает агрегат;
- [ ] `schedule_reminder` + `run_due` выполняются по расписанию;
- [ ] деградация при недоступном сервере (FAILED, REPL жив);
- [ ] L1 без регрессии; SDK только в `integrations/mcp/`;
- [ ] L2/L3/L4/гейт без регрессии.