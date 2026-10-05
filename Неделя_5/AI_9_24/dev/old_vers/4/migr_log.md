# migr_log.md — журнал миграции `den_17` → требование дня 17 (Ревизия 3)

> Журнал результатов миграции по рабочим планам `dev/migr_plan_0.md` … `dev/migr_plan_6.md`.
> План-эталон: `dev/migr_plan.md` (формат записей — §6.4, правила повтора — §6.2).
> Обозначения: ✅ выполнено · ❌ не выполнено (повтор) · ⚠ допустимое временное отклонение ·
> ⛔ блокирующая ошибка (ожидание указаний).
> История прошлых ревизий — в `dev/old_vers/` (1 — stdio дня 16, 2 — Ревизия 2 дня 16,
> 3 — снимок состояния на входе Ревизии 3).

> **Ревизия 3.** Задача дня 17: подключить к агенту MCP-инструмент
> `get_time(timezone_name) -> ISO 8601` (сервер задания `http://91.188.212.77:8000/mcp`),
> **вызвать его из приложения** (п. 4.1, Вариант A — автовызов через LLM tool-use) и
> **получить и использовать результат** (п. 4.2, Вариант 1 — через LLM-цикл: tool-сообщение
> → финальный ответ модели). Демонстрация — с **реальным LLM** (без mock). Инфраструктура
> MCP перенесена из `den_16` (Ревизия 2) без изменений; правится только конфиг сервера
> задания. План-эталон и рабочие планы переписаны под Ревизию 3 (M0–M6).

---

## Этап M0 — Базовая линия Ревизии 3 и инвентаризация
- Статус: ✅ завершён
- Было: `den_17` — структурная копия `den_16` (Ревизия 2): вся MCP-инфраструктура
  (HTTP-транспорт, gateway, provider, registry, policy, executor, LLM tool-use, блок
  `[tools]`, `/mcp`-семейство, `--mcp`/`--mcp-probe`, аудит) перенесена. Для дня 17
  **отсутствует**: сервер задания `time` в `DEFAULT_SERVERS`; чтение env `MCP_SERVER_URL`;
  реальное discovery к серверу задания; реальный вызов `get_time`; живой LLM tool-use
  «который час»; документация под день 17.
- Стало: baseline зафиксирован (всё зелёное до изменений); расхождения перечислены и
  привязаны к M1–M6; факты о сервере задания записаны; точки внедрения зафиксированы;
  служебка готова (`migr_log.md` очищен под Ревизию 3).
- Проверка (baseline, без живого ключа):
  - L1 `py_compile Kod.py core/*.py memory/*.py storage/*.py integrations/mcp/*.py` → EXIT=0;
  - L2 `env -u API_KEY python dev/tests_debug/unit_runner.py` → **122 OK, 0 FAIL**, EXIT=0;
  - L3 `API_KEY=test-key python dev/tests_debug/smoke.py` → **SMOKE OK**, EXIT=0;
  - L4 `API_KEY=test-key python dev/tests_debug/scenario.py` → **SCENARIO OK**, EXIT=0;
  - гейт `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` → **21 из 21 зелёные
    (FAIL=0)**, EXIT=0.
- Артефакты: `dev/migr_log.md` (очищен под Ревизию 3).
- Факты о сервере задания `http://91.188.212.77:8000/mcp` (живой read-only discovery
  2026-09-27): protocol `2025-06-18`; `serverInfo: Time Server`; `tools.list_changed=false`;
  1 инструмент `get_time` — `inputSchema`:
  `{"type":"object","properties":{"timezone_name":{"default":"UTC","title":"Timezone Name","type":"string"}},"title":"get_timeArguments"}`;
  `outputSchema`: `{"properties":{"result":{"type":"string"}},"required":["result"],"type":"object"}`;
  description: «Получает текущее время в указанном часовом поясе… IANA… ISO 8601»;
  `call_tool("get_time", {"timezone_name":"Europe/Moscow"})` →
  `content[0].text = "2026-09-27T11:33:00.230958+03:00"`, `isError=false`,
  `structuredContent.result = "2026-09-27T11:33:00.230958+03:00"`; транспорт — Streamable
  HTTP (`mcp.client.streamable_http.streamable_http_client`). Погодный сервер
  `https://weatherapi.projecteol.ru/mcp/` — жив (HTTP 200).
- Точки внедрения (не меняются): `core/state_machine.py` (TaskStage 8 стадий, карта, API
  контроля), `core/invariants.py`, `memory/*`, `storage/db.py`, базовые контракты
  `core/llm_client.py`/`core/prompt_builder.py`, MCP-инфраструктура Ревизии 2.
- Перечень расхождений → этапы: сервер `time` в конфиге → M1; реальное discovery → M2;
  реальный вызов `get_time` → M3; живой LLM tool-use (4.1+4.2) → M4; CLI/DI/ручной вызов →
  M5; документация (README/Проверка/arch) без тестов → M6.
- Спорное/риски: нет.
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-27)
- Гейт M0→M1: ✅ пройден

---

## Этап M1 — Конфиг сервера задания `time`
- Статус: ✅ завершён
- Было: `DEFAULT_SERVERS` = `weather` (http, enabled=True) + `demo` (stdio, enabled=False);
  env `MCP_SERVER_URL` кодом не читался; сервера задания в конфиге не было.
- Стало: добавлен `TIME_MCP_URL = os.getenv("MCP_SERVER_URL", "http://91.188.212.77:8000/mcp")`;
  в `DEFAULT_SERVERS` первым добавлен сервер `time` (`transport="http"`,
  `endpoint=TIME_MCP_URL`, `enabled=True`, `trust_level="low"`); `weather` и `demo`
  сохранены без изменений.
- Проверка:
  - L1 `py_compile integrations/mcp/config.py` → EXIT=0;
  - смоук: `load_servers_config(None)` → ids `['demo','time','weather']`;
    `time.transport=http`, `endpoint=http://91.188.212.77:8000/mcp`, `enabled=True`;
    `make_transport(time)` → `HttpMCPTransport`; `SMOKE M1 OK`, EXIT=0;
  - изоляция SDK: `grep -rn "import mcp\|from mcp" core/ memory/ storage/ Kod.py` → нет
    совпадений (GREP_EXIT=1) — SDK только в `integrations/mcp/`;
  - L2 → 122 OK, 0 FAIL, EXIT=0; L3 → SMOKE OK, EXIT=0; L4 → SCENARIO OK, EXIT=0;
    гейт → 21 из 21 зелёные (FAIL=0), EXIT=0.
- Артефакты: `integrations/mcp/config.py`.
- Спорное/риски: нет (существующий тест `test_default_servers_and_store_roundtrip`
  проверяет только `weather`/`demo` — новый сервер `time` его не ломает; тесты не
  расширялись).
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-27)
- Гейт M1→M2: ✅ пройден

---

## Этап M2 — Реальное discovery к серверу задания
- Статус: ✅ завершён
- Было: сервер `time` в конфиге (M1), но живое подключение к серверу задания не
  проверялось; при недоступном сервере транспорт падал трейсбеком (`CancelledError` —
  `BaseException`, не ловился `except Exception`).
- Стало: подтверждено **живое** подключение к `http://91.188.212.77:8000/mcp` (READY) и
  получение **настоящего** списка инструментов; каталог `catalog.json` содержит
  `mcp.time.get_time`; деградация при недоступном сервере — корректная (FAILED, REPL жив).
- Проверка:
  - `python Kod.py --mcp-probe` → `[MCP] «time»: подключён (READY)`,
    `[MCP] «weather»: подключён (READY)`; инструмент `mcp.time.get_time` с описанием
    (IANA/ISO 8601) и `input_schema` (`timezone_name: string`, default `UTC`);
    `Всего инструментов: 4`; `DISCONNECTED`; EXIT=0. Транскрипт:
    `dev/logs_reports/stages/m2_probe_live.txt`.
  - REPL `--user w17 --mcp`: `/mcp refresh` → `catalog.json` с `mcp.time.get_time`
    (provider `time`, `original_name get_time`, `enabled true`); `/mcp status` → READY;
    `/mcp tools`; `/mcp servers` (time/weather/demo); `/mcp disconnect`; EXIT=0.
  - Деградация: `MCP_SERVER_URL="https://invalid.invalid/mcp/" python Kod.py --mcp-probe`
    → `[MCP] «time»: FAILED — handshake не удался: Cancelled via cancel scope …`,
    `overall: degraded`, EXIT=1 (понятная ошибка, без трейсбека); REPL при том же URL →
    `overall: degraded`, `time: failed`, `weather: ready`, каталог честен (3 тула),
    REPL жив, EXIT=0.
  - Нерегрессия: L1 EXIT=0; L2 → 122 OK, 0 FAIL; L3 → SMOKE OK; L4 → SCENARIO OK;
    гейт → 21 из 21 зелёные (FAIL=0).
- Артефакты: `integrations/mcp/transport.py` (фикс: `except (Exception,
  asyncio.CancelledError)` в `initialize` stdio/http + `except BaseException` в
  `_SessionTransport.close`); `users/w17/integrations/mcp/catalog.json`;
  `dev/logs_reports/stages/m2_probe_live.txt`.
- Спорное/риски: `CancelledError` при недоступном HTTP-сервере — особенность SDK 2.2.0
  (anyio cancel scope); устранено точечно, без изменения контрактов.
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-27)
- Гейт M2→M3: ✅ пройден

---

## Этап M3 — Реальный вызов `get_time(timezone_name)`
- Статус: ✅ завершён
- Было: инструмент `mcp.time.get_time` в каталоге (M2); реальный вызов не проверялся.
- Стало: подтверждён **настоящий** вызов инструмента задания на живом сервере; результат —
  строка ISO 8601; вызов проходит через `ToolExecutor` (policy → gateway →
  `ToolExecutionResult` → аудит); `TaskStage` не меняется.
- Проверка:
  - `/mcp call mcp.time.get_time {"timezone_name":"Europe/Moscow"}` → `succeeded`,
    результат `2026-09-27T12:30:50.904348+03:00` (ISO 8601, +03:00);
  - `/mcp call mcp.time.get_time {}` → `succeeded`, результат
    `2026-09-27T09:30:51.005280+00:00` (дефолт `UTC`, +00:00);
  - аудит `users/w17/tasks/Основная_задача/tool_audit.jsonl`: две записи
    `{"tool":"mcp.time.get_time","status":"succeeded","phase":"invoked",…}`;
  - `TaskStage` не менялся (файла `task_state.json`/`transition_log` нет — задача не
    стартовала, вызовы инструмента переходов не создают);
  - нерегрессия: L1 EXIT=0; L2 → 122 OK, 0 FAIL; L3 → SMOKE OK; L4 → SCENARIO OK;
    гейт → 21 из 21 зелёные (FAIL=0).
- Артефакты: `users/w17/tasks/Основная_задача/tool_audit.jsonl`;
  `dev/logs_reports/stages/m3_call_live.txt`.
- Спорное/риски: нет.
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-27)
- Гейт M3→M4: ✅ пройден

---

## Этап M4 — Полный LLM tool-use: 4.1 автовызов + 4.2 результат
- Статус: ✅ завершён
- Было: реальный вызов `get_time` через `/mcp call` (M3); сквозной живой прогон с
  **реальным LLM** (автовызов инструмента моделью) не проверялся.
- Стало: подтверждено требование дня 17 на **живых** LLM + MCP: пользователь просит
  «который час в Москве?» → LLM **сам** формирует нативный `tool_call`
  `get_time({"timezone_name":"Europe/Moscow"})` (Вариант A — автовызов через
  `Agent._respond_with_tools`) → реальный вызов на сервере задания → tool-сообщение с
  ISO 8601 возвращается в модель → **финальный ответ использует результат** (Вариант 1).
- Проверка:
  - `printf 'который час в Москве?\n/exit\n' | python Kod.py --user w17 --mcp` (ключ из
    `.env`, реальный LLM) → `[MCP] «time»: подключён (READY)`; ответ агента:
    **«Сейчас в Москве 12:38.»**; EXIT=0. Транскрипт:
    `dev/logs_reports/stages/m4_live_run.txt`.
  - аудит `tool_audit.jsonl`: запись `{"tool":"mcp.time.get_time","status":"succeeded",
    "phase":"invoked","call_id":"chatcmpl-tool-a2d772dc9a468ee0",…}` — **нативный**
    tool_call (не fallback), результат `2026-09-27T12:38:09.521261+03:00`;
  - рабочая память: `external_actions` = `{tool: mcp.time.get_time, status: succeeded,
    summary: "2026-09-27T12:38:09.521261+03:00"}` (сырой ответ не пишется);
  - `TaskStage` не менялся (`current_state: new`); `transition_log` без записей от вызова;
  - нерегрессия: L1 EXIT=0; L2 → 122 OK, 0 FAIL; L3 → SMOKE OK; L4 → SCENARIO OK;
    гейт → 21 из 21 зелёные (FAIL=0).
- Артефакты: `dev/logs_reports/stages/m4_live_run.txt`;
  `users/w17/tasks/Основная_задача/{tool_audit.jsonl,working_memory.json}`.
- Спорное/риски: нет (провайдер поддержал нативный tool_calls; fallback-протокол не
  потребовался).
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-27)
- Гейт M4→M5: ✅ пройден

---

## Этап M5 — CLI/DI и ручной вызов (проверка)
- Статус: ✅ завершён
- Было: живой tool-use подтверждён (M4); детерминированный mock-путь для `get_time` не
  был покрыт (MockClient реагировал только на «москв» → `search_locations`).
- Стало: подтверждено, что полный tool-use доступен в REPL под `--mcp`, ручной `/mcp call`
  работает, endpoint берётся из env `MCP_SERVER_URL`, а без `--mcp` поведение = `den_15`.
  В `MockClient.complete_with_tools` добавлен детерминированный триггер дня 17
  («час/врем/time/timezone» → `get_time`, tz `Europe/Moscow` при «москв», иначе `UTC`).
- Проверка:
  - `--mcp --mock` + «который час в Москве?» → `[Mock] Инструмент вызван; результат:
    2026-09-27T12:44:42.070515+03:00` (tool-use цикл), EXIT=0;
  - `/mcp call mcp.time.get_time {"timezone_name":"Asia/Tokyo"}` → `succeeded`,
    `2026-09-27T18:45:10.546234+09:00` (+09:00), EXIT=0;
  - без `--mcp`: `/mcp status` → «MCP-слой выключен (запустите с флагом --mcp)»;
    обычный ответ MockClient — поведение = `den_15`, EXIT=0;
  - `MCP_SERVER_URL` учитывается (проверено в M2: неверный URL → FAILED/degraded);
  - нерегрессия: L1 EXIT=0; L2 → 122 OK, 0 FAIL; L3 → SMOKE OK; L4 → SCENARIO OK;
    гейт → 21 из 21 зелёные (FAIL=0).
- Артефакты: `core/llm_client.py` (триггер `get_time` в `MockClient`).
- Спорное/риски: нет (существующие mock-сценарии «Москва → search_locations» не затронуты —
  триггер `get_time` проверяется первым только при наличии слова «час/врем/time»).
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-27)
- Гейт M5→M6: ✅ пройден

---

## Этап M6 — Финал: документация без тестов
- Статус: ✅ завершён
- Было: код и живой прогон дня 17 готовы (M0–M5); документация (`README.md`,
  `dev/Проверка.md`, `arch_den_16.md`) описывала день 16 (Ревизия 2) — сервер задания
  `time`/`get_time`/env `MCP_SERVER_URL` и живой автовызов не были отражены.
- Стало: документация приведена в соответствие с кодом и живым прогоном дня 17.
  `README.md` — заголовок «День 17 — Первый инструмент MCP (`get_time`)», раздел
  «Подключение MCP» дополнен сервером задания `time` (`get_time`, env `MCP_SERVER_URL`,
  пример «который час в Москве?»), счётчики обновлены (приёмка 54, живой прогон 4 тула).
  `dev/Проверка.md` — добавлены критерии 49–54 дня 17 (сервер `time` в конфиге; реальное
  discovery `get_time`; реальный вызов; LLM tool-use «который час в Москве?» 4.1+4.2;
  аудит и «инструмент ≠ переход»; регрессия MCP off), итог 54/54. `arch_den_16.md` —
  актуализирован под день 17 (Ревизия 3): сервер задания `time`, `get_time`, env
  `MCP_SERVER_URL`, сводная механика инструмента задания, критерии 49–54, изменения
  кода Ревизии 3. **Тесты не писались и не расширялись** (явное указание пользователя).
- Проверка (финальный прогон, без живого ключа/сети):
  - L1 `py_compile Kod.py core/*.py memory/*.py storage/*.py integrations/mcp/*.py` → EXIT=0;
  - L2 `env -u API_KEY python dev/tests_debug/unit_runner.py` → **122 OK, 0 FAIL**, EXIT=0;
  - L3 `API_KEY=test-key python dev/tests_debug/smoke.py` → **SMOKE OK**, EXIT=0;
  - L4 `API_KEY=test-key python dev/tests_debug/scenario.py` → **SCENARIO OK**, EXIT=0;
  - гейт `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` → **21 из 21 зелёные
    (FAIL=0)**, EXIT=0;
  - живой прогон (реальный LLM + сервер задания): `printf 'который час в Москве?\n/exit\n'
    | python Kod.py --user w17 --mcp` → `[MCP] «time»: подключён (READY)`; ответ агента
    **«В Москве сейчас 12:52 (27 сентября 2026 года).»**; EXIT=0; аудит
    `tool_audit.jsonl` — `{"tool":"mcp.time.get_time","status":"succeeded","phase":"invoked",
    "call_id":"chatcmpl-tool-abc933ec3d902b7a",…}`, результат `2026-09-27T12:52:07.552102+03:00`;
    `external_actions` в рабочей памяти; `TaskStage` не менялся (`current_state: new`).
- Артефакты: `README.md`, `dev/Проверка.md`, `arch_den_16.md` (актуализированы);
  `dev/migr_log.md` (эта запись + «Итог миграции (Ревизия 3)»).
- Спорное/риски: нет.
- Перечитывание migr_plan.md перед следующим этапом: — (финальный этап)
- Гейт M6 (финальный): ✅ пройден

---

## Итог миграции (Ревизия 3)

**Задача дня 17** (`Задание_d17.txt`): подключить к агенту MCP-инструмент
`get_time(timezone_name) -> ISO 8601` (сервер задания `http://91.188.212.77:8000/mcp`),
**вызвать его из приложения** (п. 4.1) и **получить и использовать результат** (п. 4.2).
Формат отчёта — Код.

**Что сделано (этапы M0–M6):**

| Этап | Итог |
|---|---|
| M0 | Базовая линия Ревизии 3: L1 EXIT=0; L2 122 OK/0 FAIL; L3 SMOKE OK; L4 SCENARIO OK; гейт 21/21; факты о сервере задания зафиксированы |
| M1 | `integrations/mcp/config.py`: сервер `time` первым в `DEFAULT_SERVERS` (http, env `MCP_SERVER_URL`, enabled) |
| M2 | Живое discovery: `time` READY, `mcp.time.get_time`; фикс грациозной деградации `transport.py` (`CancelledError`) |
| M3 | Реальный вызов `get_time` (Moscow → `+03:00`; `{}` → `UTC`); аудит `succeeded`; `TaskStage` не менялся |
| M4 | Живой LLM tool-use: «который час в Москве?» → нативный `tool_call` `get_time` → результат использован в ответе |
| M5 | CLI/DI: `/mcp call` (Tokyo), mock-триггер `get_time` в `MockClient`, регрессия без `--mcp` |
| M6 | Документация без тестов: `README.md`, `dev/Проверка.md`, `arch_den_16.md`; финальный прогон + живой прогон |

**Результат (DoD §7 migr_plan.md):**
1. ✅ Сервер задания подключён: `--mcp-probe` / `/mcp connect` → handshake → `READY`.
2. ✅ Инструмент в каталоге: `tools/list` → `get_time` (`timezone_name: string`, default
   `UTC`), нормализован в `mcp.time.get_time`.
3. ✅ Реальный вызов: `get_time({"timezone_name":"Europe/Moscow"})` → ISO 8601.
4. ✅ Полный LLM tool-use (4.1 + 4.2): живой прогон «который час в Москве?» — LLM сам
   запрашивает `get_time` (Вариант A), результат возвращается в модель и **используется**
   в финальном ответе (Вариант 1): «В Москве сейчас 12:52».
5. ✅ Контроль и аудит: `ToolExecutor`/`ToolPolicy`; `tool_audit.jsonl`; `TaskStage` не
   меняется; сырые ответы не пишутся в память.
6. ✅ Регрессия: без `--mcp` поведение = `den_15`; тестовый контур зелёный (прогон).
7. ✅ Документы: `README.md`, `dev/Проверка.md`, актуализированный `arch_den_16.md`;
   все этапы M0–M6 в журнале. **Тесты не писались.**

**Изменения кода продукта (минимальны):** `integrations/mcp/config.py` (сервер `time` +
env `MCP_SERVER_URL`), `integrations/mcp/transport.py` (грациозная деградация),
`core/llm_client.py` (детерминированный триггер `get_time` в `MockClient`).
Инфраструктура MCP Ревизии 2 перенесена без изменений.

**Финальные числа:** L2 122 OK / 0 FAIL; L3 SMOKE OK; L4 SCENARIO OK; гейт 21/21;
приёмка 54/54; живой прогон — 4 тула (1 `time` + 3 `weather`), `get_time` →
`2026-09-27T12:52:07+03:00` → «В Москве сейчас 12:52».

**Коммит:** git-репозитория нет; коммит — только по явной команде пользователя.