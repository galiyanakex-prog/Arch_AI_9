# arch_den_16.md — итоговая целевая архитектура проекта `den_16` «Подключение MCP»

> Итоговый документ: описывает состояние, которое должно получиться **после завершения**
> проекта `den_16`. Базируется на `Nedela_3/den_15/arch_den_15.md` (персонализированный
> stateful-агент: 4 слоя памяти + мультипрофильность + строгая машина состояний + слой
> инвариантов) и **не заменяет ни один из пяти «кубиков» дней 11–15**, а добавляет к ним
> **шестой, интеграционный: MCP (Model Context Protocol) как внешний источник
> инструментов** — подключение, discovery (получение списка тулов), каталогизация в
> `ToolRegistry` и вывод списка доступных инструментов.
> Источники: `Суть_N4.md`, `Задание_d16.txt` (неизменяемый первоисточник),
> `Рекомендации_MCP_d16.txt` (фундамент на будущее — целевая MCP-подсистема всей недели 4).
>
> **Синхронизировано с фактом реализации: 2026-09-24.** Правки внесены строго по
> `README.md` (факт реализации) и `dev/migr_log.md` (история процесса и причины
> расхождений) — оба равноправные источники истины. `dev/migr_log.md` **не
> изменялся**; исходная версия документа («замысел до синхронизации») сохранена в
> `dev/old_vers/`.

---

## 0. Назначение документа

Документ фиксирует три слоя итогового состояния:

1. **Рабочая архитектура** — персонализированный stateful-агент дней 11–15 (память,
   профили, инварианты, контролируемый жизненный цикл) **без регрессии контрактов**,
   плюс **вертикальный срез будущей MCP-подсистемы**: `MCPGateway` (соединение +
   handshake + `tools/list`) → `MCPToolProvider` (нормализация тулов во внутреннюю
   модель) → `ToolRegistry` (каталог + атомарный snapshot + персистентность через
   `Store`) → CLI (`/mcp …` + флаг `--mcp-probe`). Результат задания — «код, который
   подключается к MCP и выводит список доступных инструментов», — реализуется **не
   одноразовым скриптом, а первым настоящим срезом подсистемы** (канон
   `Рекомендации_MCP_d16.txt`, раздел «Как сдавать учебное задание»).
2. **Служебное пространство `dev/`** — «проект про проект»: миграция `den_15` →
   `arch_den_16.md` по процессной модели «план-эталон → рабочие планы этапов → журнал»,
   с полным аудитом каждого этапа.
3. **Фундамент на будущее** — какие части целевой MCP-подсистемы недели 4
   (policy pipeline, `ToolExecutor`, `tools/call`, аудит, `MemoryPolicy`, resources)
   в `den_16` **не реализуются**, но их места в архитектуре уже зарезервированы,
   чтобы следующие дни наращивали, а не переписывали.

Главная идея задания (канон `Задание_d16.txt`): **минимальный код, который
устанавливает MCP-соединение и получает от MCP список доступных инструментов**.
Проверяется: соединение устанавливается; список инструментов корректно возвращается.
Формат результата — Код.

Главная идея недели (канон `Суть_N4.md`): MCP — стандарт (не фреймворк) подключения
нейронок к внешним сервисам; ядро MCP-сервера — маппинг «тул ↔ HTTP-реквест»
(description + input-схема + `CallToolResult`); токен-флоу MCP дорог (get_tools +
тяжёлая схема + накопление контекста, квадратичный рост при батчинге), поэтому
параллельно существует альтернатива Skill + CLI. День 16 — стартовый день недели:
минимальное подключение и discovery, **без** сравнения токен-флоу (это цель недели,
не дня — `Суть_N4.md` §4.8).

---

## 1. Ключевая идея и принципы

### 1.1 Ключевая идея

`den_16` — переход от «агента с внутренними возможностями» (дни 11–15: память,
профили, инварианты, переходы) к **агенту, подключённому к внешнему миру через
стандартный протокол**. Появляются четыре новых элемента:

1. **MCP-соединение** — `MCPGateway` устанавливает соединение с MCP-сервером
   (транспорт `stdio` к локальному демо-серверу; HTTP — задел), выполняет handshake
   (`initialize`) и держит состояние подключения (`MCPConnectionState`).
2. **Discovery** — получение списка доступных инструментов (`tools/list`) и
   **нормализация** каждого тула во внутреннюю модель `ToolDescriptor`: модель MCP
   не протекает в `core` (канон `Рекомендации_MCP_d16.txt`).
3. **Каталогизация** — `ToolRegistry` хранит инструменты всех источников (local +
   mcp) с **атомарным snapshot** (`ToolCatalogSnapshot`): один запрос модели никогда
   не видит «половину старого и половину нового» каталога; каталог переживает
   перезапуск (персистентность через фасад `Store`).
4. **Вывод списка** — результат задания: `/mcp tools` в REPL и флаг `--mcp-probe`
   (подключиться → получить список → вывести → выйти) — один и тот же кодовый путь
   через `MCPGateway → MCPToolProvider → ToolRegistry`.

Формула ценности дня: **соединение + список инструментов — не хак, а первый
вертикальный срез расширяемой подсистемы**: добавление нового MCP-сервера завтра не
потребует изменений в `TaskStage`, `PromptBuilder`, профилях, памяти или машине
переходов.

### 1.2 Принципы

- **MCP — не шестой фундаментальный слой, а интеграционный источник инструментов**
  (канон `Рекомендации_MCP_d16.txt`): MCP не встраивается «рядом с памятью или
  состояниями», а подключается через уже существующие механизмы (`Store`, DI) к
  универсальному `ToolRegistry`. Слои хранения остаются: `storage/` → `memory/` →
  `core/` → `integrations/` → CLI.
- **Инструмент ≠ переход**: вызов (и даже успешное завершение) MCP-инструмента
  **никогда** не означает переход `TaskStage`. `TaskStage` остаётся ровно из 8 стадий
  дня 15 (`new … failed`); MCP-стадий (`MCP_CONNECTING`, `WAITING_FOR_TOOL` и т.п.)
  **нет и не будет** — это смешивало бы бизнес-жизненный цикл задачи с
  инфраструктурой. Инфраструктурные состояния живут отдельно:
  `MCPConnectionState` (подключение) и — задел — `ToolExecutionState` (вызов).
- **`MCPGateway` — адаптер, не контролёр**: gateway знает только «как технически
  вызвать внешний инструмент»; он **не знает** о стадиях, профилях и памяти. Иначе
  возникли бы циклические зависимости `Agent → MCPGateway → StateMachine → Agent`.
  Контроль остаётся за существующими сущностями: `StateMachine` — этапы,
  `InvariantChecker` — действия (задел: расширение `ProposedAction`), `ToolExecutor`
  — процедура выполнения (задел).
- **Внутренняя модель инструментов — своя**: `ToolDescriptor` (name, description,
  input_schema, source, provider, original_name, risk_level, allowed_stages,
  requires_confirmation, enabled) — модель агента, а не MCP; имена квалифицируются
  (`mcp.<server>.<tool>`, `local.<tool>`), коллизии имён между серверами
  разрешаются префиксом провайдера.
- **MCP выключен по умолчанию** (`mcp_enabled = False`): без флага/команды агент
  работает ровно как в `den_15`; все прежние 91 юнит-тест и 35 критериев приёмки
  проходят **без** MCP и без сети. Новый функционал не меняет старое поведение —
  принципиальное требование регрессии.
- **Детерминизм без сети**: discovery, нормализация, каталог, коллизии, недоступный
  сервер, битая схема — тестируются на `FakeMCPTransport` (заглушка транспорта);
  живое stdio-соединение с демо-сервером — только интеграционный тест/демо, не гейт.
- **Атомарность каталога**: обновление реестра — только полным snapshot
  (`build_and_validate_snapshot()` → swap), никогда «по одному инструменту».
- **Хранение — только через фасад `Store`**: `MCPGateway` не пишет JSON напрямую;
  новые методы фасада: `read_mcp_servers`/`write_mcp_servers`,
  `read_tool_catalog`/`save_tool_catalog` (`read_*` → `None` при отсутствии/битости,
  дефолтизация у вызывающего; `save_tool_catalog(user_id, data: dict)` принимает
  готовый dict), а также **реализованные** `append_tool_audit`/`load_tool_audit`
  (append-only jsonl, битые строки пропускаются); каталог серверов — user-scope,
  история вызовов — task-scope.
- **Асинхронность внутри, синхронный фасад наружу**: транспорт/gateway/provider —
  `async` (нативный для MCP SDK: timeout, cancellation, несколько серверов); REPL
  `Kod.py` остаётся синхронным и зовёт gateway через `MCPGatewaySync` — тонкую
  синхронную обёртку на **постоянном фоновом event loop** (daemon-поток +
  `run_coroutine_threadsafe`; сессии SDK привязаны к loop'у `initialize`, поэтому
  `asyncio.run` на каждый вызов несовместим). Полный async core (вариант A из
  рекомендаций) — задел следующих дней; для минимального дня 16 выбран вариант B
  («async gateway за синхронным фасадом») — меньше регрессионного риска при том же
  контракте.
- **Зависимости**: к `requests` + `python-dotenv` добавляется официальный
  **`mcp` (Model Context Protocol Python SDK)** — единственная новая зависимость,
  и только для `integrations/mcp/`; `core`/`memory`/`storage` её не импортируют
  никогда (направление зависимостей однонаправленное: `Kod.py` → `core/` →
  `memory/` → `storage/`; `integrations/` — сбоку, подключается только DI-композицией
  в `Kod.py`).
- **Наследие дней 11–15 без регрессии**: контракты памяти (4 слоя), профилей
  (мультипрофиль + роутер), инвариантов, LLM-клиента и машины состояний — не
  тронуты; `den_16` добавляет модули, а не переписывает существующие.

---

## 2. Рабочая структура проекта

### 2.1 Дерево модулей

```
Nedela_4/den_16/
├── Kod.py                       # точка входа: DI-композиция (+ mcp_enabled) + REPL (+ /mcp …, --mcp-probe)
├── core/
│   ├── __init__.py
│   ├── agent.py                 # оркестратор: + self.mcp_gateway/self.tool_registry (None при MCP off)
│   ├── llm_client.py            # LLMClient (ABC) + RouterAIClient + MockClient (без изменений)
│   ├── profile_router.py        # ProfileRouter (без изменений)
│   ├── prompt_builder.py        # BLOCK_ORDER + DELIVERABLE + budget (без изменений; [tools] — задел)
│   ├── state_machine.py         # строгая машина состояний (без изменений — MCP её не трогает)
│   ├── invariants.py            # Invariant + ConstraintSet + InvariantChecker (без изменений;
│   │                            #   расширение ProposedAction MCP-полями — задел дня 17+)
│   ├── tools.py                 # ← НОВОЕ: внутренняя модель инструментов: ToolDescriptor +
│   │                            #   ToolCallRequest + ToolExecutionResult + ToolProvider (ABC) +
│   │                            #   ToolCatalogSnapshot (контракты без MCP SDK и без сети)
│   └── tool_registry.py         # ← НОВОЕ: ToolRegistry — каталог всех источников: register/
│                                #   unregister_provider/get/available_for/snapshot/refresh
│                                #   (атомарный swap snapshot; бизнес-правил не проверяет,
│                                #   StateMachine не вызывает)
├── integrations/                # ← НОВЫЙ слой: внешние интеграции (MCP и будущие)
│   ├── __init__.py
│   └── mcp/
│       ├── __init__.py
│       ├── config.py            # MCPServerConfig (server_id, transport, command/endpoint, enabled,
│       │                        #   trust_level, allowed/denied_tools, timeout, max_result_bytes)
│       │                        #   + загрузка servers.json (дефолты, битый файл не роняет)
│       ├── transport.py         # MCPTransport (ABC) + StdioMCPTransport (mcp SDK — ленивый импорт
│       │                        #   в initialize, stdio) + FakeMCPTransport (заглушка для тестов)
│       ├── client.py            # MCPClient: initialize / list_tools / (задел: call_tool) —
│       │                        #   делегирует инжектированному транспорту (SDK — в transport.py)
│       ├── gateway.py           # MCPGateway: start/stop, connection_state (MCPConnectionState),
│       │                        #   discover() → list[ToolDescriptor]; НЕ знает о стадиях/профилях/памяти
│       ├── provider.py          # MCPToolProvider: ToolProvider поверх gateway — discover() +
│       │                        #   нормализация mcp-тула → ToolDescriptor (квалифицированное имя,
│       │                        #   source="mcp", provider=server_id, original_name)
│       └── demo_server.py       # минимальный локальный MCP-сервер (stdio, mcp SDK): 3 тула
│                                #   (get_time, echo, weather_stub) — для демо и интеграционных тестов
├── memory/                      # 4 слоя + MemoryManager (без изменений; ToolMemoryPolicy — задел)
├── storage/
│   ├── __init__.py
│   ├── store.py                 # фасад: + mcp_servers_path/read/write + tool_catalog_path/
│   │                            #   read_tool_catalog/save_tool_catalog (read → None при отсутствии/
│   │                            #   битости, дефолт у вызывающего; + append/load_tool_audit)
│   └── db.py                    # ProfileRepository (без изменений)
├── users/                       # рантайм-хранилище (создаётся при работе)
│   └── <id>/integrations/mcp/   # ← НОВОЕ: servers.json (конфиг серверов) + catalog.json (снимок каталога)
├── run.sh                       # +x (без изменений)
├── run.desktop                  # (пересоздать при переносе — абсолютные пути)
├── README.md                    # + раздел «Подключение MCP»
├── arch_den_16.md               # текущая архитектура (этот файл)
├── Den_log.md                   # журнал (рантайм-артефакт; + строки [MCP] …)
├── tokens.csv                   # CSV-журнал токенов (рантайм-артефакт)
├── Задание_d16.txt              # постановка куратора (неизменяемый первоисточник)
├── Рекомендации_MCP_d16.txt     # фундамент на будущее (неизменяемый первоисточник)
└── dev/                         # служебное пространство (раздел 3), в т.ч. Проверка.md
```

Изменения относительно `den_15` — только новые модули (`core/tools.py`,
`core/tool_registry.py`, `integrations/mcp/*`), зеркальные дополнения `storage/store.py`
(методы каталога MCP) и `Kod.py` (DI + `/mcp` + `--mcp-probe`); `core/agent.py` —
минимальное касание (добавлены `self.mcp_gateway = None` и `self.tool_registry = None`
— MCP off по умолчанию; контракты жизненного цикла не изменены);
`core/state_machine.py`, `core/invariants.py`, `memory/*`, `storage/db.py` — **не
трогаются**.

### 2.2 Внутренняя модель инструментов (`core/tools.py` — контракты без MCP)

Канон `Рекомендации_MCP_d16.txt`: модель MCP не должна протекать в `core`.
`ToolDescriptor` — внутренняя модель агента; поля `allowed_stages` /
`requires_confirmation` / `risk_level` — **задел** policy pipeline (день 17+), в
`den_16` заполняются дефолтами (`allowed_stages` — все рабочие стадии,
`requires_confirmation=False`, `risk_level="unknown"`).

```python
# core/tools.py
@dataclass(frozen=True)
class ToolDescriptor:
    name: str                    # квалифицированное: "mcp.demo.get_time" | "local.<tool>"
    description: str
    input_schema: dict
    source: str                  # "local" | "mcp"
    provider: str                # server_id (mcp) | "local"
    original_name: str           # имя тула на сервере ("get_time")
    risk_level: str = "unknown"  # задел policy
    allowed_stages: frozenset = ALL_WORKING_STAGES  # задел policy
    requires_confirmation: bool = False             # задел policy
    enabled: bool = True

@dataclass(frozen=True)
class ToolCallRequest:           # задел дня 17+ (tools/call); контракт фиксируется сейчас
    name: str
    arguments: dict

@dataclass(frozen=True)
class ToolExecutionResult:       # задел дня 17+
    execution_id: str
    tool: str
    status: str                  # ToolExecutionState
    summary: str
    raw: object | None = None    # сырой ответ — только текущий execution context, не в память

class ToolProvider(ABC):         # единый интерфейс источников инструментов
    def discover(self) -> list[ToolDescriptor]: ...
    def provider_id(self) -> str: ...

@dataclass(frozen=True)
class ToolCatalogSnapshot:       # атомарная версия каталога
    version: int
    tools: tuple[ToolDescriptor, ...]
    created_at: str              # ISO-время
```

### 2.3 `ToolRegistry` — каталогизация (`core/tool_registry.py`)

```python
class ToolRegistry:
    def add_provider(self, provider: ToolProvider) -> None: ...
    def unregister_provider(self, provider_id: str) -> None: ...
    def get(self, name: str) -> ToolDescriptor: ...          # KeyError + понятное сообщение
    def available_for(self, context) -> list[ToolDescriptor]: ...  # задел: фильтры policy
    def snapshot(self) -> ToolCatalogSnapshot: ...
    def refresh(self) -> ToolCatalogSnapshot: ...
        # discover() у всех провайдеров → валидация схем (JSON Schema-примитивы) →
        # разрешение коллизий имён (квалифицированные имена) →
        # build_and_validate_snapshot() → атомарный swap self._current_snapshot
```

Правила:

- реестр **не проверяет бизнес-правила** и **не вызывает** `StateMachine` — он только
  каталогизирует (канон рекомендаций);
- обновление — только полным snapshot (никогда «по одному инструменту»);
- недоступный провайдер при `refresh()` → его тулы **исключаются** из нового
  snapshot (каталог честен: нет соединения — нет тулов), ошибка логируется, остальные
  провайдеры не страдают;
- `version` — монотонный счётчик; `created_at` — время сборки.

### 2.4 MCP-слой (`integrations/mcp/`)

**Конфиг** (`config.py`) — `MCPServerConfig` (server_id, transport="stdio",
command, enabled, trust_level, allowed_tools/denied_tools, timeout_seconds,
max_result_bytes) + загрузка `users/<id>/integrations/mcp/servers.json`; битый или
отсутствующий файл → конфиг по умолчанию (демо-сервер, `enabled=true` — единственный
в `den_16`), приложение не падает (наследие устойчивости `Store`).

**Транспорт** (`transport.py`) — `MCPTransport` (ABC: `initialize` / `list_tools` /
`call_tool`-задел / `close`) + `StdioMCPTransport` (обёртка над `mcp` SDK: ленивый
импорт SDK в `initialize()`, stdio-подпроцесс, timeout) + `FakeMCPTransport`
(детерминированная заглушка: фиксированный список тулов, программируемые
`fail_initialize`/`fail_list_tools`/`timeout` + `set_tools` (смена каталога) — для
тестов без сети и без SDK-подпроцесса).

**Клиент** (`client.py`) — `MCPClient`: транспорт инжектится, SDK напрямую не
импортирует (SDK — в `transport.py`); `initialize()` (handshake: protocol version,
capabilities), `list_tools()` →
нормализованные сырые описания `{name, description, inputSchema}`; любой сбой →
`MCPConnectionError` (gateway переводит в `MCPConnectionState.FAILED`), не `None` и
не молчание.

**Шлюз** (`gateway.py`) — `MCPGateway`:

```python
class MCPConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    READY = "ready"
    DEGRADED = "degraded"    # задел: часть серверов недоступна
    FAILED = "failed"

class MCPGateway:            # НЕ знает о TaskStage / профилях / памяти
    async def start(self) -> None            # connect + initialize → READY | FAILED
    async def stop(self) -> None             # закрытие транспортов → DISCONNECTED
    def status(self) -> dict                 # состояние подключения по серверам
    async def discover(self) -> list[ToolDescriptor]
        # list_tools у каждого включённого сервера → нормализация → ToolDescriptor[]
        # фильтр allowed_tools/denied_tools из MCPServerConfig (изоляция прав через
        # тулинг — канон Суть_N4 §3.3: серверу даём только часть тулов)
```

Синхронный фасад для REPL: `MCPGatewaySync` — **постоянный фоновый event loop**
(daemon-поток + `run_coroutine_threadsafe`; сессии `mcp` SDK привязаны к loop'у
initialize, поэтому `asyncio.run` на каждый вызов несовместим) — REPL и
`--mcp-probe` остаются синхронными.

**Провайдер** (`provider.py`) — `MCPToolProvider(ToolProvider)`: `provider_id() =
"mcp"`, `discover()` → gateway.discover() → тулы с `source="mcp"`,
`provider=server_id`, `name=f"mcp.{server_id}.{original_name}"`.

**Демо-сервер** (`demo_server.py`) — минимальный локальный MCP-сервер на `mcp` SDK
(stdio), 3 тула: `get_time` (текущее время), `echo` (повтор текста),
`weather_stub` (погода-заглушка: units Celsius|Kelvin, location — канон
погодного примера лекции). Запуск: `python -m integrations.mcp.demo_server`.
Это «локальный вариант» из задания: «поднимите MCP-сервер, если используете
локальный вариант».

### 2.5 Хранение (`Store` — новые методы фасада)

```
users/<user_id>/
└── integrations/mcp/
    ├── servers.json            # конфиг серверов (user/application scope)
    └── catalog.json            # снимок ToolCatalogSnapshot (version, tools, created_at)
```

- `Store.mcp_servers_path/read_mcp_servers/write_mcp_servers` — отсутствующий/битый
  файл → `None` (дефолтизация у вызывающего: `load_servers_config` → `[DEFAULT_SERVERS]`);
- `Store.tool_catalog_path/read_tool_catalog/save_tool_catalog` — `read_tool_catalog`
  при отсутствии/битости → `None` (дефолтизация у вызывающего: пустой каталог
  `{"schema_version": 1, "version": 0, "tools": [], "created_at": null}`);
  `save_tool_catalog(user_id, data: dict)` принимает **готовый** dict; каталог
  пересохраняется после каждого успешного `refresh()`;
- задел дня 17+: `users/<id>/tasks/<task>/tool_audit.jsonl`
  (`append_tool_audit` / `load_tool_audit` — **реализованы**, append-only, битые
  строки пропускаются) — история вызовов, **отдельно** от
  `transition_log` (успешный вызов инструмента сам по себе не создаёт запись о
  переходе — канон рекомендаций);
- `MCPGateway` JSON напрямую не пишет — только через `Store`.

### 2.6 DI-композиция и CLI

`build_agent()` расширяется опционально (канон рекомендаций):

```python
mcp_enabled = False  # по умолчанию; включается флагом --mcp

if config.mcp_enabled:
    gateway = MCPGatewaySync(load_servers_config(store.mcp_servers_path(user_id)))
    registry = ToolRegistry()
    registry.add_provider(MCPToolProvider(gateway))
    agent.mcp_gateway = gateway
    agent.tool_registry = registry
# при сборке агента registry.refresh()/save_tool_catalog НЕ вызываются —
# discovery + сейв каталога происходят только по явной команде /mcp refresh
# без флага: agent.mcp_gateway is None, agent.tool_registry is None — поведение = den_15
# local-провайдер в den_16 не регистрируется (задел: local.* — только безопасные
# доменные операции, никогда local.set_stage / local.write_task_state_file)
```

Новые команды REPL (семейство `/mcp`, 6 форм):

| Команда | Действие |
|---|---|
| `/mcp status` | состояние подключения по серверам (`MCPConnectionState`), версия каталога |
| `/mcp servers` | список сконфигурированных серверов (enabled, transport, trust_level) |
| `/mcp tools` | **результат задания**: список доступных инструментов (имя, description, input-схема) |
| `/mcp refresh` | re-discovery: gateway.discover() → registry.refresh() → атомарный swap + сейв каталога |
| `/mcp connect <id>` | включить/поднять соединение с сервером (по умолчанию — все из servers.json) |
| `/mcp disconnect` | закрыть **все** соединения (`gateway.stop()` → DISCONNECTED; тулы покидают каталог при следующем refresh) |

Новый флаг: `--mcp-probe` — **результат задания в one-shot форме**: подключиться →
handshake → `tools/list` → вывести список инструментов (имя, описание, схема) →
корректно закрыться → exit 0; при недоступном сервере — понятная ошибка, exit 1.
Флаги прежние (12) + `--mcp` (включить MCP-слой в REPL) + `--mcp-probe` → 14.

`/mcp`-команды не тратят токены LLM (локальные вызовы; LLM в loop не участвует).
Токен-флоу каталога в промте (`ToolPromptPolicy`: max_tools, max_schema_tokens) —
**задел** следующих дней (сравнение MCP vs Skill + CLI — цель недели, не дня 16).

### 2.7 Память, профили, инварианты, переходы (без изменений + заделы)

- **Память**: 4 слоя не тронуты. Задел `ToolMemoryPolicy` (include_raw_result /
  save_summary_to_short_term / save_to_working / …): сырые ответы MCP **никогда** не
  пишутся в память автоматически; в `working` — только нормализованный итог
  `external_actions[]`; профиль MCP менять не может (изменение профиля — только
  явная механика профилей).
- **Профили**: задел `tool_policy` в профиле (`allow`/`deny`) — только **сужение**
  прав, никогда расширение глобального запрета.
- **Инварианты**: задел — расширение `ProposedAction` полями `action_type` /
  `tool_name` / `arguments`: одно правило «нельзя менять схему БД» будет работать
  для локальной функции, MCP-инструмента и действия, предложенного LLM.
- **Машина состояний**: не тронута. Целевой pipeline дня 17+ (когда появится
  `tools/call`): инструмент существует → включён → схема валидна → стадия разрешает
  → инварианты разрешают → подтверждение → вызов. Успех вызова **не** создаёт
  переход; переход — только `StateMachine.try_transition()` по решению агента.
- **Промт**: `BLOCK_ORDER` не меняется; задел — блок `[external_context]` (MCP
  resources) отдельно от `long_term` (разные источники, разное доверие) и
  дозированная доставка описаний тулов под токен-бюджетом.

### 2.8 Сводная механика дня 16

```
запуск --mcp-probe (результат задания, one-shot):
  load servers.json → MCPGateway.start() (stdio → demo_server, initialize)
  → READY → discover(): list_tools → нормализация → ToolDescriptor[]
  → вывод: имя / description / input-схема → gateway.stop() → exit 0

REPL --mcp:
  /mcp connect   → gateway.start() → READY
  /mcp tools     → registry.snapshot().tools (из каталога; при пустом — подсказка /mcp refresh)
  /mcp refresh   → discover() → registry.refresh() (атомарный swap) → Store.save_tool_catalog
  /mcp status    → connection_state по серверам + version каталога
  /mcp disconnect→ gateway.stop() → DISCONNECTED
  (MCP недоступен → «MCP Gateway: FAILED/DEGRADED», но память, профили и
   state machine продолжают работать — деградация, не падение)

без --mcp / без /mcp: агент работает ровно как den_15 (MCP disabled by default)
```

---

## 3. Служебное пространство `dev/` (проект про проект)

### 3.1 Дерево `dev/`

```
Nedela_4/den_16/dev/
├── migr_plan.md                  # план-эталон миграции den_15 → arch_den_16.md
├── migr_plan_0.md … migr_plan_N.md   # исполняемые планы этапов (конец этапа — гейт в следующий)
├── migr_log.md                   # журнал миграции den_15 → arch_den_16.md
├── meta_promt/                   # метапромты (вспомогательные промты пользователя)
├── tests_debug/
│   ├── check_acceptance.sh       # гейт приёмки: 15 → 18 проверок (+3 MCP)
│   ├── unit_runner.py            # L2-раннер (без pytest)
│   ├── smoke.py                  # L3-смоук (+ MCP-прогон: --mcp-probe на FakeMCPTransport)
│   ├── scenario.py               # L4-сценарии (+ scenario_mcp_discovery)
│   ├── unit/
│   │   ├── … (10 прежних модулей — без изменений, MCP off)
│   │   └── test_mcp.py           # ← НОВОЕ: контракты + реестр + gateway на FakeMCPTransport
│   ├── scenario/scen_1.md        # сценарий ручной демонстрации (+ раздел MCP)
│   └── .tmp/                     # единственное место прогонов (.gitignore)
└── logs_reports/                 # stages/ + errors/ + archive/ (наследуется)
```

### 3.2 `tests_debug/` — что именно протестировать (канон задания)

`unit/test_mcp.py` (новый; всё на `FakeMCPTransport`, без сети и без живого
подпроцесса):

- **контракты**: `ToolDescriptor` — квалифицированное имя, source/provider;
  `ToolCatalogSnapshot` — version/tools/created_at;
- **discovery**: `MCPToolProvider.discover()` нормализует mcp-тул →
  `name="mcp.demo.get_time"`, `original_name="get_time"`, `source="mcp"`;
- **реестр**: `add_provider` → `refresh()` → snapshot содержит тулы провайдера;
  коллизия имён двух серверов разрешается префиксом; `unregister_provider` → тулы
  покидают каталог при следующем refresh; `get()` неизвестного → понятная ошибка;
- **атомарность**: во время refresh snapshot либо старый, либо новый (version
  монотонный, «половинного» каталога не бывает);
- **недоступный сервер**: transport падает → gateway → `FAILED`, тулы исключены,
  остальные провайдеры живы, исключение не роняет процесс;
- **фильтр прав**: `allowed_tools`/`denied_tools` конфига — запрещённый тул не
  попадает в discovery (изоляция прав через тулинг);
- **персистентность**: `save_tool_catalog` → `load_tool_catalog` round-trip;
  битый/отсутствующий файл → пустой каталог schema_version=1;
- **MCP не трогает состояние**: после полного цикла connect → discover → refresh
  `TaskStage` не изменился, `transition_log` пуст (инструмент ≠ переход);
- **MCP off по умолчанию**: без `--mcp` реестр пуст, агент отвечает как den_15.

`scenario.py` + **`scenario_mcp_discovery`** (L4, сквозной, канон «Проверьте» из
задания): `--mcp-probe` (на FakeMCPTransport) → соединение установлено (READY) →
список инструментов корректно возвращен (3 тула демо-сервера: get_time, echo,
weather_stub) → список выведен → отключение чистое; вторая ветка: REPL `/mcp
connect` → `/mcp tools` → `/mcp refresh` → `/mcp status` → `/mcp disconnect`.

Интеграционный тест (не гейт, помечен `@live`-аналогом по традиции проекта):
`StdioMCPTransport` поднимает `demo_server.py` подпроцессом → initialize →
list_tools → 3 тула. Живые внешние серверы — вне дня 16.

Гейт `check_acceptance.sh`: 15 прежних + 3 новых проверки (соединение
устанавливается; список инструментов корректно возвращается; список выводится
кодом `--mcp-probe`), всё на заглушках, `users/` не трогается, идемпотентен.

### 3.3 `logs_reports/`

- `migr_log.md` — журнал миграции «было → стало → проверка → статус» по этапам,
  результаты `test_mcp.py` и `scenario_mcp_discovery`;
- `errors/error_<timestamp>.md` — карточки ошибок (красный гейт этапа → карточка);
- `stages/`, `archive/` — наследуются из `den_15`.

---

## 4. Полная карта артефактов итогового состояния

### 4.1 Рабочие артефакты (продукт)

| Артефакт | Назначение |
|---|---|
| `Kod.py` + `core/` + `memory/` + `storage/` | агент дней 11–15 без регрессии + каталог инструментов |
| `core/tools.py` | внутренняя модель: ToolDescriptor / ToolCallRequest / ToolExecutionResult / ToolProvider / ToolCatalogSnapshot |
| `core/tool_registry.py` | ToolRegistry: каталогизация, атомарный snapshot, refresh |
| `integrations/mcp/*` | MCP-слой: config / transport (stdio + fake) / client / gateway / provider / demo_server |
| `users/<id>/integrations/mcp/{servers,catalog}.json` | конфиг серверов + снимок каталога (через Store) |
| `run.sh` / `run.desktop` | запуск (без изменений / пересоздать при переносе) |
| `README.md` | описание + раздел «Подключение MCP» |

### 4.2 Служебные артефакты (процесс)

| Артефакт | Назначение |
|---|---|
| `dev/Проверка.md` | чек-лист: 35 прежних + **строки 36–40** (MCP) |
| `dev/migr_plan.md` + `migr_plan_0..N.md` | план-эталон и рабочие планы миграции |
| `dev/migr_log.md` | журнал миграции + «Итог миграции» |
| `dev/tests_debug/*` | L2 (+`test_mcp.py`), L3, L4 (+`scenario_mcp_discovery`), гейт 18 проверок |

### 4.3 Критерии приёмки подключения MCP (строки 36–40)

| Пункт | Что проверяем | Как |
|---|---|---|
| 36 | MCP SDK установлен / локальный MCP-сервер поднимается | `python -c "import mcp"`; `python -m integrations.mcp.demo_server` стартует |
| 37 | Соединение устанавливается | `--mcp-probe` / `/mcp connect` → handshake initialize → `READY` (`/mcp status`) |
| 38 | Список инструментов корректно возвращается | `tools/list` → нормализация → 3 тула демо-сервера в `ToolRegistry.snapshot()` |
| 39 | Список инструментов выводится кодом | `python Kod.py --mcp-probe` печатает имя/description/схему каждого тула; `/mcp tools` в REPL |
| 40 | Регрессия: MCP off по умолчанию | без `--mcp` — 91 прежний тест OK, 35 прежних критериев зелёные, поведение = den_15 |

Гейт: `unit_runner.py` (все модули, включая `test_mcp.py`) → `scenario.py`
(10 сценариев) → `check_acceptance.sh` 18 из 18 — всё без живого ключа и без сети.

---

## 5. Порядок достижения итогового состояния

1. **Миграция `den_15` → `arch_den_16.md`** — по `dev/migr_plan.md` (и планам
   этапов `migr_plan_0..N.md`), порядок по зависимостям:
   `core/tools.py` (контракты, без SDK) → `core/tool_registry.py` (реестр +
   snapshot) → `integrations/mcp/` (config → transport+fake → client → gateway →
   provider → demo_server) → `storage/store.py` (методы каталога) → `Kod.py`
   (DI + `/mcp`-семейство + `--mcp`/`--mcp-probe`) → `test_mcp.py` +
   `scenario_mcp_discovery` + гейт 15→18 → README (раздел «Подключение MCP») +
   `Проверка.md` (строки 36–40) → `scen_1.md` (+раздел MCP) → запись этапа в
   `dev/migr_log.md`.
2. **Финал** — прогон всех проверок (L2→L3→L4→гейт 18/18), приёмка 40/40, запись
   итога в `dev/migr_log.md`, предложение коммита (коммит — только по явной команде
   пользователя).

Заделы следующих дней недели 4 (места зарезервированы, не реализуются):
policy pipeline (стадии/профили/инварианты/подтверждения — `ToolPolicy` +
расширение `ProposedAction`), `ToolExecutor` + `tools/call`, `tool_audit.jsonl`,
`ToolMemoryPolicy`, `ToolPromptPolicy` + блок `[external_context]` (resources),
полный async core (вариант A), параллелизм read-only тулов, сравнение токен-флоу
MCP vs Skill + CLI.

---

## 6. Итог

После завершения `den_16` получается:

- **Код, подключающийся к MCP и выводящий список доступных инструментов** —
  результат задания: `--mcp-probe` (one-shot) и `/mcp tools` (REPL); соединение
  устанавливается (handshake → `READY`), список корректно возвращается
  (`tools/list` → нормализация → каталог).
- **Не скрипт, а вертикальный срез подсистемы**: `MCPGateway` (адаптер, не
  контролёр) → `MCPToolProvider` (нормализация во внутреннюю `ToolDescriptor`) →
  `ToolRegistry` (каталог + атомарный snapshot + персистентность через `Store`) —
  фундамент всей MCP-работы недели 4 по `Рекомендации_MCP_d16.txt`.
- **Пять «кубиков» дней 11–15 без регрессии**: память, профили, инварианты,
  строгая машина состояний, LLM-клиент — контракты не тронуты; MCP выключен по
  умолчанию; инструмент ≠ переход (`TaskStage` не меняется от вызовов MCP).
- **Изоляция прав через тулинг**: `allowed_tools`/`denied_tools` в конфиге сервера;
  модель MCP не протекает в `core`; `MCPGateway` не знает о стадиях/профилях/памяти
  (нет циклических зависимостей).
- **Детерминированная проверяемость**: `FakeMCPTransport` — discovery, коллизии,
  недоступность, фильтры, персистентность — без сети; интеграционный stdio-прогон
  с демо-сервером — отдельно; гейт 18/18, приёмка 40/40.
- **Заделы с зарезервированными местами**: policy pipeline, `ToolExecutor`,
  аудит, `MemoryPolicy`, resources, async core, сравнение MCP vs Skill + CLI.

---

## 7. Краткое описание архитектуры

### 7.1 Формула для самой краткой характеристики (1 строка)

> Персонализированный stateful-агент дней 11–15 (память → профили → инварианты →
> контролируемый жизненный цикл), к которому MCP подключается не как шестой
> фундаментальный слой, а как интеграционный источник инструментов: gateway
> соединяет, provider нормализует, registry каталогизирует — а контроль остаётся
> за существующими механизмами.

### 7.2 Краткое и точное описание архитектуры den_16

Одно предложение (суть):

> den_16 — CLI stateful-агент (RouterAI, step-3.5-flash) дней 11–15, расширенный
> первым вертикальным срезом MCP-подсистемы: соединение с локальным stdio
> MCP-сервером (handshake initialize), discovery (tools/list), нормализация тулов
> во внутреннюю модель ToolDescriptor и каталогизация в ToolRegistry с атомарным
> snapshot и персистентностью через Store; результат задания — вывод списка
> инструментов (--mcp-probe / /mcp tools).

Развёрнуто в 6 слоях (снизу вверх):

1. **Хранилище** (`storage/`) — прежний фасад `Store` + новые методы:
   `users/<id>/integrations/mcp/servers.json` (конфиг) и `catalog.json` (снимок
   каталога); `read_*` при отсутствии/битости → `None` (дефолтизация у вызывающего),
   приложение не падает.
2. **Память** (`memory/`) — 4 слоя без изменений; сырые ответы MCP в память не
   пишутся (ToolMemoryPolicy — задел).
3. **Ядро** (`core/`) — прежние Agent / PromptBuilder / ProfileRouter /
   StateMachine / InvariantChecker / LLMClient **без изменений** + новые
   `tools.py` (внутренние контракты инструментов, без MCP SDK) и
   `tool_registry.py` (каталог всех источников, атомарный snapshot).
4. **Интеграции** (`integrations/mcp/`) — новый слой: config (MCPServerConfig,
   allowed/denied_tools), transport (ABC + StdioMCPTransport на `mcp` SDK +
   FakeMCPTransport для тестов), client (initialize/list_tools — единственный
   импорт SDK), gateway (MCPConnectionState, discover; не знает о стадиях и
   памяти), provider (нормализация → ToolDescriptor), demo_server (локальный
   stdio-сервер с 3 тулами).
5. **CLI** (`Kod.py`) — DI с `mcp_enabled=False` по умолчанию; семейство `/mcp`
   (status/servers/tools/refresh/connect/disconnect) + флаги `--mcp`,
   `--mcp-probe`; REPL синхронный (async — внутри gateway).
6. **Служебное** (`dev/`) — миграция по плану-эталону, L2 (+test_mcp.py на
   FakeMCPTransport), L4 (+scenario_mcp_discovery), гейт 18/18, приёмка 40/40.

Ключевые принципы:

- **MCP — источник инструментов, не слой контроля**: gateway — адаптер («как
  вызвать»), контроль — за StateMachine (этапы), InvariantChecker (действия,
  задел) и ToolExecutor (процедура, задел);
- **Инструмент ≠ переход**: TaskStage (8 стадий дня 15) не трогается; MCP-стадий
  нет; успех вызова не создаёт запись перехода;
- **Модель MCP не протекает в core**: ToolDescriptor — внутренняя модель;
  квалифицированные имена `mcp.<server>.<tool>`;
- **MCP off по умолчанию + детерминизм**: без флага агент = den_15; всё
  детерминированное тестируется на FakeMCPTransport без сети;
- **Однонаправленные зависимости**: Kod.py → core → memory → storage;
  integrations/ — сбоку, подключается только DI; `mcp` SDK импортируется только в
  `integrations/mcp/transport.py` (+ `demo_server.py`).

### 7.3 Полная картина архитектуры с механикой частей

Общая формула: пять «кубиков» дней 11–15 (память → персонализация → состояние →
инварианты → контролируемый жизненный цикл) + шестой интеграционный «кубик» — MCP
как внешний источник инструментов, подключённый к универсальному ToolRegistry и
защищённый существующими правилами (канон `Рекомендации_MCP_d16.txt`).

---

1. **Хранилище (storage/)** — «где всё лежит». Прежняя каноническая иерархия
   `users/<id>/…` без изменений + новая ветка `integrations/mcp/`: `servers.json`
   (какие серверы, транспорт, таймауты, allowed/denied_tools) и `catalog.json`
   (снимок каталога: schema_version, version, tools, created_at). Механика
   устойчивости — прежняя: битый/отсутствующий файл → схема по умолчанию, не
   падение. Gateway JSON напрямую не пишет — только через фасад Store. Задел:
   `tasks/<task>/tool_audit.jsonl` — история вызовов (task-scope), отдельно от
   `transition_log` (user/task lifecycle-scope).

2. **Память (memory/)** — «что агент помнит». Без изменений: 4 слоя, MERGE/append
   только через MemoryManager, дозированная доставка + токен-бюджет. MCP-политика
   памяти — задел: сырой ответ → только текущий execution context; краткое резюме →
   short_term; нормализованный итог → working (`external_actions[]`); важный факт →
   long_term только по политике; секреты — никогда; профиль MCP менять не может.

3. **Ядро (core/)** — «кто решает». Прежние сущности без изменений. Новые:
   - `tools.py` — контракты: ToolDescriptor (внутренняя модель: name, description,
     input_schema, source, provider, original_name + заделовые risk_level /
     allowed_stages / requires_confirmation), ToolCallRequest / ToolExecutionResult
     (задел tools/call), ToolProvider (ABC), ToolCatalogSnapshot (version, tools,
     created_at).
   - `tool_registry.py` — каталог: add_provider / unregister_provider / get /
     available_for / snapshot / refresh. Механика refresh: discover() у всех
     провайдеров → валидация схем → разрешение коллизий (квалифицированные имена) →
     сборка нового snapshot → атомарный swap. Реестр не проверяет бизнес-правила и
     не зовёт StateMachine. Недоступный провайдер → его тулы исключаются, остальные
     живы.

4. **Интеграции (integrations/mcp/)** — «как достучаться до внешнего мира».
   - config: MCPServerConfig (server_id, transport, command, enabled, trust_level,
     allowed_tools/denied_tools, timeout_seconds, max_result_bytes) + загрузка
     servers.json с дефолтами.
   - transport: ABC + StdioMCPTransport (обёртка над mcp SDK: ленивый импорт SDK в
     initialize, stdio-подпроцесс, timeout) + FakeMCPTransport (программируемые
     списки/отказы/таймауты/смена каталога — тесты без сети и без SDK-подпроцесса).
     SDK импортируется только в transport.py (+ demo_server.py); client.py делегирует
     транспорту.
   - client: initialize (handshake: версия протокола, capabilities) / list_tools →
     `{name, description, inputSchema}`; сбой → MCPConnectionError, не молчание.
   - gateway: start/stop/status/discover; MCPConnectionState
     (disconnected/connecting/ready/degraded/failed); фильтр allowed/denied_tools
     (изоляция прав через тулинг — канон лекции: «дать сервису только часть тулов»);
     НЕ знает о TaskStage/профилях/памяти (нет цикла Agent→Gateway→StateMachine).
     Синхронный фасад MCPGatewaySync — постоянный фоновый event loop (daemon-поток + run_coroutine_threadsafe) для REPL и --mcp-probe.
   - provider: MCPToolProvider — нормализация mcp-тула → ToolDescriptor
     (`mcp.<server>.<tool>`).
   - demo_server: локальный stdio MCP-сервер (mcp SDK), 3 тула: get_time, echo,
     weather_stub (units Celsius|Kelvin + location — сквозной пример лекции).

5. **Оркестратор и CLI** — «как этим пользуются». Agent дней 11–15 — минимальное
   касание: добавлены поля self.mcp_gateway / self.tool_registry (оба None при
   выключенном MCP — поведение = den_15); жизненный цикл не изменён
   (/plan → /approve → /step|/run → validation → done; инварианты; профили; память).
   DI: build_agent() при mcp_enabled строит MCPGatewaySync + MCPToolProvider и
   регистрирует провайдер в ToolRegistry, но refresh()/save_tool_catalog при сборке
   НЕ вызываются (discovery + сейв — только по /mcp refresh). Команды: /mcp status |
   servers | tools | refresh | connect <id> | disconnect; флаги: --mcp (включить
   слой), --mcp-probe (one-shot: подключиться → вывести список тулов → закрыться).
   /mcp-команды токенов LLM не тратят.

6. **Служебное пространство (dev/)** — «проект про проект». Миграция den_15 →
   arch_den_16.md: план-эталон → рабочие планы этапов (конец этапа — гейт в
   следующий) → журнал; красный гейт → карточка ошибки. Тестовый контур: L2 —
   unit_runner.py + test_mcp.py (FakeMCPTransport: контракты, discovery,
   нормализация, коллизии, атомарность, недоступность, фильтры прав,
   персистентность, «MCP не трогает TaskStage», «MCP off по умолчанию»); L3 —
   smoke (+MCP-прогон); L4 — scenario_mcp_discovery (соединение → список → вывод →
   чистое отключение); гейт check_acceptance.sh 18/18 (15 прежних + 3 MCP), всё в
   .tmp/, users/ не трогается, живой ключ и сеть не нужны. Приёмка — Проверка.md,
   40/40 (35 прежних без регрессии + строки 36–40 подключения MCP).

---

Сводная механика результата задания (one-shot):

```
python Kod.py --mcp-probe
  → load servers.json → StdioMCPTransport(demo_server) → initialize → READY
  → list_tools → [get_time, echo, weather_stub]
  → нормализация → mcp.demo.get_time / mcp.demo.echo / mcp.demo.weather_stub
  → вывод: имя + description + input-схема → close → exit 0
```

И сводная механика контроля (главная граница дня):

```
MCP предоставляет инструменты.      ← integrations/mcp (gateway, provider)
ToolRegistry каталогизирует.        ← core/tool_registry (атомарный snapshot)
ToolPolicy фильтрует.               ← задел дня 17+
InvariantChecker запрещает опасное. ← задел (расширение ProposedAction)
ToolExecutor управляет вызовом.     ← задел (tools/call)
MemoryPolicy решает, что запомнить. ← задел (сырое — никогда в память)
StateMachine решает, можно ли
менять этап.                        ← БЕЗ ИЗМЕНЕНИЙ: инструмент ≠ переход
Store сохраняет конфиг и каталог.   ← users/<id>/integrations/mcp/
```

Инвариант всей системы прежний + новый: детерминизм недетерминированной LLM даёт
код — и теперь ещё «внешний мир подключается через адаптер, который не имеет права
менять внутреннее состояние агента».
