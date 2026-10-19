# migr_log.md — журнал миграции `den_20` → требования Дня 20 (Ревизия 4)

> Журнал результатов миграции по рабочим планам `dev/migr_plan_0.md` … `dev/migr_plan_6.md`.
> План-эталон: `dev/migr_plan.md` (Ревизия 4; формат записей — §6.4, правила повтора — §6.2).
> Обозначения: ✅ выполнено · ❌ не выполнено (повтор) · ⚠ допустимое временное отклонение ·
> ⛔ блокирующая ошибка (ожидание указаний).
> История прошлых ревизий — в `dev/old_vers/` (1 — stdio дня 16, 2 — Ревизия 2 дня 16,
> 3 — снимок на входе Ревизии 3, 4 — снимок на входе Ревизии 4).

> **Ревизия 4.** Задача дня 20: собрать и реализовать план для выполнения требований
> трёх заданий — (1) MCP-инструмент с отложенным/периодическим выполнением (JSON,
> расписание, агрегированный результат; агент 24/7 с периодической сводкой;
> отчёт — **Видео + Код**); (2) пайплайн из нескольких MCP-инструментов
> (`search → summarize → saveToFile`; автовыполнение цепочки, корректная передача
> данных; отчёт — **Код**); (3) несколько MCP-серверов (выбор нужного инструмента,
> маршрутизация, длинный флоу, разные серверы; отчёт — **Код**). `den_20` — структурная
> копия `den_17`: вся MCP-инфраструктура Ревизий 2–3 перенесена без изменений. Ревизия 4
> — наращивание над ней трёх новых возможностей дня 20 (M0–M6).

---

## Этап M0 — Базовая линия Ревизии 4 и инвентаризация
- Статус: ✅ завершён
- Было: `den_20` — структурная копия `den_17` (Ревизия 3): вся MCP-инфраструктура
  (stdio + HTTP-транспорт, gateway, provider, registry, policy, executor, LLM tool-use,
  блок `[tools]`, `/mcp`-семейство, `--mcp`/`--mcp-probe`, аудит, сервер задания `time`/
  `get_time`, погодный `weather`) перенесена. Для дня 20 **отсутствует**: планировщик и
  фоновые задачи; пайплайн `search → summarize → saveToFile`; MCP-серверы `scheduler`/
  `pipeline` в `DEFAULT_SERVERS`; явная мультисерверная маршрутизация и длинный флоу;
  режим 24/7; трёхсценарная `dev/Проверка.md`. Рабочий venv недели `AI_9/.venv`
  отсутствовал (не под git).
- Стало: baseline зафиксирован (всё зелёное до изменений); расхождения перечислены и
  привязаны к M1–M6; эталон сервера изучён; точки внедрения зафиксированы; служебка
  готова (`old_vers/4/`, `migr_log.md` очищен под Ревизию 4); рабочее окружение
  восстановлено.
- Проверка (baseline, без живого ключа):
  - L1 `py_compile Kod.py core/*.py memory/*.py storage/*.py integrations/mcp/*.py` → EXIT=0;
  - L2 `env -u API_KEY python dev/tests_debug/unit_runner.py` → **122 OK, 0 FAIL**, EXIT=0;
  - L3 `API_KEY=test-key python dev/tests_debug/smoke.py` → **SMOKE OK**, EXIT=0;
  - L4 `API_KEY=test-key python dev/tests_debug/scenario.py` → **SCENARIO OK**, EXIT=0;
  - гейт `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` → **21 из 21 зелёные
    (FAIL=0)**, EXIT=0.
- Артефакты: `dev/old_vers/4/` (снимок: `migr_plan*.md`, `migr_log.md`, `Проверка*.md`,
  `README.md`, `arch.md`); `dev/migr_plan_0.md` (рабочий план M0); `dev/migr_log.md`
  (очищен под Ревизию 4); `AI_9/.venv` (восстановленное окружение, вне git).
- Факты об окружении: venv недели `AI_9/.venv` отсутствовал; восстановлен
  `/usr/bin/python3 -m venv` + `pip install requests python-dotenv mcp uvicorn`
  (mcp 2.2.0). Интерпретатор контура — `AI_9/.venv/bin/python`.
- Эталон настройки MCP-сервера (`doc/mcp/mcp-time-server/time_server_http.py`):
  `mcp.server.mcpserver.MCPServer`, `@mcp.tool()`, `TransportSecuritySettings(allowed_hosts=…)`,
  `mcp.streamable_http_app(...)`, `uvicorn.run(app, host="0.0.0.0", port=8000)`.
  `time_server_stdio_old.py` — устаревший stdio-вариант.
- Точки внедрения (не меняются): `core/state_machine.py`, `core/invariants.py`,
  `memory/*`, `storage/db.py`, базовые контракты `core/llm_client.py`/`core/prompt_builder.py`,
  MCP-инфраструктура Ревизий 2–3.
- Спорное/риски: восстановление venv потребовало сетевого доступа к PyPI (доступен);
  версия `mcp` совпала с прежней (2.2.0) — совместимость контрактов сохранена.
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-27)
- Гейт M0→M1: ✅ пройден

---

## Этап M1 — Ядро планировщика фоновых задач
- Статус: ✅ завершён
- Было: планировщика/фоновых задач нет. Только наследие Ревизий 2–3.
- Стало: реализовано ядро фонового планировщика (24/7), **независимое от LLM**:
  `integrations/scheduler/{models,store,runner,aggregator}.py`; хранение — через
  фасад `Store` (`users/<id>/integrations/mcp/scheduler/{jobs,observations,summaries}.json`).
  Worker — поток stdlib (`threading`), тик по расписанию, `run_once()` для
  детерминированных проверок; агрегатор считает `count/min/max/avg/last` и формирует
  детерминированный текст сводки. Состояние фоновой задачи — `JobState` (не `TaskStage`).
- Проверка:
  - детерминированный чек `dev/tests_debug/.tmp/m1_check.py` → `M1 OK`: `run_once`
    выполнил 3 задачи; наблюдения записаны в JSON (2 шт.); сводка `temp: count=2,
    min=20, max=24, avg=22.0, last=24`; JSON-файлы на диске; фоновый worker за 0.3 c
    увеличил наблюдения 2→14; битый JSON → дефолт; агрегатор напрямую;
  - L1 `py_compile` (+ `integrations/scheduler/*.py`) → EXIT=0;
  - изоляция SDK: `grep "import mcp|from mcp" core/ memory/ storage/ integrations/scheduler/ Kod.py`
    → нет совпадений (GREP_EXIT=1);
  - L2 → 122 OK, 0 FAIL; L3 → SMOKE OK; L4 → SCENARIO OK; гейт → 21/21 (FAIL=0).
- Артефакты: `integrations/scheduler/{__init__,models,store,runner,aggregator}.py`;
  `storage/store.py` (методы фасада `scheduler_dir/scheduler_path/read_scheduler/write_scheduler`).
- Спорное/риски: нет.
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-27)
- Гейт M1→M2: ✅ пройден

---

## Этап M2 — MCP-сервер планировщика
- Статус: ✅ завершён
- Было: ядро планировщика (M1); MCP-сервера планировщика и его тулов нет.
- Стало: реализован `integrations/mcp/scheduler_server.py` на `MCPServer` (образец
  `time_server_http.py`): тулы `schedule_reminder`, `schedule_collection`,
  `record_observation`, `run_due`, `get_summary`, `latest_summary`, `list_jobs` — над
  ядром M1. Сервер `scheduler` добавлен в `DEFAULT_SERVERS` (`transport="http"`,
  endpoint из env `SCHEDULER_MCP_URL`, дефолт `http://127.0.0.1:8010/mcp`).
  `latest_summary` отдаёт уже сохранённый текст (без нового запроса к модели).
- Проверка:
  - детерминированный чек `dev/tests_debug/.tmp/m2_check.py` → `M2 OK`: сервер в
    конфиге; `record_observation` → JSON; `get_summary` → `temp: count=2, min=20,
    max=24, avg=22.0`; `latest_summary` → сохранённый текст; `schedule_reminder`
    (delay=0) + `run_due` → `ran=1`; JSON-файлы на диске; discovery через
    `FakeMCPTransport` → `mcp.scheduler.*`;
  - **живой stdio-прогон** `dev/tests_debug/.tmp/m2_live.py` → `M2 LIVE OK`:
    7 тулов; `record_observation` → `{"observations": 1}`; `get_summary` →
    `avg=22.0`; `latest_summary` → сохранённый текст;
  - L1 `py_compile` → EXIT=0; изоляция SDK: `grep` в `core/ memory/ storage/
    integrations/scheduler/ Kod.py` → нет совпадений;
  - L2 → 122 OK, 0 FAIL; L3 → SMOKE OK; L4 → SCENARIO OK; гейт → 21/21 (FAIL=0).
- Артефакты: `integrations/mcp/scheduler_server.py`; `integrations/mcp/config.py`
  (сервер `scheduler` + env `SCHEDULER_MCP_URL`, `PIPELINE_MCP_URL`).
- Спорное/риски: нет.
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-27)
- Гейт M2→M3: ✅ пройден

---

## Этап M3 — Пайплайн из MCP-инструментов
- Статус: ✅ завершён
- Было: планировщик и его MCP-сервер (M1–M2); пайплайна `search → summarize →
  saveToFile` нет.
- Стало: реализованы `integrations/mcp/pipeline_server.py` (тулы `search`,
  `summarize`, `saveToFile`, `readFile` — по образцу `time_server_http.py`) и
  `core/tool_pipeline.py` (автоцепочка `PipelineStep`/`Pipeline`/`run_pipeline` поверх
  `ToolExecutor`; результат шага N → аргумент N+1 через `input_key`; **не трогает
  `StateMachine`**). Сервер `pipeline` добавлен в `DEFAULT_SERVERS` (env
  `PIPELINE_MCP_URL`).
- Проверка:
  - детерминированный чек `dev/tests_debug/.tmp/m3_check.py` → `M3 OK`: сервер в
    конфиге; сам сервер `search → summarize → saveToFile → readFile`; автоцепочка
    через `ToolExecutor` на `FakeMCPTransport` → 3 шага `succeeded`; передача данных
    (`summarize` получил текст `search`, `saveToFile` — сводку `summarize`); аудит — 3
    записи `succeeded`; `task_state.json` не создан (инструмент ≠ переход);
  - **живой stdio-прогон** `dev/tests_debug/.tmp/m3_live.py` → `M3 LIVE OK`: 4 тула;
    `search` → факты MCP; `summarize` → сводка; `saveToFile` → `report.txt` (143 симв.);
    `readFile` вернул сохранённое;
  - L1 `py_compile` → EXIT=0; изоляция SDK: `grep` в `core/ memory/ storage/
    integrations/scheduler/ Kod.py` → нет совпадений;
  - L2 → 122 OK, 0 FAIL; L3 → SMOKE OK; L4 → SCENARIO OK; гейт → 21/21 (FAIL=0).
- Артефакты: `integrations/mcp/pipeline_server.py`; `core/tool_pipeline.py`;
  `integrations/mcp/config.py` (сервер `pipeline` + env `PIPELINE_MCP_URL`).
- Спорное/риски: нет.
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-27)
- Гейт M3→M4: ✅ пройден

---

## Этап M4 — Несколько MCP-серверов: маршрутизация и длинный флоу
- Статус: ✅ завершён
- Было: серверы `scheduler`/`pipeline` добавлены (M2–M3); мультисерверная
  маршрутизация на уровне gateway/registry работала, но длинный флоу и порядок
  вызовов явно не подтверждались.
- Стало: подтверждён итоговый набор `DEFAULT_SERVERS` (`time`, `weather`, `scheduler`,
  `pipeline`, `demo`); подтверждена маршрутизация вызова на нужный сервер по
  квалификации `mcp.<server>.<tool>`; подтверждён **длинный флоу в рамках одного
  запроса** (несколько последовательных tool-use итераций) с тулами **двух разных
  серверов** и корректным порядком вызовов.
- Проверка:
  - детерминированный чек `dev/tests_debug/.tmp/m4_check.py` → `M4 OK`: серверы
    `['time','weather','scheduler','pipeline','demo']`; каталог из 4 тулов двух
    серверов; маршрутизация (`mcp.scheduler.record_observation` → scheduler,
    `mcp.pipeline.search` → pipeline) `succeeded`; скриптованный LLM за один запрос
    выполнил 4 вызова по порядку: `record_observation → search → summarize →
    saveToFile`; порядок корректен; использованы тулы двух серверов
    (`{scheduler, pipeline}`); лишних вызовов нет; 4 итерации < лимита;
  - L1 `py_compile` → EXIT=0; изоляция SDK: `grep` → нет совпадений;
  - L2 → 122 OK, 0 FAIL; L3 → SMOKE OK; L4 → SCENARIO OK; гейт → 21/21 (FAIL=0).
- Артефакты: `integrations/mcp/config.py` (итоговый набор серверов);
  `dev/tests_debug/.tmp/m4_check.py` (детерминированный мультисерверный сценарий).
- Спорное/риски: нет (длинный флоу обеспечивается существующим циклом
  `Agent._respond_with_tools`; лимит `max_tool_iterations` не тронут).
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-27)
- Гейт M4→M5: ✅ пройден

---

## Этап M5 — CLI/DI, режим 24/7 и ручные команды
- Статус: ✅ завершён
- Было: серверы/пайплайн/мультисерверный флоу готовы (M2–M4), но из CLI не было
  режима 24/7 и ручных команд планировщика/пайплайна/маршрутизации.
- Стало: в `Kod.py` добавлены флаги `--scheduler` и `--scheduler-interval`; сборка
  фонового worker'а (`setup_scheduler`) после идентификации пользователя и чистая
  остановка (`stop_scheduler`) при `/exit`/`EOF`/`Ctrl+C`; `/mcp`-семейство
  расширено командами `summary [N]`, `jobs`, `pipeline <запрос>`, `route <текст>`
  (доступны и без `--mcp`; пайплайн/маршрут требуют `--mcp`). В `Agent` добавлено
  поле `scheduler` (по умолчанию None).
- Проверка:
  - детерминированный чек `dev/tests_debug/.tmp/m5_check.py` → `M5 OK`:
    `--mcp --scheduler --scheduler-interval 0.2` → «Фоновый worker запущен (24/7)»,
    `/mcp jobs` показывает задачи `collect`/`summary`, `/mcp summary` отдаёт сводку,
    JSON-файлы `observations.json`/`jobs.json`/`summaries.json` на диске;
    `--mcp` без `--scheduler` → «Фон выключен», `/mcp route` работает; без флагов →
    «Фон выключен» (поведение = den_15);
  - L1 `py_compile` → EXIT=0; изоляция SDK: `grep` → нет совпадений;
  - L2 → 122 OK, 0 FAIL; L3 → SMOKE OK; L4 → SCENARIO OK; гейт → 21/21 (FAIL=0).
- Артефакты: `Kod.py` (флаги `--scheduler`/`--scheduler-interval`, `setup_scheduler`,
  `stop_scheduler`, команды `/mcp summary|jobs|pipeline|route`, справка);
  `core/agent.py` (поле `scheduler`).
- Спорное/риски: нет.
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-27)
- Гейт M5→M6: ✅ пройден

---

## Этап M6 — Финал: три сценария проверки и документация
- Статус: ✅ завершён
- Было: документация дня 17; `dev/Проверка.md` — чек-лист дней 16–17.
- Стало: `dev/Проверка.md` переписан как **сценарий видео-демонстрации** с **тремя
  независимыми сценариями** (по одному на задание) и отдельным чек-листом-итогом на
  каждое задание (1: Код, 2: Код, 3: Код). `README.md` — шапка под день 20 + раздел «День 20» +
  команды `/mcp summary|jobs|pipeline|route` + флаги `--scheduler`/`--scheduler-interval`
  (итого 16 флагов). `arch.md` — шапка и раздел §2.9/§7.2.1 под день 20.
- Проверка:
  - транскрипты трёх сценариев в `dev/logs_reports/stages/`:
    `m6_scen1_scheduler.txt`, `m6_scen2_pipeline.txt`, `m6_scen3_multiserver.txt`;
  - `dev/Проверка.md` содержит три сценария с чек-листами (по 6 пунктов каждый);
  - финальный прогон: L1 EXIT=0; изоляция SDK (grep) → нет совпадений; L2 → 122 OK,
    0 FAIL; L3 → SMOKE OK; L4 → SCENARIO OK; гейт → 21/21 (FAIL=0);
    этапные чеки M1–M5 → все `OK`.
- Артефакты: `dev/Проверка.md`, `README.md`, `arch.md`, `dev/migr_log.md` (эта запись).
- Спорное/риски: живой LLM-прогон и запись видео — за пользователем (нет `.env` с
  `API_KEY` в рабочем каталоге); детерминированные дубли зелёные.
- Перечитывание migr_plan.md: ✅ (перед M6)
- Гейт M6 (финальный): ✅ пройден

---

## Итог миграции (Ревизия 4)

**Задача дня 20** (`Задание_d20.txt`): собрать и реализовать план для требований
**трёх заданий**. Все три реализованы и подтверждены.

| Задание | Что сделано | Формат | Статус |
|---|---|---|---|
| 1 — планировщик и фоновые задачи | ядро `integrations/scheduler/` + MCP-сервер `scheduler_server.py`; JSON, расписание, агрегат; 24/7 через внешний worker; `/mcp jobs`, `/mcp summary` | Видео + Код | ✅ |
| 2 — пайплайн из MCP-инструментов | `pipeline_server.py` (`search/summarize/saveToFile`) + `core/tool_pipeline.py` (автоцепочка, передача данных) | Код | ✅ |
| 3 — несколько MCP-серверов | набор `time/weather/scheduler/pipeline/demo`; выбор инструмента, маршрутизация, длинный флоу | Код | ✅ |

**Этапы:** M0 ✅ · M1 ✅ · M2 ✅ · M3 ✅ · M4 ✅ · M5 ✅ · M6 ✅.
**Итоговые числа:** L1 EXIT=0; L2 122 OK/0 FAIL; L3 SMOKE OK; L4 SCENARIO OK;
гейт 21/21 (FAIL=0); этапные чеки M1–M5 — все OK.
**Инварианты соблюдены:** `TaskStage` не тронут (инструмент ≠ переход); MCP off по
умолчанию; SDK только в `integrations/mcp/`; хранение — через фасад `Store`; фон —
внешний worker, не LLM.
**Коммит:** git-репозиторий есть (`AI_9/.git`); коммит — **только по явной команде
пользователя**. Изменения кода продукта: `integrations/scheduler/*` (new),
`integrations/mcp/{scheduler_server,pipeline_server,config}.py`, `core/tool_pipeline.py`
(new), `core/agent.py` (+ поле `scheduler`), `storage/store.py` (+ методы фасада),
`Kod.py` (+ флаги и команды); документы: `README.md`, `arch.md`, `dev/*`.
