# День 20 — Планировщик, пайплайн и несколько MCP-серверов

> **Неделя 4** — «Инструменты и интеграции: MCP, тулинг, изоляция прав».
> День 16 — стартовый день недели: поверх наследия дней 11–15 (явная модель памяти,
> персонализация, формализованное состояние задачи, инварианты, строгая машина
> состояний) агент модернизируется **полным вертикальным срезом MCP-подсистемы**:
> **настоящее** подключение к **реальному** MCP-серверу (Streamable HTTP,
> `https://weatherapi.projecteol.ru/mcp/`), discovery (`tools/list`), нормализация тулов
> во внутреннюю модель `ToolDescriptor`, каталогизация в `ToolRegistry` с атомарным
> snapshot и персистентностью через `Store`, **настоящий вызов инструмента** (`tools/call`)
> и **полный LLM tool-use** (агент сам вызывает инструмент по запросу пользователя).
> Формула ценности — **соединение + список инструментов + реальный вызов — не хак, а
> вертикальный срез расширяемой подсистемы**: добавление нового MCP-сервера завтра не
> потребует изменений в `TaskStage`, `PromptBuilder`, профилях, памяти или машине
> переходов. MCP — стандарт (не фреймворк) подключения нейронок к внешним сервисам;
> ядро MCP-сервера — маппинг «тул ↔ HTTP-реквест» (description + input-схема +
> `CallToolResult`).
>
> **День 17 (наследие).** Инструмент задания `get_time(timezone_name) -> ISO 8601`
> с сервера `http://91.188.212.77:8000/mcp` (env `MCP_SERVER_URL`): LLM сам вызывает
> инструмент (`Agent._respond_with_tools`) и **использует результат** в финальном ответе.
> Демонстрация: «который час в Москве?» → `get_time({"timezone_name":"Europe/Moscow"})`
> → «В Москве сейчас 12:52».
>
> **Цепочка наследования.** `den_17` → `den_18` → `den_19` → `den_20`:  MCP-инфраструктура
> предыдущих дней перенесена без изменений.
>
> **День 20 (эта редакция).** Поверх MCP-инфраструктуры дней 16–19 добавлены **три
> возможности** (три задания `Задание_d20.txt`):
> 1. **Планировщик и фоновые задачи** — MCP-инструмент с отложенным/периодическим
>    выполнением (`schedule_reminder`/`schedule_collection`/`run_due`/`get_summary`),
>    данные в JSON, агрегированная сводка; агент работает **24/7** через **внешний
>    worker** (не LLM — «у агента нет heartbeat»). Формат отчёта — **Видео + Код**.
> 2. **Пайплайн из MCP-инструментов** — `search → summarize → saveToFile`,
>    автовыполнение цепочки и передача данных между инструментами. Формат — **Код**.
> 3. **Несколько MCP-серверов** — выбор нужного инструмента, маршрутизация, длинный
>    флоу с тулами разных серверов. Формат — **Код**.
>
> Целевая архитектура — `arch.md` (актуализирована под день 20). Сценарий ручной
> проверки (три сценария для видео) — `dev/Проверка.md`.

## Суть проекта

CLI-агент (RouterAI, модель `stepfun/step-3.5-flash`) с **явной моделью памяти**,
**настраиваемой персонализацией**, **формализованным состоянием задачи**, **набором
неизменяемых правил (инвариантов)**, **контролируемым жизненным циклом задачи** и —
новое в Дне 16 — **подключением к внешнему миру через MCP**: внешний источник
инструментов, подключённый к универсальному каталогу `ToolRegistry`.

Память разделена на четыре физически отдельных слоя (краткосрочная / рабочая /
долговременная / профиль), запись идёт только явным вызовом `memory.remember(layer,
...)`, а набор слоёв, попадающих в промт, — параметр `deliver: set[str]`
(дозированная доставка). Поверх памяти — мультипрофильность с профиль-роутером,
затем строгая машина состояний (`TaskStage` — 8 стадий, `ALLOWED_TRANSITIONS`
whitelist, `try_transition` → `InvalidTransitionError`, журнал `transition_log`) и
слой инвариантов (`InvariantChecker` — «код запрещает, промт рекомендует»).

День 16 добавляет **шестой, интеграционный «кубик»** — MCP как внешний источник
инструментов (не заменяя ни один из пяти кубиков дней 11–15). День 17 подключает к
этому «кубику» **конкретный инструмент задания** `get_time` (сервер `time`) и
демонстрирует реальное поведение агента: LLM сам вызывает инструмент и использует
результат.

```
MCPGateway (соединение + handshake + tools/list + tools/call)
   → MCPToolProvider (нормализация mcp-тула → ToolDescriptor)
      → ToolRegistry (каталог + атомарный snapshot + персистентность через Store)
         → ToolExecutor (policy → вызов → аудит) → LLM tool-use (агент сам вызывает тул)
            → CLI (/mcp tools, /mcp call, --mcp-probe — вывод списка и вызов инструментов)
```

Ключевые границы дня:

- **MCP — источник инструментов, не слой контроля**: `MCPGateway` — адаптер («как
  технически вызвать»), он не знает о стадиях, профилях и памяти; контроль остаётся
  за `StateMachine` (этапы), `InvariantChecker` (действия) и `ToolExecutor` (процедура
  вызова). Циклы `Agent → MCPGateway → StateMachine → Agent` запрещены.
- **Инструмент ≠ переход**: вызов (и даже успешное завершение) MCP-инструмента
  **никогда** не означает переход `TaskStage`; MCP-стадий нет и не будет.
  Инфраструктурные состояния живут отдельно: `MCPConnectionState` (подключение) и
  `ToolExecutionState` (вызов).
- **Модель MCP не протекает в `core`**: `mcp` SDK импортируется только в
  `integrations/mcp/` (транспорт и демо-сервер); `ToolDescriptor` — внутренняя
  модель агента; имена квалифицируются (`mcp.<server>.<tool>`).
- **MCP выключен по умолчанию** (`mcp_enabled=False`): без `--mcp` агент работает
  ровно как в `den_15`; все прежние тесты и критерии приёмки проходят без MCP и сети.
- **Изоляция прав через тулинг**: `allowed_tools`/`denied_tools` в конфиге сервера —
  запрещённый тул не попадает в discovery (серверу даём только часть тулов).

## Что нового относительно Дня 15

- **`core/tools.py`** — внутренняя модель инструментов **без MCP SDK и без сети**:
  `ToolDescriptor` (frozen: name/description/input_schema/source/provider/
  original_name + policy-поля: risk_level="unknown", allowed_stages=5 рабочих
  стадий, requires_confirmation=False, enabled=True), `ToolCallRequest` /
  `ToolExecutionResult` (**рабочий** `tools/call`), `ToolExecutionState`
  (requested/denied/waiting_confirmation/running/succeeded/failed/timed_out/
  cancelled), `ToolProvider` (ABC: provider_id/discover), `ToolCatalogSnapshot`
  (frozen: version/tools/created_at);
- **`core/tool_registry.py`** — `ToolRegistry`: add_provider (замена по provider_id
  с логом) / unregister_provider / get (неизвестное → KeyError с подсказкой) /
  available_for / snapshot / **refresh** (discover у всех провайдеров → валидация схем
  JSON-примитивами → коллизии квалифицированных имён → монотонный version →
  **атомарный swap**); недоступный провайдер изолирован; реестр не проверяет
  бизнес-правила и не зовёт `StateMachine`;
- **`core/tool_policy.py`** (новое) — `ToolPolicy.check`: enabled → схема аргументов →
  стадия (`allowed_stages`) → инварианты (`InvariantChecker` поверх `ProposedAction`) →
  `requires_confirmation`; итог `PolicyDecision`;
- **`core/tool_executor.py`** (новое) — `ToolExecutor.execute`: policy → `gateway.call_tool`
  → `ToolExecutionResult` → аудит `tool_audit.jsonl` (execution_id, tool, status, phase,
  `arguments_hash` — только отпечаток, не сырые аргументы); **не** вызывает `StateMachine`;
- **`integrations/mcp/`** — слой внешних интеграций: `config.py` (`MCPServerConfig` frozen
  + `load_servers_config`: битый/отсутствующий `servers.json` → дефолт — **сервер задания**
  `time` (инструмент `get_time`, endpoint из env `MCP_SERVER_URL`) + **реальный
  погодный HTTP-сервер** `weather` + демо-сервер `demo` для тестов; endpoint погоды из env
  `MCP_WEATHER_URL`), `transport.py` (`MCPTransport` ABC + `StdioMCPTransport` +
  **`HttpMCPTransport`** (Streamable HTTP, SDK 2.2.0) + `FakeMCPTransport`; фабрика
  `make_transport` по полю `transport`; фикс чтения схемы `input_schema`),
  `client.py` (`MCPClient`: initialize/list_tools/**call_tool**), `gateway.py`
  (`MCPConnectionState` + `MCPGateway` async: start/stop/status/discover/**call_tool** +
  синхронный фасад `MCPGatewaySync` на постоянной фоновой задаче), `provider.py`
  (`MCPToolProvider` — нормализация → `mcp.<server>.<tool>`), `demo_server.py`
  (локальный stdio MCP-сервер, 3 тула);
- **`core/llm_client.py`** — **LLM tool-use**: `LLMReply(content, tool_calls, raw)`,
  парсеры `parse_tool_calls` (нативный OpenAI-формат) и `parse_fallback_tool_call`
  (JSON-протокол), `complete_with_tools` (нативный путь `RouterAIClient` + fallback;
  `MockClient` — детерминированный tool-use);
- **`core/prompt_builder.py`** — новый необязательный блок `[tools]` (после
  `invariants`, до `long_term`) + `render_tools` под лимитами (`ToolPromptPolicy`:
  `max_tools`/`max_schema_tokens`);
- **`core/agent.py`** — **агентный tool-use цикл** (`_respond_with_tools`): LLM →
  tool call → `ToolExecutor` → tool-сообщение → LLM → ответ (лимит итераций);
  `external_actions` в рабочей памяти (сырое — не в память);
- **`storage/store.py`** — методы фасада: `users/<id>/integrations/mcp/servers.json`
  (конфиг) + `catalog.json` (снимок каталога); **рабочий** аудит `tool_audit.jsonl`
  (`append_tool_audit`/`load_tool_audit`) — история вызовов отдельно от `transition_log`;
- **`Kod.py`** — DI `build_agent(mcp_enabled=False)` (gateway → provider → registry →
  policy → executor только при `--mcp`; стартовое discovery + сейв каталога), семейство
  `/mcp` (7 форм: status/servers/tools/refresh/connect/**call**/disconnect), флаги
  `--mcp` и `--mcp-probe` (one-shot результат задания: подключиться → вывести список
  тулов → закрыться; exit 0/1) — итого **14 флагов**; `/mcp`-команды токенов LLM не тратят;
- **Тестовый контур расширен**: L2 — `test_mcp.py` (31 тест) → **122 OK**; L4 —
  `scenario_llm_tool_use` + `scenario_tool_denied` → **14/14**; L3 — smoke 7 тестов;
  гейт — **21 проверка**; приёмка — **54 критерия** (48 прежних + 49–54 дня 17);
- **Наследие дней 11–15 без регрессии**: память, профили, инварианты, машина
  состояний, LLM-клиент — контракты не тронуты; MCP off по умолчанию.

## Модель памяти

| Тип | Что хранит | Где (файл/хранилище) | Почему так |
|---|---|---|---|
| **Краткосрочная** (`ShortTermMemory`, scope=`session`) | текущий диалог — неизменяемые сообщения с `id`/`parent_id` | `users/<id>/tasks/<task>/sessions/<sid>/session.json` | сообщения — история (append-only), их нельзя переписывать; `parent_id` — задел ветвления (наследие Дня 10) |
| **Рабочая** (`WorkingMemory`, scope=`task`) | состояние задачи: `description`, `refs`, `lifecycle_summary`, `decisions`, `constraints`, `facts`, `open_questions`, `current_state` | `users/<id>/tasks/<task>/working_memory.json` | это **пересчитываемое состояние**, а не лог сообщений: списки дополняются, скаляры перезаписываются |
| **Долговременная** (`LongTermMemory`, scope=`user`) | `profile_ref` (ССЫЛКА), `tasks[]` (со ссылками и `source_session`), `decisions[]` (`{text, status}` — «выполнена»/«не выполнена»), `knowledge[]` | `users/<id>/long_term_memory.json` | живёт между сессиями и задачами; профиль держится отдельно, здесь — только ссылка (канон куратора) |
| **Профиль** (`Profile`, scope=`user`) | **несколько профилей** на пользователя: `profile_id`, `name`, `domain`, `triggers[]`, `style` + `constraints` + `context`, `skills[]` (пайплайн) | JSON в SQLite (`profiles(user_id, profile_id)`), зеркала `users/<id>/profiles/<pid>.json` | канон куратора: профили — отдельная сущность в БД, а не часть долговременной памяти; запись слиянием (MERGE); активный профиль подключён к каждому запросу |

Единая точка входа в память — `MemoryManager`: `remember()` (запись с логом маршрута),
`recall()` (чтение выбранных слоёв), `build_blocks()` (текстовые блоки для промта в порядке
`LAYER_ORDER = profile → long_term → working → short_term`), `report()` (снимок для `/memory`).

> **Про «долговременная (профиль, решения, знания)» из задания.** Формулировка описывает
> *содержание* типа, а не одну файловую реализацию. Реализован предпочтительный по куратору
> вариант: профиль — отдельное хранилище (SQLite), в `long_term_memory.json` — ссылка.

### Иерархия хранения

```
users/<user_id>/
├── profile.json                 # зеркало профиля default (авторитет — SQLite profiles)
├── profiles/                    # зеркала всех профилей пользователя
│   ├── default.json
│   ├── chemist.json
│   └── economist.json
├── long_term_memory.json        # profile_ref + задачи + решения + знания
├── integrations/mcp/            # ← НОВОЕ (День 16): ветка MCP
│   ├── servers.json             # конфиг MCP-серверов (user-scope)
│   └── catalog.json             # снимок каталога инструментов (version, tools, created_at)
└── tasks/<task_name>/
    ├── invariants.json          # ConstraintSet (неизменяемые правила задачи, День 14)
    ├── task_state.json          # снимок TaskState (+ transition_log, День 15)
    ├── working_memory.json      # пересчитываемое состояние задачи (+ current_state — зеркало стадии)
    ├── sessions_resume.md       # резюме сессий задачи (блок summary в промте)
    └── sessions/<session_id>/   # session_id = ГГГГММДД_ЧЧММСС
        └── session.json         # краткосрочная память: сообщения с parent_id
```

Разделение ответственности: `session.json` — неизменяемая история; `working_memory.json` —
пересчитываемое состояние памяти задачи; `task_state.json` — формализованное состояние
**жизненного цикла** (включая журнал переходов); `invariants.json` — **неизменяемые правила**;
`integrations/mcp/` — конфиг и каталог внешних инструментов. Пять разных сущностей, разные
файлы. **Очистка истории диалога не сбрасывает состояние, не удаляет инварианты, не трогает
журнал переходов и конфиг MCP** (разные файлы).

База профилей — `users/profiles.db` (общая для всех пользователей).
Все пути знает только `storage/store.py` (`safe_name`, `ensure_user/task/session`,
`read_json`/`write_json` с каноническими дефолтами, `task_state_path`/`read_task_state`/
`write_task_state` с миграцией `"execution"` → `implementation`,
`invariants_path`/`read/write_invariants`, `mcp_servers_path`/`read/write_mcp_servers`,
`tool_catalog_path`/`read/save_tool_catalog`, задел `tool_audit_path`/`append/load_tool_audit`).
Битый или отсутствующий файл не роняет приложение — чтение всегда возвращает схему по умолчанию;
при недоступной БД `load_profile`/`list_profiles` откатываются на зеркала `profiles/` →
`profile.json`.

### Сборка промта (явные блоки + дозированная доставка + бюджет)

```
[system: роль] → [system: profile] → [system: invariants] → [system: long_term] →
[system: working] → [system: summary, опц.] → [messages: short_term (окно 10)] →
[user: текущий запрос] → [резерв под ответ]
```

- `BLOCK_ORDER = ("role", "profile", "invariants", "long_term", "working", "summary",
  "short_term", "current")`;
- доставляемое подмножество блоков задаётся каноническим набором
  `DELIVERABLE = ("profile", "invariants", "long_term", "working", "summary",
  "short_term")` из `core/prompt_builder.py` (`role`/`current` — всегда, неуправляемы);
  `--deliver`/`/deliver` пересекаются с `DELIVERABLE` (не с `LAYER_ORDER` — тот
  задаёт порядок **слоёв памяти**), поэтому `summary` достижим из CLI
  (`--deliver profile,summary`);
- слои добавляются system-блоками с заголовком `[<имя>]` **только если имя есть в `deliver`**;
- `short_term` идёт отдельными сообщениями `{role, content}`, а не склеенным текстом;
- бюджет: необязательный блок пропускается, если `used + tokens > budget`; роль и запрос не
  урезаются никогда; бюджет передаётся в рабочем пути (`Agent.prompt_budget` ← флаг
  `--budget`, по умолчанию `None` — обрезание выключено);
- блок `[external_context]` (MCP resources) и дозированная доставка описаний тулов —
  **задел** следующих дней (`ToolPromptPolicy`); `BLOCK_ORDER` в Дне 16 не меняется.

## Персонализация

Поверх модели памяти — **несколько профилей на пользователя** (`arch_den_12.md` §2.3–2.7).
Профиль — «призма» под домен/задачу: он определяет стиль, ограничения, контекст, доменную
область и порядок скиллов. Активный профиль привязан к сессии и входит в каждый промт, поэтому
один и тот же запрос даёт разные ответы.

### Модель профиля (расширение JSON, обратно совместимое)

```json
{
  "id": "<user_id>",
  "profile_id": "chemist",
  "name": "Химик",
  "domain": "химия",
  "triggers": ["химия", "реактив", "реакция"],
  "style": {"answers": "строго по формулам"},
  "constraints": {"answers": "..."},
  "context": {"answers": "..."},
  "skills": [
    {"name": "spec",   "instructions": "сначала составь спеку ответа"},
    {"name": "review", "instructions": "проверь факты по домену"}
  ]
}
```

- `profile_id` — короткое имя профиля (`safe_name`); первый/единственный профиль — `default`;
  `domain`/`triggers`/`skills` опциональны (пустые — профиль работает как в Дне 11);
- **профиль = декларативный пайплайн скиллов**: упорядоченные инструкции подмешиваются в промт
  блоком «Пайплайн скиллов:» (движок исполнения скиллов — задел);
- **хранение**: SQLite `profiles(user_id, profile_id, …, is_default)` + зеркала
  `users/<id>/profiles/<pid>.json`; `users/<id>/profile.json` остаётся зеркалом `default`;
  БД старой схемы мигрируется автоматически при открытии;
- **запись слиянием**: `Profile.write()` обновляет только переданные поля, словари
  `style`/`constraints`/`context` мержатся по ключам — инвариант MERGE действует для активного
  профиля (`ctx.profile_id`);
- **память независима от профилей**: краткосрочная/рабочая/долговременная не меняются при
  переключении профиля — профиль влияет только на блок `profile` в промте;
- **профиль MCP менять не может** (канон `arch_den_16.md` §2.7): изменение профиля — только
  явная механика профилей; задел `tool_policy` в профиле (`allow`/`deny`) — только **сужение**
  прав, никогда расширение глобального запрета.

### Профиль-роутер (`core/profile_router.py`)

Общий профиль-роутер выбирает конкретный профиль по тексту запроса — детерминированно, без LLM:
**+2** за вхождение каждого триггера (регистронезависимо), **+1** за вхождение `domain`;
победитель = максимум (>0); ничья или ноль → `None` (остаёмся на текущем/дефолтном). Решение
логируется («[Роутер] запрос → профиль chemist (счёт 5)»), разбор по каждому кандидату показывает
`/profile route <текст>`. Режим `/profile auto on` запускает роутер на каждый запрос **до** сборки
промта.

## Инварианты и ограничения состояния (День 14, без регрессии)

Слой **неизменяемых правил** поверх памяти, персонализации и автомата: агент не имеет
права нарушать заданные инварианты. Главная идея дня 14: **инвариант — условие, которое должно
сохраняться во всех допустимых состояниях; переход, нарушающий его, должен быть запрещён**.
Недостаточно добавить правила в системный промт — перед выполнением действия запускается
**отдельная Python-проверка** («код запрещает, промт рекомендует»).

| Сущность | Назначение |
|---|---|
| `Invariant` | одно правило: `id`, `description`, `category`, `severity`, `active` |
| `ConstraintSet` | набор правил — **отдельная сущность** (не память, не профиль, не диалог) |
| `ProposedAction` | предлагаемое действие (`technology`, `adds_dependency`, `changes_database_schema`, `language`) |
| `InvariantChecker` (ABC) | интерфейс проверки: `check()` (блокирующие) + `warnings()` (`severity="warning"`) |
| `RuleBasedChecker` | детерминированная реализация: правила по id-неймспейсу, без вызовов LLM |
| `update_invariant` | изменение правила — только авторизованной операцией (`authorized=True`) |

Хранение — `users/<id>/tasks/<task>/invariants.json`, **отдельно от диалога**; очистка истории
не удаляет набор. Блок `[system: invariants]` входит в промт (после профиля, до рабочей
памяти) и участвует в дозированной доставке. При нарушении инструмент **не вызывается**, а
пользователю выдаётся отказ: (1) какое действие, (2) какой инвариант нарушен, (3) почему
обязателен, (4) допустимая альтернатива. Изменение правила — `/invariant set <id> <текст>
--yes` (без `--yes` — `PermissionError`).

**Переходы и инварианты — разные сущности контроля**: `state_machine` проверяет переходы
(этапы), `InvariantChecker` — действия; разные модели, разные проверки, разные отказы.
Задел дня 17+: расширение `ProposedAction` полями `action_type`/`tool_name`/`arguments` —
одно правило «нельзя менять схему БД» будет работать для локальной функции, MCP-инструмента
и действия, предложенного LLM.

## Контролируемые переходы состояний (День 15, без регрессии)

Главная идея Дня 15: **жизненный цикл задачи — строгая машина состояний**. Чёткий список
допустимых состояний и разрешённых переходов между ними; ассистент **физически не может
«перепрыгнуть» этап** — запрет работает на уровне кода, а не только текста.

### Модель состояний (`TaskStage` — 8)

```python
class TaskStage(Enum):
    NEW = "new"                      # задача создана, но ещё не начата
    PLANNING = "planning"            # план строится/построен, не утверждён
    PLAN_APPROVED = "plan_approved"  # план утверждён пользователем (/approve)
    IMPLEMENTATION = "implementation"  # идёт реализация (бывший execution)
    VALIDATION = "validation"        # проверка/тестирование
    DONE = "done"                    # задача завершена (терминальная)
    PAUSED = "paused"                # пауза (возврат в previous_stage)
    FAILED = "failed"                # ошибка (восстановление — /task retry)
```

### Карта переходов (whitelist)

```python
ALLOWED_TRANSITIONS: dict[TaskStage, set[TaskStage]] = {
    NEW:            {PLANNING, PAUSED, FAILED},
    PLANNING:       {PLAN_APPROVED, PAUSED, FAILED},          # НЕТ implementation
    PLAN_APPROVED:  {IMPLEMENTATION, PLANNING, PAUSED, FAILED},  # PLANNING — пересборка
    IMPLEMENTATION: {VALIDATION, PLANNING, PAUSED, FAILED},
    VALIDATION:     {DONE, IMPLEMENTATION, PLANNING, PAUSED, FAILED},
    PAUSED:         set(),        # выход только через resume_task() → previous_stage
    DONE:           set(),        # терминальная
    FAILED:         {PLANNING},   # восстановление — явный /task retry
}
```

Запреты задания реализуются **отсутствием дуги в графе** (не `if`-ами): «нельзя делать
реализацию до утверждённого плана» — нет дуг `new → implementation` и
`planning → implementation`; «нельзя делать финал без валидации» — единственный путь в
`done` через `validation`; пауза — не лазейка (из `paused` только `resume_task()` →
`previous_stage`).

### API контроля (имена из задания)

```python
can_transition(from_state, to_state) -> bool   # единственный источник истины — карта

try_transition(state, proposed) -> TaskState    # единственная точка смены этапа:
    # недопустимый → InvalidTransitionError, состояние НЕ меняется,
    # попытка пишется в transition_log (allowed=False);
    # допустимый → меняет stage + запись (allowed=True)
```

Поток: `/plan <цель>` строит план и **останавливается** в `planning` (утверждение —
контрольный пункт человека); `/approve` — единственный переход в `plan_approved`;
`/run` из `planning` не может перепрыгнуть утверждение. Отказ называет правило
(`REFUSAL_RULES` — детерминированные тексты, без LLM) и корректный следующий шаг;
каждая попытка (успех и отказ) фиксируется в `transition_log` и переживает перезапуск.

**MCP эту машину не трогает** (главная граница Дня 16): успех вызова MCP-инструмента не
создаёт запись в `transition_log`; `MCPGateway`/`ToolRegistry` не вызывают `StateMachine`
(проверяется тестом «MCP не трогает состояние»).

## Подключение MCP (День 16 → День 17)

Результат задания дня 16 — «код, который подключается к MCP и выводит список доступных
инструментов» — реализован **не одноразовым скриптом, а первым вертикальным срезом
подсистемы** (канон `Рекомендации_MCP_d16.txt`): один и тот же кодовый путь
`MCPGateway → MCPToolProvider → ToolRegistry` работает и в one-shot флаге `--mcp-probe`,
и в REPL-команде `/mcp tools`. День 17 добавляет **конкретный инструмент задания**
`get_time` (сервер `time`) и демонстрирует **реальное поведение агента**: LLM сам
вызывает инструмент и использует результат.

### Внутренняя модель инструментов (`core/tools.py`)

Контракты **без MCP SDK и без сети** — модель MCP не протекает в `core`:

| Сущность | Назначение |
|---|---|
| `ToolDescriptor` (frozen) | квалифицированное имя (`mcp.weather.search_locations`), description, input_schema, source (`"mcp"`), provider (server_id), original_name (`search_locations`) + policy-поля: risk_level, allowed_stages, requires_confirmation, enabled |
| `ToolCallRequest` / `ToolExecutionResult` | **рабочий** `tools/call`: запрос (name/arguments/call_id) и результат (execution_id/tool/status/summary/raw/is_error) |
| `ToolExecutionState` | инфраструктурные состояния вызова (requested/denied/waiting_confirmation/running/succeeded/failed/timed_out/cancelled) — НЕ `TaskStage` |
| `ToolProvider` (ABC) | единый интерфейс источников инструментов: `provider_id()` / `discover()` |
| `ToolCatalogSnapshot` (frozen) | атомарная версия каталога: version (монотонный), tools, created_at |

### Реестр (`core/tool_registry.py`)

`ToolRegistry` — каталог инструментов **всех источников** (local + mcp):

- `add_provider` (повторный provider_id → замена с логом) / `unregister_provider` /
  `get` (неизвестное имя → `KeyError` со списком доступных) / `available_for` (задел
  фильтров policy) / `snapshot` (текущий, без пересборки) / `refresh`;
- механика `refresh()`: `discover()` у всех провайдеров → валидация схем (JSON
  Schema-примитивы: type=object, properties, required) → разрешение коллизий имён
  (квалифицированные имена; дубликат → последний побеждает, лог) → сборка нового
  `ToolCatalogSnapshot` (version — монотонный счётчик) → **атомарный swap**: один
  запрос модели никогда не видит «половину старого и половину нового» каталога;
- недоступный провайдер при `refresh()` → его тулы **исключаются** из нового snapshot
  (каталог честен: нет соединения — нет тулов), ошибка логируется, остальные не страдают;
- реестр **не проверяет бизнес-правила** и **не вызывает** `StateMachine`.

### MCP-слой (`integrations/mcp/`)

| Модуль | Назначение |
|---|---|
| `config.py` | `MCPServerConfig` (frozen: server_id, transport="stdio", command, endpoint, enabled, trust_level="low", allowed_tools/denied_tools, timeout_seconds=30, max_result_bytes=65536) + `load_servers_config`: отсутствующий/битый `servers.json` → дефолт `DEFAULT_SERVERS` (**реальный погодный HTTP-сервер** `weather` + демо-сервер `demo` для тестов), неизвестные ключи игнорируются; endpoint из env `MCP_WEATHER_URL` |
| `transport.py` | `MCPTransport` (ABC: initialize/list_tools/call_tool/close) + `StdioMCPTransport` (stdio-подпроцесс) + **`HttpMCPTransport`** (Streamable HTTP, `mcp.client.streamable_http.streamable_http_client`, SDK 2.2.0) + `FakeMCPTransport` (детерминированная заглушка: фиксированный список тулов, программируемые отказы/таймауты/результаты вызова); фабрика `make_transport` (выбор по `transport`); фикс чтения схемы `input_schema` (snake_case SDK 2.2.0) |
| `client.py` | `MCPClient`: `initialize()` (handshake) / `list_tools()` → нормализованные `{name, description, inputSchema}` / **`call_tool()`** → `{isError, text, raw}`; любой сбой → `MCPConnectionError` |
| `gateway.py` | `MCPConnectionState` (disconnected/connecting/ready/degraded/failed) + `MCPGateway` (async: start/stop/status/discover/**call_tool**) + `MCPGatewaySync` (синхронный фасад на постоянной фоновой задаче — сессии `mcp` SDK привязаны к задаче initialize) |
| `provider.py` | `MCPToolProvider(ToolProvider)`: provider_id="mcp"; `discover()` → gateway.discover() → тулы с source="mcp", provider=server_id, name=`mcp.<server>.<tool>` |
| `demo_server.py` | минимальный локальный stdio MCP-сервер на `mcp` SDK: 3 тула — `get_time`, `echo`, `weather_stub`; запуск `python -m integrations.mcp.demo_server` |

**Реальный сервер недели** — `https://weatherapi.projecteol.ru/mcp/` (Streamable HTTP,
protocol `2025-11-25`, `projecteol-weather v1.0.0`), 3 инструмента:
`search_locations` (поиск города → координаты), `get_forecast_metadata`,
`get_weather_forecast` (прогноз по координатам). Endpoint переопределяется env
`MCP_WEATHER_URL`.

**Сервер задания Дня 17** — `http://91.188.212.77:8000/mcp` (Streamable HTTP,
protocol `2025-06-18`, `serverInfo: Time Server`), 1 инструмент:
`get_time(timezone_name: string = "UTC") -> ISO 8601` — текущее время в указанном
часовом поясе (IANA: `UTC`, `Europe/Moscow`, `Europe/London`, `Asia/Tokyo`; значение
по умолчанию `UTC`). Endpoint переопределяется env `MCP_SERVER_URL` (дефолт — боевой
URL). В `DEFAULT_SERVERS` сервер `time` добавлен **первым** (`transport="http"`,
`enabled=True`); погодный `weather` и демо `demo` сохранены. Живой вызов:
`get_time({"timezone_name":"Europe/Moscow"})` → `2026-09-27T12:52:07+03:00`.

Механика discovery в `MCPGateway.discover()`: `list_tools` у каждого сервера в READY →
**фильтр прав** (`denied_tools` исключает всегда; непустой `allowed_tools` сужает —
изоляция прав через тулинг: серверу даём только часть тулов) → нормализация в
`ToolDescriptor`. Сервер в FAILED → тулов нет; overall-статус: все READY → `ready`,
есть READY + другие → `degraded`, иначе `failed`, все DISCONNECTED → `disconnected`.

**Деградация, не падение**: MCP-сервер недоступен → `MCPConnectionState.FAILED`,
тулы исключены, но REPL жив — память, профили и машина состояний продолжают работать.

### Вызов инструмента и полный LLM tool-use (Ревизия 2)

- **`tools/call`**: `MCPTransport.call_tool` → `MCPClient.call_tool` →
  `MCPGateway.call_tool(provider, tool, arguments)` → `ToolExecutionResult`
  (нормализация `CallToolResult`: `isError`, текстовые части `content`).
- **`ToolExecutor`** (`core/tool_executor.py`) — единственная точка исполнения:
  `ToolPolicy` (enabled → схема аргументов → стадия → инварианты → подтверждение) →
  `gateway.call_tool` → результат → **аудит** `tool_audit.jsonl` (execution_id, tool,
  status, phase, `arguments_hash` — только отпечаток, не сырые аргументы). **Не**
  вызывает `StateMachine` (инструмент ≠ переход).
- **LLM tool-use**: `LLMClient.complete_with_tools` (нативный OpenAI-совместимый
  `tools`/`tool_calls` + детерминированный fallback-JSON-протокол); блок `[tools]` в
  промте (`ToolPromptPolicy`: `max_tools`/`max_schema_tokens`); агентный цикл
  `Agent._respond_with_tools`: LLM → tool call → `ToolExecutor` → tool-сообщение → LLM
  → финальный ответ (лимит итераций). Нормализованные вызовы пишутся в рабочую память
  (`external_actions`); **сырой** ответ — только текущий контекст, никогда в память.
- **Ручной вызов**: `/mcp call <tool> [{json}]` — прямой вызов через `ToolExecutor`.

Пример живого tool-use (реальный сервер + реальный LLM):

```text
Вы [Основная_задача]: найди город Москва
Агент: Нашёл город Москва (Россия) с координатами 55.75204, 37.61781.
```

(LLM сам предложил вызов `mcp.weather.search_locations` с `{"query":"Москва"}`;
результат вернулся в модель; в `tool_audit.jsonl` — запись `succeeded`.)

Пример живого tool-use дня 17 (сервер задания `time` + реальный LLM):

```text
Вы [Основная_задача]: который час в Москве?
Агент: В Москве сейчас 12:52 (27 сентября 2026 года).
```

(LLM сам предложил нативный `tool_call` `mcp.time.get_time` с
`{"timezone_name":"Europe/Moscow"}` (п. 4.1 — автовызов из приложения); реальный вызов
на сервере задания вернул `2026-09-27T12:52:07+03:00`; результат вернулся в модель и
**использован** в финальном ответе (п. 4.2); в `tool_audit.jsonl` — запись `succeeded`
с `call_id` нативного tool_call; `TaskStage` не изменился.)

### Хранение (`users/<id>/integrations/mcp/`)

- `servers.json` — конфиг серверов (user-scope): `Store.mcp_servers_path` /
  `read_mcp_servers` / `write_mcp_servers`;
- `catalog.json` — снимок `ToolCatalogSnapshot` (schema_version, version, tools,
  created_at): `Store.tool_catalog_path` / `read_tool_catalog` / `save_tool_catalog`;
  отсутствующий/битый файл → пустой каталог (`schema_version: 1, version: 0, tools: []`);
  каталог пересохраняется после каждого успешного `/mcp refresh` — переживает перезапуск;
- `MCPGateway` JSON напрямую не пишет — только через фасад `Store`;
- задел дня 17+: `users/<id>/tasks/<task>/tool_audit.jsonl` — история вызовов
  (`append_tool_audit`/`load_tool_audit`), **отдельно** от `transition_log`.

### DI-композиция и CLI

```python
build_agent(user_id, mock, mcp_enabled=False)   # MCP off по умолчанию
# при mcp_enabled (--mcp):
#   gateway = MCPGatewaySync(load_servers_config(...))
#   registry = ToolRegistry(); registry.add_provider(MCPToolProvider(gateway))
#   agent.mcp_gateway = gateway; agent.tool_registry = registry
# без флага: agent.mcp_gateway is None, agent.tool_registry is None — поведение = den_15
```

Семейство `/mcp` (6 форм; токенов LLM не тратят — LLM в loop не участвует):

| Команда | Действие |
|---|---|
| `/mcp status` | общее состояние подключения + по серверам + версия каталога и число тулов |
| `/mcp servers` | сконфигурированные серверы (transport, enabled, trust, allowed/denied) |
| `/mcp tools` | **результат задания**: список доступных инструментов (имя, description, input-схема) |
| `/mcp refresh` | re-discovery → registry.refresh() (атомарный swap) → сейв catalog.json |
| `/mcp connect <id>` | поднять соединение (по умолчанию — все из servers.json) |
| `/mcp call <tool> [{json}]` | ← НОВОЕ (Ревизия 2): вызвать инструмент вручную через `ToolExecutor` |
| `/mcp disconnect` | закрыть соединения (тулы покидают каталог при следующем refresh) |

Флаг `--mcp-probe` — **результат задания в one-shot форме**:

```text
$ python Kod.py --mcp-probe
[MCP] Подключение к серверам: time, weather
[MCP] Соединение установлено (READY). Список доступных инструментов:

  mcp.time.get_time
    description: Получает текущее время в указанном часовом поясе (IANA, ISO 8601)
    input_schema: {"type": "object", "properties": {"timezone_name": {"default": "UTC", "type": "string"}}}
  mcp.weather.search_locations
    ...
[MCP] Всего инструментов: 4
[MCP] Соединение закрыто (DISCONNECTED).
```

Недоступный сервер → понятная ошибка, exit 1. Без `--mcp`/`/mcp` — MCP-слой не собирается,
агент работает ровно как `den_15` (регрессия запрещена).

### Сводная механика контроля (главная граница дня)

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

## День 20 — планировщик, пайплайн, несколько MCP-серверов

### Планировщик и фоновые задачи (задание 1)

Фоновое выполнение обеспечивает **внешний worker** (поток stdlib `threading`), а
**не LLM** — канон куратора «у агента нет heartbeat». LLM участвует только в
формировании текста сводки (по запросу); готовая сводка отдаётся **без нового
запроса к модели**.

- **Ядро** (`integrations/scheduler/`): `models.py` (`Job`/`Observation`/`Summary`/
  `JobState`), `store.py` (`SchedulerStore` через фасад `Store`), `runner.py`
  (`Scheduler`: `add_job`/`due_jobs`/`run_once`/`start`/`stop`), `aggregator.py`
  (`aggregate` → `count/min/max/avg/last`). Только stdlib, без MCP SDK.
- **MCP-сервер** (`integrations/mcp/scheduler_server.py`, по образцу
  `doc/mcp/mcp-time-server/time_server_http.py`): тулы `schedule_reminder`,
  `schedule_collection`, `record_observation`, `run_due`, `get_summary`,
  `latest_summary`, `list_jobs`. HTTP :8010 (env `SCHEDULER_MCP_URL`).
- **Хранение**: `users/<id>/integrations/mcp/scheduler/{jobs,observations,summaries}.json`.
- **Запуск 24/7**: `python Kod.py --mcp --scheduler [--scheduler-interval 60]`.

### Пайплайн из MCP-инструментов (задание 2)

Цепочка `search → summarize → saveToFile` (сервер `integrations/mcp/pipeline_server.py`,
HTTP :8020, env `PIPELINE_MCP_URL`); автовыполнение и передача данных между шагами —
`core/tool_pipeline.py` (`PipelineStep`/`Pipeline`/`run_pipeline`: результат шага N →
аргумент N+1 через `input_key`; **не трогает `StateMachine`**). Команда:
`/mcp pipeline <запрос>`. Каждый вызов идёт через `ToolExecutor` → аудит.

### Несколько MCP-серверов (задание 3)

`DEFAULT_SERVERS`: `time`, `weather`, `scheduler`, `pipeline`, `demo`. Маршрутизация
по квалификации `mcp.<server>.<tool>` (`MCPGateway` + `ToolRegistry`); длинный флоу —
несколько последовательных tool-use итераций в одном запросе
(`Agent._respond_with_tools`, лимит `max_tool_iterations`). Команды: `/mcp servers`,
`/mcp tools`, `/mcp route <текст>`.

## RAG-индексация и поиск по документам (Ревизия 6)

Поверх MCP-инфраструктуры добавлен **расширяемый RAG-модуль** (`rag/`): агент умеет
индексировать корпус документов, искать по нему **гибридно** (лексика + векторы) и
подмешивать найденные источники в промпт **со ссылками**, а ответ — проверять на
опору на источники (grounding). Требование `Задание_d21.txt`.

### Назначение и конвейер

```
corpus (rag/datasets/corpus.list) → chunking (fixed | structural)
  → embedding (Ollama bge-m3, локально) → index (BM25 + dense, плоский)
  → retrieval (BM25 ⊕ dense → RRF → реранк → MMR) → блок [rag] в промпте
  → grounding (ответ обязан опираться на найденное)
```

- **Эмбеддинги — строго локально:** только `127.0.0.1:11434` (Ollama, модель
  `bge-m3`, dim 1024). Любой другой адрес отвергается валидацией `RagConfig`.
  При недоступности Ollama — деградация на `HashingEmbedder` (офлайн-фолбэк).
- **Плоский индекс** без FAISS (решение куратора): BM25-постинги + векторы в
  `rag/index/` (в `.gitignore`); переживает перезапуск, обновляется **инкрементально**
  (неизменённые документы не переэмбедятся).
- **Две стратегии чанкинга** (`fixed` — окно токенов; `structural` — по заголовкам),
  сравнение — отчёт `dev/logs_reports/stages/rag_chunking_compare.md`.
- **Гибрид ≥ каждой компоненты** (BM25, dense) по recall@20 и hit-rate@5; веса RRF
  подобраны экспериментально (`w_bm25=0.1`, `w_dense=1.0`).
- **Ссылки обязательны:** при активном RAG каждое утверждение помечается
  `[doc_id#chunk_id]`; grounding (`off|warn|strict`) ловит выдуманные числа и в
  `strict` запускает **одну** авто-перегенерацию с фидбэком.
- **RAG off по умолчанию:** без `--rag` промпт байт-в-байт прежний, `rag` не
  импортируется; `TaskStage` не затрагивается (RAG ≠ переход).

### Как запустить Ollama

```bash
# Установка (выполняет оператор, требует sudo) и модель:
curl -fsSL https://ollama.com/install.sh | sh
ollama pull bge-m3
# Проверка: сервис слушает только localhost, модель доступна
curl -s http://127.0.0.1:11434/api/tags
```

### Команды и флаги

```bash
./run.sh --rag-ingest                       # проиндексировать корпус (одна команда)
./run.sh --rag-search "как считается бюджет токенов"   # поиск без LLM (топ-5 со скорами)
./run.sh --rag-eval                         # метрики на golden-датасете (recall/hit-rate/mrr/ndcg)
./run.sh --rag-compare                      # сравнение стратегий × режимов + вердикт
./run.sh --rag --user alice                 # REPL с блоком [rag] в промпте
./run.sh --rag --rag-mode bm25 --rag-top-k 3
./run.sh --rag --rag-grounding strict       # проверка опоры ответа (off|warn|strict)
./run.sh --rag --rag-multi-query            # переформулирование запроса (тратит токены)
./run.sh --rag --no-rag-block               # диагностика: ищет, но в промпт не кладёт
```

**Флаги RAG:** `--rag`, `--no-rag-block`, `--rag-ingest`, `--rag-path <путь>`,
`--rag-search <запрос>`, `--rag-eval [датасет]`, `--rag-compare`, `--rag-mode {bm25,dense,hybrid}`,
`--rag-strategy {fixed,structural}`, `--rag-top-k <N>`, `--rag-config <файл>`,
`--rag-grounding {off,warn,strict}`, `--rag-multi-query`.

**Команды REPL:** `/rag status|on|off|ingest|find|stats|eval|check` — `/rag find`
показывает скорами, **почему** выбран чанк; `/rag check <ответ>` проверяет опору
ответа на последние источники (LLM не тратит); `/rag stats` — индекс, модель, размер,
RAM, кэш (хиты/промахи/TTL), латентность p50/p95, состояние Ollama.

### Пример вывода

```
[RAG] Запрос «как запретить агенту менять технологический стек проекта» (режим hybrid): Найдено источников: 5
  1. [5a49d570…#5a49d570…#0] core/invariants.py · раздел: … · score=0.0179
  2. [5a49d570…#5a49d570…#7] core/invariants.py · раздел: … · score=0.0174
```

```
[RAG] Оценка по rag/datasets/queries.jsonl (k=5, режим hybrid):
  recall@k: 0.9167   hit_rate@k: 0.9167   mrr: 0.7479   ndcg@k: 0.9165
  латентность: p50=147 мс, p95=168 мс
```

## Команды REPL

Команды дней 11–15 сохранены полностью; новое — семейство `/mcp` (6 форм).

| Команда | Действие | Пункт приёмки |
|---|---|---|
| `/memory` | снимок «какие данные в каком типе памяти» (report по всем слоям) | 4 |
| `/profile` | активный профиль: `style` / `constraints` / `context` (обратно совместимо с Днём 11) | 2 |
| `/profile list` | профили пользователя (`*` default, `>` активный) | 20 |
| `/profile show <id>` | полный JSON профиля | 20 |
| `/profile use <id>` | переключить активный профиль сессии | 22 |
| `/profile new <id>` | создать профиль (мини-интервью) и активировать его | 20 |
| `/profile route <текст>` | показать решение роутера (explain), НЕ переключая | 22 |
| `/profile auto on\|off` | авто-роутинг профиля по каждому запросу | 22 |
| `/tasks` | список задач + отметка активной (`*`) | 8 |
| `/task <имя>` | переключить/создать задачу + загрузка её `task_state.json` | 8 |
| `/task retry` | восстановление из `failed` → `planning` (steps/results/error очищены, снова `/approve`) | 25 |
| `/plan <цель>` | `new → planning`, план строится и **ожидает утверждения** | 23, 31 |
| `/approve` | утвердить план (`planning → plan_approved`); из других стадий — отказ с объяснением | 31, 33 |
| `/goto <этап>` | попытка явного перехода (демо контроля: недопустимый → отказ с правилом, состояние не меняется) | 33, 34 |
| `/transitions` | карта `ALLOWED_TRANSITIONS` + журнал `transition_log` + счётчик отказов | 32 |
| `/step` | один проход автомата | 23 |
| `/run` | крутить автомат до `done`/`failed`/`paused`; из `planning` — останавливается | 25 |
| `/pause` | пауза на любой рабочей стадии (`previous_stage` сохраняется) | 24 |
| `/resume` | продолжение с того же этапа и шага, без повторных объяснений | 24, 35 |
| `/deliver <слои>` | набор доставляемых слоёв, напр. `/deliver profile,working` | 5 |
| `/compare` | ответ с `long_term` и без него — демонстрация влияния памяти | 14 |
| `/summary` | резюме сессий текущей задачи (`sessions_resume.md`) | 12 |
| `/state` | снимок `TaskState` + разрешённые переходы + счётчик отказов + карта | 11, 23, 32 |
| `/invariants` | список инвариантов задачи (`on/off`, id, category, severity, description) | 26 |
| `/invariant add <id> <category> <текст>` | добавить инвариант (сейв `invariants.json`) | 26 |
| `/invariant set <id> <текст> [--yes]` | изменить инвариант — без `--yes` требует подтверждения | 30 |
| `/invariant on\|off <id>` | включить/выключить инвариант | 28 |
| `/check <действие>` | прогнать `ProposedAction` через `InvariantChecker` (демонстрация, без исполнения) | 28 |
| `/tokens` | локальная оценка токенов сессии + указание на CSV-журнал | 16 |
| `/cost` | стоимость обменов (локальная оценка, ₽) | 16 |
| `/mcp status` | ← НОВОЕ (Д16): состояние MCP-подключения + версия каталога | 37 |
| `/mcp servers` | ← НОВОЕ (Д16): сконфигурированные MCP-серверы | — |
| `/mcp tools` | ← НОВОЕ (Д16): **список доступных инструментов** (результат задания) | 38, 39 |
| `/mcp refresh` | ← НОВОЕ (Д16): re-discovery + атомарный swap + сейв catalog.json | 38 |
| `/mcp connect <id>` | ← НОВОЕ (Д16): поднять соединение с MCP-сервером | 37 |
| `/mcp call <tool> [{json}]` | ← НОВОЕ (Ревизия 2): вызвать инструмент вручную | 44 |
| `/mcp disconnect` | ← НОВОЕ (Д16): закрыть MCP-соединения | — |
| `/mcp summary [N]` | ← НОВОЕ (Д20): последняя сохранённая сводка планировщика (без нового запроса к LLM) | 1.4 |
| `/mcp jobs` | ← НОВОЕ (Д20): задачи планировщика (`state`/`interval`/`runs`) | 1.3 |
| `/mcp pipeline <запрос>` | ← НОВОЕ (Д20): пайплайн `search → summarize → saveToFile` | 2.3 |
| `/mcp route <текст>` | ← НОВОЕ (Д20): объяснить выбор инструмента/сервера (без вызова) | 3.2 |
| `/rag status` | ← НОВОЕ (Ревизия 6): состояние RAG (вкл/выкл, режим, топ-k, grounding, индекс) | — |
| `/rag on\|off` | ← НОВОЕ (Ревизия 6): включить/выключить RAG в сессии | — |
| `/rag ingest` | ← НОВОЕ (Ревизия 6): проиндексировать корпус (инкрементально) | — |
| `/rag find <запрос>` | ← НОВОЕ (Ревизия 6): поиск со скорами — **почему** выбран чанк | — |
| `/rag check <ответ>` | ← НОВОЕ (Ревизия 6): проверка опоры ответа на последние источники (без LLM) | — |
| `/rag stats` | ← НОВОЕ (Ревизия 6): индекс, модель, RAM, кэш, латентность p50/p95, Ollama | — |
| `/rag eval` | ← НОВОЕ (Ревизия 6): метрики на golden-датасете | — |
| `/help` | список команд | — |
| `/exit` | `save_state()` (+ сейв `task_state.json` с `transition_log`) и выход | 12, 25 |

Без активной задачи `/step`, `/run`, `/pause`, `/resume`, `/approve`, `/goto` печатают
подсказку «сначала `/plan <цель>`». `EOFError` / `KeyboardInterrupt` тоже вызывают
`save_state()` — состояние не теряется. Неизвестная команда и исключения цикла логируются
и не прерывают сессию. `/mcp`-команды без флага `--mcp` печатают «MCP-слой выключен».

## Запуск

```bash
# Через обёртку (активирует venv недели AI_9, работает из любого каталога)
./run.sh                     # интерактивный REPL — спросит user_id
./run.sh --user alice        # сразу идентификация alice
./run.sh --mock              # MockClient: детерминированные ответы, ключ не нужен

# Напрямую
python Kod.py --mock --user alice

# Персонализация
./run.sh --user alice --profile chemist    # активный профиль на старте

# MCP (День 16 → День 17)
python Kod.py --mcp-probe                  # one-shot: подключиться → список тулов → выйти
./run.sh --user alice --mcp                # REPL с MCP-слоем + полным LLM tool-use (/mcp …)
MCP_SERVER_URL=http://91.188.212.77:8000/mcp python Kod.py --mcp-probe  # сервер задания (get_time)
MCP_WEATHER_URL=https://weatherapi.projecteol.ru/mcp/ python Kod.py --mcp-probe  # явный endpoint погоды
python -m integrations.mcp.demo_server     # локальный MCP-сервер (stdio) отдельно

# День 20 — планировщик 24/7 и новые серверы
python Kod.py --mcp --scheduler            # фоновый worker 24/7 (сбор + сводка)
python Kod.py --mcp --scheduler --scheduler-interval 5   # укороченный интервал (демо)
python -m integrations.mcp.scheduler_server             # MCP-сервер планировщика (HTTP :8010)
python -m integrations.mcp.pipeline_server              # MCP-сервер пайплайна (HTTP :8020)
```

**Флаги (16):** `--user <id>`, `--profile <id>`, `--deliver <слои>` (по умолчанию полный
канонический набор `DELIVERABLE`), `--mock`, `--fresh`, `--log`, `--token-log`,
`--max-tokens`, `--price-in` / `--price-out` (₽ за 1M, по умолчанию 11 / 33), `--budget <N>`,
`--memory-dir` (перенос хранилища — используется тестами для изоляции), **`--mcp`**
(включить MCP-слой в REPL), **`--mcp-probe`** (one-shot результат задания),
**`--scheduler`** (фоновый worker 24/7, День 20), **`--scheduler-interval <сек>`**.
**Флаги RAG (Ревизия 6):** `--rag`, `--no-rag-block`, `--rag-ingest`, `--rag-path <путь>`,
`--rag-search <запрос>`, `--rag-eval [датасет]`, `--rag-compare`, `--rag-mode {bm25,dense,hybrid}`,
`--rag-strategy {fixed,structural}`, `--rag-top-k <N>`, `--rag-config <файл>`,
`--rag-grounding {off,warn,strict}`, `--rag-multi-query`.

Все пути строятся от `BASE_DIR`; ключ — `API_KEY` из `.env` (`load_dotenv()`).
При `--mock`, отсутствии ключа или `API_KEY=test-key` автоматически выбирается `MockClient`.
`run.desktop` содержит абсолютные `Exec=`/`Path=` — после переноса на другой хост
его нужно пересоздать (в `.desktop` переменные окружения не раскрываются).

## Агентный цикл

```
старт → DI-сборка build_agent(mcp_enabled=--mcp) → идентификация user_id
      ├─ профиль есть → load_state(): long_term → задача → task_state.json
      └─ нет профиля  → интервью (style/constraints/context) → initialize_user()
      → активный профиль (--profile) → deliver (--deliver ∩ DELIVERABLE)
обмен:  сообщение → [auto_route: ProfileRouter до сборки промта]
        → remember_message("user") → build_context → PromptBuilder.build(ctx, deliver, budget)
        → llm.complete(messages) → remember_message("assistant") → токен-оценка + CSV
автомат: /plan → /approve → /step|/run → validation → done|failed
         (переходы — только try_transition по карте; отказы — REFUSAL_RULES + transition_log)
MCP:    --mcp-probe → start → READY → discover → печать списка → stop → exit 0
        /mcp connect|tools|refresh|status|disconnect (токенов LLM не тратят;
        недоступный сервер → FAILED/DEGRADED, REPL жив — деградация, не падение)
RAG:    --rag → RagService.search (кэш → BM25⊕dense → RRF → реранк → MMR)
        → блок [rag] в промпте (после [tools]) → ответ со ссылками → grounding
        (strict: провал → одна авто-перегенерация); без --rag rag/ не импортируется
выход:  save_state() + сейв task_state.json (включая transition_log)
```

LLM за интерфейсом: `LLMClient (ABC)` → `RouterAIClient` (живой: POST + Bearer,
retry на HTTP 429 с задержками 2 → 4 → 8 сек, таймаут 30 сек, любой сбой → `None`)
и `MockClient` (детерминированная заглушка). Агент зависит только от абстракции —
провайдер инжектится на старте.

## Архитектура

```
./
├── Kod.py                       # точка входа: DI-композиция (+ mcp_enabled) + REPL
│                                #   (+ /mcp-семейство, --mcp, --mcp-probe, run_mcp_probe)
├── core/                        # ядро агентности
│   ├── agent.py                 # stateful-оркестратор (+ mcp_gateway/tool_registry = None)
│   ├── invariants.py            # Invariant + ConstraintSet + InvariantChecker + RuleBasedChecker
│   ├── llm_client.py            # LLMClient (ABC) + RouterAIClient + MockClient
│   ├── profile_router.py        # ProfileRouter — детерминированный выбор профиля
│   ├── prompt_builder.py        # BLOCK_ORDER (+invariants), build(ctx, deliver, budget)
│   ├── state_machine.py         # строгая машина состояний (MCP её не трогает)
│   ├── tools.py                 # ← Д16: внутренняя модель инструментов (без MCP SDK)
│   └── tool_registry.py         # ← Д16: ToolRegistry — каталог + атомарный snapshot
├── integrations/                # ← Д16: новый слой внешних интеграций
│   └── mcp/
│       ├── config.py            # MCPServerConfig + load_servers_config (servers.json)
│       ├── transport.py         # MCPTransport ABC + StdioMCPTransport (mcp SDK) + Fake
│       ├── client.py            # MCPClient: initialize / list_tools
│       ├── gateway.py           # MCPGateway + MCPConnectionState + MCPGatewaySync
│       ├── provider.py          # MCPToolProvider — нормализация → ToolDescriptor
│       └── demo_server.py       # локальный stdio MCP-сервер (3 тула)
├── memory/                      # модель памяти (4 слоя + MemoryManager) — без изменений
├── rag/                         # ← Ревизия 6: RAG-модуль (индексация + поиск)
│   ├── config.py                # RagConfig (+ валидация: эмбеддинги только localhost)
│   ├── corpus.py                # discover/delta — сбор корпуса, deny-список
│   ├── chunking.py              # две стратегии: fixed | structural
│   ├── embedding.py             # OllamaEmbedder (bge-m3) + HashingEmbedder (фолбэк)
│   ├── index.py                 # плоский индекс: BM25-постинги + векторы, save/load
│   ├── retrieval.py             # bm25 | dense | hybrid (RRF + MMR)
│   ├── rerank.py                # LexicalReranker (интерфейс под cross-encoder)
│   ├── cache.py                 # LRU+TTL кэш поиска (инвалидация по mtime)
│   ├── grounding.py             # проверка опоры ответа на источники
│   ├── eval.py / compare.py     # метрики и сравнение стратегий
│   ├── service.py               # RagService — фасад для Kod.py/Agent
│   └── datasets/                # corpus.list + queries.jsonl (golden)
├── storage/
│   ├── store.py                 # фасад: + mcp_servers/catalog + задел tool_audit
│   └── db.py                    # ProfileRepository (SQLite) — без изменений
├── users/                       # рантайм-данные (+ integrations/mcp/ у пользователя)
└── dev/                         # служебное: миграция, тесты, Проверка.md
```

Направление зависимостей однонаправленное: `Kod.py` → `core/` → `memory/` → `storage/`;
`integrations/` и `rag/` — сбоку, подключаются только DI-композицией в `Kod.py`.
`mcp` SDK импортируется только в `integrations/mcp/`; `core`/`memory`/`storage` его не
импортируют никогда. **`rag/` не импортирует `core/`, а `core/` не импортирует `rag/`** —
связь через DI-фасад `RagService` и готовый текст блока `[rag]`. Слои памяти и ядро ФС
напрямую не трогают — только через фасад `Store`.

## Демонстрации задания

| Что проверяем | Как посмотреть | Что видно |
|---|---|---|
| **Соединение устанавливается** | `python Kod.py --mcp-probe` | «[MCP] Соединение установлено (READY)» — handshake initialize прошёл (реальный сервер) |
| **Список инструментов корректно возвращается** | `--mcp-probe` или `/mcp tools` после `/mcp refresh` | 4 тула: `mcp.time.get_time` (сервер задания) + `mcp.weather.search_locations`, `mcp.weather.get_forecast_metadata`, `mcp.weather.get_weather_forecast` — имя, description, input-схема |
| **Список выводится кодом** | `python Kod.py --mcp-probe` (exit 0) | печать каждого тула + «Всего инструментов: 4» + чистое закрытие (DISCONNECTED) |
| **Настоящий вызов инструмента** | `/mcp call mcp.weather.search_locations {"query":"Москва"}` | результат с координатами Москвы (55.75204, 37.61781) |
| **Полный LLM tool-use** | `--mcp` → «найди город Москва» | LLM сам вызывает `search_locations` → ответ с координатами Москвы |
| **Инструмент задания дня 17** | `--mcp` → «который час в Москве?» | LLM сам вызывает `mcp.time.get_time` → ответ «В Москве сейчас 12:52» (результат использован) |
| **Ручной вызов `get_time`** | `/mcp call mcp.time.get_time {"timezone_name":"Europe/Moscow"}` | ISO 8601 `2026-09-27T12:52:07+03:00`; `{}` → время в `UTC` |
| REPL-флоу MCP | `--mcp` → `/mcp connect` → `/mcp tools` → `/mcp refresh` → `/mcp status` → `/mcp disconnect` | READY → каталог (4 тула) → атомарный refresh + сейв catalog.json → статус → DISCONNECTED |
| Изоляция прав | `denied_tools` в `servers.json` → `/mcp refresh` → `/mcp tools` | запрещённый тул не попадает в discovery |
| Недоступный сервер — деградация | `/mcp connect` при упавшем сервере | FAILED/DEGRADED, тулов нет, REPL жив (память/профили/автомат работают) |
| Какие данные попадают в каждый слой | `/memory`, журнал `Den_log.md` | `[Память] … ← …` по каждому слою |
| Как память влияет на ответы | `/compare` | два ответа: с `long_term` и без него |
| Дозированная доставка | `/deliver profile,working` | слой `long_term` физически отсутствует в промте |
| Недопустимый переход блокируется кодом | `/plan <цель>` → `/goto implementation` → `/state` | «ОТКАЗАНО», правило, состояние не изменилось, запись `allowed: false` |
| Утверждение плана — контрольный пункт | `/plan` → `/run` (остановка) → `/approve` → `/run` | `/run` не обходит утверждение |
| Конфликт запроса и инварианта | «Перепиши наш API на FastAPI» (при инварианте Django) | отказ: id правила, причина, альтернатива |
| **RAG: индексация корпуса** | `./run.sh --rag-ingest` | дельта индексации + число чанков (110 / 9 документов) |
| **RAG: гибридный поиск** | `./run.sh --rag-search "как считается бюджет токенов"` | топ-5 источников со скорами и метаданными (`source`/`section`/`chunk_id`) |
| **RAG: блок `[rag]` в промпте** | `./run.sh --rag --user demo` → вопрос | блок `[rag]` после `[tools]`, до `[long_term]`; ответ со ссылками `[doc_id#chunk_id]` |
| **RAG: проверка опоры (grounding)** | `/rag check <ответ с выдуманным числом>` | `Вердикт: hallucination`, «числа вне источников» |
| **RAG: метрики и сравнение** | `./run.sh --rag-eval` / `--rag-compare` | recall/hit-rate/mrr/ndcg; таблица «стратегия × режим» + вердикт |
| **RAG: без `--rag` — регрессия** | `./run.sh --user demo` (без флага) | блок `[rag]` отсутствует, `rag` не импортируется |

Готовый сценарий живой демонстрации куратору — `dev/tests_debug/scenario/scen_1.md`
(MCP) и `dev/tests_debug/scenario/scen_rag.md` (RAG, Ревизия 6).

## Тестирование и приёмка

Всё — **без живого ключа** (`API_KEY=test-key`, `MockClient`, `FakeMCPTransport`),
тестовые данные пишутся только в `dev/tests_debug/.tmp/` (в `.gitignore`), рабочие
`users/` не затрагиваются. `pytest` в venv недели отсутствует, поэтому L2 идёт через
собственный лёгкий раннер `unit_runner.py`.

| Уровень | Команда | Результат |
|---|---|---|
| L1 | `python -m py_compile Kod.py core/*.py memory/*.py storage/*.py integrations/mcp/*.py` | exit 0 |
| L2 | `env -u API_KEY python dev/tests_debug/unit_runner.py` | **244 OK, 0 FAIL** (18 модулей: 195 прежних + MCP + **RAG: 16 test_rag_integration + 18 test_rag_grounding + 15 test_rag_cache**) |
| L3 | `API_KEY=test-key python dev/tests_debug/smoke.py` | SMOKE OK, exit 0 |
| L4 | `API_KEY=test-key python dev/tests_debug/scenario.py` | SCENARIO OK, exit 0 |
| Гейт | `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` | **33 из 33 ✅, exit 0** (25 прежних + **8 Ревизии 6**: импорт `rag`; индекс строится и переживает save/load; поиск отдаёт хит с метаданными; две стратегии чанкинга; отчёт сравнения; без `--rag` нет `[rag]`; `TaskStage` не затронут; `--rag-eval` hit-rate@5 ≥ 0.80) |
| Интеграция | `timeout 60 python Kod.py --mcp-probe` (реальный HTTP-сервер) | READY → 4 тула (1 `time` + 3 `weather`) → DISCONNECTED, exit 0 (не гейт — живой прогон) |
| Живой tool-use | `printf 'найди город Москва\n/exit\n' \| python Kod.py --user u --mcp` | LLM вызывает `search_locations` → ответ с координатами Москвы (не гейт — живой прогон) |
| Живой tool-use дня 17 | `printf 'который час в Москве?\n/exit\n' \| python Kod.py --user u --mcp` | LLM вызывает `mcp.time.get_time` → ответ «В Москве сейчас 12:52» (не гейт — живой прогон) |

`test_mcp.py` (21 тест) — канон `arch_den_16.md` §3.2: контракты (квалифицированное
имя, source/provider); discovery-нормализация; реестр (add/refresh/snapshot, коллизии,
unregister, get-ошибка); атомарность (version монотонный, «половинного» каталога не
бывает); недоступный сервер (FAILED, тулы исключены, остальные живы); фильтр
allowed/denied; персистентность (round-trip, битый файл → schema_version=1); **MCP не
трогает состояние** (TaskStage не изменился, transition_log пуст); **MCP off по
умолчанию** (без `--mcp` реестр пуст, агент = den_15); конфиг (дефолт/битый/неизвестные
ключи).

Человеческая версия приёмки — **54 критерия, 54/54 зелёных** — в
[`dev/Проверка.md`](dev/Проверка.md): 40 прежних (без регрессии) + **строки 41–48
Ревизии 2** (41 — HTTP-транспорт/конфиг; 42 — настоящее соединение; 43 — настоящий
список; 44 — настоящий вызов `tools/call`; 45 — контроль вызова и аудит; 46 — полный
LLM tool-use «найди город Москва»; 47 — инструмент ≠ переход; 48 — регрессия MCP off).
День 17 добавляет **строки 49–54** (49 — сервер задания `time` в конфиге; 50 — реальное
discovery `get_time`; 51 — реальный вызов `get_time`; 52 — LLM tool-use «который час в
Москве?» (4.1+4.2); 53 — аудит и «инструмент ≠ переход»; 54 — регрессия MCP off) —
итог **54/54**.

## Что зафиксировано в процессе создания

- **Миграция `den_15` → `arch_den_16.md`** (день 16, журнал `dev/migr_log.md`,
  план-эталон `dev/migr_plan.md` + рабочие планы `migr_plan_0..12.md`): **Ревизия 2** —
  этапы M0–M12 по зависимостям (базовая линия → HTTP-транспорт → реальное discovery →
  `tools/call` → `ToolExecutor`/`ToolPolicy` → LLM tool-use → промт `[tools]` → агентный
  цикл → CLI → живой прогон → тесты → документация → финал + актуализация
  `arch_den_16.md`); перечитывание эталона перед каждым этапом; история прошлой ревизии
  (M0–M8: discovery по локальному stdio) сохранена в `dev/old_vers/2/`;
- **Миграция `den_16` → `den_17`** (день 17, журнал `dev/migr_log.md`, план-эталон
  `dev/migr_plan.md` + рабочие планы `migr_plan_0..6.md`): **Ревизия 3** — этапы M0–M6
  (базовая линия → сервер задания `time` в конфиге → реальное discovery → реальный вызов
  `get_time` → живой LLM tool-use 4.1+4.2 → CLI/DI → документация **без тестов**);
  инфраструктура MCP Ревизии 2 перенесена без изменений; правится только конфиг сервера
  задания; снимок состояния на входе Ревизии 3 — в `dev/old_vers/3/`;
- **Карточки-знания** (журнал): pip-квирк копированного venv (установка только
  `python -m pip`); `python` отсутствует в PATH (подпроцессы через `sys.executable`);
  квирк event loop (сессии `mcp` SDK привязаны к задаче initialize → `MCPGatewaySync`
  держит постоянную фоновую задачу; повторный `start()` идемпотентен);
- **Миграция `den_20` → Ревизия 5** (день 20, журнал `dev/migr_log.md`, план-эталон
  `dev/migr_plan.md` + рабочие планы `migr_plan_0..12.md`): **Ревизия 5** — этапы 0–12
  (инфраструктурный контур VPS 0–3: доступ/привилегии, `time` под `systemd --user`,
  скрипты отладки + живая база, `scheduler:8010` + `pipeline:8020`; пакет правок
  дефектов продукта 4–12, метки D1–D7, M0/M7: порог probe + `enabled`-политика,
  каталог в промте, мультисерверный флоу, `core/tool_routing.py` + `/mcp route`,
  таймауты транспорта, пакет мелких исправлений, авторизация транспорта); история
  Ревизии 4 сохранена в `dev/old_vers/5/`;
- **API SDK 2.2.0 отличается от v1**: `FastMCP` → `MCPServer`,
  `StdioServerParameters(command: str, args: list)`, HTTP-вход —
  `streamable_http_client` (не `streamablehttp_client`), атрибут схемы тула —
  `input_schema` (snake_case) — найдено интеграционным прогоном;
- Наследие инцидентов дней 11–15 (живой ключ в тесте, `bash -x` с ключом,
  загрязнение корня смоуком, naming-инцидент) — уроки перенесены, контур дня 16
  без живого ключа и сети (живой прогон — отдельно, в приёмке).

## Файлы проекта

| Файл / каталог | Назначение |
|---|---|
| `Kod.py` | Точка входа: DI-композиция `build_agent()` (+ mcp_enabled), REPL, `/mcp`-семейство, `--mcp-probe`, токен-учёт |
| `core/` | Ядро: `agent.py`, `llm_client.py`, `profile_router.py`, `prompt_builder.py`, `state_machine.py`, `invariants.py`, **`tools.py`** (модель инструментов), **`tool_registry.py`** (каталог), **`tool_policy.py`** (проверки вызова), **`tool_executor.py`** (исполнение + аудит) |
| `integrations/mcp/` | **MCP-слой**: config / transport (stdio + **HTTP**) / client / gateway / provider / demo_server |
| `memory/` | Модель памяти: `base.py`, 4 слоя, `manager.py` |
| `storage/` | Хранилище: `store.py` (фасад + MCP-методы), `db.py` (SQLite профилей) |
| `users/` | Рантайм-данные: профили, память задач, `integrations/mcp/{servers,catalog}.json` |
| `run.sh` / `run.desktop` | Запускающий скрипт (+x) и ярлык (пересоздать при переносе) |
| `Den_log.md` / `tokens.csv` | Журнал маршрутизации памяти; CSV-журнал токенов |
| `README.md` | Текстовая часть результата — модель памяти, персонализация, инварианты, переходы, **подключение MCP** |
| `Задание_d16.txt` / `Рекомендации_MCP_d16.txt` | Постановка куратора дня 16 + фундамент MCP-подсистемы недели (не изменяются) |
| `Задание_d17.txt` | Постановка куратора дня 17: подключить `get_time` и вызвать из приложения (не изменяется) |
| `arch_den_16.md` | Целевая архитектура проекта (актуализирована под день 20) |
| `dev/Проверка.md` | Чек-лист приёмки: 48 критериев дня 16 + строки 49–54 дня 17 |
| `dev/migr_plan.md` + `migr_plan_0..12.md` | План-эталон и рабочие планы миграции (Ревизия 5, этапы 0–12) |
| `dev/migr_log.md` | Журнал миграции: записи этапов 0–12 + «Итог Ревизии 5» |
| `dev/tests_debug/` | L2 (`unit_runner.py` + `unit/` — 17 модулей), L3 (`smoke.py`), L4 (`scenario.py` — 13 сценариев), гейт (`check_acceptance.sh` — 25 проверок), `scenario/scen_1.md`, `.tmp/` |
| `dev/logs_reports/` | `stages/` (в т.ч. `m9_live_run.md` — живой прогон), `errors/`, `archive/` |

## Общее с Днями 6–11 (перенесённые уроки)

- API: RouterAI (OpenAI-совместимый), ключ в `.env` (переменная `API_KEY`), модель
  `stepfun/step-3.5-flash` не менять;
- Retry при HTTP 429: до 3 повторов, задержка 2 → 4 → 8 сек; таймаут 30 сек; сбои →
  `None`, цикл чата не прерывается;
- Устойчивость: `sys.stdin/stdout.reconfigure(errors="replace")`, `try: import
  readline`, все пути через `BASE_DIR`;
- Токен-учёт: локальная оценка `~1 токен на 4 символа` с явной оговоркой, что
  авторитет — `usage` живого API; CSV-журнал стоимости;
- Зависимости: `requests`, `python-dotenv`, стандартная библиотека + **`mcp`**
  (Model Context Protocol Python SDK 2.2.0 — только для `integrations/mcp/`).

## Известные шероховатости и заделы

**Заделы по замыслу (программа следующих дней недели 4):**

- **`ToolMemoryPolicy`**: сырые ответы MCP никогда не пишутся в память автоматически
  (в Дне 16 — только нормализованные `external_actions` + аудит);
- **`ToolPromptPolicy` + блок `[external_context]`** (MCP resources): дозированная
  доставка описаний тулов под токен-бюджет (в Дне 16 — базовые лимиты `max_tools`/
  `max_schema_tokens`); сравнение токен-флоу MCP vs Skill + CLI — цель недели;
- **полный async core**:  — async gateway за синхронным фасадом `MCPGatewaySync` (меньше регрессионного риска);
- **параллелизм read-only тулов**; **local-провайдер** (`local.*` — только безопасные
  доменные операции, никогда `local.set_stage` / `local.write_task_state_file`);
- **расширение policy pipeline** (риск-уровни, подтверждения, `ToolPolicy` как
  полноценный движок) — в Дне 16 реализован минимальный набор ступеней;
- `PolicyEngine` в `memory/base.py` — пустой интерфейс-задел (рабочий слой
  инвариантов — отдельный модуль `core/invariants.py`);
- `parent_id` сообщений — задел ветвления диалога; `skills[]` — декларативный
  пайплайн (движок оркестрации — следующие дни); `transition_log` растёт без
  ограничения (сжатие — следующие дни).

**Расхождения spec/кода (на поведение не влияют):**

- `mcp` SDK импортируется в `transport.py` и `demo_server.py` (уровень транспорта),
  а не в `client.py`, как в плане M3: фактический API SDK 2.2.0 (`stdio_client` +
  `ClientSession`) живёт на уровне транспорта, клиент делегирует; инвариант «SDK
  только в `integrations/mcp/`» соблюдён;
- `handle_mcp_command` (`/mcp servers`, `/mcp connect`) читает приватное
  `gateway.gateway._servers` — допустимо для CLI-слоя, кандидат на публичный
  accessor дня 17+;
- смоуки этапов миграции (`m1_smoke.py` … `m6_smoke.py` в `dev/tests_debug/.tmp/`)
  — рабочие артефакты этапов M1–M6, вне дерева `arch_den_16.md` §3.1; оставлены как
  доказательства этапов (традиция den_15; решение зафиксировано в `dev/migr_log.md`).

**Косметика:**

- каталоги `dev/tests_debug/fixtures/` и `smoke/` созданы каркасом и остались пустыми;
  в `.tmp/` накапливаются каталоги прошлых прогонов (в `.gitignore`, не удаляются
  автоматически);
- `dev/meta_promt/` в этой копии пуст (метапромты и журналы дебага дней 13–14
  остались в `Nedela_3/den_13/`, `Nedela_3/den_14/`);
- изменения миграции не закоммичены (коммит — только по явной команде пользователя).

## Результат

- **Код, подключающийся к MCP и выводящий список доступных инструментов** — результат
  задания дня 16: `--mcp-probe` (one-shot, exit 0/1) и `/mcp tools` (REPL); соединение
  устанавливается (handshake `initialize` → `READY`), список корректно возвращается
  (`tools/list` → нормализация → каталог) — **на реальном сервере**
  `https://weatherapi.projecteol.ru/mcp/` (3 инструмента);
- **Инструмент задания дня 17 подключён и вызван из приложения** (п. 4.1): сервер
  задания `http://91.188.212.77:8000/mcp` (env `MCP_SERVER_URL`) в `DEFAULT_SERVERS`
  (сервер `time`); `get_time(timezone_name) -> ISO 8601` в каталоге
  (`mcp.time.get_time`); живой прогон «который час в Москве?» → LLM **сам** предлагает
  нативный `tool_call` `get_time({"timezone_name":"Europe/Moscow"})` → реальный вызов →
  **результат использован** в финальном ответе (п. 4.2): «В Москве сейчас 12:52»;
- **Настоящий вызов инструмента и полный LLM tool-use**: `tools/call` на живом сервере
  (`search_locations({"query":"Москва"})` → координаты Москвы; `get_time({"timezone_name":
  "Europe/Moscow"})` → `2026-09-27T12:52:07+03:00`); в REPL сообщение «найди город
  Москва» / «который час в Москве?» → LLM сам вызывает инструмент → ответ с результатом;
- **Не скрипт, а вертикальный срез подсистемы**: `MCPGateway` (адаптер, не контролёр)
  → `MCPToolProvider` (нормализация во внутреннюю `ToolDescriptor`) → `ToolRegistry`
  (каталог + атомарный snapshot + персистентность через `Store`) → `ToolExecutor`
  (policy + аудит) → LLM tool-use — фундамент всей MCP-работы недели 4;
- **Пять «кубиков» дней 11–15 без регрессии**: память, профили, инварианты, строгая
  машина состояний, LLM-клиент — контракты не тронуты; MCP выключен по умолчанию;
- **Инструмент ≠ переход**: `TaskStage` (8 стадий) не меняется от вызовов MCP;
  MCP-стадий нет; успех вызова не создаёт запись в `transition_log`;
- **Изоляция прав через тулинг**: `allowed_tools`/`denied_tools` в конфиге сервера;
  модель MCP не протекает в `core`; `MCPGateway` не знает о стадиях/профилях/памяти;
- **Деградация, не падение**: недоступный сервер → FAILED/DEGRADED, REPL жив;
- **Проверяемость**: L2 122 / L3 7 / L4 14 без живого ключа и сети, гейт 21/21,
  приёмка 54/54; живой прогон (реальный HTTP-сервер + реальный LLM) — 4 тула (1 `time`
  + 3 `weather`), вызов `search_locations` (координаты Москвы) и `get_time`
  («который час в Москве?» → «В Москве сейчас 12:52»);
- **Заделы с зарезервированными местами**: `ToolMemoryPolicy` (сырое — никогда в память),
  `ToolPromptPolicy`/resources, параллелизм read-only тулов, local-провайдер, полный
  async core, сравнение токен-флоу MCP vs Skill + CLI.

## Ручная проверка

Пошаговый чек-лист приёмки с отметками — в файле
[`dev/Проверка.md`](dev/Проверка.md): 40 критериев с конкретной командой проверки по
каждому (комплектность и сборка, четыре слоя памяти, иерархия хранилища, явная
маршрутизация, дозированная доставка, идентификация и интервью, задачи и переходы,
промт блоками, LLM за интерфейсом, state machine, resume, неизменяемые сообщения,
демонстрации, текстовое описание, уроки Дня 10, тесты без ключа, задел инвариантов,
расположение чек-листа,
+ строки 20–22: несколько профилей, миграция и обратная совместимость, роутер,
+ строки 23–25: формализованное состояние, пауза/продолжение, персистентность,
+ строки 26–30: инварианты — отдельное хранение, учёт в промте, отказ, конфликт,
изменение с подтверждением,
+ строки 31–35: контролируемые переходы — явный набор состояний, явная карта,
блокировка кодом, реакция ассистента, корректность продолжения после паузы,
+ **строки 36–40: подключение MCP** — SDK/демо-сервер, соединение устанавливается,
список корректно возвращается, список выводится кодом, регрессия MCP off,
+ **строки 41–48: реальное подключение и полный LLM tool-use** (Ревизия 2),
+ **строки 49–54: инструмент задания дня 17** — сервер `time` в конфиге, реальное
discovery `get_time`, реальный вызов `get_time`, LLM tool-use «который час в Москве?»
(4.1+4.2), аудит и «инструмент ≠ переход», регрессия MCP off).
Машиночитаемый дубль — `dev/tests_debug/check_acceptance.sh` (21 проверка, идемпотентен).
Сценарий живой демонстрации куратору — `dev/tests_debug/scenario/scen_1.md`.
