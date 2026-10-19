# AI_9 — AI-ассистент поддержки пользователей (День 33)

> AI_9 — персонализированный CLI stateful-агент (память → профили → инварианты →
> контролируемый жизненный цикл) с RAG-поиском по документации продукта и FAQ,
> MCP-подключением к CRM / JSON с пользователями и тикетами, веб-чатом для клиентов
> и AI-ассистентом поддержки, который отвечает на вопросы с учётом контекста пользователя
> и тикета.

---

## Содержание

- [Суть проекта](#суть-проекта)
- [Модель памяти](#модель-памяти)
- [Персонализация](#персонализация)
- [Инварианты и ограничения состояния](#инварианты-и-ограничения-состояния)
- [Контролируемые переходы состояний](#контролируемые-переходы-состояний)
- [Модульность и слои](#модульность-и-слои)
- [Архитектура](#архитектура)
- [Команды REPL](#команды-repl)
- [Запуск](#запуск)
- [Агентный цикл](#агентный-цикл)
- [Тестирование и приёмка](#тестирование-и-приёмка)
- [Служебное пространство `dev/` (проект про проект)](#служебное-пространство-dev-проект-про-проект)
- [Карта артефактов](#карта-артефактов)
- [Порядок достижения итогового состояния](#порядок-достижения-итогового-состояния)
- [Риски и откат](#риски-и-откат)
- [Известные шероховатости и заделы](#известные-шероховатости-и-заделы)
- [Результат](#результат)

---

## Суть проекта

CLI-агент (RouterAI, модель `stepfun/step-3.5-flash`) с **явной моделью памяти**,
**настраиваемой персонализацией**, **формализованным состоянием задачи**, **набором
неизменяемых правил (инвариантов)**, **контролируемым жизненным циклом задачи**,
**MCP-подключением к CRM / JSON с пользователями и тикетами**,
**RAG-модулем**, который индексирует документацию продукта и FAQ для ответов на вопросы
поддержки, и **веб-чатом** как удобным каналом для клиентов.

Память разделена на четыре физически отдельных слоя (краткосрочная / рабочая /
долговременная / профиль), запись идёт только явным вызовом `memory.remember(layer,
...)`, а набор слоёв, попадающих в промт, — параметр `deliver: set[str]`
(дозированная доставка). Поверх памяти — мультипрофильность с профиль-роутером,
затем строгая машина состояний (`TaskStage` — 8 стадий, `ALLOWED_TRANSITIONS`
whitelist, `try_transition` → `InvalidTransitionError`, журнал `transition_log`) и
слой инвариантов (`InvariantChecker` — «код запрещает, промт рекомендует»).

**День 33 — AI-ассистент поддержки пользователей**: разворачивается AI-first сервис
поддержки (типа собственной CRM). Ассистент отвечает на вопросы о продукте, использует
RAG (FAQ, документация продукта), учитывает контекст пользователя и тикета. Через MCP
подключается CRM или JSON с пользователями/тикетами. Клиентский канал — веб-чат с
сохранением контекста беседы.

RAG-модуль расширяется корпусом FAQ и документации продукта:
   → RagService (индексация FAQ + документация продукта → гибридный поиск → блок [rag] в промте → grounding)
      → PromptBuilder → LLM (ответ со ссылками [doc_id#chunk_id])

MCP-слой (CRM / JSON с пользователями и тикетами):
   → MCPGateway (соединение + handshake + tools/list + tools/call)
      → MCPToolProvider (нормализация mcp-тула → ToolDescriptor)
         → ToolRegistry (каталог + атомарный snapshot + персистентность через Store)
            → ToolExecutor (policy → вызов → аудит) → LLM tool-use (агент сам вызывает тул)

**Пайплайн AI-ассистента поддержки (День 33):**
   → Клиентский веб-чат (клиент создаёт тикет / задаёт вопрос)
      → Загрузка контекста пользователя и тикета через MCP (CRM / JSON)
         → RAG-поиск по FAQ и документации продукта для контекста
            → LLM-анализ: ответ с учётом контекста пользователя/тикета
               → Формирование ответа + обновление статуса тикета

Ключевые границы:

- **MCP — источник данных и инструментов, не слой контроля**: `MCPGateway` — адаптер
  («как технически вызвать CRM/JSON»), он не знает о стадиях, профилях и памяти;
  контроль остаётся за `StateMachine` (этапы), `InvariantChecker` (действия) и
  `ToolExecutor` (процедура вызова). Циклы `Agent → MCPGateway → StateMachine → Agent`
  запрещены.
- **Инструмент ≠ переход**: вызов (и даже успешное завершение) MCP-инструмента
  **никогда** не означает переход `TaskStage`; MCP-стадий нет и не будет.
- **Модель MCP не протекает в `core`**: `mcp` SDK импортируется только в
  `integrations/mcp/` (транспорт и демо-сервер); `ToolDescriptor` — внутренняя
  модель агента; имена квалифицируются (`mcp.<server>.<tool>`).
- **`rag/` и `core/` не импортируют друг друга** — связь только через DI-фасад
  `RagService` и готовый текст блока `[rag]`.
- **MCP выключен по умолчанию** (`mcp_enabled=False`); **RAG выключен по умолчанию**
  (`--rag`). Без флагов агент работает ровно как в предыдущей ревизии; прежние тесты и
  критерии приёмки проходят без MCP, без RAG и без сети.
- **Изоляция прав через тулинг**: `allowed_tools`/`denied_tools` в конфиге сервера —
  запрещённый тул не попадает в discovery (серверу даём только часть тулов).
- **Однонаправленные зависимости**: `Kod.py` → `core/` → `memory/` → `storage/`;
  `integrations/` и `rag/` — сбоку, подключаются только DI-композицией в `Kod.py`.

---

## Модель памяти

Память агента — это четыре разных «склада» для данных. Ниже — что каждый склад хранит,
где физически лежит и почему сделано именно так.

- **Краткосрочная память** (`ShortTermMemory`, область видимости — `session`).
  Что хранит: текущий диалог — сами сообщения, которые нельзя менять, у каждого есть
  свой `id` и ссылка `parent_id` на «родителя».
  Где лежит: `users/<id>/tasks/<task>/sessions/<sid>/session.json`.
  Почему так: сообщения — это история, её только добавляют в конец (append-only), нельзя
  переписывать; `parent_id` — заготовка на будущее для ветвления диалога.
- **Рабочая память** (`WorkingMemory`, область видимости — `task`).
  Что хранит: состояние задачи — `description`, `refs`, `lifecycle_summary`, `decisions`,
  `constraints`, `facts`, `open_questions`, `current_state`, **`goal`** (цель диалога),
  **`clarifications`** (уточнения), **`terms`** (термины вида `{термин: определение}`),
  **`ticket_context`** (контекст тикета: id, статус, история, данные пользователя).
  Где лежит: `users/<id>/tasks/<task>/working_memory.json`.
  Почему так: это **пересчитываемое состояние**, а не журнал сообщений — списки
  дополняются, скалярные поля перезаписываются, а `terms` сливаются (merge).
- **Долговременная память** (`LongTermMemory`, область видимости — `user`).
  Что хранит: `profile_ref` (только ССЫЛКА на профиль), `tasks[]` (со ссылками и
  `source_session`), `decisions[]` (каждая запись вида `{text, status}` — «выполнена» /
  «не выполнена»), `knowledge[]`.
  Где лежит: `users/<id>/long_term_memory.json`.
  Почему так: живёт между сессиями и задачами; профиль держится отдельно, здесь — только
  ссылка (канон куратора).
- **Профиль** (`Profile`, область видимости — `user`).
  Что хранит: **несколько профилей** на одного пользователя — `profile_id`, `name`,
  `domain`, `triggers[]`, `style` + `constraints` + `context`, `skills[]` (пайплайн).
  Где лежит: JSON в SQLite (таблица `profiles(user_id, profile_id)`), плюс «зеркала»
  в `users/<id>/profiles/<pid>.json`.
  Почему так: профили — отдельная сущность в базе, а не часть долговременной памяти;
  запись идёт слиянием (MERGE); активный профиль подключается к каждому запросу.

Единая точка входа в память — `MemoryManager`: `remember()` (запись с логом маршрута),
`recall()` (чтение выбранных слоёв), `build_blocks()` (текстовые блоки для промта в порядке
`LAYER_ORDER = profile → long_term → working → short_term`), `report()` (снимок для `/memory`).

> **Про «долговременная (профиль, решения, знания)» из задания.** Формулировка описывает
> *содержание* типа, а не одну файловую реализацию. Реализован предпочтительный по куратору
> вариант: профиль — отдельное хранилище (SQLite), в `long_term_memory.json` — ссылка.

### Иерархия хранения


users/<user_id>/
├── profile.json                 # зеркало профиля default (авторитет — SQLite profiles)
├── profiles/                    # зеркала всех профилей пользователя
│   ├── default.json
│   ├── chemist.json
│   └── economist.json
├── long_term_memory.json        # profile_ref + задачи + решения + знания
├── integrations/mcp/            # ветка MCP
│   ├── servers.json             # конфиг MCP-серверов (user-scope)
│   ├── catalog.json             # снимок каталога инструментов (version, tools, created_at)
│   └── scheduler/               # {jobs,observations,summaries}.json (планировщик, день 20)
└── tasks/<task_name>/
    ├── invariants.json          # ConstraintSet (неизменяемые правила задачи)
    ├── task_state.json          # снимок TaskState (+ transition_log)
    ├── working_memory.json      # пересчитываемое состояние задачи (+ current_state)
    ├── sessions_resume.md       # резюме сессий задачи (блок summary в промте)
    ├── tool_audit.jsonl         # история вызовов инструментов (task-scope)
    ├── review_log.jsonl         # история AI-ревью PR (task-scope, день 32)
    ├── ticket_context.json      # контекст тикета поддержки (день 33)
    ├── sessions/<session_id>/   # session_id = ГГГГММДД_ЧЧММСС
    │   └── session.json         # краткосрочная память: сообщения с parent_id


Разделение ответственности: `session.json` — неизменяемая история; `working_memory.json` —
пересчитываемое состояние памяти задачи; `task_state.json` — формализованное состояние
**жизненного цикла** (включая журнал переходов); `invariants.json` — **неизменяемые правила**;
`integrations/mcp/` — конфиг и каталог внешних инструментов; `tool_audit.jsonl` — история
вызовов (отдельно от `transition_log`); `review_log.jsonl` — история AI-ревью PR (день 32);
`ticket_context.json` — контекст тикета поддержки (день 33). **Очистка истории диалога не
сбрасывает состояние, не удаляет инварианты, не трогает журнал переходов, конфиг MCP и
журнал ревью.**

База профилей — `users/profiles.db` (общая для всех пользователей).
Все пути знает только `storage/store.py` (`safe_name`, `ensure_user/task/session`,
`read_json`/`write_json` с каноническими дефолтами, `task_state_path`/`read_task_state`/
`write_task_state` с миграцией `"execution"` → `implementation`,
`invariants_path`/`read/write_invariants`, `mcp_servers_path`/`read/write_mcp_servers`,
`tool_catalog_path`/`read/save_tool_catalog`, `append_tool_audit`/`load_tool_audit`,
`ticket_context_path`/`read/write_ticket_context`).
Битый или отсутствующий файл не роняет приложение — чтение всегда возвращает схему по
умолчанию (`read_*` → `None` при отсутствии/битости, дефолтизация у вызывающего);
при недоступной БД `load_profile`/`list_profiles` откатываются на зеркала `profiles/` →
`profile.json`.

### Сборка промта (явные блоки + дозированная доставка + бюджет)


[system: роль] → [system: profile] → [system: invariants] → [system: tools, опц.] →
[system: long_term] → [system: working] → [system: summary, опц.] →
[messages: short_term (окно 10)] → [user: текущий запрос] → [резерв под ответ]


- `BLOCK_ORDER = ("role", "profile", "invariants", "tools", "long_term", "working",
  "summary", "short_term", "current")`; блок `[rag]` вставляется после `[tools]`, до
  `[long_term]` (см. ниже);
- доставляемое подмножество блоков задаётся каноническим набором
  `DELIVERABLE = ("profile", "invariants", "tools", "long_term", "working", "summary",
  "short_term")` из `core/prompt_builder.py` (`role`/`current` — всегда, неуправляемы);
  `--deliver`/`/deliver` пересекаются с `DELIVERABLE`, поэтому `summary` достижим из CLI
  (`--deliver profile,summary`);
- слои добавляются system-блоками с заголовком `[<имя>]` **только если имя есть в `deliver`**;
- `short_term` идёт отдельными сообщениями `{role, content}`, а не склеенным текстом;
- бюджет: необязательный блок пропускается, если `used + tokens > budget`; роль и запрос не
  урезаются никогда; бюджет передаётся в рабочем пути (`Agent.prompt_budget` ← флаг
  `--budget`, по умолчанию `None` — обрезание выключено);
- блок `[tools]` — каталог инструментов (`render_tools` под лимитами `ToolPromptPolicy`:
  `max_tools`/`max_schema_tokens`); блок `[rag]` — найденные источники со ссылками
  `[doc_id#chunk_id]` (усекается первым при нехватке бюджета);
- блок `[external_context]` (MCP resources) и дозированная доставка описаний тулов —
  **задел** следующих дней.

---

## Персонализация

Поверх модели памяти — **несколько профилей на пользователя**. Профиль — «призма» под
домен/задачу: он определяет стиль, ограничения, контекст, доменную область и порядок
скиллов. Активный профиль привязан к сессии и входит в каждый промт, поэтому один и
тот же запрос даёт разные ответы.

### Модель профиля (расширение JSON, обратно совместимое)


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
- **профиль MCP менять не может**: изменение профиля — только явная механика профилей;
  задел `tool_policy` в профиле (`allow`/`deny`) — только **сужение** прав, никогда
  расширение глобального запрета.

### Профиль-роутер (`core/profile_router.py`)

Общий профиль-роутер выбирает конкретный профиль по тексту запроса — детерминированно, без LLM:
**+2** за вхождение каждого триггера (регистронезависимо), **+1** за вхождение `domain`;
победитель = максимум (>0); ничья или ноль → `None` (остаёмся на текущем/дефолтном). Решение
логируется («[Роутер] запрос → профиль chemist (счёт 5)»), разбор по каждому кандидату показывает
`/profile route <текст>`. Режим `/profile auto on` запускает роутер на каждый запрос **до** сборки
промта.

---

## Инварианты и ограничения состояния

Слой **неизменяемых правил** поверх памяти, персонализации и автомата: агент не имеет
права нарушать заданные инварианты. Главная идея: **инвариант — условие, которое должно
сохраняться во всех допустимых состояниях; переход, нарушающий его, должен быть запрещён**.
Недостаточно добавить правила в системный промт — перед выполнением действия запускается
**отдельная Python-проверка** («код запрещает, промт рекомендует»).

- `Invariant` — одно правило: `id`, `description`, `category`, `severity`, `active`.
- `ConstraintSet` — набор правил, **отдельная сущность** (это не память, не профиль и
  не диалог).
- `ProposedAction` — предлагаемое действие (`technology`, `adds_dependency`,
  `changes_database_schema`, `language`; расширен MCP-полями `action_type`, `tool_name`,
  `arguments`).
- `InvariantChecker` (абстрактный) — интерфейс проверки: метод `check()` для блокирующих
  правил и `warnings()` для правил с `severity="warning"`.
- `RuleBasedChecker` — детерминированная реализация: правила разбираются по id-неймспейсу,
  без вызовов LLM.
- `update_invariant` — изменение правила только авторизованной операцией (`authorized=True`).

Хранение — `users/<id>/tasks/<task>/invariants.json`, **отдельно от диалога**; очистка истории
не удаляет набор. Блок `[system: invariants]` входит в промт (после профиля, до рабочей
памяти) и участвует в дозированной доставке. При нарушении инструмент **не вызывается**, а
пользователю выдаётся отказ: (1) какое действие, (2) какой инвариант нарушен, (3) почему
обязателен, (4) допустимая альтернатива. Изменение правила — `/invariant set <id> <текст>
--yes` (без `--yes` — `PermissionError`).

**Правило `tool.deny.<qualified>`** запрещает конкретный инструмент; одно правило «нельзя
менять схему БД» работает для локальной функции, MCP-инструмента и действия, предложенного
LLM.

**Переходы и инварианты — разные сущности контроля**: `state_machine` проверяет переходы
(этапы), `InvariantChecker` — действия; разные модели, разные проверки, разные отказы.

---

## Контролируемые переходы состояний

**Жизненный цикл задачи — строгая машина состояний**. Чёткий список
допустимых состояний и разрешённых переходов между ними; ассистент **физически не может
«перепрыгнуть» этап** — запрет работает на уровне кода, а не только текста.

### Модель состояний (`TaskStage` — 8)

python
class TaskStage(Enum):
    NEW = "new"                      # задача создана, но ещё не начата
    PLANNING = "planning"            # план строится/построен, не утверждён
    PLAN_APPROVED = "plan_approved"  # план утверждён пользователем (/approve)
    IMPLEMENTATION = "implementation"  # идёт реализация (бывший execution)
    VALIDATION = "validation"        # проверка/тестирование
    DONE = "done"                    # задача завершена (терминальная)
    PAUSED = "paused"                # пауза (возврат в previous_stage)
    FAILED = "failed"                # ошибка (восстановление — /task retry)


### Карта переходов (whitelist)

python
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


Запреты задания реализуются **отсутствием дуги в графе** (не `if`-ами): «нельзя делать
реализацию до утверждённого плана» — нет дуг `new → implementation` и
`planning → implementation`; «нельзя делать финал без валидации» — единственный путь в
`done` через `validation`; пауза — не лазейка (из `paused` только `resume_task()` →
`previous_stage`).

### API контроля

python
can_transition(from_state, to_state) -> bool   # единственный источник истины — карта

try_transition(state, proposed) -> TaskState    # единственная точка смены этапа:
    # недопустимый → InvalidTransitionError, состояние НЕ меняется,
    # попытка пишется в transition_log (allowed=False);
    # допустимый → меняет stage + запись (allowed=True)


Поток: `/plan <цель>` строит план и **останавливается** в `planning` (утверждение —
контрольный пункт человека); `/approve` — единственный переход в `plan_approved`;
`/run` из `planning` не может перепрыгнуть утверждение. Отказ называет правило
(`REFUSAL_RULES` — детерминированные тексты, без LLM) и корректный следующий шаг;
каждая попытка (успех и отказ) фиксируется в `transition_log` и переживает перезапуск.

**MCP и RAG эту машину не трогают**: успех вызова инструмента не создаёт запись в
`transition_log`; `MCPGateway`/`ToolRegistry`/`RagService` не вызывают `StateMachine`
(проверяется тестами «MCP не трогает состояние» и «TaskStage не затронут»).

---

## Модульность и слои

Направление зависимостей однонаправленное: `Kod.py` → `core/` → `memory/` → `storage/`;
`integrations/` и `rag/` — сбоку, подключаются только DI-композицией в `Kod.py`.
`mcp` SDK импортируется только в `integrations/mcp/`; `core`/`memory`/`storage` его не
импортируют никогда. **`rag/` не импортирует `core/`, а `core/` не импортирует `rag/`** —
связь через DI-фасад `RagService` и готовый текст блока `[rag]`. Слои памяти и ядро ФС
напрямую не трогают — только через фасад `Store`.

**Хранилище** (`storage/`) — прежний фасад `Store` + ветка `integrations/mcp/`:
`servers.json` (какие серверы, транспорт, таймауты, allowed/denied_tools), `catalog.json`
(снимок каталога: schema_version, version, tools, created_at), `tasks/<task>/tool_audit.jsonl`
(история вызовов, task-scope, отдельно от `transition_log`). Механика устойчивости —
битый/отсутствующий файл → схема по умолчанию, не падение. Gateway JSON напрямую не пишет —
только через фасад `Store`.

**Память** (`memory/`) — 4 слоя, MERGE/append только через `MemoryManager`, дозированная
доставка + токен-бюджет. MCP-политика памяти — задел: сырой ответ → только текущий execution
context; краткое резюме → short_term; нормализованный итог → working (`external_actions[]`);
важный факт → long_term только по политике; секреты — никогда; профиль MCP менять не может.

**Ядро** (`core/`) — прежние сущности без регрессии + инструменты:
`tools.py` (контракты), `tool_registry.py` (каталог + атомарный snapshot),
`tool_policy.py` (проверки вызова), `tool_executor.py` (исполнение + аудит),
`tool_routing.py` (детерминированный выбор инструмента), `tool_pipeline.py` (пайплайн);
расширения `llm_client.py` (tool-use), `prompt_builder.py` (блоки `[tools]`/`[rag]`),
`agent.py` (агентный цикл, RAG-слой), `invariants.py` (MCP-поля `ProposedAction`).

**Интеграции** (`integrations/`) — новый слой: `mcp/` (config, transport, client, gateway,
provider, demo_server, scheduler_server, pipeline_server, time_server, auth) и `scheduler/`
(models, store, runner, aggregator — ядро планировщика на stdlib). SDK импортируется только здесь.

**RAG** (`rag/`) — расширяемый RAG-модуль: индексация корпуса FAQ и документации продукта,
гибридный поиск, блок `[rag]` в промте, источники/цитаты и проверка опоры ответа.
Сеть — исключительно `127.0.0.1:11434` (Ollama).

**CLI** (`Kod.py`) — DI с `mcp_enabled=False` по умолчанию; семейство `/mcp` и `/rag`;
флаги `--mcp`, `--mcp-probe`, `--scheduler*`, `--rag*`, `--no-tools-block`. REPL
синхронный (async — внутри gateway).

**Служебное** (`dev/`) — «проект про проект»: план-эталон → рабочие планы этапов
(конец этапа — гейт в следующий) → журнал; красный гейт → карточка ошибки.

---

## Архитектура

### Дерево модулей


AI_9/
├── Kod.py                       # точка входа: DI-композиция (+ mcp_enabled, RagService) + REPL
├── serve.py                     # фасад: HTTP-вход агента (Flask, 127.0.0.1:8090)
├── models.json                  # реестр моделей и профилей (Ревизия 8)
├── gateway/                     # веб-шлюз на VPS (Flask)
│   ├── app.py                   # вход/регистрация/интервью/чат, лимиты, прокси на фасад
│   ├── config.py                # конфиг шлюза (gateway.json + env-секрет)
│   ├── questions.py             # снапшот вопросов интервью (сверка отпечатка)
│   ├── sync_questions.py        # обновление questions.json из канона
│   ├── users.py                 # регистрация/вход (пароли только хэшами)
│   └── templates/               # login/register/interview/chat.html
├── core/                        # ядро агентности
│   ├── agent.py                 # оркестратор: + mcp_gateway/tool_registry/tool_executor/tool_policy
│   │                            #   (None при MCP off) + агентный tool-use цикл (_respond_with_tools)
│   │                            #   + ленивый RAG-слой (check_grounding, _grounding_guard)
│   ├── llm_client.py            # LLMClient (ABC) + RouterAIClient + MockClient + LLMReply +
│   │                            #   complete_with_tools (нативный tool-use + fallback-протокол)
│   ├── profile_router.py        # ProfileRouter — детерминированный выбор профиля
│   ├── prompt_builder.py        # BLOCK_ORDER + DELIVERABLE + budget + блоки [tools], [rag]
│   ├── state_machine.py         # строгая машина состояний (MCP/RAG её не трогают)
│   ├── invariants.py            # Invariant + ConstraintSet + InvariantChecker + ProposedAction
│   │                            #   (MCP-поля action_type/tool_name/arguments; правило tool.deny.*)
│   ├── model_registry.py        # ModelRegistry + ModelSpec: реестр моделей (Ревизия 8)
│   ├── resources.py             # замеры ресурсов хоста (Ревизия 8)
│   ├── subagents.py             # SubagentRunner: дочерние CLI-сессии (Ревизия 8)
│   ├── tools.py                 # внутренняя модель инструментов: ToolDescriptor + ToolCallRequest +
│   │                            #   ToolExecutionResult + ToolExecutionState + ToolProvider (ABC) +
│   │                            #   ToolCatalogSnapshot (контракты без MCP SDK и без сети)
│   ├── tool_registry.py         # ToolRegistry — каталог всех источников: add_provider/
│   │                            #   unregister_provider/get/available_for/snapshot/refresh
│   ├── tool_policy.py           # ToolPolicy — проверки вызова (enabled/схема/стадия/
│   │                            #   инварианты/подтверждение) → PolicyDecision
│   ├── tool_executor.py         # ToolExecutor — policy → gateway.call_tool → результат →
│   │                            #   аудит tool_audit.jsonl (StateMachine не вызывает)
│   ├── tool_routing.py          # rank_tools — детерминированный выбор инструмента (RU→EN)
│   └── tool_pipeline.py         # PipelineStep/Pipeline/run_pipeline — пайплайн из инструментов
├── integrations/                # слой внешних интеграций (MCP + планировщик)
│   ├── mcp/
│   │   ├── config.py            # MCPServerConfig (server_id, transport, command/endpoint, enabled,
│   │   │                        #   trust_level, allowed/denied_tools, timeout, max_result_bytes)
│   │   │                        #   + load_servers_config (дефолты: time + weather + scheduler +
│   │   │                        #   pipeline + demo; битый файл не роняет)
│   │   ├── auth.py              # серверная проверка токена MCP-серверов (Bearer, env)
│   │   ├── time_server.py       # MCP-сервер времени (HTTP :8000)
│   │   ├── transport.py         # MCPTransport (ABC: initialize / list_tools / call_tool / close)
│   │   │                        #   + StdioMCPTransport + HttpMCPTransport + FakeMCPTransport
│   │   ├── client.py            # MCPClient: initialize / list_tools / call_tool
│   │   ├── gateway.py           # MCPGateway: start/stop/connection_state, discover(), call_tool();
│   │   │                        #   MCPGatewaySync — синхронный фасад (постоянная фоновая задача)
│   │   ├── provider.py          # MCPToolProvider: discover() + нормализация → ToolDescriptor
│   │   ├── demo_server.py       # локальный stdio MCP-сервер (get_time, echo, weather_stub)
│   │   ├── scheduler_server.py  # MCP-сервер планировщика (HTTP :8010)
│   │   ├── pipeline_server.py   # MCP-сервер пайплайна (search/summarize/saveToFile, HTTP :8020)
│   │   └── crm_server.py        # MCP-сервер CRM/тикетов (HTTP :8030, день 33)
│   └── scheduler/               # ядро планировщика (stdlib): models/store/runner/aggregator
├── memory/                      # 4 слоя + MemoryManager (ToolMemoryPolicy — задел)
├── rag/                         # RAG-модуль (индексация FAQ + документации продукта + гибридный поиск)
│   ├── config.py / config.json  # RagConfig (+ валидация: эмбеддинги только 127.0.0.1:11434)
│   ├── types.py / text.py       # Chunk/DocMeta/Hit/Source/Quote/Answer ; нормализация/токенизация
│   ├── corpus.py / chunking.py  # сбор корпуса (FAQ + документация продукта), sha1/mtime
│   ├── embedding.py             # OllamaEmbedder (bge-m3, dim 1024) + HashingEmbedder (фолбэк)
│   ├── index.py                 # плоский индекс: BM25-постинги + векторы; save/load/version
│   ├── retrieval.py / rerank.py # bm25 | dense | hybrid (RRF + MMR) + порог; LexicalReranker
│   ├── rewrite.py               # query rewrite (снятие шума + термины из истории)
│   ├── cache.py                 # SearchCache — LRU+TTL, инвалидация по mtime
│   ├── grounding.py / eval.py / compare.py  # опора ответа; метрики; сравнение режимов
│   ├── sources.py / citations.py # источники (source+section/chunk_id) и дословные цитаты
│   ├── verify.py                # проверка формата ответа (источники/цитаты/смысл) на 10 вопросах
│   ├── service.py               # RagService — фасад для Kod.py/Agent
│   ├── datasets/                # corpus.list (FAQ + документация) + queries.jsonl
│   └── index/                   # рантайм-индекс (в .gitignore): chunks/postings/vectors/meta
├── storage/
│   ├── store.py                 # фасад: + mcp_servers/catalog + tool_audit + ticket_context
│   └── db.py                    # ProfileRepository (без изменений)
├── users/                       # рантайм-хранилище (создаётся при работе)
│   └── <id>/integrations/mcp/   # servers.json + catalog.json + scheduler/
├── ND/                          # справочные материалы (не код)
│   ├── models/                  # справки по моделям: <model>_params.md
│   ├── other/                   # прочие заметки (1.txt, 2.txt, tunel_plan.md)
│   └── tasks/                   # задания куратора по неделям (n_1 … n_7)
├── project/                     # документация проекта (RAG-корпус)
│   ├── README.md                # основной README проекта
│   ├── docs/                    # дополнительная документация
│   │   ├── architecture.md      # архитектура системы
│   │   ├── api.md               # API-описания
│   │   └── data_schemas.md      # схемы данных
│   └── code/                    # исходный код (для индексации)
├── faq/                         # FAQ по продукту (день 33)
├── .github/                     # CI/CD (день 32)
│   └── workflows/               # GitHub Actions
│       └── ai-review.yml        # пайплайн AI-ревью кода на PR (день 32)
├── run.sh / run.desktop         # запуск (+x / пересоздать при переносе)
├── README.md                    # этот файл — единый источник данных о проекте
├── agents.md                    # краткая памятка агенту (20 строк)
├── Den_log.md                   # журнал (рантайм-артефакт)
├── tokens.csv                   # CSV-журнал токенов (рантайм-артефакт)
└── dev/                         # служебное пространство (см. раздел)


### Внутренняя модель инструментов (`core/tools.py` — контракты без MCP)

Модель MCP не должна протекать в `core`. `ToolDescriptor` — внутренняя модель агента;
поля `allowed_stages` / `requires_confirmation` / `risk_level` заполняются дефолтами
(`allowed_stages` — все рабочие стадии, `requires_confirmation=False`,
`risk_level="unknown"`) и **используются** `ToolPolicy` при проверке вызова.

python
# core/tools.py
@dataclass(frozen=True)
class ToolDescriptor:
    name: str                    # квалифицированное: "mcp.git.get_branch" | "mcp.crm.get_ticket"
    description: str
    input_schema: dict
    source: str                  # "local" | "mcp"
    provider: str                # server_id (mcp) | "local"
    original_name: str           # имя тула на сервере ("get_ticket")
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


### `ToolRegistry` — каталогизация (`core/tool_registry.py`)

python
class ToolRegistry:
    def add_provider(self, provider: ToolProvider) -> None: ...     # повторный id → замена с логом
    def unregister_provider(self, provider_id: str) -> None: ...
    def get(self, name: str) -> ToolDescriptor: ...                 # KeyError + понятное сообщение
    def available_for(self, context) -> list[ToolDescriptor]: ...   # задел: фильтры policy
    def snapshot(self) -> ToolCatalogSnapshot: ...                  # текущий, без пересборки
    def refresh(self) -> ToolCatalogSnapshot:
        # discover() у всех провайдеров → валидация схем (JSON Schema-примитивы) →
        # разрешение коллизий имён (квалифицированные имена) →
        # build_and_validate_snapshot() → атомарный swap self._current_snapshot


Правила:

- реестр **не проверяет бизнес-правила** и **не вызывает** `StateMachine` — он только
  каталогизирует;
- обновление — только полным snapshot (никогда «по одному инструменту»): один запрос
  модели никогда не видит «половину старого и половину нового» каталога;
- недоступный провайдер при `refresh()` → его тулы **исключаются** из нового snapshot
  (каталог честен: нет соединения — нет тулов), ошибка логируется, остальные не страдают;
- `version` — монотонный счётчик; `created_at` — время сборки.

### MCP-слой (`integrations/mcp/`)

**Конфиг** (`config.py`) — `MCPServerConfig` (server_id, transport, command, endpoint,
enabled, trust_level, allowed_tools/denied_tools, timeout_seconds, max_result_bytes,
headers/token_env) + загрузка `users/<id>/integrations/mcp/servers.json`; битый или
отсутствующий файл → `DEFAULT_SERVERS` (приложение не падает):

- **сервер git** `git` (`transport="stdio"`, команда `git`, `enabled=true`, инструменты
  `get_branch`, `list_files`, `get_diff`) — **первым**;
- **сервер задания** `time` (`transport="http"`, endpoint из env `MCP_SERVER_URL`, дефолт
  `http://91.188.212.77:8000/mcp`, `enabled=true`, инструмент `get_time`) — **вторым**;
- **реальный погодный HTTP-сервер** `weather` (endpoint из env `MCP_WEATHER_URL`, дефолт
  `https://weatherapi.projecteol.ru/mcp/`, `enabled=true`);
- **сервер CRM/тикетов** `crm` (`transport="http"`, endpoint из env `CRM_MCP_URL`, дефолт
  `http://127.0.0.1:8030/mcp`, `enabled=true`, инструменты `get_ticket`, `update_ticket`,
  `list_tickets`, `get_user`) — **четвёртым** (день 33);
- `scheduler` (`:8010`, env `SCHEDULER_MCP_URL`) и `pipeline` (`:8020`, env
  `PIPELINE_MCP_URL`) — включаются флагами `SCHEDULER_MCP_ENABLED`/`PIPELINE_MCP_ENABLED`
  (по умолчанию `False`);
- демо-сервер `demo` (stdio, `enabled=false` — для детерминированных тестов).

**Транспорт** (`transport.py`) — `MCPTransport` (ABC: `initialize` / `list_tools` /
`call_tool` / `close`) + `StdioMCPTransport` (обёртка над `mcp` SDK: ленивый импорт SDK,
stdio-подпроцесс, timeout) + **`HttpMCPTransport`** (Streamable HTTP:
`mcp.client.streamable_http.streamable_http_client`, SDK 2.2.0) + `FakeMCPTransport`
(детерминированная заглушка: фиксированный список тулов, программируемые
`fail_initialize`/`fail_list_tools`/`fail_call`/`error_call`/`timeout` + `set_tools`/
`set_tool_result`). Фабрика `make_transport(server)` выбирает транспорт по полю
`transport`. Единый хелпер `_tool_schema` читает схему из `input_schema` (snake_case SDK
2.2.0) с fallback на `inputSchema`/dict. Таймауты — `asyncio.wait_for`.

**Клиент** (`client.py`) — `MCPClient`: транспорт инжектится, SDK напрямую не импортирует;
`initialize()` (handshake: protocol version, capabilities), `list_tools()` →
нормализованные сырые описания `{name, description, inputSchema}`, **`call_tool()`** →
`{isError, text, raw}`; любой сбой → `MCPConnectionError` (gateway переводит в
`MCPConnectionState.FAILED`), не `None` и не молчание.

**Шлюз** (`gateway.py`) — `MCPGateway`:

python
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
        # тулинг: серверу даём только часть тулов)
    async def call_tool(self, provider, tool_name, arguments, execution_id="") -> ToolExecutionResult
        # вызов инструмента на сервере provider; сервер не READY → failed-результат (не исключение)


Синхронный фасад для REPL: `MCPGatewaySync` — **постоянная фоновая задача** в
daemon-потоке (все операции исполняются в одной долгоживущей задаче: HTTP/stdio-контексты
`mcp` SDK держат anyio cancel scope, который обязан войти и выйти в одной задаче) —
REPL и `--mcp-probe` остаются синхронными. Повторный `start()` идемпотентен.

**Провайдер** (`provider.py`) — `MCPToolProvider(ToolProvider)`: `provider_id() =
"mcp"`, `discover()` → gateway.discover() → тулы с `source="mcp"`,
`provider=server_id`, `name=f"mcp.{server_id}.{original_name}"`.

**Демо-сервер** (`demo_server.py`) — минимальный локальный MCP-сервер на `mcp` SDK
(stdio), 3 тула: `get_time`, `echo`, `weather_stub`. Запуск:
`python -m integrations.mcp.demo_server`.

**CRM-сервер** (`crm_server.py`) — MCP-сервер для CRM/тикетов (HTTP :8030, день 33):
инструменты `get_ticket` (получить тикет по id), `update_ticket` (обновить статус),
`list_tickets` (список тикетов пользователя), `get_user` (получить данные пользователя).
Запуск: `python -m integrations.mcp.crm_server`.

Механика discovery в `MCPGateway.discover()`: `list_tools` у каждого сервера в READY →
**фильтр прав** (`denied_tools` исключает всегда; непустой `allowed_tools` сужает) →
нормализация в `ToolDescriptor`. Сервер в FAILED → тулов нет; overall-статус: все READY
→ `ready`, есть READY + другие → `degraded`, иначе `failed`, все DISCONNECTED →
`disconnected`.

**Деградация, не падение**: MCP-сервер недоступен → `MCPConnectionState.FAILED`, тулы
исключены, но REPL жив — память, профили и машина состояний продолжают работать.

### Внутренняя механика вызова и LLM tool-use

- **`tools/call`**: `MCPTransport.call_tool` → `MCPClient.call_tool` →
  `MCPGateway.call_tool(provider, tool, arguments)` → `ToolExecutionResult`
  (нормализация `CallToolResult`: `isError`, текстовые части `content`).
- **`ToolExecutor`** (`core/tool_executor.py`) — единственная точка исполнения:
  `ToolPolicy` (enabled → схема аргументов → стадия → инварианты → подтверждение) →
  `gateway.call_tool` → результат → **аудит** `tool_audit.jsonl` (execution_id, tool,
  status, phase, `arguments_hash` — только отпечаток, не сырые аргументы). **Не**
  вызывает `StateMachine` (инструмент ≠ переход).
- **`ToolPolicy.check`** (`core/tool_policy.py`): ступени enabled → схема аргументов →
  стадия (`allowed_stages`) → инварианты (`InvariantChecker` поверх `ProposedAction`) →
  `requires_confirmation`; итог `PolicyDecision(allowed, reason, needs_confirmation)`.
- **LLM tool-use**: `LLMClient.complete_with_tools` (нативный OpenAI-совместимый
  `tools`/`tool_calls` + детерминированный fallback-JSON-протокол); блок `[tools]` в
  промте (`ToolPromptPolicy`: `max_tools`/`max_schema_tokens`); агентный цикл
  `Agent._respond_with_tools`: LLM → tool call → `ToolExecutor` → tool-сообщение → LLM
  → финальный ответ (лимит `max_tool_iterations`). Нормализованные вызовы пишутся в
  рабочую память (`external_actions`); **сырой** ответ — только текущий контекст, никогда
  в память.
- **`rank_tools`** (`core/tool_routing.py`) — детерминированный выбор инструмента
  (RU→EN-эвристика, без SDK/сети); `/mcp route <текст>` печатает кандидата с обоснованием.
- **Ручной вызов**: `/mcp call <tool> [{json}]` — прямой вызов через `ToolExecutor`.

### Хранение (`Store` — методы фасада)


users/<user_id>/
└── integrations/mcp/
    ├── servers.json            # конфиг серверов (user-scope)
    └── catalog.json            # снимок ToolCatalogSnapshot (version, tools, created_at)


- `Store.mcp_servers_path/read_mcp_servers/write_mcp_servers` — отсутствующий/битый файл
  → `None` (дефолтизация у вызывающего: `load_servers_config` → `[DEFAULT_SERVERS]`);
- `Store.tool_catalog_path/read_tool_catalog/save_tool_catalog` — `read_tool_catalog` при
  отсутствии/битости → `None` (дефолт: пустой каталог `{"schema_version": 1, "version": 0,
  "tools": [], "created_at": null}`); каталог пересохраняется после каждого успешного
  `refresh()` и переживает перезапуск;
- `users/<id>/tasks/<task>/tool_audit.jsonl` (`append_tool_audit` / `load_tool_audit`,
  append-only, битые строки пропускаются) — история вызовов, **отдельно** от
  `transition_log`;
- `users/<id>/tasks/<task>/review_log.jsonl` (`append_review_log` / `load_review_log`,
  append-only, битые строки пропускаются) — история AI-ревью PR (день 32), **отдельно**
  от `tool_audit.jsonl` и `transition_log`;
- `users/<id>/tasks/<task>/ticket_context.json` (`read/write_ticket_context`) — контекст
  тикета поддержки (id, статус, история, данные пользователя), **отдельно** от диалога;
- `MCPGateway` JSON напрямую не пишет — только через `Store`.

### DI-композиция и CLI

python
mcp_enabled = False   # по умолчанию; включается флагом --mcp

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
# без флага: agent.mcp_gateway/tool_registry/tool_executor is None — поведение = предыдущая ревизия
# local-провайдер в AI_9 не регистрируется (задел: local.* — только безопасные
# доменные операции, никогда local.set_stage / local.write_task_state_file)

# RAG (--rag): RagService собирается в Kod.py и передаётся агенту; без --rag rag/ не импортируется


Семейство `/mcp` (команды дня 31):

- `/mcp status` — общее состояние подключения + по серверам + версия каталога и число тулов;
- `/mcp servers` — сконфигурированные серверы (transport, enabled, trust, allowed/denied);
- `/mcp tools` — **список доступных инструментов** (имя, description, input-схема);
- `/mcp refresh` — re-discovery → registry.refresh() (атомарный swap) → сейв catalog.json;
- `/mcp connect <id>` — поднять соединение (по умолчанию — все из servers.json); `<id>` — только целевой;
- `/mcp call <tool> [{json}]` — вызвать инструмент вручную через `ToolExecutor` (policy → вызов → аудит);
- `/mcp disconnect` — закрыть соединения (`gateway.stop()` → DISCONNECTED; тулы покидают каталог при refresh);
- `/mcp route <текст>` — объяснить выбор инструмента/сервера (без вызова).

Флаг `--mcp-probe` — **результат задания в one-shot форме**: подключиться → handshake →
`tools/list` → вывести список инструментов (имя, описание, схема) → корректно закрыться →
exit 0; при недоступном сервере — понятная ошибка, exit 1.

text
$ python Kod.py --mcp-probe
[MCP] Подключение к серверам: git, time, weather, crm
[MCP] Соединение установлено (READY). Список доступных инструментов:

  mcp.git.get_branch
    description: Получает текущую git-ветку репозитория
    input_schema: {"type": "object", "properties": {}}
  mcp.git.list_files
    description: Выводит список файлов в репозитории
    input_schema: {"type": "object", "properties": {"path": {"type": "string"}}}
  mcp.git.get_diff
    description: Показывает diff изменений
    input_schema: {"type": "object", "properties": {"path": {"type": "string"}}}
  mcp.crm.get_ticket
    description: Получает данные тикета поддержки по ID
    input_schema: {"type": "object", "properties": {"ticket_id": {"type": "string"}}}
  mcp.crm.update_ticket
    description: Обновляет статус тикета
    input_schema: {"type": "object", "properties": {"ticket_id": {"type": "string"}, "status": {"type": "string"}}}
  mcp.crm.list_tickets
    description: Список тикетов пользователя
    input_schema: {"type": "object", "properties": {"user_id": {"type": "string"}}}
  mcp.crm.get_user
    description: Получает данные пользователя
    input_schema: {"type": "object", "properties": {"user_id": {"type": "string"}}}
  mcp.time.get_time
    ...
[MCP] Всего инструментов: 7
[MCP] Соединение закрыто (DISCONNECTED).


Без `--mcp`/`/mcp` — MCP-слой не собирается, агент работает ровно как в предыдущей ревизии
(регрессия запрещена).

### RAG-слой (`rag/`)

Расширяемый RAG-модуль: индексация корпуса FAQ и документации продукта, гибридный поиск,
блок `[rag]` в промпте со ссылками, источники/цитаты и проверка опоры ответа (grounding).

**Корпус FAQ и документации продукта:**

- **README.md** — основной README проекта (этот файл);
- **project/docs/** — дополнительная документация:
  - `architecture.md` — архитектура системы;
  - `api.md` — API-описания;
  - `data_schemas.md` — схемы данных;
- **FAQ** — часто задаваемые вопросы по продукту (файлы в `project/faq/`);
- **документация продукта** — руководства пользователя, инструкции, справочные материалы;
- **код** — исходные файлы `core/`, `memory/`, `storage/`, `integrations/`, `rag/`;
- **схемы данных** — описания моделей и структур данных.

**Конвейер:**


corpus (README, project/docs/, project/faq/, документация продукта, код) → chunking (fixed | structural)
  → embedding (Ollama bge-m3, локально) → index (BM25 + dense, плоский)
  → rewrite (query rewrite: снятие шума + термины из истории)
  → retrieval (BM25 ⊕ dense → RRF → реранк → MMR → порог отсечения)
  → блок [rag] в промпте → ответ со ссылками [doc_id#chunk_id]
  → sources (source + section/chunk_id) + quotes (дословные цитаты из чанков)
  → grounding (ответ обязан опираться на найденное; режим «не знаю» при слабом контексте)


**Границы модуля:**

- только stdlib; **сеть — исключительно `127.0.0.1:11434`** (Ollama) — валидация в
  `RagConfig.validate`; при недоступности Ollama — деградация на `HashingEmbedder`;
- **`rag/` не импортирует `core/`**, а `core/` не импортирует `rag/` — связь только
  через DI-фасад `RagService` (в `Kod.py`) и готовый текст блока `[rag]`;
- индекс **глобальный** (`rag/index/`, в `.gitignore`), плоский, без FAISS;
- новых pip-зависимостей нет; `TaskStage` не затрагивается (RAG ≠ переход).

**Ключевые решения:**

- **Гибрид ≥ каждой компоненты** (BM25, dense) по recall@20 и hit-rate@5; веса RRF
  подобраны экспериментально (`w_bm25=0.1`, `w_dense=1.0`); порядок:
  BM25⊕dense → RRF → реранк → дедуп (≤2/док) → MMR (λ=0.7) → **порог отсечения** → top-k;
- **Порог отсечения** (`retrieval.threshold=0.45`, абсолютный косинус запрос-чанк):
  отсекает нерелевантный хвост (нерелевантные ≤0.42, релевантные ≥0.52); калибруется
  под модель эмбеддингов (в офлайн-юнитах на `HashingEmbedder` — 0.14);
- **Query rewrite** (`rag/rewrite.py`): снятие шумовых оборотов («пожалуйста, расскажи…»)
  и подтягивание значимых терминов из истории при местоименном/коротком запросе; режимы
  `heuristic` (детерминированно) и `llm` (через DI); обязан не ухудшать recall@5;
- **Ссылки обязательны** при активном RAG: `[doc_id#chunk_id]`; grounding
  (`off|warn|strict`) ловит выдуманные числа/даты и в `strict` запускает **одну**
  авто-перегенерацию с фидбэк-промптом;
- **Источники и цитаты** (`rag/sources.py`, `rag/citations.py`): ответ несёт список
  `Source(source, section, chunk_id, score)` (дедуп по `chunk_id`, сорт по скору) и
  дословные `Quote(chunk_id, text, source)` — фрагменты **чанков** (не текста ответа),
  чтобы проверить, что модель не выдумывает;
- **Режим «не знаю»** (`unknown.enabled`): при пустом RAG-поиске (всё ниже порога)
  `verdict="insufficient"`, источников/цитат нет, **LLM не вызывается** — ответ
  «В источниках нет ответа на этот вопрос…»;
- **Кэш поиска** (`SearchCache`): ключ `sha256(model_id | index_version | norm_query |
  params | filters)`, TTL + инвалидация по mtime затронутых документов, LRU 256;
- **Multi-query** (опц.): `rephrase` через LLM (фолбэк — детерминированная эвристика
  по стемам) → поиск по каждому варианту → RRF-склейка;
- **RAG off по умолчанию:** без `--rag` промпт байт-в-байт прежний, `rag` не
  импортируется (ленивый импорт).

**Сводная механика:**


./run.sh --rag-ingest
  → corpus.discover → delta (sha1) → chunking → embedding (Ollama) → index.save
  → инкрементально: неизменённые документы не переэмбедятся

./run.sh --rag --user alice  →  вопрос
  → RagService.search (кэш → rewrite → BM25⊕dense → RRF → реранк → MMR → порог) → context_block
  → PromptBuilder: блок [rag] ПОСЛЕ [tools], ДО [long_term] (усекается первым)
  → llm.complete → ответ со ссылками [doc_id#chunk_id]
  → sources (source+section/chunk_id) + quotes (дословные цитаты из чанков)
  → grounding (strict): провал → ОДНА авто-перегенерация с фидбэком → пометка
  → пустой поиск (всё ниже порога) → «не знаю» (insufficient), LLM не вызывается

/rag check <ответ>  → ground(answer, last_rag_hits) → ok | partial | hallucination
/rag stats          → индекс, модель, размер, RAM, кэш, латентность p50/p95, Ollama


**Команды и флаги:**

bash
./run.sh --rag-ingest                       # проиндексировать FAQ + документацию продукта
./run.sh --rag-search "как работает авторизация"   # поиск без LLM (топ-5 со скорами)
./run.sh --rag-ask "почему не работает авторизация"   # ответ + источники + цитаты
./run.sh --rag --user alice                 # REPL с блоком [rag] в промпте
./run.sh --rag --rag-mode bm25 --rag-top-k 3
./run.sh --rag --rag-threshold 0.45         # порог отсечения нерелевантных результатов
./run.sh --rag --rag-unknown on             # режим «не знаю» при слабом контексте
./run.sh --rag --rag-reranker lexical       # второй этап ранжирования (реранкер)
./run.sh --rag --rag-rewrite heuristic      # query rewrite перед поиском (off|llm|heuristic)
./run.sh --rag --rag-grounding strict       # проверка опоры ответа (off|warn|strict)
./run.sh --rag --rag-multi-query            # переформулирование запроса (тратит токены)
./run.sh --rag --no-rag-block               # диагностика: ищет, но в промпт не кладёт


**Флаги RAG:** `--rag`, `--no-rag-block`, `--rag-ingest`, `--rag-path <путь>`,
`--rag-search <запрос>`, `--rag-ask <вопрос>`, `--rag-verify`, `--rag-eval [датасет]`,
`--rag-compare`, `--rag-mode {bm25,dense,hybrid}`, `--rag-strategy {fixed,structural}`,
`--rag-top-k <N>`, `--rag-threshold <F>`, `--rag-unknown {off,on}`,
`--rag-reranker {off,lexical}`, `--rag-rewrite {off,llm,heuristic}`, `--rag-config <файл>`,
`--rag-grounding {off,warn,strict}`, `--rag-multi-query`.

---

## Команды REPL

Команды сгруппированы по смыслу.

**Память и профили:**

- `/memory` — снимок «какие данные в каком типе памяти» (report по всем слоям);
- `/profile` — активный профиль: `style` / `constraints` / `context`;
- `/profile list` — профили пользователя (`*` default, `>` активный);
- `/profile show <id>` — полный JSON профиля;
- `/profile use <id>` — переключить активный профиль сессии;
- `/profile new <id>` — создать профиль (мини-интервью) и активировать его;
- `/profile route <текст>` — показать решение роутера (explain), НЕ переключая;
- `/profile auto on|off` — авто-роутинг профиля по каждому запросу.

**Задачи и состояние автомата:**

- `/tasks` — список задач + отметка активной (`*`);
- `/task <имя>` — переключить/создать задачу + загрузка её `task_state.json`;
- `/task retry` — восстановление из `failed` → `planning` (steps/results/error очищены);
- `/plan <цель>` — `new → planning`, план строится и **ожидает утверждения**;
- `/approve` — утвердить план (`planning → plan_approved`); из других стадий — отказ;
- `/goto <этап>` — попытка явного перехода (демо контроля: недопустимый → отказ с правилом);
- `/transitions` — карта `ALLOWED_TRANSITIONS` + журнал `transition_log` + счётчик отказов;
- `/step` — один проход автомата;
- `/run` — крутить автомат до `done`/`failed`/`paused`; из `planning` — останавливается;
- `/pause` — пауза на любой рабочей стадии (`previous_stage` сохраняется);
- `/resume` — продолжение с того же этапа и шага, без повторных объяснений;
- `/deliver <слои>` — набор доставляемых слоёв, напр. `/deliver profile,working`;
- `/compare` — ответ с `long_term` и без него — демонстрация влияния памяти;
- `/summary` — резюме сессий текущей задачи (`sessions_resume.md`);
- `/state` — снимок `TaskState` + разрешённые переходы + счётчик отказов + карта.

**Инварианты:**

- `/invariants` — список инвариантов задачи (`on/off`, id, category, severity, description);
- `/invariant add <id> <category> <текст>` — добавить инвариант (сейв `invariants.json`);
- `/invariant set <id> <текст> [--yes]` — изменить инвариант; без `--yes` требует подтверждения;
- `/invariant on|off <id>` — включить/выключить инвариант;
- `/check <действие>` — прогнать `ProposedAction` через `InvariantChecker` (демонстрация).

**Токены и стоимость:**

- `/tokens` — локальная оценка токенов сессии + указание на CSV-журнал;
- `/cost` — стоимость обменов (локальная оценка, ₽).

**MCP-инструменты (git + CRM/тикеты):**

- `/mcp status` — состояние MCP-подключения + версия каталога;
- `/mcp servers` — сконфигурированные MCP-серверы;
- `/mcp tools` — **список доступных инструментов** (результат задания);
- `/mcp refresh` — re-discovery + атомарный swap + сейв catalog.json;
- `/mcp connect <id>` — поднять соединение с MCP-сервером (по умолчанию — все);
- `/mcp call <tool> [{json}]` — вызвать инструмент вручную через `ToolExecutor`;
- `/mcp disconnect` — закрыть MCP-соединения;
- `/mcp route <текст>` — объяснить выбор инструмента/сервера (без вызова).

**AI-ревью кода (День 32):**

- `/review <diff>` — запустить AI-ревью кода по diff (потенциальные баги, архитектурные
  проблемы, рекомендации); использует RAG для контекста;
- `/review pr <pr_url>` — получить diff PR через MCP (git.get_diff) и запустить ревью;
- `/review status` — статус последнего ревью;
- `/review log` — история ревью из `review_log.jsonl`.

**Поддержка пользователей (День 33):**

- `/ticket <ticket_id>` — загрузить контекст тикета (данные тикета + пользователь);
- `/ticket list <user_id>` — список тикетов пользователя (через MCP CRM);
- `/ticket update <ticket_id> <status>` — обновить статус тикета (через MCP CRM);
- `/support <вопрос>` — ответ на вопрос поддержки с учётом контекста тикета и RAG;
- `/chat` — режим веб-чата: клиент задаёт вопрос → ассистент отвечает с учётом контекста.

**Помощь по проекту (День 31):**

- `/help` — **ассистент отвечает на вопросы о проекте**, используя документацию
  (README, код, project/docs) и контекст проекта через RAG-модуль;
  ассистент понимает структуру проекта и отвечает на вопросы о нём.

**RAG:**

- `/rag status` — состояние RAG (вкл/выкл, режим, топ-k, grounding, индекс);
- `/rag on|off` — включить/выключить RAG в сессии;
- `/rag ingest` — проиндексировать FAQ и документацию продукта (инкрементально);
- `/rag find <запрос>` — поиск со скорами — **почему** выбран чанк;
- `/rag ask <вопрос>` — ответ с RAG (ответ + источники + цитаты);
- `/rag sources` — источники последнего ответа агента (source + section/chunk_id);
- `/rag quotes` — цитаты последнего ответа агента (дословные фрагменты чанков);
- `/rag verify` — проверка источников/цитат на 10 контрольных вопросах;
- `/rag check <ответ>` — проверка опоры ответа на последние источники (без LLM);
- `/rag stats` — индекс, модель, RAM, кэш, латентность p50/p95, Ollama;
- `/rag eval` — метрики на golden-датасете.

**Прочее:**

- `/help` — список команд;
- `/exit` — `save_state()` (+ сейв `task_state.json` с `transition_log`) и выход.

Без активной задачи `/step`, `/run`, `/pause`, `/resume`, `/approve`, `/goto` печатают
подсказку «сначала `/plan <цель>`». `EOFError` / `KeyboardInterrupt` тоже вызывают
`save_state()` — состояние не теряется. Неизвестная команда и исключения цикла логируются
и не прерывают сессию. `/mcp`-команды без флага `--mcp` печатают «MCP-слой выключен».

---

## Запуск

bash
# Через обёртку (активирует venv недели AI_9, работает из любого каталога)
./run.sh                     # интерактивный REPL — спросит user_id
./run.sh --user alice        # сразу идентификация alice

# Напрямую (живой LLM RouterAI, ключ из .env)
python Kod.py --user alice

# Персонализация
./run.sh --user alice --profile chemist    # активный профиль на старте

# MCP (git + CRM/тикеты)
python Kod.py --mcp-probe                  # one-shot: подключиться → список тулов → выйти
./run.sh --user alice --mcp                # REPL с MCP-слоем (/mcp …)
python -m integrations.mcp.demo_server     # локальный MCP-сервер (stdio) отдельно
python -m integrations.mcp.crm_server      # MCP-сервер CRM/тикетов (HTTP :8030) отдельно

# RAG (FAQ + документация продукта)
./run.sh --rag-ingest                       # проиндексировать FAQ + документацию продукта
./run.sh --rag-ask "почему не работает авторизация"   # ответ + источники + цитаты
./run.sh --rag --user alice                 # REPL с блоком [rag] в промпте

# AI-ревью кода (День 32)
./run.sh --user alice --rag --mcp           # REPL с RAG + MCP для ревью
./run.sh --user alice --rag                 # /review <diff> с RAG-контекстом

# AI-ассистент поддержки (День 33)
./run.sh --user alice --rag --mcp           # REPL с RAG + MCP для поддержки
./run.sh --user alice --rag                 # /support <вопрос> с RAG-контекстом
./run.sh --user alice --rag --mcp           # /ticket <id> → /support <вопрос>

# Команда /help (ассистент разработчика)
./run.sh --user alice --rag                 # /help отвечает на вопросы о проекте


**Флаги:** `--user <id>`, `--profile <id>`, `--deliver <слои>` (по умолчанию `DELIVERABLE`),
`--mock`, `--fresh`, `--log`, `--token-log`, `--max-tokens`, `--price-in` / `--price-out`
(₽ за 1M, по умолчанию 11 / 33), `--budget <N>`, `--memory-dir` (перенос хранилища —
используется тестами для изоляции), `--mcp` (включить MCP-слой в REPL), `--mcp-probe`
(one-shot результат задания), `--no-tools-block`, `--scheduler` (фоновый worker 24/7),
`--scheduler-interval <сек>`.
**Флаги RAG:** `--rag`, `--no-rag-block`, `--rag-ingest`, `--rag-path <путь>`,
`--rag-search <запрос>`, `--rag-ask <вопрос>`, `--rag-verify`, `--rag-eval [датасет]`,
`--rag-compare`, `--rag-mode {bm25,dense,hybrid}`, `--rag-strategy {fixed,structural}`,
`--rag-top-k <N>`, `--rag-threshold <F>`, `--rag-unknown {off,on}`,
`--rag-reranker {off,lexical}`, `--rag-rewrite {off,llm,heuristic}`, `--rag-config <файл>`,
`--rag-grounding {off,warn,strict}`, `--rag-multi-query`.

> **НЕ ТРОГАТЬ (следы функционала).** Флаги `--temperature F`, `--max-tokens N`,
> `--context-window N` (разовое переопределение параметров) и связанная с ними информация
> (профили `temperature` / `max_tokens` / `context_window`) — следы функционала Дня 5
> (`ND/tasks/n_1/005_День 5/`), **ошибочно затёртого в одной из прошлых ревизий**.
> Их **не удалять, не переписывать и не «чистить»**: предстоит **восстановление
> в следующей ревизии**. Любое расхождение с текущим `Kod.py` — ожидаемо и не является
> поводом для правки.

Все пути строятся от `BASE_DIR`; ключ — `API_KEY` из `.env` (`load_dotenv()`).
При `--mock`, отсутствии ключа или `API_KEY=test-key` автоматически выбирается `MockClient`.
`run.desktop` содержит абсолютные `Exec=`/`Path=` — после переноса на другой хост
его нужно пересоздать (в `.desktop` переменные окружения не раскрываются).

---

## Агентный цикл


старт → DI-сборка build_agent(mcp_enabled=--mcp) (+ RagService при --rag) → идентификация user_id
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
        LLM tool-use: _respond_with_tools (LLM → tool call → ToolExecutor → tool-сообщение → LLM)
RAG:    --rag → RagService.search (кэш → rewrite → BM25⊕dense → RRF → реранк → MMR → порог)
        → блок [rag] в промпте (после [tools]) → ответ со ссылками → источники/цитаты
        → grounding (strict: провал → одна авто-перегенерация; пустой поиск → «не знаю»);
        без --rag rag/ не импортируется
/ticket: <ticket_id> → MCP CRM (get_ticket) → загрузка контекста тикета → ticket_context.json
/support: <вопрос> → RAG-поиск по FAQ + документации продукта → LLM-анализ с контекстом тикета
           → формирование ответа → обновление ticket_context
/chat:    клиентский веб-чат → вопрос → /ticket (контекст) → /support (ответ) → ответ клиенту
/help:   вопрос о проекте → RAG-поиск по документации (README, код, project/docs)
         → блок [rag] в промпте → ответ со ссылками на источники
выход:   save_state() + сейв task_state.json (включая transition_log)


---

## Тестирование и приёмка

Всё — **без живого ключа** (`API_KEY=test-key`, `MockClient`, `FakeMCPTransport`),
тестовые данные пишутся только в `dev/tests_debug/.tmp/` (в `.gitignore`), рабочие
`users/` не затрагиваются. `pytest` установлен в `.venv` (9.1.1) как **дополнительный**
раннер; L2 идёт через собственный лёгкий раннер `unit_runner.py`.

**Уровни проверок** (чем выше номер, тем крупнее проверка):

- **L1 — компиляция.** Команда:
  `python -m py_compile Kod.py core/*.py memory/*.py storage/*.py integrations/mcp/*.py`.
  Результат: exit 0 (файлы синтаксически корректны).
- **L2 — юнит-тесты.** Команда:
  `env -u API_KEY python dev/tests_debug/unit_runner.py`.
  Результат: **412 OK, 0 FAIL** (42 модуля).
- **L3 — смоук.** Команда: `API_KEY=test-key python dev/tests_debug/smoke.py`.
  Результат: SMOKE OK, exit 0.
- **L4 — сценарии.** Команда: `API_KEY=test-key python dev/tests_debug/scenario.py`.
  Результат: SCENARIO OK, exit 0.
- **Гейт приёмки.** Команда:
  `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh`.
  Результат: **58 из 58 ✅, exit 0**.
- **Диалоги.** Команда: `API_KEY=test-key python dev/tests_debug/dialog_runner.py`.
  Результат: DIALOG OK, exit 0 (2 длинных сценария).

**Состав тестовых модулей:**


- `unit/test_mcp.py` — контракты (квалифицированное имя, source/provider); discovery-
  нормализация; реестр (add/refresh/snapshot, коллизии, unregister, get-ошибка);
  атомарность (version монотонный); недоступный сервер (FAILED, тулы исключены,
  остальные живы); фильтр allowed/denied; HTTP-транспорт + фикс схемы `input_schema`;
  `tools/call` + policy + аудит; персистентность (round-trip, битый файл →
  schema_version=1); **MCP не трогает состояние** (TaskStage не изменился,
  transition_log пуст); **MCP off по умолчанию**; конфиг (дефолт/битый/неизвестные
  ключи); LLM tool-use (парсеры, агентный цикл, блок `[tools]`);
- `unit/test_rag_*.py` — интеграция (18), grounding (18), cache (15), rerank (10),
  verify (10), working_memory (9), service;
- L4 сценарии — проверки внутри `scenario.py`: `scenario_mcp_discovery`,
  `scenario_llm_tool_use`, `scenario_tool_denied`, `scenario_multiserver_flow` + базовые.
  Отдельно в `scenario/` лежат **9 md-файлов сценариев ручной демонстрации**
  (`scen_1`, `scen_rag`, `scen_dialog_A`, `scen_dialog_B`, `scen_multiserver_flow`,
  `scen_local_llm`, `scen_rag_local`, `scen_optimize`, `scen_access`) — это чек-листы
  живых прогонов, а не автотесты;
- `dialog_runner.py` — прогон 2 длинных диалоговых сценариев (`scen_dialog_A.md` — 12
  сообщений, `scen_dialog_B.md` — 13) с активным RAG: поиск на каждом обмене, источники
  в каждом ответе, цель/термины в памяти задачи;
- гейт `check_acceptance.sh` — **58 проверок** (25 прежних + 8 RAG Ревизии 6 + 10 RAG
  Ревизии 7 + 15 Ревизии 8: реестр моделей и `models.json`; `--model-list`; подпись модели
  в баннере; без `--model` промпт байт-в-байт прежний; субагент пишет лог с подписью;
  `--local-gen` выбирает локальную модель; сравнение генераторов — три оси; профиль
  параметров в теле запроса; отчёт «до/после»; фасад `/ask`+`/models`; шлюз — вход +
  лимит 6/мин; юнит туннеля; MCP-порты сохранены; секретов в конфигах нет; 4 сценария
  демонстрации). Идемпотентен, `users/` не трогает.

**Человеческая версия приёмки** — **48 критериев, 48/48 зелёных** — в
[`dev/Проверка.md`](dev/Проверка.md).

### Демонстрации задания (День 33)

**AI-ассистент поддержки пользователей — пайплайн:**

- **Веб-чат как клиентский канал.** Как посмотреть: клиентский веб-чат (интеграция с
  `gateway/templates/chat.html`).
  Что видно: клиент создаёт тикет / задаёт вопрос → ассистент отвечает с учётом контекста.
- **Контекст тикета загружается через MCP CRM.** Как: `/ticket <ticket_id>` →
  `mcp.crm.get_ticket` → данные тикета сохраняются в `ticket_context.json`.
  Что видно: ID тикета, статус, история, данные пользователя.
- **RAG по FAQ и документации продукта.** Как: `--rag` → `/support <вопрос>` →
  `RagService.search` по FAQ + документации продукта.
  Что видно: найденные релевантные чанки с скорами и источниками.
- **Ответ с учётом контекста.** Как: LLM-анализ вопроса + RAG-контекст + данные тикета
  из `ticket_context.json` → формирование ответа.
  Что видно: текст ответа с учётом истории тикета и данных пользователя.
- **Обновление статуса тикета.** Как: `/ticket update <id> <status>` →
  `mcp.crm.update_ticket` → обновление статуса.
  Что видно: подтверждение обновления.

**Команды `/ticket` — управление тикетами:**

- **`/ticket <ticket_id>` — загрузка контекста тикета.** Как: `--mcp` → `/ticket 12345`.
  Что видно: данные тикета (статус, история, пользователь).
- **`/ticket list <user_id>` — список тикетов пользователя.** Как: `--mcp` → `/ticket list user_001`.
  Что видно: список тикетов с статусами.
- **`/ticket update <ticket_id> <status>` — обновление статуса.** Как: `--mcp` → `/ticket update 12345 resolved`.
  Что видно: подтверждение обновления.

**Команды `/support` — ответы на вопросы поддержки:**

- **`/support <вопрос>` — ответ с контекстом тикета и RAG.** Как: `--rag --mcp` → `/ticket 12345` → `/support почему не работает авторизация?`.
  Что видно: ответ с учётом данных тикета, RAG-поиска по FAQ и документации продукта.
- **`/chat` — режим веб-чата.** Как: клиентский веб-чат → вопрос → ассистент отвечает.
  Что видно: диалог с клиентом, контекст беседы сохраняется.

**Пример сценария «Почему не работает авторизация?»:**

1. Клиент создаёт тикет через веб-чат: «Почему не работает авторизация?».
2. Ассистент загружает контекст тикета через MCP CRM (`get_ticket`).
3. Ассистент ищет ответ в FAQ и документации продукта через RAG.
4. Ассистент формирует ответ с учётом данных тикета (например, «У вас истёк токен,
   обновите в настройках профиля»).
5. Ассистент обновляет статус тикета на «resolved» через MCP CRM (`update_ticket`).

---

## Служебное пространство `dev/` (проект про проект)

### Дерево `dev/`


AI_9/dev/
├── migr_plan.md                  # план-эталон миграции
├── migr_plan_0.md … migr_plan_12.md  # исполняемые планы этапов
├── review/                       # ревью документации
├── migr_log.md                   # журнал миграции «было → стало → проверка → статус»
├── Проверка.md                   # чек-лист приёмки (48 критериев)
├── old_vers/                     # история прошлых ревизий (1…8)
├── meta_promt/                   # метапромты (вспомогательные промты)
├── tests_debug/
│   ├── check_acceptance.sh       # гейт приёмки (58 проверок)
│   ├── unit_runner.py            # L2-раннер (без pytest)
│   ├── smoke.py                  # L3-смоук
│   ├── scenario.py               # L4-сценарии
│   ├── dialog_runner.py          # прогон 2 длинных диалоговых сценариев
│   ├── unit/                     # 42 модуля test_*.py
│   ├── scenario/                 # 9 сценариев ручной демонстрации
│   ├── fixtures/                 # фикстуры (пусто — заполняется по мере надобности)
│   └── .tmp/                     # единственное место прогонов (.gitignore)
│       ├── README_31.md          # результат Дня 31
│       ├── README_32.md          # результат Дня 32
│       └── README_33.md          # результат Дня 33 (этот файл)
├── logs_reports/                 # stages/ + errors/ + archive/
└── vps/                          # инфраструктурный контур VPS


### `tests_debug/` — что именно протестировать (канон задания)

- **контракты**: `ToolDescriptor` — квалифицированное имя, source/provider;
  `ToolCatalogSnapshot` — version/tools/created_at; `ToolExecutionState`;
- **discovery**: `MCPToolProvider.discover()` нормализует mcp-тул →
  `name="mcp.crm.get_ticket"`, `original_name="get_ticket"`, `source="mcp"`;
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
  попадает в discovery;
- **`tools/call`**: fake успех/`isError`; `gateway.call_tool` маршрутизирует по
  provider и отдаёт failed-результат для не-READY сервера;
- **`ToolPolicy`/`ToolExecutor`**: отказ по схеме/стадии; исполнение + аудит;
  отказ по инварианту (`tool.deny.*`) → `denied` в аудите;
- **LLM tool-use**: парсеры (нативный/fallback); агентный цикл (намерение → вызов →
  ответ); блок `[tools]` в промте + порядок блоков;
- **персистентность**: `save_tool_catalog` → `load_tool_catalog` round-trip;
  битый/отсутствующий файл → пустой каталог schema_version=1;
- **MCP не трогает состояние**: после полного цикла connect → discover → refresh
  `TaskStage` не изменился, `transition_log` пуст;
- **MCP off по умолчанию**: без `--mcp` реестр пуст, агент отвечает как в предыдущей ревизии;
- **RAG**: импорт `rag`; индекс строится и переживает save/load; поиск отдаёт хит с
  метаданными; две стратегии чанкинга; отчёт сравнения; без `--rag` нет `[rag]`;
  `TaskStage` не затронут;
- **ticket_context**: `read/write_ticket_context` round-trip; контекст тикета
  загружается через MCP CRM и сохраняется отдельно от диалога.

Интеграционный тест (не гейт, живой прогон): `HttpMCPTransport` подключается к реальному
серверу → initialize → list_tools → тулы; `call_tool` → результат. Живой LLM tool-use —
тоже вне гейта (приёмка).

### `logs_reports/`

- `migr_log.md` — журнал миграции «было → стало → проверка → статус» по этапам;
- `errors/error_<timestamp>.md` — карточки ошибок (красный гейт этапа → карточка);
- `stages/` (+ `rag_*` транскрипты), `archive/` — живой прогон, отчёты этапов.

---

## Карта артефактов

### Рабочие артефакты (продукт)

- `Kod.py` + `core/` + `memory/` + `storage/` — агент без регрессии, плюс
  каталог инструментов, tool-use и RAG.
- `core/tools.py` — внутренняя модель: ToolDescriptor, ToolCallRequest, ToolExecutionResult,
  ToolExecutionState, ToolProvider, ToolCatalogSnapshot.
- `core/tool_registry.py` — ToolRegistry: каталогизация, атомарный snapshot, refresh.
- `core/tool_policy.py` — ToolPolicy: проверки вызова (enabled, схема, стадия, инварианты,
  подтверждение).
- `core/tool_executor.py` — ToolExecutor: policy → вызов → аудит.
- `core/tool_routing.py` и `core/tool_pipeline.py` — выбор инструмента и пайплайн.
- `integrations/mcp/*` — MCP-слой: config, transport (stdio + HTTP + fake), client, gateway,
  provider, demo_server, scheduler_server, pipeline_server, time_server, auth, **crm_server**.
- `integrations/scheduler/*` — ядро планировщика (на stdlib): models, store, runner,
  aggregator.
- `rag/*` — RAG-модуль: config, corpus (FAQ + документация продукта), chunking, embedding,
  index, retrieval, rerank, rewrite, cache, grounding, eval, compare, sources, citations,
  verify, service.
- `serve.py` — фасад: HTTP-вход агента на хосте (`127.0.0.1:8090`), `/ask` и `/models`.
- `gateway/*` — веб-шлюз на VPS: `app.py` (чат, прокси), `users.py` (регистрация),
  `questions.py` + `questions.json` (интервью), `config.py` + `gateway.json` (лимиты).
- `dev/vps/*` — инфраструктура доступа: скрипты деплоя, systemd-юниты, README.
- `users/<id>/integrations/mcp/{servers,catalog}.json` — конфиг серверов и снимок каталога.
- `users/<id>/tasks/<task>/tool_audit.jsonl` — история вызовов инструментов.
- `users/<id>/tasks/<task>/review_log.jsonl` — история AI-ревью PR (день 32).
- `users/<id>/tasks/<task>/ticket_context.json` — контекст тикета поддержки (день 33).
- `project/` — документация проекта (RAG-корпус):
  - `README.md` — основной README;
  - `docs/` — дополнительная документация (architecture, api, data_schemas);
  - `faq/` — FAQ по продукту (день 33);
  - `code/` — исходный код для индексации.
- `.github/workflows/ai-review.yml` — пайплайн AI-ревью кода на PR (день 32).
- `run.sh` и `run.desktop` — запуск.
- `README.md` — единый источник данных о проекте (этот файл).

### Служебные артефакты (процесс)

- `dev/Проверка.md` — чек-лист приёмки: 48 критериев.
- `dev/migr_plan.md` и `migr_plan_*.md` — план-эталон и рабочие планы миграции.
- `dev/migr_log.md` — журнал миграции и итоги ревизий.
- `dev/review/migr_review.md` и `migr_review_*.md` — мастер-план и рабочие планы
  ревью документации.
- `dev/tests_debug/*` — L2 (42 модуля), L3, L4 (9 сценариев), гейт 58/58.
- `dev/logs_reports/stages/*` — транскрипты живых прогонов.
- `agents.md` — краткая памятка агенту (20 строк).
- `ND/tasks/n_1 … n_7` — задания куратора по неделям (источник требований).

---

## Порядок достижения итогового состояния

Порядок по зависимостям (от контрактов к CLI):

1. **Базовый агент** — память, профили, инварианты, машина состояний, LLM-клиент.
2. **Контракты инструментов** — `core/tools.py` → `core/tool_registry.py`
   → `integrations/mcp/` (config → transport + fake + HTTP → client → gateway → provider).
3. **Контроль и исполнение** — `core/tool_policy.py` + `core/tool_executor.py`.
4. **LLM tool-use** — `core/llm_client.py` (tool-use) → `core/prompt_builder.py`
   (блок `[tools]`) → `core/agent.py` (агентный цикл) → `storage/store.py` (каталог + аудит).
5. **CLI** — `Kod.py` (DI + `/mcp`-семейство + `--mcp`/`--mcp-probe`).
6. **RAG (FAQ + документация продукта)** — `rag/` (config → corpus [FAQ, docs, код] →
   chunking → embedding → index → retrieval → rerank → rewrite → cache → grounding →
   sources → citations → verify → service) + DI-фасад в `Kod.py` + блок `[rag]`
   в `prompt_builder.py` + `core/agent.py` (grounding, источники/цитаты).
7. **День 31 — ассистент разработчика**:
   - RAG-корпус = README + project/docs + код + схемы данных;
   - MCP-сервер git = get_branch, list_files, get_diff;
   - Команда `/help` = RAG-поиск по документации + контекст проекта.
8. **День 32 — автоматизация ревью кода**:
   - Пайплайн `.github/workflows/ai-review.yml` — GitHub Action на PR;
   - Получение diff и изменённых файлов через MCP (`mcp.git.get_diff`);
   - RAG-поиск по документации проекта для контекста ревью;
   - LLM-анализ: потенциальные баги, архитектурные проблемы, рекомендации;
   - Формирование текста ревью + запись в `review_log.jsonl`;
   - Команды `/review <diff>`, `/review pr <url>`, `/review status`, `/review log`.
9. **День 33 — AI-ассистент поддержки пользователей**:
   - RAG-корпус = FAQ + документация продукта + README + project/docs + код;
   - MCP-сервер CRM = get_ticket, update_ticket, list_tickets, get_user;
   - Веб-чат как клиентский канал (чат с сохранением контекста беседы);
   - Команды `/ticket <id>`, `/ticket list`, `/ticket update`, `/support <вопрос>`, `/chat`;
   - Контекст тикета сохраняется в `ticket_context.json` (task-scope).
10. **Финал** — прогон всех проверок (L1→L2→L3→L4→гейт), приёмка, живой прогон,
    запись итога в `dev/migr_log.md`.

---

## Риски и откат

- **Регрессия ядра** — MCP/RAG выключены по умолчанию (`mcp_enabled=False`, `--rag`);
  без флагов поведение = предыдущая ревизия. Откат — не включать флаги.
- **Зависимость от внешнего MCP-сервера** — недоступный сервер → `FAILED`/`DEGRADED`,
  тулы исключаются, REPL жив. Откат — `/mcp disconnect`.
- **Зависимость от Ollama (RAG)** — при недоступности `127.0.0.1:11434` деградация на
  `HashingEmbedder`. Откат — не использовать `--rag`.
- **Протечка модели MCP в `core`** — исключена: SDK импортируется только в
  `integrations/mcp/`. Проверяется тестами.
- **Загрязнение рабочих данных** — тесты пишут только в `dev/tests_debug/.tmp/`,
  `users/` не затрагивается.
- **Недетерминированность LLM** — детерминированный тестовый контур на `MockClient` +
  `FakeMCPTransport`; живой LLM — только приёмка.
- **Пайплайн AI-ревью** — GitHub Action требует настроенного репозитория и API-ключа;
  локально пайплайн заменяется командами `/review <diff>` и `/review pr <url>`.

---

## Известные шероховатости и заделы

**Заделы по замыслу:**

- **`ToolMemoryPolicy`**: сырые ответы MCP никогда не пишутся в память автоматически;
- **`ToolPromptPolicy` + блок `[external_context]`** (MCP resources): дозированная
  доставка описаний тулов под токен-бюджет;
- **полный async core**: async gateway за синхронным фасадом `MCPGatewaySync`;
- **параллелизм read-only тулов**; **local-провайдер** (`local.*` — только безопасные
  доменные операции);
- **расширение policy pipeline** (риск-уровни, подтверждения);
- `PolicyEngine` в `memory/base.py` — пустой интерфейс-задел;
- `parent_id` сообщений — задел ветвления диалога; `skills[]` — декларативный
  пайплайн; `transition_log` растёт без ограничения (сжатие — следующие дни);
- **веб-чат с сохранением контекста беседы** — задел: клиентский канал (чат) интегрируется
  с `gateway/templates/chat.html`, контекст беседы сохраняется в `session.json`;
- **полноценная CRM** — задел: MCP CRM-сервер (`crm_server.py`) — заглушка, для продакшена
  нужна интеграция с реальной CRM (REST API, база данных).

**Расхождения spec/кода (на поведение не влияют):**

- `mcp` SDK импортируется в `transport.py` и `demo_server.py` (уровень транспорта),
  а не в `client.py`; инвариант «SDK только в `integrations/mcp/`» соблюдён;
- `handle_mcp_command` читает приватное `gateway.gateway._servers` — допустимо для CLI;
- смоуки этапов миграции — рабочие артефакты этапов, вне дерева §3.1.

**Косметика:**

- каталоги `dev/tests_debug/fixtures/` и `smoke/` созданы каркасом и остались пустыми;
  в `.tmp/` накапливаются каталоги прошлых прогонов (в `.gitignore`);
- изменения миграции не закоммичены (коммит — только по явной команде пользователя).

---

## Результат

- **RAG-модуль с FAQ и документацией продукта**: индексация корпуса (FAQ, project/docs,
  код, схемы данных, API-описания), гибридный поиск (BM25⊕dense → RRF → реранк → MMR →
  порог), query rewrite, блок `[rag]` со ссылками `[doc_id#chunk_id]`, **источники**
  (`source`+`section`/`chunk_id`) и **дословные цитаты** из чанков, режим «не знаю» при
  слабом контексте, grounding (`ok|partial|hallucination`) и одна авто-перегенерация в
  `strict`.
- **MCP-подключение к CRM / JSON с пользователями и тикетами**: `get_ticket` (данные
  тикета), `update_ticket` (обновление статуса), `list_tickets` (список тикетов),
  `get_user` (данные пользователя); LLM tool-use — агент сам вызывает CRM-инструменты
  и использует результат.
- **AI-ассистент поддержки пользователей (День 33)**:
  - Веб-чат как клиентский канал (чат с сохранением контекста беседы);
  - Загрузка контекста тикета через MCP CRM (`mcp.crm.get_ticket`);
  - RAG-поиск по FAQ и документации продукта для контекста поддержки;
  - LLM-анализ: ответ с учётом контекста пользователя/тикета;
  - Обновление статуса тикета через MCP CRM (`mcp.crm.update_ticket`);
  - Контекст тикета сохраняется в `ticket_context.json` (task-scope);
  - Команды `/ticket <id>`, `/ticket list`, `/ticket update`, `/support <вопрос>`, `/chat`.
- **Команда `/help` — ассистент разработчика**: отвечает на вопросы о структуре проекта,
  используя документацию (README, код, project/docs) и контекст проекта через RAG-модуль.
- **Не скрипт, а AI-first сервис поддержки**: `MCPGateway` (адаптер CRM) →
  `MCPToolProvider` (нормализация) → `ToolRegistry` (каталог + snapshot) →
  `ToolExecutor` (policy + аудит) → LLM tool-use → RAG (FAQ + документация) → ответ.
- **Пять «кубиков» дней 11–15 без регрессии**: память, профили, инварианты, строгая
  машина состояний, LLM-клиент — контракты не тронуты; MCP и RAG выключены по умолчанию.
- **Инструмент ≠ переход**: `TaskStage` (8 стадий) не меняется от вызовов MCP/RAG;
  успех вызова не создаёт запись в `transition_log`.
- **Изоляция прав через тулинг**: `allowed_tools`/`denied_tools` в конфиге сервера;
  модель MCP не протекает в `core`; `MCPGateway` не знает о стадиях/профилях/памяти.
- **Деградация, не падение**: недоступный сервер → FAILED/DEGRADED, REPL жив;
  недоступная Ollama → `HashingEmbedder`.
- **Проверяемость**: L1 OK / L2 412 OK / L3 SMOKE OK / L4 SCENARIO OK, гейт **58/58**,
  приёмка **48 критериев** — без живого ключа и сети; живой прогон (реальный HTTP-сервер
  + реальный LLM) — отдельно.
- **Заделы с зарезервированными местами**: `ToolMemoryPolicy`, `ToolPromptPolicy`/resources,
  параллелизм read-only тулов, local-provider, полный async core, полноценная CRM,
  веб-чат с сохранением контекста беседы.
