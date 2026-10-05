# arch_den_16.md — итоговая целевая архитектура проекта `den_16` «Подключение MCP»

> Итоговый документ: описывает состояние, которое должно получиться **после завершения**
> проекта `den_16`. Базируется на `Nedela_3/den_15/arch_den_15.md` (персонализированный
> stateful-агент: 4 слоя памяти + мультипрофильность + строгая машина состояний + слой
> инвариантов) и **не заменяет ни один из пяти «кубиков» дней 11–15**, а добавляет к ним
> **шестой, интеграционный: MCP (Model Context Protocol) как внешний источник
> инструментов** — **настоящее** подключение к **реальному** MCP-серверу, discovery
> (получение списка тулов), каталогизация в `ToolRegistry`, **настоящий вызов
> инструмента** (`tools/call`) и **полный LLM tool-use**.
> Источники: `Суть_N4.md`, `Задание_d16.txt` (неизменяемый первоисточник),
> `Рекомендации_MCP_d16.txt` (фундамент на будущее — целевая MCP-подсистема всей недели 4).
>
> **Синхронизировано с фактом реализации: 2026-09-25 (Ревизия 2).** Правки внесены строго
> по `README.md` (факт реализации) и `dev/migr_log.md` (история процесса и причины
> расхождений) — оба равноправные источники истины. **Ревизия 2** отражает уточнение
> куратора: «👉 устанавливает MCP-соединение; 👉 получает от MCP список доступных
> инструментов» означают **настоящее** подключение к **настоящему** MCP-серверу
> (`https://weatherapi.projecteol.ru/mcp/`, Streamable HTTP) и **настоящий** запрос
> инструментов; глубина — **полный LLM tool-use** (агент сам вызывает инструмент по
> запросу пользователя, сценарий «найди город Москва»). История прошлой ревизии
> (discovery по локальному stdio) сохранена в `dev/old_vers/2/`.

---

## 0. Назначение документа

Документ фиксирует три слоя итогового состояния:

1. **Рабочая архитектура** — персонализированный stateful-агент дней 11–15 (память,
   профили, инварианты, контролируемый жизненный цикл) **без регрессии контрактов**,
   плюс **полный вертикальный срез MCP-подсистемы**: `MCPGateway` (соединение +
   handshake + `tools/list` + `tools/call`) → `MCPToolProvider` (нормализация тулов во
   внутреннюю модель) → `ToolRegistry` (каталог + атомарный snapshot + персистентность
   через `Store`) → `ToolExecutor` (policy + аудит) → **LLM tool-use** (агент сам
   вызывает инструмент) → CLI (`/mcp …` + флаг `--mcp-probe`). Результат задания —
   «код, который подключается к MCP и выводит список доступных инструментов», —
   реализуется **не одноразовым скриптом, а настоящим срезом подсистемы** (канон
   `Рекомендации_MCP_d16.txt`, раздел «Как сдавать учебное задание») и проверяется на
   **реальном** сервере.
2. **Служебное пространство `dev/`** — «проект про проект»: миграция `den_15` →
   `arch_den_16.md` по процессной модели «план-эталон → рабочие планы этапов → журнал»,
   с полным аудитом каждого этапа (Ревизия 2: этапы M0–M12).
3. **Фундамент на будущее** — какие части целевой MCP-подсистемы недели 4
   (`ToolMemoryPolicy`, resources/`[external_context]`, полный async core, параллелизм
   read-only тулов, local-провайдер, сравнение токен-флоу MCP vs Skill + CLI)
   в `den_16` **не реализуются**, но их места в архитектуре уже зарезервированы,
   чтобы следующие дни наращивали, а не переписывали.

Главная идея задания (канон `Задание_d16.txt`): **минимальный код, который
устанавливает MCP-соединение и получает от MCP список доступных инструментов**.
Проверяется: соединение устанавливается; список инструментов корректно возвращается.
Формат результата — Код. **Ревизия 2**: проверка — на **реальном** сервере, и глубина
доведена до **настоящего вызова инструмента** и **полного LLM tool-use**.

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
стандартный протокол**. Появляются новые элементы:

1. **MCP-соединение** — `MCPGateway` устанавливает соединение с MCP-сервером
   (транспорт **Streamable HTTP** к реальному серверу `weatherapi`; stdio — для
   локального демо-сервера и тестов), выполняет handshake (`initialize`) и держит
   состояние подключения (`MCPConnectionState`).
2. **Discovery** — получение списка доступных инструментов (`tools/list`) и
   **нормализация** каждого тула во внутреннюю модель `ToolDescriptor`: модель MCP
   не протекает в `core` (канон `Рекомендации_MCP_d16.txt`).
3. **Каталогизация** — `ToolRegistry` хранит инструменты всех источников (local +
   mcp) с **атомарным snapshot** (`ToolCatalogSnapshot`): один запрос модели никогда
   не видит «половину старого и половину нового» каталога; каталог переживает
   перезапуск (персистентность через фасад `Store`).
4. **Вызов инструмента** — `tools/call` на всех транспортах; `ToolExecutor` (policy →
   вызов → аудит `tool_audit.jsonl`); **полный LLM tool-use** — LLM видит инструменты
   (блок `[tools]` + спецификация function-calling), предлагает вызов, результат
   возвращается в модель, модель формирует ответ.
5. **Вывод списка** — результат задания: `/mcp tools` в REPL и флаг `--mcp-probe`
   (подключиться → получить список → вывести → выйти) — один и тот же кодовый путь
   через `MCPGateway → MCPToolProvider → ToolRegistry`.

Формула ценности дня: **соединение + список инструментов + реальный вызов — не хак,
а вертикальный срез расширяемой подсистемы**: добавление нового MCP-сервера завтра не
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
  `MCPConnectionState` (подключение) и `ToolExecutionState` (вызов).
- **`MCPGateway` — адаптер, не контролёр**: gateway знает только «как технически
  вызвать внешний инструмент»; он **не знает** о стадиях, профилях и памяти. Иначе
  возникли бы циклические зависимости `Agent → MCPGateway → StateMachine → Agent`.
  Контроль остаётся за существующими сущностями: `StateMachine` — этапы,
  `InvariantChecker` — действия (расширение `ProposedAction` MCP-полями),
  `ToolExecutor` — процедура выполнения (policy → вызов → аудит).
- **Внутренняя модель инструментов — своя**: `ToolDescriptor` (name, description,
  input_schema, source, provider, original_name, risk_level, allowed_stages,
  requires_confirmation, enabled) — модель агента, а не MCP; имена квалифицируются
  (`mcp.<server>.<tool>`, `local.<tool>`), коллизии имён между серверами
  разрешаются префиксом провайдера.
- **MCP выключен по умолчанию** (`mcp_enabled = False`): без флага/команды агент
  работает ровно как в `den_15`; все прежние 91 юнит-тест и 40 критериев приёмки
  проходят **без** MCP и без сети. Новый функционал не меняет старое поведение —
  принципиальное требование регрессии.
- **Детерминизм без сети**: discovery, нормализация, каталог, коллизии, недоступный
  сервер, битая схема, `tools/call`, policy, tool-use цикл — тестируются на
  `FakeMCPTransport` + `MockClient`; живое HTTP-соединение с реальным сервером и
  живой LLM — только интеграционный прогон/демо, не гейт.
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
│   ├── agent.py                 # оркестратор: + self.mcp_gateway/tool_registry/tool_executor/tool_policy
│   │                            #   (None при MCP off) + агентный tool-use цикл (_respond_with_tools)
│   ├── llm_client.py            # LLMClient (ABC) + RouterAIClient + MockClient + LLMReply +
│   │                            #   complete_with_tools (нативный tool-use + fallback-протокол)
│   ├── profile_router.py        # ProfileRouter (без изменений)
│   ├── prompt_builder.py        # BLOCK_ORDER + DELIVERABLE + budget + блок [tools] (render_tools)
│   ├── state_machine.py         # строгая машина состояний (без изменений — MCP её не трогает)
│   ├── invariants.py            # Invariant + ConstraintSet + InvariantChecker + ProposedAction
│   │                            #   (расширен MCP-полями action_type/tool_name/arguments; правило tool.deny.*)
│   ├── tools.py                 # внутренняя модель инструментов: ToolDescriptor + ToolCallRequest +
│   │                            #   ToolExecutionResult + ToolExecutionState + ToolProvider (ABC) +
│   │                            #   ToolCatalogSnapshot (контракты без MCP SDK и без сети)
│   ├── tool_registry.py         # ToolRegistry — каталог всех источников: add_provider/
│   │                            #   unregister_provider/get/available_for/snapshot/refresh
│   │                            #   (атомарный swap snapshot; бизнес-правил не проверяет,
│   │                            #   StateMachine не вызывает)
│   ├── tool_policy.py           # ← НОВОЕ: ToolPolicy — проверки вызова (enabled/схема/стадия/
│   │                            #   инварианты/подтверждение) → PolicyDecision
│   └── tool_executor.py         # ← НОВОЕ: ToolExecutor — policy → gateway.call_tool → результат →
│                                #   аудит tool_audit.jsonl (StateMachine не вызывает)
├── integrations/                # ← НОВЫЙ слой: внешние интеграции (MCP и будущие)
│   ├── __init__.py
│   └── mcp/
│       ├── __init__.py
│       ├── config.py            # MCPServerConfig (server_id, transport, command/endpoint, enabled,
│       │                        #   trust_level, allowed/denied_tools, timeout, max_result_bytes)
│       │                        #   + загрузка servers.json (дефолты: реальный weather + demo; битый файл не роняет)
│       ├── transport.py         # MCPTransport (ABC) + StdioMCPTransport + HttpMCPTransport
│       │                        #   (Streamable HTTP, mcp SDK) + FakeMCPTransport; фабрика make_transport;
│       │                        #   фикс чтения схемы input_schema (snake_case SDK 2.2.0)
│       ├── client.py            # MCPClient: initialize / list_tools / call_tool —
│       │                        #   делегирует инжектированному транспорту (SDK — в transport.py)
│       ├── gateway.py           # MCPGateway: start/stop, connection_state (MCPConnectionState),
│       │                        #   discover() → list[ToolDescriptor], call_tool(); НЕ знает о стадиях/профилях/памяти
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

Изменения относительно `den_15` — новые модули (`core/tools.py`,
`core/tool_registry.py`, `core/tool_policy.py`, `core/tool_executor.py`,
`integrations/mcp/*`), зеркальные дополнения `storage/store.py` (методы каталога MCP
и аудита) и `Kod.py` (DI + `/mcp` + `--mcp-probe`); `core/agent.py` — расширение
(добавлены `self.mcp_gateway/tool_registry/tool_executor/tool_policy` — MCP off по
умолчанию; агентный tool-use цикл `_respond_with_tools`); `core/llm_client.py` —
обратно совместимое расширение (`LLMReply`, `complete_with_tools`);
`core/prompt_builder.py` — новый необязательный блок `[tools]`;
`core/invariants.py` — `ProposedAction` расширен MCP-полями (обратно совместимо);
`core/state_machine.py`, `memory/*`, `storage/db.py` — **не трогаются**.

### 2.2 Внутренняя модель инструментов (`core/tools.py` — контракты без MCP)

Канон `Рекомендации_MCP_d16.txt`: модель MCP не должна протекать в `core`.
`ToolDescriptor` — внутренняя модель агента; поля `allowed_stages` /
`requires_confirmation` / `risk_level` заполняются дефолтами (`allowed_stages` — все
рабочие стадии, `requires_confirmation=False`, `risk_level="unknown"`) и
**используются** `ToolPolicy` при проверке вызова.

```python
# core/tools.py
@dataclass(frozen=True)
class ToolDescriptor:
    name: str                    # квалифицированное: "mcp.weather.search_locations" | "local.<tool>"
    description: str
    input_schema: dict
    source: str                  # "local" | "mcp"
    provider: str                # server_id (mcp) | "local"
    original_name: str           # имя тула на сервере ("search_locations")
    risk_level: str = "unknown"  # policy
    allowed_stages: frozenset = ALL_WORKING_STAGES  # policy
    requires_confirmation: bool = False             # policy
    enabled: bool = True

@dataclass(frozen=True)
class ToolCallRequest:           # рабочий tools/call
    name: str
    arguments: dict
    call_id: str = ""            # id в протоколе tool-use (связка с LLM)

@dataclass(frozen=True)
class ToolExecutionResult:       # рабочий tools/call
    execution_id: str
    tool: str
    status: str                  # ToolExecutionState
    summary: str
    raw: object | None = None    # сырой ответ — только текущий execution context, не в память
    is_error: bool = False
    call_id: str = ""

class ToolExecutionState(str, Enum):   # инфраструктурные состояния вызова (НЕ TaskStage)
    REQUESTED = "requested"; DENIED = "denied"; WAITING_CONFIRMATION = "waiting_confirmation"
    RUNNING = "running"; SUCCEEDED = "succeeded"; FAILED = "failed"
    TIMED_OUT = "timed_out"; CANCELLED = "cancelled"

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
command, endpoint, enabled, trust_level, allowed_tools/denied_tools, timeout_seconds,
max_result_bytes) + загрузка `users/<id>/integrations/mcp/servers.json`; битый или
отсутствующий файл → конфиг по умолчанию: **реальный погодный HTTP-сервер** `weather`
(`transport="http"`, `endpoint` из env `MCP_WEATHER_URL`, дефолт
`https://weatherapi.projecteol.ru/mcp/`, `enabled=true`) + демо-сервер `demo`
(stdio, `enabled=false` — для детерминированных тестов), приложение не падает
(наследие устойчивости `Store`).

**Транспорт** (`transport.py`) — `MCPTransport` (ABC: `initialize` / `list_tools` /
`call_tool` / `close`) + `StdioMCPTransport` (обёртка над `mcp` SDK: ленивый импорт
SDK в `initialize()`, stdio-подпроцесс, timeout) + **`HttpMCPTransport`** (Streamable
HTTP: `mcp.client.streamable_http.streamable_http_client`, SDK 2.2.0) +
`FakeMCPTransport` (детерминированная заглушка: фиксированный список тулов,
программируемые `fail_initialize`/`fail_list_tools`/`fail_call`/`error_call`/`timeout`
+ `set_tools`/`set_tool_result` — для тестов без сети и без SDK-подпроцесса). Фабрика
`make_transport(server)` выбирает транспорт по полю `transport`. Единый хелпер
`_tool_schema` читает схему из `input_schema` (snake_case SDK 2.2.0) с fallback на
`inputSchema`/dict.

**Клиент** (`client.py`) — `MCPClient`: транспорт инжектится, SDK напрямую не
импортирует (SDK — в `transport.py`); `initialize()` (handshake: protocol version,
capabilities), `list_tools()` →
нормализованные сырые описания `{name, description, inputSchema}`, **`call_tool()`** →
`{isError, text, raw}`; любой сбой → `MCPConnectionError` (gateway переводит в
`MCPConnectionState.FAILED`), не `None` и не молчание.

**Шлюз** (`gateway.py`) — `MCPGateway`:

```python
class MCPConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    READY = "ready"
    DEGRADED = "degraded"    # часть серверов недоступна
    FAILED = "failed"

class MCPGateway:            # НЕ знает о TaskStage / профилях / памяти
    async def start(self) -> None            # connect + initialize → READY | FAILED (идемпотентно)
    async def stop(self) -> None             # закрытие транспортов → DISCONNECTED
    def status(self) -> dict                 # состояние подключения по серверам
    async def discover(self) -> list[ToolDescriptor]
        # list_tools у каждого включённого сервера → нормализация → ToolDescriptor[]
        # фильтр allowed_tools/denied_tools из MCPServerConfig (изоляция прав через
        # тулинг — канон Суть_N4 §3.3: серверу даём только часть тулов)
    async def call_tool(self, provider, tool_name, arguments, execution_id="") -> ToolExecutionResult
        # вызов инструмента на сервере provider; сервер не READY → failed-результат (не исключение)
```

Синхронный фасад для REPL: `MCPGatewaySync` — **постоянная фоновая задача** в
daemon-потоке (все операции исполняются в одной долгоживущей задаче: HTTP/stdio-контексты
`mcp` SDK держат anyio cancel scope, который обязан войти и выйти в одной задаче) —
REPL и `--mcp-probe` остаются синхронными.

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
- `users/<id>/tasks/<task>/tool_audit.jsonl`
  (`append_tool_audit` / `load_tool_audit` — **реализованы и задействованы**,
  append-only, битые строки пропускаются) — история вызовов, **отдельно** от
  `transition_log` (успешный вызов инструмента сам по себе не создаёт запись о
  переходе — канон рекомендаций); запись ведёт `ToolExecutor` (execution_id, tool,
  status, phase, `arguments_hash` — только отпечаток, не сырые аргументы);
- `MCPGateway` JSON напрямую не пишет — только через `Store`.

### 2.6 DI-композиция и CLI

`build_agent()` расширяется опционально (канон рекомендаций):

```python
mcp_enabled = False  # по умолчанию; включается флагом --mcp

if config.mcp_enabled:
    gateway = MCPGatewaySync(load_servers_config(store.mcp_servers_path(user_id)))
    registry = ToolRegistry()
    registry.add_provider(MCPToolProvider(gateway))
    policy = ToolPolicy()
    executor = ToolExecutor(registry, policy, gateway, store=store, checker=agent.checker)
    agent.mcp_gateway = gateway
    agent.tool_registry = registry
    agent.tool_policy = policy
    agent.tool_executor = executor
    agent.deliver.add("tools")           # блок [tools] в промте
    gateway.start(); registry.refresh()  # стартовое discovery + сейв каталога (деградация — не падение)
# без флага: agent.mcp_gateway/tool_registry/tool_executor is None — поведение = den_15
# local-провайдер в den_16 не регистрируется (задел: local.* — только безопасные
# доменные операции, никогда local.set_stage / local.write_task_state_file)
```

Новые команды REPL (семейство `/mcp`, 7 форм):

| Команда | Действие |
|---|---|
| `/mcp status` | состояние подключения по серверам (`MCPConnectionState`), версия каталога |
| `/mcp servers` | список сконфигурированных серверов (enabled, transport, trust_level) |
| `/mcp tools` | **результат задания**: список доступных инструментов (имя, description, input-схема) |
| `/mcp refresh` | re-discovery: gateway.discover() → registry.refresh() → атомарный swap + сейв каталога |
| `/mcp connect <id>` | включить/поднять соединение с сервером (по умолчанию — все из servers.json) |
| `/mcp call <tool> [{json}]` | **ручной вызов инструмента** через `ToolExecutor` (policy → вызов → аудит) |
| `/mcp disconnect` | закрыть **все** соединения (`gateway.stop()` → DISCONNECTED; тулы покидают каталог при следующем refresh) |

Новый флаг: `--mcp-probe` — **результат задания в one-shot форме**: подключиться →
handshake → `tools/list` → вывести список инструментов (имя, описание, схема) →
корректно закрыться → exit 0; при недоступном сервере — понятная ошибка, exit 1.
Флаги прежние (12) + `--mcp` (включить MCP-слой в REPL) + `--mcp-probe` → 14.

`/mcp`-команды не тратят токены LLM (локальные вызовы; LLM в loop не участвует).
Токен-флоу каталога в промте (`ToolPromptPolicy`: max_tools, max_schema_tokens) —
базовые лимиты реализованы (`render_tools`); сравнение MCP vs Skill + CLI — цель
недели, не дня 16.

### 2.6.1 LLM tool-use (Ревизия 2)

- **`core/llm_client.py`**: `LLMReply(content, tool_calls, raw)`; парсеры
  `parse_tool_calls` (нативный OpenAI-формат) и `parse_fallback_tool_call`
  (JSON-протокол `{"tool":..,"arguments":..}`); `complete_with_tools(messages, tools)`
  — нативный путь `RouterAIClient` (`tools`/`tool_choice` + разбор `message.tool_calls`)
  с fallback на текстовый протокол; `MockClient` — детерминированный tool-use.
  `complete(messages)` — прежнее поведение (обратная совместимость).
- **`core/prompt_builder.py`**: блок `[tools]` (позиция после `invariants`, до
  `long_term`; `BLOCK_ORDER`/`DELIVERABLE` расширены без смещения прежних блоков);
  `render_tools` под лимитами.
- **`core/agent.py`**: `_respond_with_tools` — цикл «LLM → tool call → `ToolExecutor`
  → tool-сообщение → LLM → ответ» (лимит `max_tool_iterations`); `_tool_specs`
  (OpenAI function-calling); `_record_external_action` — нормализованная запись
  `external_actions` в рабочую память (сырой ответ — не в память). Без каталога —
  прежний путь (регрессия).

### 2.6.2 `ToolExecutor` / `ToolPolicy` (Ревизия 2)

- **`core/tool_policy.py`**: `ToolPolicy.check` — ступени enabled → схема аргументов →
  стадия (`allowed_stages`) → инварианты (`InvariantChecker` поверх `ProposedAction`) →
  `requires_confirmation`; итог `PolicyDecision(allowed, reason, needs_confirmation)`.
- **`core/tool_executor.py`**: `ToolExecutor.execute(request)` — policy → `gateway.call_tool`
  → `ToolExecutionResult` → аудит `tool_audit.jsonl`. **Не** вызывает `StateMachine`
  (инструмент ≠ переход).

### 2.7 Память, профили, инварианты, переходы (без изменений + заделы)

- **Память**: 4 слоя не тронуты. Задел `ToolMemoryPolicy` (include_raw_result /
  save_summary_to_short_term / save_to_working / …): сырые ответы MCP **никогда** не
  пишутся в память автоматически; в `working` — только нормализованный итог
  `external_actions[]` (реализовано в `Agent._record_external_action`); профиль MCP
  менять не может (изменение профиля — только явная механика профилей).
- **Профили**: задел `tool_policy` в профиле (`allow`/`deny`) — только **сужение**
  прав, никогда расширение глобального запрета.
- **Инварианты**: `ProposedAction` расширен полями `action_type` / `tool_name` /
  `arguments` (обратно совместимо): одно правило «нельзя менять схему БД» работает
  для локальной функции, MCP-инструмента и действия, предложенного LLM; добавлено
  правило `tool.deny.<qualified>` — запрет конкретного инструмента.
- **Машина состояний**: не тронута. Pipeline вызова (реализован в `ToolPolicy`):
  инструмент существует → включён → схема валидна → стадия разрешает → инварианты
  разрешают → подтверждение → вызов. Успех вызова **не** создаёт переход; переход —
  только `StateMachine.try_transition()` по решению агента.
- **Промт**: `BLOCK_ORDER` расширен новым необязательным блоком `[tools]` (после
  `invariants`, до `long_term`; прежние блоки не смещены); задел — блок
  `[external_context]` (MCP resources) отдельно от `long_term` (разные источники,
  разное доверие).

### 2.8 Сводная механика дня 16

```
запуск --mcp-probe (результат задания, one-shot):
  load servers.json → MCPGateway.start() (HTTP → weatherapi, initialize)
  → READY → discover(): list_tools → нормализация → ToolDescriptor[]
  → вывод: имя / description / input-схема → gateway.stop() → exit 0

REPL --mcp:
  /mcp connect   → gateway.start() → READY
  /mcp tools     → registry.snapshot().tools (из каталога; при пустом — подсказка /mcp refresh)
  /mcp refresh   → discover() → registry.refresh() (атомарный swap) → Store.save_tool_catalog
  /mcp call <t>  → ToolExecutor.execute (policy → gateway.call_tool → аудит)
  /mcp status    → connection_state по серверам + version каталога
  /mcp disconnect→ gateway.stop() → DISCONNECTED
  (MCP недоступен → «MCP Gateway: FAILED/DEGRADED», но память, профили и
   state machine продолжают работать — деградация, не падение)

LLM tool-use (Ревизия 2):
  сообщение «найди город Москва» → промт с [tools] + спецификация function-calling
  → LLM предлагает tool_call(search_locations, {"query":"Москва"})
  → ToolExecutor.execute → gateway.call_tool → реальный вызов на weatherapi
  → результат возвращается в модель → финальный ответ с координатами Москвы
  (аудит в tool_audit.jsonl; TaskStage не меняется — инструмент ≠ переход)

без --mcp / без /mcp: агент работает ровно как den_15 (MCP disabled by default)
```

---

## 3. Служебное пространство `dev/` (проект про проект)

### 3.1 Дерево `dev/`

```
Nedela_4/den_16/dev/
├── migr_plan.md                  # план-эталон миграции den_15 → arch_den_16.md (Ревизия 2)
├── migr_plan_0.md … migr_plan_12.md  # исполняемые планы этапов (конец этапа — гейт в следующий)
├── migr_log.md                   # журнал миграции den_15 → arch_den_16.md (Ревизия 2)
├── old_vers/                     # история прошлой ревизии (discovery по локальному stdio)
├── meta_promt/                   # метапромты (вспомогательные промты пользователя)
├── tests_debug/
│   ├── check_acceptance.sh       # гейт приёмки: 18 → 21 проверка (+3 Ревизии 2)
│   ├── unit_runner.py            # L2-раннер (без pytest)
│   ├── smoke.py                  # L3-смоук (+ MCP-прогон + tool-use)
│   ├── scenario.py               # L4-сценарии (+ scenario_mcp_discovery, scenario_llm_tool_use, scenario_tool_denied)
│   ├── unit/
│   │   ├── … (10 прежних модулей — без изменений, MCP off)
│   │   └── test_mcp.py           # ← НОВОЕ: контракты + реестр + gateway + call_tool + policy + tool-use
│   ├── scenario/scen_1.md        # сценарий ручной демонстрации (реальный сервер + tool-use)
│   └── .tmp/                     # единственное место прогонов (.gitignore)
└── logs_reports/                 # stages/ (в т.ч. m9_live_run.md) + errors/ + archive/
```

### 3.2 `tests_debug/` — что именно протестировать (канон задания)

`unit/test_mcp.py` (всё на `FakeMCPTransport`, без сети и без живого
подпроцесса; 31 тест):

- **контракты**: `ToolDescriptor` — квалифицированное имя, source/provider;
  `ToolCatalogSnapshot` — version/tools/created_at; `ToolExecutionState`;
- **discovery**: `MCPToolProvider.discover()` нормализует mcp-тул →
  `name="mcp.demo.get_time"`, `original_name="get_time"`, `source="mcp"`;
- **HTTP-транспорт**: `make_transport` выбирает `HttpMCPTransport`/`StdioMCPTransport`
  по конфигу; `_tool_schema` читает `input_schema` (snake_case SDK 2.2.0);
- **реестр**: `add_provider` → `refresh()` → snapshot содержит тулы провайдера;
  коллизия имён двух серверов разрешается префиксом; `unregister_provider` → тулы
  покидают каталог при следующем refresh; `get()` неизвестного → понятная ошибка;
- **атомарность**: во время refresh snapshot либо старый, либо новый (version
  монотонный, «половинного» каталога не бывает);
- **недоступный сервер**: transport падает → gateway → `FAILED`, тулы исключены,
  остальные провайдеры живы, исключение не роняет процесс;
- **фильтр прав**: `allowed_tools`/`denied_tools` конфига — запрещённый тул не
  попадает в discovery (изоляция прав через тулинг);
- **`tools/call`**: fake успех/`isError`; `gateway.call_tool` маршрутизирует по
  provider и отдаёт failed-результат для не-READY сервера;
- **`ToolPolicy`/`ToolExecutor`**: отказ по схеме/стадии; исполнение + аудит;
  отказ по инварианту (`tool.deny.*`) → `denied` в аудите;
- **LLM tool-use**: парсеры (нативный/fallback); агентный цикл (намерение → вызов →
  ответ); блок `[tools]` в промте + порядок блоков;
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
Плюс **`scenario_llm_tool_use`** (намерение → вызов → ответ + аудит) и
**`scenario_tool_denied`** (отказ инварианта).

Интеграционный тест (не гейт, помечен `@live`-аналогом по традиции проекта):
`HttpMCPTransport` подключается к реальному серверу `weatherapi` → initialize →
list_tools → 3 тула; `call_tool("search_locations", {"query":"Москва"})` → координаты
Москвы. Живой LLM tool-use («найди город Москва») — тоже вне гейта (приёмка).

Гейт `check_acceptance.sh`: 18 прежних + 3 новых проверки Ревизии 2 (HTTP-транспорт
и фикс схемы; `tools/call` + policy + аудит; блок `[tools]` + tool-use цикл), всё на
заглушках, `users/` не трогается, идемпотентен.

### 3.3 `logs_reports/`

- `migr_log.md` — журнал миграции «было → стало → проверка → статус» по этапам
  (Ревизия 2: M0–M12), результаты `test_mcp.py`, `scenario_mcp_discovery`,
  `scenario_llm_tool_use`, `scenario_tool_denied` и живой прогон `m9_live_run.md`;
- `errors/error_<timestamp>.md` — карточки ошибок (красный гейт этапа → карточка);
- `stages/`, `archive/` — наследуются из `den_15` (+ `stages/m9_live_run.md`).

---

## 4. Полная карта артефактов итогового состояния

### 4.1 Рабочие артефакты (продукт)

| Артефакт | Назначение |
|---|---|
| `Kod.py` + `core/` + `memory/` + `storage/` | агент дней 11–15 без регрессии + каталог инструментов + tool-use |
| `core/tools.py` | внутренняя модель: ToolDescriptor / ToolCallRequest / ToolExecutionResult / ToolExecutionState / ToolProvider / ToolCatalogSnapshot |
| `core/tool_registry.py` | ToolRegistry: каталогизация, атомарный snapshot, refresh |
| `core/tool_policy.py` | ToolPolicy: проверки вызова (enabled/схема/стадия/инварианты/подтверждение) |
| `core/tool_executor.py` | ToolExecutor: policy → вызов → аудит |
| `integrations/mcp/*` | MCP-слой: config / transport (stdio + **HTTP** + fake) / client / gateway / provider / demo_server |
| `users/<id>/integrations/mcp/{servers,catalog}.json` | конфиг серверов + снимок каталога (через Store) |
| `users/<id>/tasks/<task>/tool_audit.jsonl` | история вызовов инструментов (через Store) |
| `run.sh` / `run.desktop` | запуск (без изменений / пересоздать при переносе) |
| `README.md` | описание + раздел «Подключение MCP» (реальный сервер, tool-use) |

### 4.2 Служебные артефакты (процесс)

| Артефакт | Назначение |
|---|---|
| `dev/Проверка.md` | чек-лист: 40 прежних + **строки 41–48** (Ревизия 2) |
| `dev/migr_plan.md` + `migr_plan_0..12.md` | план-эталон и рабочие планы миграции (Ревизия 2) |
| `dev/migr_log.md` | журнал миграции + «Итог миграции» |
| `dev/tests_debug/*` | L2 (+`test_mcp.py`), L3, L4 (+`scenario_mcp_discovery`, `scenario_llm_tool_use`, `scenario_tool_denied`), гейт 21 проверка |

### 4.3 Критерии приёмки подключения MCP (строки 36–48)

| Пункт | Что проверяем | Как |
|---|---|---|
| 36 | MCP SDK установлен / локальный MCP-сервер поднимается | `python -c "import mcp"`; `python -m integrations.mcp.demo_server` стартует |
| 37 | Соединение устанавливается | `--mcp-probe` / `/mcp connect` → handshake initialize → `READY` (`/mcp status`) |
| 38 | Список инструментов корректно возвращается | `tools/list` → нормализация → 3 тула в `ToolRegistry.snapshot()` |
| 39 | Список инструментов выводится кодом | `python Kod.py --mcp-probe` печатает имя/description/схему каждого тула; `/mcp tools` в REPL |
| 40 | Регрессия: MCP off по умолчанию | без `--mcp` — 91 прежний тест OK, 40 прежних критериев зелёные, поведение = den_15 |
| 41 | HTTP-транспорт и конфиг реального сервера | `HttpMCPTransport`; `MCPServerConfig.transport="http"`, endpoint `weatherapi` (env `MCP_WEATHER_URL`); гейт №19 |
| 42 | **Настоящее соединение** к `weatherapi` | `python Kod.py --mcp-probe` → handshake → `READY`; гейт №16 |
| 43 | **Настоящий список** инструментов | `tools/list` → 3 тула (`search_locations`, `get_forecast_metadata`, `get_weather_forecast`); гейт №17, №18 |
| 44 | **Настоящий запрос** инструмента (`tools/call`) | `/mcp call mcp.weather.search_locations {"query":"Москва"}` → координаты Москвы; гейт №20 |
| 45 | Контроль вызова и аудит | `ToolExecutor`/`ToolPolicy` + `tool_audit.jsonl`; гейт №20 |
| 46 | **Полный LLM tool-use** («найди город Москва») | REPL `--mcp`: LLM сам вызывает тул, ответ содержит Москву/координаты; `scenario_llm_tool_use`; гейт №21; живой прогон `m9_live_run.md` |
| 47 | Инструмент ≠ переход | после вызовов `TaskStage` не менялся, `transition_log` без записей от вызовов |
| 48 | Регрессия MCP off | без `--mcp` поведение = den_15; прежние 40 критериев без регрессии |

Гейт: `unit_runner.py` (все модули, включая `test_mcp.py` — 122 OK) → `scenario.py`
(14 сценариев) → `check_acceptance.sh` 21 из 21 — всё без живого ключа и без сети.
Живой прогон (реальный HTTP-сервер + реальный LLM) — отдельно, в приёмке.

---

## 5. Порядок достижения итогового состояния

1. **Миграция `den_15` → `arch_den_16.md`** — по `dev/migr_plan.md` (и планам
   этапов `migr_plan_0..12.md`, Ревизия 2), порядок по зависимостям:
   `core/tools.py` (контракты, без SDK) → `core/tool_registry.py` (реестр +
   snapshot) → `integrations/mcp/` (config → transport+fake+**HTTP** → client →
   gateway → provider → demo_server) → `core/tool_policy.py` + `core/tool_executor.py`
   → `core/llm_client.py` (tool-use) → `core/prompt_builder.py` (блок `[tools]`) →
   `core/agent.py` (агентный цикл) → `storage/store.py` (каталог + аудит) → `Kod.py`
   (DI + `/mcp`-семейство + `--mcp`/`--mcp-probe`) → `test_mcp.py` +
   `scenario_mcp_discovery`/`scenario_llm_tool_use`/`scenario_tool_denied` + гейт
   18→21 → README (раздел «Подключение MCP») + `Проверка.md` (строки 41–48) →
   `scen_1.md` (реальный прогон) → запись этапа в `dev/migr_log.md`.
2. **Финал** — прогон всех проверок (L2→L3→L4→гейт 21/21), приёмка 48/48, живой
   прогон (реальный сервер + реальный LLM), запись итога в `dev/migr_log.md`,
   предложение коммита (коммит — только по явной команде пользователя).

Заделы следующих дней недели 4 (места зарезервированы, не реализуются):
`ToolMemoryPolicy` (полная политика памяти), `ToolPromptPolicy` + блок
`[external_context]` (resources), полный async core (вариант A), параллелизм
read-only тулов, local-провайдер, сравнение токен-флоу MCP vs Skill + CLI.

---

## 6. Итог

После завершения `den_16` получается:

- **Код, подключающийся к MCP и выводящий список доступных инструментов** —
  результат задания: `--mcp-probe` (one-shot) и `/mcp tools` (REPL); соединение
  устанавливается (handshake → `READY`), список корректно возвращается
  (`tools/list` → нормализация → каталог) — **на реальном сервере** `weatherapi`.
- **Настоящий вызов инструмента и полный LLM tool-use**: `tools/call` на живом
  сервере (`search_locations({"query":"Москва"})` → координаты Москвы); в REPL
  сообщение «найди город Москва» → LLM сам вызывает инструмент → ответ с координатами.
- **Не скрипт, а вертикальный срез подсистемы**: `MCPGateway` (адаптер, не
  контролёр) → `MCPToolProvider` (нормализация во внутреннюю `ToolDescriptor`) →
  `ToolRegistry` (каталог + атомарный snapshot + персистентность через `Store`) →
  `ToolExecutor` (policy + аудит) → LLM tool-use — фундамент всей MCP-работы недели 4
  по `Рекомендации_MCP_d16.txt`.
- **Пять «кубиков» дней 11–15 без регрессии**: память, профили, инварианты,
  строгая машина состояний, LLM-клиент — контракты не тронуты; MCP выключен по
  умолчанию; инструмент ≠ переход (`TaskStage` не меняется от вызовов MCP).
- **Изоляция прав через тулинг**: `allowed_tools`/`denied_tools` в конфиге сервера;
  модель MCP не протекает в `core`; `MCPGateway` не знает о стадиях/профилях/памяти
  (нет циклических зависимостей).
- **Детерминированная проверяемость**: `FakeMCPTransport` + `MockClient` — discovery,
  коллизии, недоступность, фильтры, персистентность, `tools/call`, policy, tool-use
  цикл — без сети; живой HTTP-прогон с реальным сервером и живой LLM — отдельно;
  гейт 21/21, приёмка 48/48.
- **Заделы с зарезервированными местами**: `ToolMemoryPolicy`, resources, async core,
  параллелизм read-only тулов, local-провайдер, сравнение MCP vs Skill + CLI.

---

## 7. Краткое описание архитектуры

### 7.1 Формула для самой краткой характеристики (1 строка)

> Персонализированный stateful-агент дней 11–15 (память → профили → инварианты →
> контролируемый жизненный цикл), к которому MCP подключается не как шестой
> фундаментальный слой, а как интеграционный источник инструментов: gateway
> соединяет (реальный HTTP-сервер), provider нормализует, registry каталогизирует,
> executor вызывает и аудитирует, LLM сам предлагает вызовы — а контроль остаётся
> за существующими механизмами.

### 7.2 Краткое и точное описание архитектуры den_16

Одно предложение (суть):

> den_16 — CLI stateful-агент (RouterAI, step-3.5-flash) дней 11–15, расширенный
> полным вертикальным срезом MCP-подсистемы: соединение с **реальным** MCP-сервером
> (Streamable HTTP, handshake initialize), discovery (tools/list), нормализация тулов
> во внутреннюю модель ToolDescriptor, каталогизация в ToolRegistry с атомарным
> snapshot и персистентностью через Store, **настоящий вызов инструмента** (tools/call
> через ToolExecutor с policy и аудитом) и **полный LLM tool-use**; результат задания —
> вывод списка инструментов (--mcp-probe / /mcp tools) и вызов инструмента по запросу
> пользователя.

Развёрнуто в 6 слоях (снизу вверх):

1. **Хранилище** (`storage/`) — прежний фасад `Store` + новые методы:
   `users/<id>/integrations/mcp/servers.json` (конфиг) и `catalog.json` (снимок
   каталога), `users/<id>/tasks/<task>/tool_audit.jsonl` (аудит вызовов); `read_*`
   при отсутствии/битости → `None` (дефолтизация у вызывающего), приложение не падает.
2. **Память** (`memory/`) — 4 слоя без изменений; сырые ответы MCP в память не
   пишутся (в working — только нормализованные `external_actions`; ToolMemoryPolicy — задел).
3. **Ядро** (`core/`) — прежние Agent / PromptBuilder / ProfileRouter /
   StateMachine / InvariantChecker / LLMClient **без регрессии** + новые
   `tools.py` (внутренние контракты инструментов, без MCP SDK), `tool_registry.py`
   (каталог всех источников, атомарный snapshot), `tool_policy.py` (проверки вызова),
   `tool_executor.py` (исполнение + аудит); расширения `llm_client.py` (tool-use),
   `prompt_builder.py` (блок `[tools]`), `agent.py` (агентный цикл), `invariants.py`
   (MCP-поля `ProposedAction`).
4. **Интеграции** (`integrations/mcp/`) — новый слой: config (MCPServerConfig,
   allowed/denied_tools), transport (ABC + StdioMCPTransport + **HttpMCPTransport** +
   FakeMCPTransport), client (initialize/list_tools/call_tool — единственный
   импорт SDK), gateway (MCPConnectionState, discover, call_tool; не знает о стадиях
   и памяти), provider (нормализация → ToolDescriptor), demo_server (локальный
   stdio-сервер с 3 тулами).
5. **CLI** (`Kod.py`) — DI с `mcp_enabled=False` по умолчанию; семейство `/mcp`
   (status/servers/tools/refresh/connect/call/disconnect) + флаги `--mcp`,
   `--mcp-probe`; REPL синхронный (async — внутри gateway).
6. **Служебное** (`dev/`) — миграция по плану-эталону (Ревизия 2, M0–M12), L2
   (+test_mcp.py на FakeMCPTransport), L4 (+scenario_mcp_discovery,
   scenario_llm_tool_use, scenario_tool_denied), гейт 21/21, приёмка 48/48.

Ключевые принципы:

- **MCP — источник инструментов, не слой контроля**: gateway — адаптер («как
  вызвать»), контроль — за StateMachine (этапы), InvariantChecker (действия) и
  ToolExecutor (процедура);
- **Инструмент ≠ переход**: TaskStage (8 стадий дня 15) не трогается; MCP-стадий
  нет; успех вызова не создаёт запись перехода;
- **Модель MCP не протекает в core**: ToolDescriptor — внутренняя модель;
  квалифицированные имена `mcp.<server>.<tool>`;
- **MCP off по умолчанию + детерминизм**: без флага агент = den_15; всё
  детерминированное тестируется на FakeMCPTransport + MockClient без сети;
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

3. **Ядро (core/)** — «кто решает». Прежние сущности без регрессии. Новые:
   - `tools.py` — контракты: ToolDescriptor (внутренняя модель: name, description,
     input_schema, source, provider, original_name + policy-поля risk_level /
     allowed_stages / requires_confirmation), ToolCallRequest / ToolExecutionResult
     (рабочий tools/call), ToolExecutionState, ToolProvider (ABC),
     ToolCatalogSnapshot (version, tools, created_at).
   - `tool_registry.py` — каталог: add_provider / unregister_provider / get /
     available_for / snapshot / refresh. Механика refresh: discover() у всех
     провайдеров → валидация схем → разрешение коллизий (квалифицированные имена) →
     сборка нового snapshot → атомарный swap. Реестр не проверяет бизнес-правила и
     не зовёт StateMachine. Недоступный провайдер → его тулы исключаются, остальные
     живы.
   - `tool_policy.py` — проверки вызова: enabled → схема → стадия → инварианты →
     подтверждение → PolicyDecision.
   - `tool_executor.py` — исполнение: policy → gateway.call_tool → результат → аудит
     tool_audit.jsonl; StateMachine не вызывает.
   - `llm_client.py` — LLMReply + complete_with_tools (нативный tool-use + fallback);
     `prompt_builder.py` — блок [tools]; `agent.py` — агентный цикл _respond_with_tools;
     `invariants.py` — ProposedAction + MCP-поля + правило tool.deny.*.

4. **Интеграции (integrations/mcp/)** — «как достучаться до внешнего мира».
   - config: MCPServerConfig (server_id, transport, command/endpoint, enabled,
     trust_level, allowed_tools/denied_tools, timeout_seconds, max_result_bytes) +
     загрузка servers.json с дефолтами (реальный weather + demo).
   - transport: ABC + StdioMCPTransport (обёртка над mcp SDK: ленивый импорт SDK в
     initialize, stdio-подпроцесс, timeout) + HttpMCPTransport (Streamable HTTP) +
     FakeMCPTransport (программируемые списки/отказы/таймауты/смена каталога/результаты
     вызова — тесты без сети и без SDK-подпроцесса). Фабрика make_transport; SDK
     импортируется только в transport.py (+ demo_server.py); client.py делегирует
     транспорту.
   - client: initialize (handshake: версия протокола, capabilities) / list_tools →
     `{name, description, inputSchema}` / call_tool → `{isError, text, raw}`; сбой →
     MCPConnectionError, не молчание.
   - gateway: start/stop/status/discover/call_tool; MCPConnectionState
     (disconnected/connecting/ready/degraded/failed); фильтр allowed/denied_tools
     (изоляция прав через тулинг — канон лекции: «дать сервису только часть тулов»);
     НЕ знает о TaskStage/профилях/памяти (нет цикла Agent→Gateway→StateMachine).
     Синхронный фасад MCPGatewaySync — постоянная фоновая задача (daemon-поток) для
     REPL и --mcp-probe.
   - provider: MCPToolProvider — нормализация mcp-тула → ToolDescriptor
     (`mcp.<server>.<tool>`).
   - demo_server: локальный stdio MCP-сервер (mcp SDK), 3 тула: get_time, echo,
     weather_stub (units Celsius|Kelvin + location — сквозной пример лекции).

5. **Оркестратор и CLI** — «как этим пользуются». Agent дней 11–15 — расширение:
   добавлены поля self.mcp_gateway / self.tool_registry / self.tool_policy /
   self.tool_executor (все None при выключенном MCP — поведение = den_15) и агентный
   tool-use цикл; жизненный цикл не изменён (/plan → /approve → /step|/run →
   validation → done; инварианты; профили; память). DI: build_agent() при mcp_enabled
   строит MCPGatewaySync + MCPToolProvider + ToolPolicy + ToolExecutor, регистрирует
   провайдер в ToolRegistry, добавляет слой tools в доставку и делает стартовое
   gateway.start()/registry.refresh() (деградация — не падение). Команды: /mcp status |
   servers | tools | refresh | connect <id> | call <tool> [{json}] | disconnect; флаги:
   --mcp (включить слой), --mcp-probe (one-shot: подключиться → вывести список тулов →
   закрыться). /mcp-команды токенов LLM не тратят.

6. **Служебное пространство (dev/)** — «проект про проект». Миграция den_15 →
   arch_den_16.md (Ревизия 2): план-эталон → рабочие планы этапов (конец этапа — гейт
   в следующий) → журнал; красный гейт → карточка ошибки. Тестовый контур: L2 —
   unit_runner.py + test_mcp.py (FakeMCPTransport: контракты, discovery, нормализация,
   коллизии, атомарность, недоступность, фильтры прав, персистентность, call_tool,
   policy, tool-use, «MCP не трогает TaskStage», «MCP off по умолчанию»); L3 — smoke
   (+MCP-прогон + tool-use); L4 — scenario_mcp_discovery + scenario_llm_tool_use +
   scenario_tool_denied; гейт check_acceptance.sh 21/21 (18 прежних + 3 Ревизии 2),
   всё в .tmp/, users/ не трогается, живой ключ и сеть не нужны. Приёмка — Проверка.md,
   48/48 (40 прежних без регрессии + строки 41–48 Ревизии 2).

---

Сводная механика результата задания (one-shot):

```
python Kod.py --mcp-probe
  → load servers.json → HttpMCPTransport(weatherapi) → initialize → READY
  → list_tools → [search_locations, get_forecast_metadata, get_weather_forecast]
  → нормализация → mcp.weather.search_locations / … / mcp.weather.get_weather_forecast
  → вывод: имя + description + input-схема → close → exit 0
```

Сводная механика вызова и tool-use (Ревизия 2):

```
/mcp call mcp.weather.search_locations {"query":"Москва"}
  → ToolExecutor.execute → ToolPolicy.check → gateway.call_tool → weatherapi
  → ToolExecutionResult(succeeded) → аудит tool_audit.jsonl

«найди город Москва» (REPL --mcp)
  → промт с [tools] + function-calling → LLM предлагает tool_call
  → ToolExecutor.execute → реальный вызов → результат в модель → ответ с координатами
```

И сводная механика контроля (главная граница дня):

```
MCP предоставляет инструменты.      ← integrations/mcp (gateway, provider)
ToolRegistry каталогизирует.        ← core/tool_registry (атомарный snapshot)
ToolPolicy фильтрует.               ← core/tool_policy (enabled/схема/стадия/инварианты/подтверждение)
InvariantChecker запрещает опасное. ← core/invariants (ProposedAction + tool.deny.*)
ToolExecutor управляет вызовом.     ← core/tool_executor (policy → вызов → аудит)
MemoryPolicy решает, что запомнить. ← задел (сырое — никогда в память; external_actions — реализовано)
StateMachine решает, можно ли
менять этап.                        ← БЕЗ ИЗМЕНЕНИЙ: инструмент ≠ переход
Store сохраняет конфиг и каталог.   ← users/<id>/integrations/mcp/ + tasks/<task>/tool_audit.jsonl
```

Инвариант всей системы прежний + новый: детерминизм недетерминированной LLM даёт
код — и теперь ещё «внешний мир подключается через адаптер, который не имеет права
менять внутреннее состояние агента».
