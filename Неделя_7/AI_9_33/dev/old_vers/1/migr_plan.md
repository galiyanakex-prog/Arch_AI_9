# migr_plan.md — план-эталон миграции проекта `den_15` на архитектуру `arch_den_16.md`

> **Роль документа.** Это **план-эталон** (мастер-план) миграции проекта
> `Nedela_4/den_16/` (копия `den_15` — персонализированный stateful-агент с 4-слойной
> памятью, мультипрофилями, инвариантами и строгой машиной состояний) на целевую
> архитектуру `Nedela_4/den_16/arch_den_16.md` (подключение MCP: вертикальный срез
> MCP-подсистемы поверх наследия дней 11–15). Документ **не исполняется напрямую**:
> на его основе создаются рабочие план-файлы отдельных этапов `migr_plan_0.md`,
> `migr_plan_1.md`, … (`migr_plan_N.md`). Каждый рабочий план — это **подробный,
> исполняемый план-алгоритм одного этапа**. **Конец одного этапа — автоматический
> гейт в следующий этап.** Результаты выполнения каждого этапа записываются в журнал
> выполнения `Nedela_4/den_16/dev/migr_log.md`.
> Источники: `arch_den_16.md` (целевое состояние), `Задание_d16.txt` (неизменяемый
> первоисточник), `Рекомендации_MCP_d16.txt` (фундамент на будущее — целевая
> MCP-подсистема недели 4), `Суть_N4.md` (канон недели: MCP — стандарт, не
> фреймворк; тулинг — изоляция прав; день 16 — минимальное подключение и discovery),
> `Nedela_3/den_15/dev/migr_plan.md` (процессная модель-образец).

---

## 0. Назначение и границы

### 0.1 Что делает миграция
Приводит проект `den_16` (копия `den_15`) к целевому состоянию `arch_den_16.md`
добавлением **шестого, интеграционного «кубика» — MCP как внешний источник
инструментов** (не заменяя ни один из пяти кубиков дней 11–15):

1. **Внутренняя модель инструментов** — `core/tools.py`: `ToolDescriptor`,
   `ToolCallRequest`, `ToolExecutionResult`, `ToolProvider` (ABC),
   `ToolCatalogSnapshot` — контракты **без MCP SDK и без сети**; модель MCP не
   протекает в `core`.
2. **Каталогизация** — `core/tool_registry.py`: `ToolRegistry` (add_provider /
   unregister_provider / get / available_for / snapshot / refresh) с **атомарным
   snapshot**; реестр не проверяет бизнес-правила и не вызывает `StateMachine`.
3. **MCP-слой** — `integrations/mcp/`: `config.py` (`MCPServerConfig` + загрузка
   `servers.json`), `transport.py` (`MCPTransport` ABC + `StdioMCPTransport` на
   `mcp` SDK + `FakeMCPTransport`), `client.py` (`MCPClient`: initialize /
   list_tools — единственный импорт SDK), `gateway.py` (`MCPGateway` +
   `MCPConnectionState` + синхронный фасад `MCPGatewaySync`), `provider.py`
   (`MCPToolProvider` — нормализация mcp-тула → `ToolDescriptor`), `demo_server.py`
   (локальный stdio MCP-сервер, 3 тула: get_time, echo, weather_stub).
4. **Хранение** — `storage/store.py`: `users/<id>/integrations/mcp/servers.json`
   (конфиг) + `catalog.json` (снимок каталога) через новые методы фасада; битый
   файл → дефолт, приложение не падает.
5. **CLI** — `Kod.py`: DI с `mcp_enabled=False` по умолчанию; семейство `/mcp`
   (status / servers / tools / refresh / connect / disconnect); флаги `--mcp` и
   `--mcp-probe` (one-shot: подключиться → вывести список тулов → закрыться).
6. **Результат задания** — «код, который подключается к MCP и выводит список
   доступных инструментов»: `--mcp-probe` и `/mcp tools` — один кодовый путь
   `MCPGateway → MCPToolProvider → ToolRegistry`.

### 0.2 Границы (что миграция НЕ делает)
- **Не переписывает** наследие дней 11–15: `LLMClient`/`RouterAIClient`/`MockClient`,
  модель памяти (4 слоя), `MemoryManager`, `ProfileRepository`, `ProfileRouter`,
  `core/invariants.py`, `core/state_machine.py` (строгая машина состояний),
  `prompt_builder.py` (`BLOCK_ORDER`/`DELIVERABLE`/`budget`) — контракты сохраняются
  полностью (см. `arch_den_16.md` §2.7).
- **Не реализует** заделы недели 4 (места зарезервированы, не строятся):
  policy pipeline (`ToolPolicy`, расширение `ProposedAction`), `ToolExecutor` +
  `tools/call`, `tool_audit.jsonl`, `ToolMemoryPolicy`, `ToolPromptPolicy` +
  блок `[external_context]`, полный async core (вариант A), параллелизм read-only
  тулов, сравнение токен-флоу MCP vs Skill + CLI (цель недели, не дня 16).
- **Не меняет** `TaskStage` (8 стадий дня 15) и не добавляет MCP-стадий:
  **инструмент ≠ переход**; успех вызова MCP не создаёт запись в `transition_log`.
- **Не регрессирует**: прежние 35 критериев приёмки остаются зелёными; MCP
  выключен по умолчанию (`mcp_enabled=False`) — без `--mcp` агент работает ровно
  как `den_15`.
- **Не трогает** рабочие артефакты пользователя `users/` проекта во время прогонов
  тестов (временные файлы — только в `dev/tests_debug/.tmp/`).
- **Не коммитит** без явной команды пользователя.

### 0.3 Целевые артефакты (продукт) — из `arch_den_16.md` §4.1
`core/tools.py`, `core/tool_registry.py`, `integrations/mcp/*` (config / transport /
client / gateway / provider / demo_server), `storage/store.py` (+ методы каталога),
`Kod.py` (+ `/mcp`-семейство, `--mcp`, `--mcp-probe`),
`users/<id>/integrations/mcp/{servers,catalog}.json`, `README.md` (+ раздел
«Подключение MCP»).

### 0.4 Исходное состояние (факт M0)
`den_16` — копия `den_15` после завершённой миграции M0–M7 (журнал
`Nedela_3/den_15/dev/migr_log.md`): L2 **91 OK / 0 FAIL** (10 модулей), L3 SMOKE OK,
L4 **9/9**, гейт **15 из 15**, приёмка **35/35**. В корне копии: `arch_den_16.md`
(создан), `Задание_d16.txt`, `Рекомендации_MCP_d16.txt`, `Video_d15.txt`,
`Den_log.md`, `tokens.csv`, `run.sh`, `run.desktop`, `Kod.py`, `core/`, `memory/`,
`storage/`, `users/`, `dev/` (унаследованный контур: `unit_runner.py`, `smoke.py`,
`scenario.py`, `check_acceptance.sh` — 15 проверок, смоуки этапов `m1/m2/m34_smoke.py`,
`Проверка.md` — 35 строк, `migr_plan.md`/`migr_log.md` — **от den_15, подлежат
переделке под den_16**). `mcp` SDK в venv **не установлен** (проверено: `import mcp`
→ ModuleNotFoundError; в venv только requests/python-dotenv) — устанавливается M1.
`README.md` в корне копии **отсутствует** (как и в копии den_15 на M0) — создаётся M7.

---

## 1. Конвейер документов: `migr_plan.md` → `migr_plan_N.md` → `migr_log.md`

```text
migr_plan.md  (план-эталон, ЭТОТ файл)
      │  описывает этапы M0…M8, зависимости, критерии гейтов
      ▼
migr_plan_0.md … migr_plan_N.md  (рабочий план-алгоритм ОДНОГО этапа)
      │  пошагово, исполняемо: команды, файлы, ожидаемые результаты
      ▼
выполнение этапа  →  АВТОМАТИЧЕСКИЙ ГЕЙТ (см. §6)
      │   зелёный  → ПЕРЕЧИТАТЬ migr_plan.md → открывается migr_plan_(N+1).md
      │   красный → карточка ошибки в logs_reports/errors/, этап НЕ закрыт
      ▼
migr_log.md  (журнал: было → стало → проверка → статус, по каждому этапу)
```

### 1.1 Правила работы с документами
- `migr_plan.md` — **единственный источник истины** по составу и порядку этапов;
  рабочие планы `migr_plan_N.md` **не противоречат** ему и **не расширяют** объём
  этапа без записи в `migr_log.md`.
- Один рабочий план = один этап = один автоматический гейт.
- **ОБЯЗАТЕЛЬНО: после завершения каждого этапа (перед началом следующего) —
  перечитать `migr_plan.md`.** Эталон мог быть обновлён по итогам этапа; следующий
  рабочий план `migr_plan_(N+1).md` создаётся **только после повторного чтения**
  актуального `migr_plan.md`. Пропуск перечитывания — нарушение процесса миграции.
- `migr_log.md` — журнал миграции (форма записи — §6.4); **перед M0 журнал den_15
  очищается** (его итоги сохранены в `Nedela_3/den_15/dev/migr_log.md`).
- Нумерация: `migr_plan_0.md` — первый этап, далее `_1`, `_2`, … по порядку §4.

---

## 2. Принципы миграции (правила процесса)

- **Инварианты самой миграции**: (1) не менять контракты дней 11–15 (вне новых
  модулей и точек внедрения §4); (2) `TaskStage` не трогается — инструмент ≠
  переход; (3) MCP выключен по умолчанию — регрессия запрещена; (4) модель MCP не
  протекает в `core` (SDK импортируется только в `integrations/mcp/client.py`);
  (5) временные файлы — только в `.tmp/`.
- **MCP — источник инструментов, не слой контроля**: `MCPGateway` — адаптер («как
  технически вызвать»), не знает о стадиях/профилях/памяти; контроль остаётся за
  `StateMachine` (этапы), `InvariantChecker` (действия — задел) и `ToolExecutor`
  (процедура — задел). Циклы `Agent → MCPGateway → StateMachine → Agent` запрещены.
- **Порядок по зависимостям**: сначала контракты без SDK (`core/tools.py`), затем
  реестр, затем MCP-слой (config → transport → client → gateway → provider →
  demo_server), хранение, CLI, тесты, документация.
- **Детерминизм без сети**: discovery, нормализация, каталог, коллизии, недоступный
  сервер, фильтры прав — тестируются на `FakeMCPTransport`; живое stdio-соединение
  с демо-сервером — интеграционный тест/демо, не гейт; живой ключ LLM не требуется.
- **Атомарность каталога**: обновление реестра — только полным snapshot
  (`build_and_validate_snapshot()` → swap), никогда «по одному инструменту».
- **Изоляция прав через тулинг** (канон `Суть_N4.md` §3.3): `allowed_tools`/
  `denied_tools` в `MCPServerConfig` — запрещённый тул не попадает в discovery.
- **Перечитывание эталона между этапами (обязательно)**: после завершения каждого
  этапа и **перед началом следующего** — перечитать `migr_plan.md`.
- **Обратимость**: каждый этап оставляет репозиторий в компилируемом/запускаемом
  состоянии (зелёный гейт — точка отката).
- **Устойчивость хранения**: битый/отсутствующий `servers.json`/`catalog.json` не
  роняет приложение — дефолт (наследие `Store`).

---

## 3. Карта этапов (обзор)

| Этап | Рабочий план | Цель | Основные артефакты | Зависит от |
|---|---|---|---|---|
| **M0** | `migr_plan_0.md` | Базовая линия и инвентаризация | отчёт-сверка, baseline | — |
| **M1** | `migr_plan_1.md` | SDK + контракты инструментов | `mcp` в venv, `core/tools.py` | M0 |
| **M2** | `migr_plan_2.md` | Реестр: каталог + атомарный snapshot | `core/tool_registry.py` | M1 |
| **M3** | `migr_plan_3.md` | MCP-слой: config/transport/client | `integrations/mcp/{config,transport,client}.py` | M1 |
| **M4** | `migr_plan_4.md` | MCP-слой: gateway/provider/demo | `integrations/mcp/{gateway,provider,demo_server}.py` | M3 |
| **M5** | `migr_plan_5.md` | Хранение: servers.json + catalog.json | `storage/store.py` | M1, M4 |
| **M6** | `migr_plan_6.md` | CLI: DI + `/mcp` + `--mcp-probe` | `Kod.py` | M1–M5 |
| **M7** | `migr_plan_7.md` | Тесты и отладка | `dev/tests_debug/*` | M1–M6 |
| **M8** | `migr_plan_8.md` | Документация + финал | `README.md`, `Проверка.md`, `scen_1.md`, приёмка | M0–M7 |

> Примечание к baseline: `README.md` в корне копии отсутствует → 2 проверки гейта
> ([2] «README непустой», [7] «README содержит раздел модели памяти») красные до M8
> (как в den_15 на M0). Гейт до M7 прогоняется с ожиданием «13 из 15 + 2 известных
> красных (README)» — допустимое временное отклонение ⚠, закрывается M8. После M7
> гейт расширяется до 18 проверок (+3 MCP), после M8 — 18 из 18.

---

## 4. Детальный план по этапам

> Для каждого этапа: **Цель**, **Вход**, **Шаги**, **Выход**, **Гейт**. Рабочий план
> `migr_plan_N.md` разворачивает шаги в конкретные команды/правки.

### Этап M0 — Базовая линия и инвентаризация (`migr_plan_0.md`)

- **Цель**: зафиксировать текущее состояние `den_16` (копия `den_15`) и убедиться,
  что наследие зелёное **до** изменений; перечислить расхождения с
  `arch_den_16.md` §2.1; подготовить служебные документы.
- **Шаги**:
  1. Сверить фактическое дерево модулей с `arch_den_16.md` §2.1 (что есть/нет:
     `core/tools.py`, `core/tool_registry.py`, `integrations/` — отсутствуют).
  2. Зафиксировать baseline: L1/L2/L3/L4/гейт (без живого ключа); зафиксировать 2
     известных красных проверки гейта (README — отсутствует в копии, закрывается M8).
  3. Отметить точки внедрения (не менять): `llm_client.py`, `memory/*`,
     `storage/db.py`, `profile_router.py`, `invariants.py`, `state_machine.py`,
     `prompt_builder.py`.
  4. Составить перечень расхождений «текущее → целевое» (для M1–M8).
  5. Подготовить служебные документы: переделать `dev/migr_plan.md` (этот файл —
     уже переделан под den_16), **очистить** `dev/migr_log.md` (итоги den_15
     сохранены в `Nedela_3/den_15/dev/migr_log.md`), создать `dev/Проверка.md`
     под День 16 (35 прежних строк + задел строк 36–40), заархивировать смоуки
     этапов den_15 (`m1/m2/m34_smoke.py` → `dev/logs_reports/archive/`).
- **Гейт M0→M1**: baseline зафиксирован (L2 91 / L4 9 / гейт 13+2⚠); расхождения
  перечислены; точки внедрения зафиксированы; служебные документы готовы.

### Этап M1 — SDK + контракты инструментов (`migr_plan_1.md`)

- **Цель**: установить `mcp` SDK и создать внутреннюю модель инструментов
  (`arch_den_16.md` §2.2) — **без MCP-слоя и без сети**.
- **Шаги**:
  1. Установить `mcp` (Model Context Protocol Python SDK) в venv недели
     (`../../.venv/bin/pip install mcp`); зафиксировать версию; проверить
     `python -c "import mcp"`; убедиться, что `core/`/`memory/`/`storage/` SDK
     **не импортируют** (зависимость — только для `integrations/mcp/`).
  2. `core/tools.py` — контракты: `ToolDescriptor` (frozen dataclass: name,
     description, input_schema, source, provider, original_name + дефолты заделов
     risk_level="unknown", allowed_stages=ALL_WORKING_STAGES,
     requires_confirmation=False, enabled=True); `ToolCallRequest` (задел);
     `ToolExecutionResult` (задел); `ToolProvider` (ABC: discover / provider_id);
     `ToolCatalogSnapshot` (version, tools, created_at); `ALL_WORKING_STAGES`
     (5 рабочих стадий дня 15).
  3. Примитив-смоук этапа: импорт контрактов, создание дескриптора, snapshot.
- **Гейт M1→M2**: `import mcp` успешен; `core/tools.py` импортируется; L1/L2/L3/L4
  без регрессии (SDK не протёк в ядро); смоук контрактов зелёный.

### Этап M2 — Реестр: каталог + атомарный snapshot (`migr_plan_2.md`)

- **Цель**: `core/tool_registry.py` по `arch_den_16.md` §2.3.
- **Шаги**:
  1. `ToolRegistry`: `add_provider` / `unregister_provider` / `get` (неизвестное
     имя → понятная ошибка) / `available_for` (задел: пока без фильтров) /
     `snapshot` / `refresh`.
  2. Механика `refresh()`: `discover()` у всех провайдеров → валидация схем
     (JSON Schema-примитивы: type/properties/required) → разрешение коллизий имён
     (квалифицированные имена `mcp.<server>.<tool>`) → сборка нового
     `ToolCatalogSnapshot` (version — монотонный счётчик) → **атомарный swap**.
  3. Недоступный провайдер при refresh → его тулы исключаются из нового snapshot,
     ошибка логируется, остальные провайдеры не страдают.
  4. Примитив-смоук этапа: реестр на заглушечном провайдере (без MCP): регистрация,
     snapshot, коллизия, unregister, недоступность.
- **Гейт M2→M3**: реестр импортируется; смоук зелёный (snapshot атомарен, version
  монотонный, коллизии разрешены, недоступность не роняет); L1/L2 без регрессии.

### Этап M3 — MCP-слой: config / transport / client (`migr_plan_3.md`)

- **Цель**: фундамент MCP-интеграции (`arch_den_16.md` §2.4, часть 1).
- **Шаги**:
  1. `integrations/__init__.py`, `integrations/mcp/__init__.py`.
  2. `config.py`: `MCPServerConfig` (frozen dataclass: server_id, transport="stdio",
     command, endpoint, enabled, trust_level, allowed_tools/denied_tools,
     timeout_seconds, max_result_bytes) + `load_servers_config(path)` — загрузка
     `servers.json` с дефолтами; битый/отсутствующий файл → конфиг по умолчанию
     (демо-сервер, enabled=true), приложение не падает.
  3. `transport.py`: `MCPTransport` (ABC: initialize / list_tools / call_tool-задел /
     close) + `StdioMCPTransport` (обёртка над `mcp` SDK: stdio-подпроцесс, timeout)
     + `FakeMCPTransport` (детерминированная заглушка: фиксированный список тулов,
     программируемые отказы/таймауты/is_error/смена каталога).
  4. `client.py`: `MCPClient` — единственное место импорта `mcp` SDK;
     `initialize()` (handshake: protocol version, capabilities), `list_tools()` →
     нормализованные сырые описания `{name, description, inputSchema}`; любой сбой →
     `MCPConnectionError` (не `None`, не молчание).
  5. Примитив-смоук этапа: config-дефолты + битый файл; FakeMCPTransport —
     list_tools/отказ/таймаут; StdioMCPTransport — импорт без запуска подпроцесса.
- **Гейт M3→M4**: модули импортируются; смоук зелёный (дефолты, битый файл,
  fake-транспорт, ошибка → исключение); L1/L2 без регрессии; SDK импортируется
  только в `client.py` (grep-проверка).

### Этап M4 — MCP-слой: gateway / provider / demo_server (`migr_plan_4.md`)

- **Цель**: шлюз, провайдер и локальный демо-сервер (`arch_den_16.md` §2.4, часть 2).
- **Шаги**:
  1. `gateway.py`: `MCPConnectionState` (disconnected/connecting/ready/degraded/
     failed) + `MCPGateway` (async: start/stop/status/discover; discover →
     list_tools у включённых серверов → фильтр allowed/denied_tools → нормализация;
     НЕ знает о TaskStage/профилях/памяти) + `MCPGatewaySync` (тонкая синхронная
     обёртка `asyncio.run` для REPL).
  2. `provider.py`: `MCPToolProvider(ToolProvider)` — provider_id="mcp"; discover()
     → gateway.discover() → тулы с source="mcp", provider=server_id,
     name=f"mcp.{server_id}.{original_name}".
  3. `demo_server.py`: минимальный локальный stdio MCP-сервер на `mcp` SDK, 3 тула:
     `get_time` (текущее время), `echo` (повтор текста), `weather_stub` (units
     Celsius|Kelvin + location — канон погодного примера лекции); запуск
     `python -m integrations.mcp.demo_server`.
  4. Примитив-смоук этапа: gateway на FakeMCPTransport (start → READY → discover →
     фильтр прав → stop → DISCONNECTED); интеграционный прогон: StdioMCPTransport
     поднимает demo_server подпроцессом → initialize → list_tools → 3 тула.
- **Гейт M4→M5**: gateway/provider импортируются; смоук зелёный (READY, фильтр,
  чистое отключение); **интеграционный прогон с demo_server даёт 3 тула**; L1/L2
  без регрессии.

### Этап M5 — Хранение: servers.json + catalog.json (`migr_plan_5.md`)

- **Цель**: персистентность MCP-конфига и каталога через фасад `Store`
  (`arch_den_16.md` §2.5).
- **Шаги**:
  1. `storage/store.py`: `mcp_servers_path` / `read_mcp_servers` /
     `write_mcp_servers`; `tool_catalog_path` / `save_tool_catalog` /
     `load_tool_catalog` (миграция: отсутствующий/битый файл → пустой каталог
     `{"schema_version": 1, "version": 0, "tools": [], "created_at": null}`).
  2. Задел (только сигнатуры, без реализации): `append_tool_audit` /
     `load_tool_audit` — `users/<id>/tasks/<task>/tool_audit.jsonl` (день 17+).
  3. Проверка: round-trip каталога (save → load равны); битый файл → пустой
     каталог; `MCPGateway` JSON напрямую не пишет (grep-проверка).
- **Гейт M5→M6**: round-trip равен; битый файл не роняет; gateway не пишет JSON
  мимо Store; L1/L2/L3/L4 без регрессии.

### Этап M6 — CLI: DI + `/mcp` + `--mcp-probe` (`migr_plan_6.md`)

- **Цель**: рабочие команды и флаги результата задания (`arch_den_16.md` §2.6).
- **Шаги**:
  1. `build_agent()`: опциональная сборка MCP-слоя при `mcp_enabled` (gateway →
     provider → `tool_registry.add_provider`); по умолчанию `mcp_enabled=False`.
  2. Семейство `/mcp` (6 форм): `status` (состояние подключения + версия каталога),
     `servers` (список из servers.json), `tools` (**результат задания**: имя /
     description / input-схема каждого тула), `refresh` (discover → registry.
     refresh → атомарный swap → сейв каталога), `connect <id>`, `disconnect <id>`.
  3. Флаги: `--mcp` (включить MCP-слой в REPL), `--mcp-probe` (one-shot: подключиться
     → handshake → tools/list → вывести список → корректно закрыться → exit 0;
     недоступный сервер → понятная ошибка, exit 1). Итого флагов 14 (12 + 2).
  4. `/help` — обновление (семейство `/mcp`); `/mcp`-команды токенов LLM не тратят.
  5. REPL-смоук этапа: `--mcp-probe` (на FakeMCPTransport) → список тулов → exit 0;
     REPL `/mcp connect` → `/mcp tools` → `/mcp refresh` → `/mcp status` →
     `/mcp disconnect`; без `--mcp` агент работает как den_15.
- **Гейт M6→M7**: REPL-смоук канона задания проходит полностью; `--mcp-probe`
  выводит список; без `--mcp` поведение = den_15; наследие не регрессирует;
  L1 зелёный.

### Этап M7 — Тесты и отладка (`migr_plan_7.md`)

- **Цель**: закрыть тестовый контур `arch_den_16.md` §3.2.
- **Шаги**:
  1. `unit/test_mcp.py` (новый; всё на `FakeMCPTransport`, без сети): контракты
     (квалифицированное имя, source/provider); discovery-нормализация; реестр
     (add/refresh/snapshot, коллизии, unregister, get-ошибка); атомарность
     (version монотонный, «половинного» каталога не бывает); недоступный сервер
     (FAILED, тулы исключены, остальные живы); фильтр allowed/denied_tools;
     персистентность (round-trip, битый файл → schema_version=1); **MCP не трогает
     состояние** (TaskStage не изменился, transition_log пуст); **MCP off по
     умолчанию** (без --mcp реестр пуст, агент = den_15).
  2. `scenario.py` + `scenario_mcp_discovery` (L4, сквозной, канон «Проверьте» из
     задания): `--mcp-probe` → соединение установлено (READY) → список корректно
     возвращен (3 тула) → список выведен → чистое отключение; вторая ветка — REPL
     `/mcp connect` → `/mcp tools` → `/mcp refresh` → `/mcp status` → `/mcp disconnect`.
  3. `smoke.py` — MCP-прогон (in-process + CLI subprocess с `--mcp-probe` на
     FakeMCPTransport).
  4. `check_acceptance.sh` — гейт 15 → **18 проверок** (+3: соединение
     устанавливается; список инструментов корректно возвращается; список выводится
     кодом `--mcp-probe`).
  5. Интеграционный тест (не гейт): StdioMCPTransport + demo_server подпроцессом.
- **Гейт M7→M8**: `unit_runner.py` — все зелёные (вкл. `test_mcp.py`); `scenario.py`
  — 10 сценариев; `check_acceptance.sh` — 16 из 18 (2 ⚠ README — закрываются M8);
  всё без живого ключа и сети; идемпотентность гейта.

### Этап M8 — Документация + финал (`migr_plan_8.md`)

- **Цель**: описать фактическую реализацию и провести приёмку
  (`arch_den_16.md` §4.1–4.3, §5).
- **Шаги**:
  1. `README.md` — создать на базе `den_15/README.md` + раздел «Подключение MCP»
     (модель инструментов, реестр, MCP-слой, `/mcp`-команды, `--mcp-probe`,
     изоляция прав, «инструмент ≠ переход», MCP off по умолчанию); обновить
     счётчики (команды, флаги 14, сценарии 10, гейт 18, приёмка 40, L2).
  2. `dev/Проверка.md` — строки 36–40 (критерии подключения MCP: SDK установлен /
     сервер поднимается; соединение устанавливается; список корректно
     возвращается; список выводится кодом; регрессия MCP off) + итог 40/40.
  3. `dev/tests_debug/scenario/scen_1.md` — переписать под День 16 (демо MCP:
     `--mcp-probe`, `/mcp`-семейство, фильтр прав, недоступный сервер).
  4. Сверить формулировки README/Проверки с кодом (без расхождений).
  5. Финальный прогон: L1 → L2 → L3 → L4 → гейт **18/18**; приёмка **40/40**
     (36–40 зелёные + прежние 35 без регрессии); трассируемость §9.
  6. Запись итога в `migr_log.md` («Итог миграции»); **предложение коммита**
     (коммит — только по явной команде пользователя).
- **Гейт (финальный)**: 36–40 зелёные **и** прежние 35 зелёные; гейт 18/18;
  артефакты `arch_den_16.md` §4 присутствуют; все этапы M0–M8 в `migr_log.md` (✅).

---

## 5. Сквозные требования и запреты

- **Регрессия запрещена**: прежние 35 критериев приёмки остаются зелёными после
  каждого этапа; без `--mcp` поведение агента = den_15.
- **Контракты дней 11–15 не меняются**: `LLMClient`/`RouterAIClient`/`MockClient`,
  `MemoryLayer`/`MemoryManager`, `ProfileRepository`/`ProfileRouter`,
  `core/invariants.py`, `core/state_machine.py` (TaskStage 8, карта, API контроля),
  `prompt_builder.py` (`BLOCK_ORDER`/`DELIVERABLE`/`budget`).
- **Инструмент ≠ переход**: `TaskStage` не меняется от вызовов MCP; MCP-стадий
  (`MCP_CONNECTING`, `WAITING_FOR_TOOL` и т.п.) не добавлять; инфраструктурные
  состояния — только `MCPConnectionState` (и задел `ToolExecutionState`).
- **Модель MCP не протекает в `core`**: `mcp` SDK импортируется только в
  `integrations/mcp/client.py`; `ToolDescriptor` — внутренняя модель агента.
- **Циклы зависимостей запрещены**: `MCPGateway` не знает о стадиях/профилях/памяти;
  направление: `Kod.py` → `core/` → `memory/` → `storage/`; `integrations/` —
  сбоку, подключается только DI-композицией.
- **Временные файлы — только в `dev/tests_debug/.tmp/`**; `users/` проекта тестами
  не трогается.
- **Без живого ключа и без сети**: тесты и гейты на `MockClient` /
  `API_KEY=test-key` / `FakeMCPTransport`; живой stdio-прогон с demo_server —
  интеграционный тест/демо, не гейт.
- **Один этап = один рабочий план = один гейт**; порядок по §4.
- **ОБЯЗАТЕЛЬНО: перечитывать `migr_plan.md` после завершения каждого этапа и перед
  началом следующего.**
- **Хранение — только через фасад `Store`**: gateway/provider JSON напрямую не
  пишут; битые файлы → дефолт.

---

## 6. Механизм автоматического гейта

### 6.1 Назначение
Гейт — проверяемая точка перехода: конец этапа `N` автоматически открывает этап `N+1`
**только при зелёном гейте**. Красный гейт закрывает этап в статусе «не завершён».

### 6.2 Порядок срабатывания
```text
завершение шагов migr_plan_N.md
        ↓
авто-прогон проверок гейта этапа N (см. §4, «Гейт N→N+1»)
        ↓
зелёный → ПЕРЕЧИТАТЬ migr_plan.md (обязательно, перед следующим этапом)
          → создать/открыть migr_plan_(N+1).md, запись этапа N в migr_log.md (✅)
красный → карточка ошибки в logs_reports/errors/error_<ts>.md, этап N остаётся открыт
```

### 6.3 Критерии гейта
Общие требования: компилируемость/запускаемость после этапа; нерегрессия прежних
критериев; детерминированность (без живого ключа и сети); изоляция временных файлов
в `.tmp/`; обязательное перечитывание `migr_plan.md` перед следующим этапом.
Особенность этой миграции: до M7 гейт `check_acceptance.sh` прогоняется с ожиданием
«13 из 15» (2 известных красных README-проверки [2], [7] — допустимое временное
отклонение ⚠, закрывается M8); после M7 гейт расширяется до 18 проверок, после M8 —
все 18 зелёные.

### 6.4 Шаблон записи в `migr_log.md`
```text
## Этап M<N> — <название>
- Статус: ✅ завершён | ⚠️ обход | ❌ открыт
- Было: <состояние до этапа>
- Стало: <состояние после этапа>
- Проверка: <команды/тесты и результат, exit-код>
- Артефакты: <изменённые/созданные файлы>
- Спорное/риски: <если есть>
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (дата/время)
- Гейт M<N>→M<N+1>: ✅ пройден | ❌ не пройден
```

---

## 7. Определение готовности (DoD) миграции

Миграция завершена, когда одновременно выполнено:
1. Целевые артефакты `arch_den_16.md` §4.1 созданы (`core/tools.py`,
   `core/tool_registry.py`, `integrations/mcp/*`, методы каталога в `Store`,
   `/mcp`-семейство + `--mcp`/`--mcp-probe` в `Kod.py`, раздел «Подключение MCP»
   в `README.md`).
2. Критерии приёмки 36–40 — зелёные (`arch_den_16.md` §4.3).
3. Прежние 35 критериев — без регрессии (приёмка 40/40).
4. Гейт: `unit_runner.py` → `scenario.py` (10) → `check_acceptance.sh` (18/18) —
   всё без живого ключа и сети.
5. Все этапы M0–M8 отражены в `migr_log.md` со статусом ✅; открытых ошибок нет.
6. Рабочие планы `migr_plan_0.md … migr_plan_8.md` созданы и исполнены.
7. После каждого этапа `migr_plan.md` перечитан (фиксация в `migr_log.md`).

---

## 8. Риски и откат

| Риск | Проявление | Смягчение |
|---|---|---|
| Регрессия наследия дней 11–15 | падение прежних тестов (91 OK) | baseline M0; прогон после каждого этапа; запрет правок контрактов; MCP off по умолчанию |
| SDK протёк в ядро | `core/` импортирует `mcp` | grep-проверка на каждом этапе; SDK только в `integrations/mcp/client.py` |
| Цикл зависимостей Agent→Gateway→StateMachine | импорт-петля, падение | gateway не знает о стадиях/памяти; DI-композиция только в `Kod.py` |
| Инструмент меняет TaskStage | нарушение канона «инструмент ≠ переход» | gateway/registry не вызывают StateMachine; тест «MCP не трогает состояние» (M7) |
| Коллизии имён тулов | перезапись тулов разных серверов | квалифицированные имена `mcp.<server>.<tool>` (M2) + тест |
| Неатомарное обновление каталога | «половинный» каталог для модели | атомарный swap snapshot (M2) + тест |
| Недоступный MCP-сервер роняет REPL | падение агента | `MCPConnectionState.FAILED` + деградация: память/профили/автомат работают (M4) + тест |
| Битые servers.json/catalog.json | потеря конфига/каталога | дефолты при загрузке (M3/M5) + тест |
| Фильтр прав не работает | запрещённый тул доступен | allowed/denied_tools в discovery (M4) + тест |
| Загрязнение `users/` тестами | испорченные данные | `.tmp/` для прогонов; `$TST/.tmp/acc_$$` |
| Сломанные callers CLI | падение `Kod.py` | MCP-слой опционален в DI; прежние команды не тронуты |

**Откат**: последний зелёный гейт — точка отката. Откат — только по явной команде
пользователя.

---

## 9. Трассируемость (архитектура → этапы)

| Раздел `arch_den_16.md` | Этап миграции |
|---|---|
| §2.2 Внутренняя модель инструментов (core/tools.py) | M1 |
| §2.3 ToolRegistry (каталог + атомарный snapshot) | M2 |
| §2.4 MCP-слой: config / transport / client | M3 |
| §2.4 MCP-слой: gateway / provider / demo_server | M4 |
| §2.5 Хранение (servers.json, catalog.json, задел audit) | M5 |
| §2.6 DI-композиция и CLI (/mcp, --mcp, --mcp-probe) | M6 |
| §2.7 Наследие без изменений + заделы (ProposedAction, ToolMemoryPolicy, [external_context]) | M0, все гейты |
| §2.8 Сводная механика дня 16 | M4, M6 |
| §3.2 tests_debug (test_mcp, scenario_mcp_discovery, гейт 18) | M7 |
| §4.1–4.3 Артефакты и критерии 36–40 | M8 |
