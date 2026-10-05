# migr_log.md — журнал миграции `den_16` → полное требование куратора (Ревизия 2)

> Журнал результатов миграции по рабочим планам `dev/migr_plan_0.md` … `dev/migr_plan_12.md`.
> План-эталон: `dev/migr_plan.md` (формат записей — §6.4, правила повтора — §6.2).
> Обозначения: ✅ выполнено · ❌ не выполнено (повтор) · ⚠ допустимое временное отклонение ·
> ⛔ блокирующая ошибка (ожидание указаний).
> История прошлой ревизии (M0–M8: discovery по локальному stdio) — в `dev/old_vers/2/`.

> **Ревизия 2.** Куратор уточнил: «👉 устанавливает MCP-соединение; 👉 получает от MCP
> список доступных инструментов» означают **настоящее** подключение к **настоящему**
> MCP-серверу и **настоящий** запрос инструментов; глубина реализации — **полный LLM
> tool-use**. Соответственно план-эталон и рабочие планы переписаны заново (M0–M12).

---

## Этап M0 — Базовая линия Ревизии 2 и инвентаризация

- Статус: ✅ завершён
- Было: `den_16` с готовым вертикальным срезом прошлой ревизии (stdio): `core/tools.py`,
  `core/tool_registry.py`, `integrations/mcp/{config,transport,client,gateway,provider,
  demo_server}.py` (только stdio), `/mcp`-семейство (6 форм) + `--mcp`/`--mcp-probe` в
  `Kod.py`; L2 112 / L3 6 / L4 10 / гейт 18. **Нет** для полного требования: HTTP-транспорт,
  реальный endpoint, `tools/call`, `ToolExecutor`/`ToolPolicy`, LLM tool-use, блок `[tools]`,
  `/mcp call`.
- Стало: baseline зафиксирован; расхождения до полного требования перечислены; факты о
  реальном сервере записаны; точки внедрения зафиксированы; служебка под Ревизию 2 готова
  (`migr_log.md` очищен, `Проверка.md` — задел новых критериев).
- Проверка (без живого ключа):
  - L1 `py_compile Kod.py core/*.py memory/*.py storage/*.py integrations/mcp/*.py` → **ok**;
  - L2 `env -u API_KEY …/unit_runner.py` → **112 OK, 0 FAIL** (EXIT 0);
  - L3 `smoke.py` → **SMOKE OK** (6 тестов, EXIT 0);
  - L4 `scenario.py` → **10/10** (EXIT 0);
  - гейт `check_acceptance.sh` → **18 из 18, FAIL=0** (EXIT 0).
- **Факты о реальном сервере `https://weatherapi.projecteol.ru/mcp/`** (живой read-only
  discovery 2026-09-25):
  - protocol `2025-11-25`; `serverInfo: projecteol-weather v1.0.0`; `tools.list_changed=false`;
    instructions: «Use search_locations before requesting a forecast for a place name…»;
  - 3 тула: `search_locations` (`query: string` required, `limit: int 1..8` default 5),
    `get_forecast_metadata` (без аргументов), `get_weather_forecast`
    (`latitude`,`longitude` required числа; `start`, `hours` 1..168, `parameters[]`,
    `interpolation` enum nearest|linear);
  - `call_tool("search_locations",{"query":"Москва"})` → results[0] = Moscow RU,
    `lat 55.75204, lon 37.61781, tz Europe/Moscow`;
  - SDK 2.2.0 квирки: HTTP-вход — `mcp.client.streamable_http.streamable_http_client`
    (НЕ `streamablehttp_client`); атрибут схемы тула — `input_schema` (snake_case), что
    потребует фикса чтения схемы в M1.
- **Таблица расхождений «текущее → полное требование»**:

| Требование (Ревизия 2) | Текущее | Этап |
|---|---|---|
| `HttpMCPTransport` (Streamable HTTP) | нет (только stdio) | **M1** |
| Конфиг реального сервера (endpoint + env) | нет (только demo stdio) | **M1** |
| Фикс чтения схемы (`input_schema`) | читает `inputSchema` | **M1** |
| Реальное discovery к `weatherapi` | только demo | **M2** |
| `tools/call` (настоящий вызов) | `NotImplementedError` | **M3** |
| `ToolExecutor` + `ToolPolicy` + аудит | нет | **M4** |
| LLM tool-use (tools/tool_calls) | нет | **M5** |
| Блок `[tools]` + `ToolPromptPolicy` | нет | **M6** |
| Агентный tool-use цикл | нет | **M7** |
| `/mcp call`, DI tool-use, env | нет | **M8** |
| Живой прогон «найди Москва» | не делался | **M9** |
| Тесты/гейт под tool-use | контур stdio | **M10** |
| README/Проверка/scen под реальность | под stdio | **M11** |
| `arch_den_16.md` | под stdio | **M12** |

- **Точки внедрения (не менять)**: `core/state_machine.py` (TaskStage 8, карта, API
  контроля), `core/invariants.py` (кроме опционального расширения `ProposedAction`),
  `memory/*` (полностью), `storage/db.py`; базовые контракты `core/llm_client.py` и
  `core/prompt_builder.py` — расширяются **только обратно совместимо**.
- Артефакты: `dev/migr_log.md` (очищен, шапка Ревизии 2), `dev/Проверка.md` (задел),
  `dev/migr_plan.md` + `migr_plan_0..12.md` (переписаны под Ревизию 2).
- Спорное/риски: R1 — нативный tool-use у провайдера может быть недоступен → fallback (M5);
  R2 — SDK-квирки 2.2.0 → фикс (M1), проверка живым прогоном (M2/M9).
- Перечитывание migr_plan.md перед следующим этапом: ⏳ (будет отмечено после M1)
- Гейт M0→M1: ✅ пройден (baseline зафиксирован: L1 ok / L2 112 / L3 OK / L4 10 / гейт 18;
  расхождения перечислены; факты о сервере записаны; контракты зафиксированы; служебка готова)

---

## Этап M1 — HTTP-транспорт + конфиг реального сервера

- Статус: ✅ завершён
- Было: `transport.py` — только stdio + fake; чтение схемы через `inputSchema`; в конфиге
  только демо-сервер (stdio).
- Стало:
  - `transport.py`: + `HttpMCPTransport` (обёртка над `mcp.client.streamable_http.
    streamable_http_client`, SDK 2.2.0); единые хелперы `_tool_schema` (читает
    `input_schema` snake_case + fallback `inputSchema`/dict), `_normalize_tool`,
    `_normalize_call_result`, `_content_text`; `call_tool` в `Fake/Stdio/Http`; фабрика
    `make_transport(server)` (выбор по `transport`: `http`→Http, иначе stdio).
  - `config.py`: `WEATHER_MCP_URL` (env `MCP_WEATHER_URL`, дефолт
    `https://weatherapi.projecteol.ru/mcp/`); `DEFAULT_SERVERS` — основной `weather`
    (transport=http, enabled=True), демо `demo` (stdio, enabled=False) сохранён для тестов.
  - `client.py`/`gateway.py`: дефолтный транспорт — через `make_transport`; `_make_client`
    больше не падает в stdio.
  - `gateway.py`: `MCPGatewaySync` переписан на **одну долгоживущую задачу** (`_worker` в
    фоновом loop) — любой async-контекст `mcp` SDK (anyio cancel scope) входит и выходит
    в одной задаче (иначе `RuntimeError: cancel scope in a different task` на close).
- Проверка: L1 ok; L2 **112 OK, 0 FAIL**; L3 SMOKE OK; L4 10/10; гейт **18/18** (EXIT 0);
  смоук выбора транспорта (`http→HttpMCPTransport`, `stdio→StdioMCPTransport`), фикс схемы
  на объекте с `input_schema` — ok; тест `test_default_servers_and_store_roundtrip`
  обновлён под новый дефолт.
- Артефакты: `integrations/mcp/{transport,config,client,gateway}.py`,
  `dev/tests_debug/unit/test_mcp.py`.
- Спорное/риски: переписан `MCPGatewaySync` (устранён любой-to-cancel-scope квирк при
  повторном start/stop).
- Перечитывание migr_plan.md: ✅ выполнено
- Гейт M1→M2: ✅ пройден

---

## Этап M2 — Реальное discovery к weatherapi

- Статус: ✅ завершён
- Было: discovery только на локальном демо-сервере (stdio).
- Стало: **настоящее** подключение к `https://weatherapi.projecteol.ru/mcp/` и получение
  **настоящего** списка инструментов.
- Проверка (живой прогон, 2026-09-25):
  - `python Kod.py --mcp-probe` → `«weather»: подключён (READY)`; 3 инструмента
    `mcp.weather.search_locations` / `.get_forecast_metadata` / `.get_weather_forecast`
    с описаниями и input-схемами; `Всего инструментов: 3`; `DISCONNECTED`; **exit=0**.
  - REPL `--mcp`: `/mcp connect` → READY; `/mcp refresh` → «Каталог обновлён: 3 тулов
    (версия 1) … снимок сохранён (catalog.json)»; `/mcp status` → ready; `/mcp tools` —
    3 тула; `/mcp disconnect` → DISCONNECTED; `catalog.json` записан.
  - Деградация: `MCP_WEATHER_URL=https://invalid.invalid/mcp/` → `[MCP] Ошибка подключения`,
    **exit=1**; REPL жив (память/профили/автомат).
- Артефакты: подтверждённый живой вывод (транскрипты), `catalog.json` пользователя.
- Спорное/риски: —
- Перечитывание migr_plan.md: ✅ выполнено
- Гейт M2→M3: ✅ пройден

---

## Этап M3 — tools/call (инвентарь вызова)

- Статус: ✅ завершён
- Было: `MCPTransport.call_tool` — `NotImplementedError`; контракты `ToolCallRequest`/
  `ToolExecutionResult` — «задел».
- Стало:
  - `transport.py`: `call_tool` реализован в `Fake`/`Stdio`/`Http`; нормализация
    `CallToolResult` → `{isError, text, raw}`.
  - `client.py`: `MCPClient.call_tool` (сбой → `MCPConnectionError`).
  - `gateway.py`: `MCPGateway.call_tool(provider, tool, arguments, execution_id)` →
    `ToolExecutionResult` (сервер не READY → failed-результат, не исключение);
    `MCPGatewaySync.call_tool`.
  - `core/tools.py`: `ToolCallRequest` (+`call_id`), `ToolExecutionResult`
    (+`is_error`, `call_id`), новый `ToolExecutionState` (requested/denied/
    waiting_confirmation/running/succeeded/failed/timed_out/cancelled) — инфраструктурное
    состояние, НЕ `TaskStage`.
- Проверка (живой прогон): `gateway.call_tool("weather","search_locations",
  {"query":"Москва"})` → `status=succeeded`, `summary` содержит
  `"name": "Moscow", "country": "RU", "latitude": 55.75204, "longitude": 37.61781`.
  Fake: успех/`isError` — ok.
- Артефакты: `integrations/mcp/{transport,client,gateway}.py`, `core/tools.py`.
- Спорное/риски: `TaskStage` не затрагивается (инструмент ≠ переход).
- Перечитывание migr_plan.md: ✅ выполнено
- Гейт M3→M4: ✅ пройден

---

## Этап M4 — ToolExecutor + ToolPolicy + аудит

- Статус: ✅ завершён
- Было: вызов собирался вручную через gateway; понятий «policy» и «аудит вызова» не было.
- Стало:
  - `core/tool_policy.py` (новый): `ToolPolicy.check` — ступени enabled → схема
    аргументов → стадия (`allowed_stages`) → инварианты (`InvariantChecker` поверх
    `ProposedAction`) → `requires_confirmation`; итог `PolicyDecision(allowed, reason,
    needs_confirmation)`.
  - `core/tool_executor.py` (новый): `ToolExecutor.execute(request)` — policy → gateway →
    `ToolExecutionResult` → аудит `store.append_tool_audit` (execution_id, tool, status,
    phase, `arguments_hash` — только отпечаток, не сырые аргументы). НЕ вызывает StateMachine.
  - `core/invariants.py`: `ProposedAction` расширен опциональными
    `action_type`/`tool_name`/`arguments` (обратно совместимо); новое правило
    `tool.deny.<qualified>` — запрет конкретного инструмента.
- Проверка (смоук, fake-транспорт): исполнение (succeeded), отказ по схеме (нет required),
  отказ по стадии, отказ `not_found`, запись аудита (6 записей с `arguments_hash`);
  `TaskStage` не затрагивается. L1 ok; L2 **112 OK, 0 FAIL**; гейт **18/18** (EXIT 0).
- Артефакты: `core/tool_policy.py`, `core/tool_executor.py`, `core/invariants.py`.
- Спорное/риски: —
- Перечитывание migr_plan.md: ✅ выполнено
- Гейт M4→M5: ✅ пройден

---

## Этап M5 — LLM-клиент с поддержкой tool-use

- Статус: ✅ завершён
- Было: `LLMClient.complete` возвращал только текст; tools/tool_calls не поддерживались.
- Стало (`core/llm_client.py`):
  - `LLMReply(content, tool_calls, raw)`; парсеры `parse_tool_calls` (нативный
    OpenAI-формат) и `parse_fallback_tool_call` (JSON `{"tool":..,"arguments":..}`,
    снятие ```-обёрток), `TOOL_PROTOCOL_PROMPT`.
  - `LLMClient.complete_with_tools(messages, tools=None)` — базовый fallback-путь
    (для любого клиента); `RouterAIClient.complete_with_tools` — **нативный** путь
    (`tools`/`tool_choice`; разбор `message.tool_calls`; если нет — fallback-JSON из
    текста); `MockClient.complete_with_tools` — детерминированный tool-use по намерению
    («…Москва» → вызов `search_locations`; наличие tool-результата в истории →
    финальный ответ).
  - Обратная совместимость: `complete(messages)` — прежнее поведение.
- Проверка: парсеры (нативный/fallback/обычный текст/битый JSON) — ок; L1 ok;
  L2 **112 OK, 0 FAIL**; гейт **18/18** (EXIT 0).
- Артефакты: `core/llm_client.py`.
- Спорное/риски: если провайдер не даёт нативный tool_calls — сработает fallback
  (проверка на живом прогоне M9).
- Перечитывание migr_plan.md: ✅ выполнено
- Гейт M5→M6: ✅ пройден

---

## Этап M6 — Промт: блок [tools] + ToolPromptPolicy

- Статус: ✅ завершён
- Было: у `PromptBuilder` не было блока инструментов; `DELIVERABLE`/`BLOCK_ORDER` — без `tools`.
- Стало (`core/prompt_builder.py`):
  - `BLOCK_ORDER` — `tools` после `invariants`, до `long_term` (прежние блоки не смещены);
    `DELIVERABLE` расширен именем `tools`.
  - `render_tools(tools, max_tools, max_schema_tokens, include_descriptions)` — имя +
    описание + схема под лимитами (обрезка по числу и по бюджету токенов схем).
  - блок `[tools]` добавляется только если `tools` ∈ `deliver` и есть каталог/готовый
    `ctx.tools_block`; лимиты берутся из `ctx.max_tools`/`ctx.max_schema_tokens`.
  - `core/agent.py::PromptContext` расширен `tools/tools_block/max_tools/max_schema_tokens`.
- Проверка: блок `[tools]` присутствует при доставке `tools`, отсутствует иначе; порядок
  блоков сохранён (`tools` следует за `invariants`); `max_tools=0` → пусто; L1 ok;
  L2 **112 OK, 0 FAIL**; гейт **18/18** (EXIT 0).
- Артефакты: `core/prompt_builder.py`, `core/agent.py` (PromptContext).
- Спорное/риски: порядок блоков и нерегрессия подтверждены `test_blocks_order`.
- Перечитывание migr_plan.md: ✅ выполнено
- Гейт M6→M7: ✅ пройден

---

## Этап M7 — Агентный tool-use цикл + память/аудит

- Статус: ✅ завершён
- Было: `Agent.respond` делал один вызов LLM без инструментов.
- Стало (`core/agent.py`):
  - при включённом `tool_executor` + непустом каталоге — `_respond_with_tools`:
    цикл «LLM → tool call → execute → tool-сообщение → LLM» (лимит
    `max_tool_iterations=5`); спецификация тулов `_tool_specs` (OpenAI function-calling);
    добавление `TOOL_PROTOCOL_PROMPT` для fallback-пути.
  - `_record_external_action` — нормализованная запись `external_actions` в рабочую
    память (execution_id/tool/status/summary; сырой ответ НЕ пишется).
  - `build_context` подмешивает `tools` из каталога; без каталога — прежний путь.
- Проверка (смоук): «найди город Москва» (MockClient + fake-транспорт) → вызов
  `mcp.weather.search_locations` → ответ с результатом; аудит `tool_audit.jsonl` (1 запись,
  `arguments_hash`, call_id); инвариант `tool.deny.*` → вызов отклонён, ответ объясняет
  причину; L2 **112 OK**; L3 SMOKE OK; L4 10/10; гейт **18/18** (EXIT 0). `TaskStage`
  не меняется (инструмент ≠ переход).
- Артефакты: `core/agent.py`.
- Спорное/риски: MockClient детерминирован — живой прогон LLM на M9.
- Перечитывание migr_plan.md: ✅ выполнено
- Гейт M7→M8: ✅ пройден

---

## Этап M8 — CLI/DI: tool-use, /mcp call, env

- Статус: ✅ завершён
- Было: `--mcp` только строил gateway+registry; tool-use в REPL не включался; `/mcp call` не было.
- Стало (`Kod.py`):
  - `build_agent(--mcp)`: + `ToolPolicy` + `ToolExecutor` (с policy, gateway, store,
    checker); `agent.tool_executor/tool_policy`; `agent.deliver.add("tools")`;
    стартовое `gateway.start()` + `registry.refresh()` (деградация — не падение).
  - новая команда `/mcp call <tool> [{json}]` — ручной вызов через `ToolExecutor`;
    обновлён `/help`.
  - endpoint реального сервера — из env `MCP_WEATHER_URL` (через `config.WEATHER_MCP_URL`).
- Проверка: живой `/mcp call mcp.weather.search_locations {"query":"Москва"}` → результат
  с Moscow RU (55.75204, 37.61781); L1 ok; L2 **112 OK, 0 FAIL**; L4 10/10; гейт **18/18**.
- Артефакты: `Kod.py`.
- Спорное/риски: —
- Перечитывание migr_plan.md: ✅ выполнено
- Гейт M8→M9: ✅ пройден

---

## Этап M9 — Живой прогон «найди город Москва»

- Статус: ✅ завершён
- Было: сквозной живой прогон LLM+MCP не выполнялся.
- Стало: **полное требование куратора подтверждено на живых LLM + MCP**.
- Проверка (живой прогон, 2026-09-25, доказательства — `dev/logs_reports/stages/m9_live_run.md`):
  - REPL `--user m9u --mcp`, сообщение «найди город Москва» → агент: **«Нашёл город
    Москва (Россия) с координатами 55.75204, 37.61781»**; в логе
    `[Инструменты] mcp.weather.search_locations: succeeded`; `call_id` нативного
    формата (`chatcmpl-tool-…`).
  - `tool_audit.jsonl`: 1 запись (succeeded, `arguments_hash`, duration_ms=424).
  - Живой `/mcp call mcp.weather.search_locations {"query":"Москва"}` → Moscow RU
    (55.75204, 37.61781).
  - Живой `--mcp-probe` → 3 реальных тула, exit 0.
  - `TaskStage` не менялся; сырое не в память.
  - Каталог персистится при старте `--mcp` (`catalog.json`, 3 тула).
- Артефакты: `dev/logs_reports/stages/m9_live_run.md`, `m9_tool_audit.jsonl`,
  `m9_catalog.json`; правка `Kod.py` (сохранение каталога при стартовом discovery).
- Спорное/риски: нативный tool-use подтверждён (fallback не понадобился).
- Перечитывание migr_plan.md: ✅ выполнено
- Гейт M9→M10: ✅ пройден

---

## Этап M10 — Тесты и отладка

- Статус: ✅ завершён
- Было: L2 112, L3 6, L4 10, гейт 18 (контур stdio).
- Стало:
  - `unit/test_mcp.py`: +10 тестов (блоки 12–15): выбор HTTP-транспорта по конфигу;
    фикс `input_schema`; `call_tool` (fake успех/`isError`); `gateway.call_tool`
    (маршрут + failed); `ToolPolicy` (схема/стадия); `ToolExecutor` (исполнение+аудит,
    отказ по инварианту); парсеры tool-use; агентный tool-use цикл; блок `[tools]`.
    Обновлён `test_default_servers_and_store_roundtrip` под новый дефолт.
  - `scenario.py`: +`scenario_llm_tool_use` (намерение → вызов → ответ + аудит),
    +`scenario_tool_denied` (отказ инварианта).
  - `smoke.py`: +`test_mcp_tool_use_in_process`.
  - `check_acceptance.sh`: +3 проверки (HTTP-транспорт/схема; tools/call+policy+аудит;
    блок `[tools]`+tool-use цикл).
  - `core/tool_executor.py`: `_invoke` устойчив к sync-фасаду и async-шлюзу.
- Проверка (без живого ключа/сети): L1 ok; L2 **122 OK, 0 FAIL**; L3 **SMOKE OK**;
  L4 **14/14**; гейт **21 из 21** (EXIT 0).
- Артефакты: `dev/tests_debug/{unit/test_mcp.py,scenario.py,smoke.py,check_acceptance.sh}`,
  `core/tool_executor.py`.
- Спорное/риски: —
- Перечитывание migr_plan.md: ✅ выполнено
- Гейт M10→M11: ✅ пройден

---

## Этап M11 — Документация

- Статус: ✅ завершён
- Было: README/Проверка/scen описывали discovery по локальному stdio.
- Стало:
  - `README.md`: раздел «Подключение MCP» переписан под реальный сервер (HTTP,
    `weatherapi`), `tools/call`, `ToolExecutor`/`ToolPolicy`, полный LLM tool-use,
    `/mcp call`, пример «найди город Москва», env `MCP_WEATHER_URL`, аудит; обновлены
    счётчики (L2 122 / L3 7 / L4 14 / гейт 21 / приёмка 48), дерево модулей, команды,
    запуск, демонстрации, заделы, «Что зафиксировано».
  - `dev/Проверка.md`: критерии 41–48 заполнены (✅), итог 48/48.
  - `dev/tests_debug/scenario/scen_1.md`: переписан под реальный прогон (probe, REPL,
    `/mcp call`, LLM tool-use «найди Москва», изоляция прав, деградация, наследие).
- Проверка: гейт **21/21** (EXIT 0); расхождений документации с кодом нет.
- Артефакты: `README.md`, `dev/Проверка.md`, `dev/tests_debug/scenario/scen_1.md`.
- Спорное/риски: —
- Перечитывание migr_plan.md: ✅ выполнено
- Гейт M11→M12: ✅ пройден

---

## Этап M12 — Финал + актуализация `arch_den_16.md`

- Статус: ✅ завершён
- Было: `arch_den_16.md` описывал discovery по локальному stdio (Ревизия 1).
- Стало: `arch_den_16.md` актуализирован под Ревизию 2 — реальный HTTP-сервер
  (`weatherapi`), `HttpMCPTransport`, `tools/call`, `ToolExecutor`/`ToolPolicy`,
  полный LLM tool-use, аудит, `external_actions`, критерии 41–48, трассируемость
  (M0–M12); обновлены шапка, §0–§7 (дерево модулей, контракты, MCP-слой, DI/CLI,
  память/инварианты/промт, механика, карта артефактов, порядок достижения, итог,
  краткое описание).
- Финальный прогон (без живого ключа/сети): L1 ok; L2 **122 OK, 0 FAIL**;
  L3 **SMOKE OK**; L4 **14/14**; гейт **21 из 21** (EXIT 0).
- Живой прогон (реальный сервер + реальный LLM): `--mcp-probe` → READY, 3 тула,
  DISCONNECTED, exit 0; REPL «найди город Москва» → ответ с координатами Москвы
  (55.75204, 37.61781); аудит `succeeded` (call_id `chatcmpl-tool-…`); каталог
  персистится. Доказательства — `dev/logs_reports/stages/m9_live_run.md` (раздел M12).
- Артефакты: `arch_den_16.md`, `dev/logs_reports/stages/m9_live_run.md`.
- Спорное/риски: —
- Перечитывание migr_plan.md: ✅ выполнено
- Гейт M12 (финальный): ✅ пройден

---

## Итог миграции (Ревизия 2)

Миграция `den_15` → `arch_den_16.md` завершена: этапы **M0–M12** пройдены, все гейты
зелёные. Достигнуто полное требование куратора: **настоящее** подключение к
**реальному** MCP-серверу (`https://weatherapi.projecteol.ru/mcp/`, Streamable HTTP),
**настоящий** список инструментов (`tools/list` → 3 тула), **настоящий** вызов
инструмента (`tools/call` → координаты Москвы) и **полный LLM tool-use** (агент сам
вызывает инструмент по запросу «найди город Москва»).

- Тесты (без живого ключа/сети): L1 ok / L2 **122 OK** / L3 **SMOKE OK** / L4 **14/14** /
  гейт **21/21**.
- Приёмка: **48/48** (`dev/Проверка.md`).
- Живой прогон: `--mcp-probe` (3 тула) + REPL tool-use (ответ с координатами Москвы) +
  аудит `tool_audit.jsonl`.
- Наследие дней 11–15 без регрессии; MCP off по умолчанию; инструмент ≠ переход.

Коммит — только по явной команде пользователя.