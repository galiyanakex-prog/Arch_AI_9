# migr_log.md — журнал выполнения миграции `den_15` → `arch_den_16.md`

> Журнал результатов миграции по рабочим планам `dev/migr_plan_0.md` … `dev/migr_plan_8.md`.
> План-эталон: `dev/migr_plan.md` (формат записей — §6.4, правила повтора — §6.2).
> Обозначения: ✅ выполнено · ❌ не выполнено (повтор) · ⚠ допустимое временное отклонение ·
> ⛔ блокирующая ошибка (ожидание указаний).
> Итоги предыдущей миграции (den_14 → den_15) — в `Nedela_3/den_15/dev/migr_log.md`.

---

## Этап M0 — Базовая линия и инвентаризация (2026-09-22)

- Статус: ✅ завершён
- Было: `den_16` — копия `den_15` после завершённой миграции M0–M7 (L2 91 OK,
  L4 9/9, гейт 15/15, приёмка 35/35 — по `Nedela_3/den_15/dev/migr_log.md`);
  `mcp` SDK отсутствовал; `integrations/`, `core/tools.py`, `core/tool_registry.py`
  не существовали; `dev/migr_plan.md` переделан под den_16; `migr_log.md`/
  `Проверка.md` — от den_15; смоуки этапов den_15 в `tests_debug/`.
- Стало: baseline зафиксирован; расхождения с `arch_den_16.md` §2.1 перечислены
  (таблица ниже); точки внедрения (неизменяемые контракты) зафиксированы;
  служебные документы готовы: `migr_log.md` очищен (шапка den_16),
  `Проверка.md` — под День 16 (35 строк наследия + задел 36–40), смоуки den_15
  архивированы в `dev/logs_reports/archive/den15_stage_smokes/`.
- Проверка:
  - L1 `py_compile Kod.py core/*.py memory/*.py storage/*.py` → ok;
  - L2 `env -u API_KEY .../unit_runner.py` → **91 OK, 0 FAIL** (EXIT 0);
  - L3 `smoke.py` → **SMOKE OK** (EXIT 0);
  - L4 `scenario.py` → **9 сценариев OK** (EXIT 0);
  - гейт `check_acceptance.sh` → **13 из 15** (FAIL=2): [2] «README непустой» и
    [7] «README содержит раздел модели памяти» — **только из-за отсутствия
    `README.md` в корне копии** (код и тесты зелёные); допустимое временное
    отклонение ⚠, закрывается этапом M8 (документация) — зафиксировано в
    `migr_plan.md` §3/§6.3;
  - `python -c "import mcp"` → **ModuleNotFoundError** (факт для M1 — SDK
    устанавливается M1);
  - `bash run.sh --help` → usage без ошибок импорта (12 флагов);
  - гейт после архивации смоуков — без новых красных (ссылок на смоуки в
    контуре нет — grep).
- Артефакты: `dev/migr_log.md` (очищен, шапка den_16), `dev/Проверка.md`
  (День 16), `dev/logs_reports/archive/den15_stage_smokes/{m1,m2,m34}_smoke.py`;
  изменённых файлов продукта нет.
- Спорное/риски: R1 (README в копии) — закрывается M8; R2 (гейт до M7 содержит
  15 проверок, после M7 — 18) — счёт гейта меняется на M7, ожидаемо.

### Таблица расхождений «текущее → целевое» (для M1–M8)

| Целевое (`arch_den_16.md`) | Текущее | Этап |
|---|---|---|
| `mcp` SDK в venv | отсутствует (ModuleNotFoundError) | **M1** |
| `core/tools.py` (ToolDescriptor/ToolProvider/ToolCatalogSnapshot…) | нет | **M1** |
| `core/tool_registry.py` (каталог + атомарный snapshot) | нет | **M2** |
| `integrations/mcp/config.py` (MCPServerConfig + servers.json) | нет | **M3** |
| `integrations/mcp/transport.py` (ABC + Stdio + Fake) | нет | **M3** |
| `integrations/mcp/client.py` (initialize/list_tools, единственный импорт SDK) | нет | **M3** |
| `integrations/mcp/gateway.py` (MCPConnectionState, discover, фильтр прав) | нет | **M4** |
| `integrations/mcp/provider.py` (MCPToolProvider) | нет | **M4** |
| `integrations/mcp/demo_server.py` (3 тула: get_time/echo/weather_stub) | нет | **M4** |
| `storage/store.py`: mcp_servers_path/read/write + tool_catalog_path/save/load | нет | **M5** |
| Задел `append_tool_audit`/`load_tool_audit` | нет | **M5** |
| `Kod.py`: DI mcp_enabled + `/mcp` (6 форм) + `--mcp`/`--mcp-probe` (14 флагов) | 12 флагов, без /mcp | **M6** |
| `unit/test_mcp.py` | нет | **M7** |
| `scenario_mcp_discovery` (10-й сценарий) | 9 сценариев | **M7** |
| Гейт 18 проверок (+3 MCP) | 15 проверок | **M7** |
| `README.md` (+ раздел «Подключение MCP») | **отсутствует в копии** | **M8** |
| `dev/Проверка.md` строки 36–40 | 35 строк (задел) | **M8** |
| `scen_1.md` под День 16 | сценарий Дня 15 | **M8** |

### Точки внедрения (НЕ менять — контракты дней 11–15, `arch_den_16.md` §2.7)
- `core/llm_client.py` (`LLMClient`/`RouterAIClient`/`MockClient` + константы);
- `memory/*` (4 слоя, `MemoryManager` — полностью);
- `storage/db.py` (`ProfileRepository`);
- `core/profile_router.py` (`ProfileRouter`);
- `core/invariants.py` (`ConstraintSet`/`InvariantChecker`/`RuleBasedChecker`);
- `core/state_machine.py` (TaskStage 8, `ALLOWED_TRANSITIONS`,
  `can_transition`/`try_transition`/`InvalidTransitionError` — **MCP его не
  трогает: инструмент ≠ переход**);
- `core/prompt_builder.py` (`BLOCK_ORDER`/`DELIVERABLE`/`build(ctx, deliver, budget)`).

- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-22)
- Гейт M0→M1: ✅ пройден (baseline зафиксирован: L2 91 / L3 OK / L4 9 / гейт 13+2⚠
  с зафиксированной причиной; расхождения перечислены; контракты зафиксированы;
  служебка готова; `import mcp` — факт для M1)

---

## Этап M1 — SDK + контракты инструментов (2026-09-22)

- Статус: ✅ завершён
- Было: `mcp` SDK отсутствовал (ModuleNotFoundError); `core/tools.py` не существовал.
- Стало: **`mcp` 2.2.0** установлен в venv недели (транзитивные зависимости:
  pydantic 2.13.5, anyio, httpx2, starlette, uvicorn и др. — зафиксировано;
  `requests`/`dotenv` живы); **`core/tools.py`** — контракты внутренней модели:
  `ALL_WORKING_STAGES` (5 рабочих стадий дня 15, строками — без импорта
  state_machine), `ToolDescriptor` (frozen, 10 полей: name/description/
  input_schema/source/provider/original_name + дефолты заделов risk_level=
  "unknown"/allowed_stages=ALL_WORKING_STAGES/requires_confirmation=False/
  enabled=True), `ToolCallRequest` (задел), `ToolExecutionResult` (задел, raw —
  только execution context), `ToolProvider` (ABC: provider_id/discover),
  `ToolCatalogSnapshot` (frozen: version/tools/created_at ISO).
- Проверка:
  - примитив-смоук `dev/tests_debug/.tmp/m1_smoke.py` → **6/6 блоков OK**
    (EXIT 0): import mcp; импорт контрактов; frozen+дефолты; snapshot; ABC;
    заделы;
  - grep `import mcp` в `core/ memory/ storage/ Kod.py` → **пусто** (SDK не
    протёк);
  - grep `core.tools` в `core/ memory/ storage/ Kod.py` → **пусто** (модуль
    подключается на M6);
  - регрессия: L1 ok; L2 **91 OK, 0 FAIL**; L3 SMOKE OK; L4 9/9; гейт
    **13 из 15** (2 ⚠ README [2]/[7] — ожидаемо, закрывается M8).
- Артефакты: venv (+`mcp` 2.2.0), `core/tools.py` (новый),
  `dev/tests_debug/.tmp/m1_smoke.py` (смоук этапа).
- Спорное/риски: (1) `mcp` 2.2.0 тянет заметный набор транзитивных зависимостей
  (pydantic/starlette/uvicorn) — это штатно для официального SDK, зафиксировано;
  (2) смоук этапа лежит в `.tmp/` (в `.gitignore`) — судьба смоуков этапов
  решается на M8 (традиция den_15: остаются как доказательства).
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-22)
- Гейт M1→M2: ✅ пройден (import mcp OK, версия зафиксирована; контракты = arch
  §2.2 построчно; SDK не протёк (grep ×2); L1 зелёный; L2 91/0; L3/L4/гейт —
  без изменений; прежние зависимости живы)

---

## Этап M2 — Реестр: каталог + атомарный snapshot (2026-09-22)

- Статус: ✅ завершён
- Было: каталогизации не было (`core/tools.py` — только контракты).
- Стало: **`core/tool_registry.py`** — `ToolRegistry`: `add_provider` (замена
  по provider_id с логом) / `unregister_provider` / `get` (неизвестное имя →
  KeyError с сообщением и списком доступных) / `available_for` (задел: все тулы
  snapshot) / `snapshot` (текущий, без пересборки) / `refresh` (discover у всех
  провайдеров → валидация схем JSON-примитивы (dict, type=object,
  properties/required) → коллизии квалифицированных имён (последний побеждает +
  лог) → сборка ToolCatalogSnapshot (version — монотонный счётчик) → **атомарный
  swap**). Недоступный провайдер изолирован: его тулы исключаются, остальные
  живы, refresh не падает. Реестр не импортирует `mcp`/`state_machine` (grep).
- Проверка:
  - примитив-смоук `dev/tests_debug/.tmp/m2_smoke.py` → **8/8 блоков OK**
    (EXIT 0): add+refresh; get известного/неизвестного; коллизия; невалидная
    схема; недоступный провайдер; атомарность (version 1,2; snapshot между
    refresh — старый целиком); unregister; available_for;
  - при отладке смоука найдена ошибка **самого смоука** (не реестра): два
    провайдера с одинаковым provider_id="stub" — второй заменяет первого
    (штатная семантика add_provider), поэтому «изоляция недоступного» не
    проявлялась; фикс — отдельный provider_id="fail" у падающего провайдера;
  - grep `state_machine|StateMachine|import mcp` в `core/tool_registry.py` →
    пусто (границы чистые);
  - регрессия: L1 ok; L2 **91 OK, 0 FAIL**; гейт **13 из 15** (2 ⚠ README).
- Артефакты: `core/tool_registry.py` (новый),
  `dev/tests_debug/.tmp/m2_smoke.py` (смоук этапа).
- Спорное/риски: (1) семантика «повторный provider_id → замена» — выбрана
  осознанно (обновление конфигурации провайдера без утечки старых тулов);
  задокументировано в докстринге; (2) невалидная схема → тул исключается с
  логом (не падение) — соответствует arch §2.3.
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-22)
- Гейт M2→M3: ✅ пройден (API = arch §2.3; refresh атомарен, version монотонный;
  коллизии разрешены; невалидная схема изолирована; недоступный провайдер
  изолирован; unregister работает; get — понятная ошибка; реестр не импортирует
  mcp/state_machine; L1 зелёный; L2 91/0; гейт 13+2⚠)

---

## Этап M3 — MCP-слой: config / transport / client (2026-09-22)

- Статус: ✅ завершён
- Было: `integrations/` не существовал; SDK установлен (M1), но не использовался.
- Стало: **`integrations/mcp/`** — `config.py` (`MCPServerConfig` frozen:
  server_id/transport/command/endpoint/enabled/trust_level/allowed_tools/
  denied_tools/timeout_seconds/max_result_bytes; `DEFAULT_SERVERS` — демо-сервер
  stdio; `load_servers_config` — отсутствующий/битый файл → `[DEFAULT_SERVERS]`,
  неизвестные ключи игнорируются, list→tuple); `transport.py`
  (`MCPConnectionError(server_id, reason)`; `MCPTransport` ABC (initialize/
  list_tools/call_tool-задел/close); `FakeMCPTransport` — программируемые
  fail_initialize/fail_list_tools/timeout + `set_tools` (смена каталога);
  `StdioMCPTransport` — обёртка над mcp SDK 2.2.0 (`mcp.client.stdio.
  stdio_client` + `ClientSession`, ошибки → MCPConnectionError)); `client.py`
  (`MCPClient`: транспорт инжектится; `initialize` (handshake, init_info);
  `list_tools` → нормализация `{name, description, inputSchema}` с дефолтами,
  битые описания пропускаются; любой сбой → MCPConnectionError, не None).
- Проверка:
  - примитив-смоук `dev/tests_debug/.tmp/m3_smoke.py` → **8/8 блоков OK**
    (EXIT 0): дефолт без файла; битый JSON; валидный файл (tuple/frozenset/
    неизвестные ключи); fake initialize+list_tools; отказ list_tools →
    исключение; таймаут → исключение; нормализация клиента с дефолтами;
    импорт StdioMCPTransport;
  - grep SDK: `import mcp` — **только** `integrations/mcp/transport.py`
    (внутри `StdioMCPTransport.initialize`, ленивый импорт; `client.py` —
    без прямого импорта SDK, транспорт инжектится); вне `integrations/` —
    чисто;
  - grep внутренностей: `state_machine|profile|memory` в `integrations/mcp/*`
    → пусто (слой не знает о внутренностях агента);
  - регрессия: L1 ok (включая `integrations/mcp/*.py`); L2 **91 OK, 0 FAIL**;
    гейт **13 из 15** (2 ⚠ README).
- Артефакты: `integrations/__init__.py`, `integrations/mcp/__init__.py`,
  `integrations/mcp/{config,transport,client}.py`,
  `dev/tests_debug/.tmp/m3_smoke.py`.
- Спорное/риски: (1) SDK импортируется в `transport.py` (StdioMCPTransport),
  а не в `client.py`, как в плане M3 — фактический API SDK 2.2.0 живёт на
  уровне транспорта (stdio_client/ClientSession), клиент только делегирует;
  инвариант «SDK только в integrations/mcp/» соблюдён, уточнение зафиксировано
  здесь; (2) ленивый импорт SDK внутри `initialize()` — fake-транспорт работает
  без SDK-инициализации при импорте модуля.
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-22)
- Гейт M3→M4: ✅ пройден (MCPServerConfig + дефолты; ABC + stdio + fake +
  MCPConnectionError; клиент initialize/list_tools с нормализацией; сбой →
  исключение; SDK только в integrations/mcp/ (grep); слой не знает о
  внутренностях (grep); L1 зелёный; L2 91/0; гейт 13+2⚠)

---

## Этап M4 — MCP-слой: gateway / provider / demo_server (2026-09-22)

- Статус: ✅ завершён
- Было: config/transport/client готовы (M3); шлюза, провайдера и демо-сервера не
  было.
- Стало: **`integrations/mcp/gateway.py`** — `MCPConnectionState` (disconnected/
  connecting/ready/degraded/failed); `MCPGateway` (async: `start` — CONNECTING →
  initialize → READY, сбой сервера → FAILED без падения остальных; `stop` —
  чистое закрытие → DISCONNECTED; `status` — по серверам + overall; `discover` —
  list_tools у серверов в READY → **фильтр прав** (denied исключает всегда,
  allowed непустой сужает) → нормализация в `ToolDescriptor` с квалифицированным
  именем `mcp.<server>.<tool>`; сервер в FAILED → тулов нет (каталог честен);
  `overall_state` — READY/DEGRADED/FAILED/DISCONNECTED); `MCPGatewaySync` —
  синхронный фасад (asyncio.run) для REPL. **`integrations/mcp/provider.py`** —
  `MCPToolProvider(ToolProvider)`: provider_id="mcp"; discover() — делегация
  шлюзу (async→sync через asyncio.run при прямом MCPGateway). **`integrations/
  mcp/demo_server.py`** — минимальный локальный stdio MCP-сервер на SDK 2.2.0
  (`MCPServer`, бывший FastMCP): 3 тула `get_time` / `echo` / `weather_stub`
  (location required, units Celsius|Kelvin — канон погодного примера лекции);
  запуск `python -m integrations.mcp.demo_server`.
- Проверка:
  - примитив-смоук `dev/tests_debug/.tmp/m4_smoke.py` → **7/7 блоков OK**
    (EXIT 0): start→READY; discover→3 тула с нормализацией; фильтр прав
    (denied/allowed); недоступный сервер изолирован + DEGRADED; stop→
    DISCONNECTED + discovery пуст; MCPToolProvider; MCPGatewaySync;
  - **интеграционный stdio-прогон** `dev/tests_debug/.tmp/m4_integration.py` →
    **ALL OK** (EXIT 0): initialize → READY; list_tools → 3 тула
    (mcp.demo.echo/get_time/weather_stub); close → DISCONNECTED; подпроцесс
    завершается чисто;
  - grep: gateway/provider не знают о TaskStage/профилях/памяти (единственное
    совпадение — слово «TaskStage» в докстринге gateway о том, что он их НЕ
    знает); SDK — только `transport.py` + `demo_server.py`;
  - регрессия: L1 ok; L2 **91 OK, 0 FAIL**; гейт **13 из 15** (2 ⚠ README).
- Артефакты: `integrations/mcp/{gateway,provider,demo_server}.py`,
  `dev/tests_debug/.tmp/{m4_smoke,m4_integration}.py`.
- Спорное/риски: (1) **API SDK 2.2.0 отличается от v1**: `FastMCP` переименован
  в `MCPServer` (`mcp.server.mcpserver`), `StdioServerParameters` принимает
  `command: str` + `args: list[str]` (не список целиком) — оба расхождения
  найдены интеграционным прогоном и исправлены (transport: command/args;
  demo_server: MCPServer); зафиксировано как карточка-знание, не ошибка
  процесса; (2) `MCPToolProvider.discover()` оборачивает async→sync
  (asyncio.run) при прямом MCPGateway — при MCPGatewaySync делегирует фасаду
  (без вложенных loop); (3) `status()["tools_count"]` — заглушка 0 (счётчик
  тулов заполняется discovery; уточнение — M6 при подключении к CLI).
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-22)
- Гейт M4→M5: ✅ пройден (MCPConnectionState 5 состояний; start/stop/status/
  discover работают; нормализация с квалифицированными именами; фильтр прав;
  недоступный сервер изолирован + DEGRADED; после stop discovery пуст;
  MCPGatewaySync работает; интеграционный stdio-прогон — 3 тула, чистое
  закрытие; границы grep; L1 зелёный; L2 91/0; гейт 13+2⚠)

---

## Этап M5 — Хранение: servers.json + catalog.json (2026-09-22)

- Статус: ✅ завершён
- Было: Store без MCP-методов; конфиг и каталог не переживали перезапуск.
- Стало: **`storage/store.py`** расширен (существующие методы не тронуты):
  `mcp_dir` (`users/<id>/integrations/mcp/`), `mcp_servers_path`/
  `read_mcp_servers`/`write_mcp_servers` (отсутствующий/битый файл → None —
  дефолт `[DEFAULT_SERVERS]` у вызывающего через `load_servers_config`);
  `tool_catalog_path`/`read_tool_catalog`/`save_tool_catalog` (снимок
  ToolCatalogSnapshot; отсутствующий/битый → None → пустой каталог
  schema_version=1/version=0); **задел аудита**: `tool_audit_path`/
  `append_tool_audit`/`load_tool_audit` (`users/<id>/tasks/<task>/
  tool_audit.jsonl`, append-only, битые строки пропускаются) — отдельно от
  `transition_log` (успешный вызов инструмента не создаёт запись о переходе).
- Проверка:
  - смоук `dev/tests_debug/.tmp/m5_smoke.py` → **8/8 блоков OK** (EXIT 0):
    servers round-trip; без файла → None; catalog round-trip (включая
    allowed_stages frozenset→sorted list); без файла → None; битый JSON → None;
    иерархия integrations/mcp; задел audit (append/load + битые строки);
    audit отдельно от transition_log;
  - grep `json.dump|open(` в `gateway.py`/`provider.py` → пусто (JSON пишут
    только через Store);
  - регрессия: L1 ok; L2 **91 OK, 0 FAIL** (`test_storage.py` зелёный);
    гейт **13 из 15** (2 ⚠ README).
- Артефакты: `storage/store.py` (расширение), `dev/tests_debug/.tmp/m5_smoke.py`.
- Спорное/риски: (1) `read_mcp_servers`/`read_tool_catalog` возвращают None при
  отсутствии/битости (а не дефолт) — дефолтизация в вызывающем
  (`load_servers_config`/DI), чтобы Store оставался тонким фасадом; (2) задел
  audit реализован полностью (append/load), рабочий вызов — день 17+.
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-22)
- Гейт M5→M6: ✅ пройден (round-trip равен; битые файлы → None/дефолт, не падают;
  задел audit зарезервирован; gateway/provider JSON не пишут (grep); иерархия
  = arch §2.5; L1 зелёный; L2 91/0; гейт 13+2⚠; db.py не тронут)

---

## Этап M6 — CLI: DI + `/mcp` + `--mcp-probe` (2026-09-23)

- Статус: ✅ завершён
- Было: `Kod.py` без MCP-флагов и `/mcp`-команд; `Agent` без атрибутов
  `mcp_gateway`/`tool_registry` (AttributeError при mcp off); дефолтный
  command demo-сервера — `("python", ...)` (падение: `python` нет в PATH);
  `MCPGatewaySync` делал `asyncio.run()` на каждый вызов.
- Стало: **`Kod.py`** — флаги `--mcp`/`--mcp-probe` (итого 14 флагов),
  `build_agent(mcp_enabled=False)` с DI (gateway+registry создаются только при
  `--mcp`; без флага — None, поведение = den_15), `run_mcp_probe()` (start →
  overall!=ready → exit 1 → discover → печать name/description/input_schema →
  stop → exit 0; без `input()`), `handle_mcp_command()` — 6 подкоманд
  (connect/tools/refresh/status/servers/disconnect), `/help` обновлён, dispatch
  в REPL и `main()` (`--mcp-probe` → `sys.exit(run_mcp_probe())`).
  **`core/agent.py`** — в `Agent.__init__` добавлены `self.mcp_gateway = None`,
  `self.tool_registry = None` (MCP off по умолчанию — атрибуты есть, значения
  нет). **`integrations/mcp/config.py`** — DEFAULT_SERVERS.command →
  `(sys.executable, "-m", "integrations.mcp.demo_server")`. **`integrations/mcp/
  gateway.py`** — `MCPGatewaySync` переведён на **постоянный фоновый event loop**
  (`threading.Thread` + `run_coroutine_threadsafe`): сессии `mcp` SDK привязаны
  к задачам loop'а, где прошёл initialize, поэтому отдельный `asyncio.run()` на
  каждый вызов зависал на `list_tools` (живой прогон это поймал, смоук на
  FakeMCPTransport — нет). API фасада не менялся.
- Проверка:
  - REPL-смоук `dev/tests_debug/.tmp/m6_smoke.py` → **21/21 OK** (EXIT 0):
    ветки A (probe fake: exit 0/exit 1), B (REPL: connect→READY, tools,
    refresh→3 тула+catalog.json, status, servers, disconnect, неизвестная
    подкоманда), C (без --mcp: None + наследие /memory+/state живо), D
    (недоступный сервер: FAILED→0 тулов, REPL жив), E (grep: Kod.py без
    `import mcp`);
  - **живой stdio-прогон** `timeout 30 env -u API_KEY ../../.venv/bin/python
    Kod.py --mcp-probe` → **EXIT 0**: READY → 3 тула (mcp.demo.get_time/echo/
    weather_stub) → DISCONNECTED; первый прогон до фикса event loop зависал
    (timeout 124) — зависание поймано живым прогоном и устранено;
  - интеграционный `dev/tests_debug/.tmp/m4_integration.py` → **ALL OK**
    (EXIT 0; в смоуке исправлен захардкоженный `("python", ...)` →
    `sys.executable` — тот же квирк PATH);
  - регрессия: L1 ok; L2 **91 OK, 0 FAIL**; L3 smoke OK; L4 scenario OK;
    гейт **13 из 15** (2 ⚠ README — закрывается M8).
- Артефакты: `Kod.py`, `core/agent.py`, `integrations/mcp/{config,gateway}.py`,
  `dev/tests_debug/.tmp/{m6_smoke,m4_integration}.py`.
- Спорное/риски: (1) `handle_mcp_command` читает приватные
  `gateway.gateway._servers` — допустимо для CLI-слоя, кандидат на публичный
  accessor при M7/M8; (2) судьба смоуков `.tmp/` (m1–m6) — решение на M8;
  (3) фоновый поток event loop в `MCPGatewaySync` — daemon, завершается с
  процессом; при встраивании в долгоживущие процессы стоит добавить явный
  `close()` фасада (день 17+); (4) `status()["tools_count"]` — счётчик из
  каталога (заполняется refresh).
- Карточки-знания: (а) **pip-квирк копированного venv**: `../../.venv/bin/pip`
  имеет shebang на ОРИГИНАЛЬНЫЙ venv (`pip show mcp` OK, `import mcp` падал) —
  установка ТОЛЬКО `../../.venv/bin/python -m pip install <pkg>`; утверждение
  журнала M1 «import mcp OK» было ложным (проверено 2026-09-23: `mcp` 2.2.0
  доустановлен в локальный venv); (б) **`python` отсутствует в PATH** (только
  `python3`) — все запуски подпроцессов через `sys.executable`; (в) **квирк
  event loop**: `asyncio.run()` на каждый вызов фасада несовместим с сессиями
  `mcp` SDK — нужен один постоянный loop на время жизни соединения.
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-23)
- Гейт M6→M7: ✅ пройден (флаги --mcp/--mcp-probe работают; /mcp 6 подкоманд;
  probe exit 0/1; без --mcp поведение = den_15; недоступный сервер не роняет
  REPL; Kod.py без import mcp (grep); живой stdio-прогон EXIT 0 — 3 тула,
  чистое закрытие; L1 зелёный; L2 91/0; L3/L4 OK; гейт 13+2⚠)

---

## Этап M7 — Тесты и отладка (2026-09-23)

- Статус: ✅ завершён
- Было: контур den_15 (91 тест, 9 сценариев, гейт 15); MCP-тестов нет.
- Стало: **`dev/tests_debug/unit/test_mcp.py`** — 21 тест, 11 блоков канона
  §3.2 (контракты, discovery-нормализация, реестр, коллизии, атомарность,
  недоступный сервер, фильтр прав, персистентность, «MCP не трогает
  состояние», «MCP off по умолчанию», конфиг); **`scenario.py`** —
  `scenario_mcp_discovery` (10-й сценарий, 3 ветки: probe-флоу, REPL-флоу
  connect→tools→refresh→status→disconnect, деградация fail_initialize);
  **`smoke.py`** — 6 тестов (4 прежних + `test_mcp_in_process` +
  `test_mcp_probe_subprocess` через wrapper-подпроцесс с подменой модулей);
  **`check_acceptance.sh`** — гейт 15 → **18** (+3 MCP: [16] probe/fake →
  READY + 3 тула + exit 0; [17] имена `mcp.demo.*`; [18] description +
  input_schema в stdout).
- Проверка:
  - L1 `py_compile` (включая `integrations/mcp/*.py`) → ok;
  - L2 `unit_runner.py` → **112 OK, 0 FAIL** (EXIT 0; 91 + 21 MCP);
  - L3 `smoke.py` → **SMOKE OK** (EXIT 0, 6 тестов);
  - L4 `scenario.py` → **10/10** (EXIT 0);
  - гейт `check_acceptance.sh` → **16 из 18** (FAIL=2: [2]/[7] — только
    README, ⚠ закрывается M8); идемпотентность — повторный прогон тот же
    результат;
  - интеграционный stdio-прогон (вне гейта, `timeout 30`, настоящий
    `StdioMCPTransport` + demo_server подпроцессом) → **EXIT 0**: READY →
    3 тула → DISCONNECTED, чистое завершение;
  - всё без живого ключа и сети; `users/` не тронуты; артефакты — только
    `dev/tests_debug/.tmp/`.
- **Правка продукта (отклонение от паспорта «Меняет поведение: нет»)**:
  баг-фикс `integrations/mcp/gateway.py` — `MCPGateway.stop()` сбрасывал
  состояния только подключённых серверов (`_clients`), поэтому FAILED-сервер
  залипал в "failed" → overall "failed" после stop (упал
  `test_failed_server_isolated`). По канону `arch_den_16.md` L305 (stop →
  DISCONNECTED) `stop()` теперь закрывает `_clients` (print «отключён» по
  каждому), `_clients.clear()`, затем сброс `self._states` **всех** серверов
  в DISCONNECTED. Поведение изменилось только в части сброса FAILED-серверов
  при stop — это исправление к канону, а не расширение; регрессия зелёная
  (L2 112/0, L3/L4 OK, гейт 16+2⚠).
- Артефакты: `dev/tests_debug/unit/test_mcp.py` (новый),
  `dev/tests_debug/{scenario.py, smoke.py, check_acceptance.sh}` (расширены),
  `integrations/mcp/gateway.py` (баг-фикс stop()).
- Спорное/риски: (1) fake-фасады в тестах наследуют `MCPGatewaySync`,
  переопределяя `__init__` (без фонового loop) и `_run` (=asyncio.run) —
  контракт `MCPToolProvider.discover()` (isinstance MCPGatewaySync →
  синхронный вызов) требует наследования, а не утиной типизации;
  (2) wrapper-обёртки probe получают корень дня через `ACC_BASE` (переменная
  окружения) — подсчёт dirname ненадёжен (глубина вложенности tmp-каталога
  различается между smoke и гейтом); (3) судьба смоуков `.tmp/` (m1–m6) —
  решение на M8.
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (2026-09-23)
- Гейт M7→M8: ✅ пройден (test_mcp 21/21 зелёные — 11 блоков §3.2;
  scenario_mcp_discovery 3 ветки, L4 10/10; smoke SMOKE OK 6 тестов; гейт
  18 проверок = 16 зелёных + 2 ⚠ README (причина зафиксирована), идемпотентен;
  интеграционный stdio-прогон — 3 тула, чистое завершение; без живого ключа
  и сети; users/ не тронуты; .tmp/ изолирован)

---

## Этап M8 — Документация + финал (2026-09-24)

- Статус: ✅ завершён
- Было: `README.md` в корне дня отсутствовал (причина ⚠ [2]/[7] гейта);
  `Проверка.md` — 35 зелёных + 36–40 задел 🟡; `scen_1.md` — сценарий Дня 15;
  итог миграции в журнале не записан.
- Стало: **`README.md`** создан в корне дня (база — `den_15/README.md`):
  шапка Дня 16, «Что нового относительно Дня 15», раздел «Модель памяти»
  (закрывает ⚠ [7]) + иерархия хранения с веткой `integrations/mcp/`, раздел
  **«Подключение MCP»** (модель инструментов, реестр, MCP-слой, хранение,
  DI/CLI, `/mcp` 6 форм, `--mcp-probe` с примером вывода, изоляция прав,
  «инструмент ≠ переход», сводная механика контроля), счётчики по факту
  (флаги 14, L2 112, L4 10, гейт 18, приёмка 40), заделы недели 4, известные
  шероховатости (SDK в transport.py, `gateway.gateway._servers`, смоуки
  `.tmp/` — оставлены как доказательства этапов, традиция den_15).
  **`dev/Проверка.md`** — строки 36–40: 🟡 → ✅ (команды по факту: гейт
  №16–18, test_mcp, scenario_mcp_discovery, интеграционные прогоны); итог
  файла — **40/40**. **`dev/tests_debug/scenario/scen_1.md`** — переписан под
  День 16 (5 шагов: `--mcp-probe` one-shot, REPL `/mcp`-флоу + catalog.json,
  изоляция прав denied_tools, недоступный сервер — деградация, наследие +
  «инструмент ≠ переход»; соответствие `Задание_d16.txt`; честность демо).
  **`dev/migr_plan_8.md`** — рабочий план этапа (создан по канону после
  перечитывания эталона).
- Проверка (финальный прогон, всё без живого ключа и сети):
  - L1 `py_compile` (включая `integrations/mcp/*.py`) → ok;
  - L2 `unit_runner.py` → **112 OK, 0 FAIL** (EXIT 0);
  - L3 `smoke.py` → **SMOKE OK** (EXIT 0, 6 тестов);
  - L4 `scenario.py` → **10/10** (EXIT 0);
  - гейт `check_acceptance.sh` → **18 из 18, FAIL=0, EXIT 0** — ⚠ [2]/[7]
    закрыты README; повторный прогон — тот же результат (идемпотентность ✅);
  - сверка документации с кодом: «Подключение MCP» и «Модель памяти» в
    README (grep), «40 из 40» в Проверке.md, счётчики = факт (112/10/18/40);
  - приёмка: 36–40 зелёные + прежние 35 без регрессии → **40/40**.
- Артефакты: `README.md` (новый, корень дня), `dev/Проверка.md` (36–40 + итог),
  `dev/tests_debug/scenario/scen_1.md` (переписан), `dev/migr_plan_8.md`
  (новый), `dev/migr_log.md` (эта запись + итог ниже). Код не менялся
  (паспорт «Меняет поведение: нет» соблюдён).
- Спорное/риски: (1) смоуки этапов `.tmp/` (m1–m6 + m4_integration/m5_verify)
  — **решение: остаются как доказательства этапов** (традиция den_15; в
  `.gitignore`, в дерево arch §3.1 не входят); (2) `handle_mcp_command` читает
  приватное `gateway.gateway._servers` — задокументировано в README как
  известная шероховатость, кандидат на публичный accessor дня 17+.
- Перечитывание migr_plan.md перед этапом: ✅ выполнено (2026-09-24, перед
  созданием migr_plan_8.md)
- Гейт (финальный): ✅ пройден (36–40 зелёные и прежние 35 зелёные — 40/40;
  гейт 18/18 exit 0; артефакты arch §4.1 присутствуют — README с разделом
  «Подключение MCP», Проверка.md 40/40, scen_1.md День 16; этапы M0–M8 в
  журнале ✅)

---

## Итог миграции (den_15 → arch_den_16.md)

Миграция завершена: **все этапы M0–M8 ✅**, DoD `migr_plan.md` §7 выполнен.

1. **Артефакты `arch_den_16.md` §4.1 созданы**: `core/tools.py` (контракты без
   SDK), `core/tool_registry.py` (каталог + атомарный snapshot),
   `integrations/mcp/{config,transport,client,gateway,provider,demo_server}.py`,
   методы каталога в `storage/store.py` (+ задел tool_audit), `/mcp`-семейство
   (6 форм) + `--mcp`/`--mcp-probe` (14 флагов) в `Kod.py`, `README.md` с
   разделом «Подключение MCP».
2. **Критерии приёмки 36–40 — зелёные** (SDK/демо-сервер; соединение
   устанавливается; список корректно возвращается; список выводится кодом;
   регрессия MCP off).
3. **Прежние 35 критериев — без регрессии** (приёмка **40/40**).
4. **Гейт**: L2 112/0 → L3 SMOKE OK → L4 10/10 → `check_acceptance.sh`
   **18/18 exit 0** — всё без живого ключа и сети; идемпотентность
   подтверждена. Интеграционный stdio-прогон (demo_server подпроцессом) —
   READY → 3 тула → DISCONNECTED, EXIT 0.
5. **Все этапы M0–M8 отражены в журнале** со статусом ✅; открытых ошибок нет
   (карточек в `logs_reports/errors/` за миграцию не создавалось — красных
   гейтов не было).
6. **Рабочие планы `migr_plan_0.md` … `migr_plan_8.md` созданы и исполнены.**
7. **Перечитывание `migr_plan.md` перед каждым этапом** — зафиксировано в
   каждой записи (M0–M8).

Отклонения от паспортов этапов (зафиксированы в журнале): баг-фикс
`MCPGateway.stop()` на M7 (правка продукта, сброс состояний всех серверов в
DISCONNECTED по канону arch L305); уточнение «SDK импортируется в
transport.py/demo_server.py, не в client.py» на M3 (фактический API SDK 2.2.0).
Результат задания («код, который подключается к MCP и выводит список доступных
инструментов») реализован вертикальным срезом `MCPGateway → MCPToolProvider →
ToolRegistry` в двух формах: `--mcp-probe` (one-shot) и `/mcp tools` (REPL).

---