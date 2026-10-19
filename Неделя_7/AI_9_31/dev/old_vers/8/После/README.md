# AI_9 — llm-agent (планировщик, пайплайн, несколько MCP-серверов и RAG)

> AI_9 — персонализированный CLI stateful-агент (память → профили → инварианты →
> контролируемый жизненный цикл) с RAG-поиском по документам, к которому MCP
> подключается не как отдельный фундаментальный слой, а как интеграционный источник
> инструментов: gateway соединяет (реальный HTTP-сервер), provider нормализует,
> registry каталогизирует, executor вызывает и аудитирует, LLM сам предлагает вызовы —
> а контроль остаётся за существующими механизмами.

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
- [Локальные LLM и доступ к агенту](#локальные-llm-и-доступ-к-агенту)
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
**подключением к внешнему миру через MCP** (внешний источник инструментов) и
**RAG-модулем** (поиск по документам с проверкой опоры ответа).

Память разделена на четыре физически отдельных слоя (краткосрочная / рабочая /
долговременная / профиль), запись идёт только явным вызовом `memory.remember(layer,
...)`, а набор слоёв, попадающих в промт, — параметр `deliver: set[str]`
(дозированная доставка). Поверх памяти — мультипрофильность с профиль-роутером,
затем строгая машина состояний (`TaskStage` — 8 стадий, `ALLOWED_TRANSITIONS`
whitelist, `try_transition` → `InvalidTransitionError`, журнал `transition_log`) и
слой инвариантов (`InvariantChecker` — «код запрещает, промт рекомендует»).

**Шестой, интеграционный «кубик»** — MCP как внешний источник инструментов (не
заменяя ни один из пяти кубиков дней 11–15). К нему подключён **конкретный инструмент
задания** `get_time` (сервер `time`), демонстрирующий реальное поведение агента: LLM
сам вызывает инструмент и использует результат. **RAG-модуль** добавляет седьмой слой —
поиск по локальному корпусу документов с гибридным ранжированием и проверкой опоры.


MCPGateway (соединение + handshake + tools/list + tools/call)
   → MCPToolProvider (нормализация mcp-тула → ToolDescriptor)
      → ToolRegistry (каталог + атомарный snapshot + персистентность через Store)
         → ToolExecutor (policy → вызов → аудит) → LLM tool-use (агент сам вызывает тул)
            → CLI (/mcp tools, /mcp call, --mcp-probe — вывод списка и вызов инструментов)

RagService (индексация корпуса → гибридный поиск → блок [rag] в промте → grounding)
   → PromptBuilder → LLM (ответ со ссылками [doc_id#chunk_id])


Ключевые границы:

- **MCP — источник инструментов, не слой контроля**: `MCPGateway` — адаптер («как
  технически вызвать»), он не знает о стадиях, профилях и памяти; контроль остаётся
  за `StateMachine` (этапы), `InvariantChecker` (действия) и `ToolExecutor` (процедура
  вызова). Циклы `Agent → MCPGateway → StateMachine → Agent` запрещены.
- **Инструмент ≠ переход**: вызов (и даже успешное завершение) MCP-инструмента
  **никогда** не означает переход `TaskStage`; MCP-стадий нет и не будет.
  Инфраструктурные состояния живут отдельно: `MCPConnectionState` (подключение) и
  `ToolExecutionState` (вызов). То же для RAG: RAG ≠ переход.
- **Модель MCP не протекает в `core`**: `mcp` SDK импортируется только в
  `integrations/mcp/` (транспорт и демо-сервер); `ToolDescriptor` — внутренняя
  модель агента; имена квалифицируются (`mcp.<server>.<tool>`).
- **`rag/` и `core/` не импортируют друг друга** — связь только через DI-фасад
  `RagService` и готовый текст блока `[rag]`.
- **MCP выключен по умолчанию** (`mcp_enabled=False`); **RAG выключен по умолчанию**
  (`--rag`). Без флагов агент работает ровно как в предыдущей ревизии (день 15); прежние тесты и критерии
  приёмки проходят без MCP, без RAG и без сети.
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
  **`clarifications`** (уточнения), **`terms`** (термины вида `{термин: определение}`).
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
    └── sessions/<session_id>/   # session_id = ГГГГММДД_ЧЧММСС
        └── session.json         # краткосрочная память: сообщения с parent_id


Разделение ответственности: `session.json` — неизменяемая история; `working_memory.json` —
пересчитываемое состояние памяти задачи; `task_state.json` — формализованное состояние
**жизненного цикла** (включая журнал переходов); `invariants.json` — **неизменяемые правила**;
`integrations/mcp/` — конфиг и каталог внешних инструментов; `tool_audit.jsonl` — история
вызовов (отдельно от `transition_log`). Разные сущности, разные файлы. **Очистка истории
диалога не сбрасывает состояние, не удаляет инварианты, не трогает журнал переходов и
конфиг MCP.**

База профилей — `users/profiles.db` (общая для всех пользователей).
Все пути знает только `storage/store.py` (`safe_name`, `ensure_user/task/session`,
`read_json`/`write_json` с каноническими дефолтами, `task_state_path`/`read_task_state`/
`write_task_state` с миграцией `"execution"` → `implementation`,
`invariants_path`/`read/write_invariants`, `mcp_servers_path`/`read/write_mcp_servers`,
`tool_catalog_path`/`read/save_tool_catalog`, `append_tool_audit`/`load_tool_audit`).
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
provider, demo_server, scheduler_server, pipeline_server) и `scheduler/` (models, store,
runner, aggregator — ядро планировщика на stdlib). SDK импортируется только здесь.

**RAG** (`rag/`) — расширяемый RAG-модуль: индексация корпуса, гибридный поиск, блок `[rag]`
в промте, источники/цитаты и проверка опоры ответа. Сеть — исключительно `127.0.0.1:11434` (Ollama).

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
│                                #   (+ /mcp…, /rag…, --mcp-probe, run_mcp_probe)
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
│   │   ├── transport.py         # MCPTransport (ABC) + StdioMCPTransport + HttpMCPTransport
│   │   │                        #   (Streamable HTTP, mcp SDK) + FakeMCPTransport; make_transport
│   │   ├── client.py            # MCPClient: initialize / list_tools / call_tool
│   │   ├── gateway.py           # MCPGateway: start/stop/connection_state, discover(), call_tool();
│   │   │                        #   MCPGatewaySync — синхронный фасад (постоянная фоновая задача)
│   │   ├── provider.py          # MCPToolProvider: discover() + нормализация → ToolDescriptor
│   │   ├── demo_server.py       # локальный stdio MCP-сервер (get_time, echo, weather_stub)
│   │   ├── scheduler_server.py  # MCP-сервер планировщика (HTTP :8010)
│   │   └── pipeline_server.py   # MCP-сервер пайплайна (search/summarize/saveToFile, HTTP :8020)
│   └── scheduler/               # ядро планировщика (stdlib): models/store/runner/aggregator
├── memory/                      # 4 слоя + MemoryManager (ToolMemoryPolicy — задел)
├── rag/                         # RAG-модуль (индексация + гибридный поиск)
│   ├── config.py / config.json  # RagConfig (+ валидация: эмбеддинги только 127.0.0.1:11434)
│   ├── types.py / text.py       # Chunk/DocMeta/Hit/Source/Quote/Answer ; нормализация/токенизация
│   ├── corpus.py / chunking.py  # сбор корпуса, sha1/mtime; fixed | structural
│   ├── embedding.py             # OllamaEmbedder (bge-m3, dim 1024) + HashingEmbedder (фолбэк)
│   ├── index.py                 # плоский индекс: BM25-постинги + векторы; save/load/version
│   ├── retrieval.py / rerank.py # bm25 | dense | hybrid (RRF + MMR) + порог; LexicalReranker
│   ├── rewrite.py               # query rewrite (снятие шума + термины из истории)
│   ├── cache.py                 # SearchCache — LRU+TTL, инвалидация по mtime
│   ├── grounding.py / eval.py / compare.py  # опора ответа; метрики; сравнение режимов
│   ├── sources.py / citations.py # источники (source+section/chunk_id) и дословные цитаты
│   ├── verify.py                # проверка формата ответа (источники/цитаты/смысл) на 10 вопросах
│   ├── service.py               # RagService — фасад для Kod.py/Agent
│   ├── datasets/                # corpus.list (9 файлов) + queries.jsonl (24 golden + 10 контрольных)
│   └── index/                   # рантайм-индекс (в .gitignore): chunks/postings/vectors/meta
├── storage/
│   ├── store.py                 # фасад: + mcp_servers/catalog + tool_audit (+ RAG-метрики)
│   └── db.py                    # ProfileRepository (без изменений)
├── users/                       # рантайм-хранилище (создаётся при работе)
│   └── <id>/integrations/mcp/   # servers.json + catalog.json + scheduler/
├── ND/                          # справочные материалы (не код)
│   ├── models/                  # справки по моделям: <model>_params.md
│   │                            #   (bge-m3, DeepSeek-V4-Pro, GPT-5-Nano,
│   │                            #    Llama-3-8B-Lunaris, Qwen2.5-Coder-3B-…,
│   │                            #    Step-3.5-Flash, LM-Studio/)
│   ├── other/                   # прочие заметки (1.txt, 2.txt, tunel_plan.md)
│   └── tasks/                   # задания куратора по неделям (n_1 … n_7)
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

- **сервер задания** `time` (`transport="http"`, endpoint из env `MCP_SERVER_URL`, дефолт
  `http://91.188.212.77:8000/mcp`, `enabled=true`, инструмент `get_time`) — **первым**;
- **реальный погодный HTTP-сервер** `weather` (endpoint из env `MCP_WEATHER_URL`, дефолт
  `https://weatherapi.projecteol.ru/mcp/`, `enabled=true`);
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

**Реальный сервер недели** — `https://weatherapi.projecteol.ru/mcp/` (Streamable HTTP,
protocol `2025-11-25`, `projecteol-weather v1.0.0`), 3 инструмента:
`search_locations` (поиск города → координаты), `get_forecast_metadata`,
`get_weather_forecast` (прогноз по координатам).

**Сервер задания** — `http://91.188.212.77:8000/mcp` (Streamable HTTP, protocol
`2025-06-18`, `serverInfo: Time Server`), 1 инструмент:
`get_time(timezone_name: string = "UTC") -> ISO 8601` (IANA: `UTC`, `Europe/Moscow`,
`Europe/London`, `Asia/Tokyo`). Живой вызов:
`get_time({"timezone_name":"Europe/Moscow"})` → `2026-09-27T12:52:07+03:00`.

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
# без флага: agent.mcp_gateway/tool_registry/tool_executor is None — поведение = предыдущая ревизия (день 15)
# local-провайдер в AI_9 не регистрируется (задел: local.* — только безопасные
# доменные операции, никогда local.set_stage / local.write_task_state_file)

# RAG (--rag): RagService собирается в Kod.py и передаётся агенту; без --rag rag/ не импортируется


Семейство `/mcp` (7 базовых форм + команды дня 20; токенов LLM не тратят):

- `/mcp status` — общее состояние подключения + по серверам + версия каталога и число тулов;
- `/mcp servers` — сконфигурированные серверы (transport, enabled, trust, allowed/denied);
- `/mcp tools` — **список доступных инструментов** (имя, description, input-схема);
- `/mcp refresh` — re-discovery → registry.refresh() (атомарный swap) → сейв catalog.json;
- `/mcp connect <id>` — поднять соединение (по умолчанию — все из servers.json); `<id>` — только целевой;
- `/mcp call <tool> [{json}]` — вызвать инструмент вручную через `ToolExecutor` (policy → вызов → аудит);
- `/mcp disconnect` — закрыть соединения (`gateway.stop()` → DISCONNECTED; тулы покидают каталог при refresh);
- `/mcp jobs` — список задач планировщика (`state`/`interval`/`runs`);
- `/mcp summary [N]` — последняя сохранённая сводка планировщика (без нового запроса к LLM);
- `/mcp pipeline <запрос>` — пайплайн `search → summarize → saveToFile`;
- `/mcp route <текст>` — объяснить выбор инструмента/сервера (без вызова).

Флаг `--mcp-probe` — **результат задания в one-shot форме**: подключиться → handshake →
`tools/list` → вывести список инструментов (имя, описание, схема) → корректно закрыться →
exit 0; при недоступном сервере — понятная ошибка, exit 1.

text
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


Без `--mcp`/`/mcp` — MCP-слой не собирается, агент работает ровно как в предыдущей ревизии (день 15)
(регрессия запрещена).

### RAG-слой (`rag/`)

Расширяемый RAG-модуль: индексация корпуса, гибридный поиск, блок `[rag]` в промпте
со ссылками, источники/цитаты и проверка опоры ответа (grounding).

**Конвейер:**


corpus (rag/datasets/corpus.list) → chunking (fixed | structural)
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


**Как запустить Ollama:**

bash
# Установка (выполняет оператор, требует sudo) и модель:
curl -fsSL https://ollama.com/install.sh | sh
ollama pull bge-m3
# Проверка: сервис слушает только localhost, модель доступна
curl -s http://127.0.0.1:11434/api/tags


> Юнит `ollama.service` (systemd) держит модель `bge-m3` (dim 1024). Управление:
> `sudo systemctl start|stop|restart|enable|disable ollama`. При остановке RAG
> деградирует на `HashingEmbedder` (юниты и гейт от Ollama не зависят).

**Команды и флаги:**

bash
./run.sh --rag-ingest                       # проиндексировать корпус (одна команда)
./run.sh --rag-search "как считается бюджет токенов"   # поиск без LLM (топ-5 со скорами)
./run.sh --rag-ask "как считается бюджет токенов"      # ответ + источники + цитаты (тратит LLM)
./run.sh --rag-verify                       # проверка источников/цитат на 10 вопросах
./run.sh --rag-eval                         # метрики на golden-датасете (recall/hit-rate/mrr/ndcg)
./run.sh --rag-compare                      # сравнение стратегий × режимов + вердикт
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

**Пример вывода:**


[RAG] Запрос «как запретить агенту менять технологический стек проекта» (режим hybrid): Найдено источников: 5
  1. [5a49d570…#0] core/invariants.py · раздел: … · score=0.0179
  2. [5a49d570…#7] core/invariants.py · раздел: … · score=0.0174



[RAG] Оценка по rag/datasets/queries.jsonl (k=5, режим hybrid):
  recall@k: 0.8824   hit_rate@k: 0.8824   mrr: 0.7240   ndcg@k: 0.9026
  латентность: p50=126 мс, p95=148 мс


### Сводная механика (итог)


one-shot результат задания:
python Kod.py --mcp-probe
  → load servers.json → HttpMCPTransport(time) → initialize → READY
  → list_tools → [get_time]  (+ weather: search_locations, get_forecast_metadata, get_weather_forecast)
  → нормализация → mcp.time.get_time / mcp.weather.search_locations / …
  → вывод: имя + description + input-схема → close → exit 0

REPL:
  /mcp connect   → gateway.start() → READY
  /mcp tools     → registry.snapshot().tools (при пустом — подсказка /mcp refresh)
  /mcp refresh   → discover() → registry.refresh() (атомарный swap) → Store.save_tool_catalog
  /mcp call <t>  → ToolExecutor.execute (policy → gateway.call_tool → аудит)
  /mcp status    → connection_state по серверам + version каталога
  /mcp disconnect→ gateway.stop() → DISCONNECTED

LLM tool-use:
  «найди город Москва» / «который час в Москве?» → промт с [tools] + function-calling
  → LLM сам предлагает tool_call → ToolExecutor.execute → gateway.call_tool (реальный сервер)
  → результат возвращается в модель → финальный ответ
  (аудит в tool_audit.jsonl; TaskStage не меняется — инструмент ≠ переход)

RAG:
  --rag → RagService.search → блок [rag] → ответ со ссылками → источники/цитаты → grounding
  (strict: одна авто-перегенерация; пустой поиск → «не знаю» без вызова LLM)


**Сводная механика контроля (главная граница):**


MCP предоставляет инструменты.      ← integrations/mcp (gateway, provider)
ToolRegistry каталогизирует.        ← core/tool_registry (атомарный snapshot)
ToolPolicy фильтрует.               ← core/tool_policy (enabled/схема/стадия/инварианты/подтверждение)
InvariantChecker запрещает опасное. ← core/invariants (ProposedAction + tool.deny.*)
ToolExecutor управляет вызовом.     ← core/tool_executor (policy → вызов → аудит)
MemoryPolicy решает, что запомнить. ← сырое — никогда в память; external_actions — реализовано
StateMachine решает, можно ли
менять этап.                        ← БЕЗ ИЗМЕНЕНИЙ: инструмент ≠ переход
Store сохраняет конфиг и каталог.   ← users/<id>/integrations/mcp/ + tasks/<task>/tool_audit.jsonl


### Три кратких описания архитектуры

#### Формула для самой краткой характеристики (1 строка)

> AI_9 — персонализированный CLI stateful-агент (память → профили → инварианты →
> контролируемый жизненный цикл) с RAG-поиском по документам, к которому MCP
> подключается не как отдельный фундаментальный слой, а как интеграционный источник
> инструментов: gateway соединяет (реальный HTTP-сервер), provider нормализует,
> registry каталогизирует, executor вызывает и аудитирует, LLM сам предлагает вызовы —
> а контроль остаётся за существующими механизмами.

#### Краткое и точное описание (одно предложение)

> AI_9 — CLI stateful-агент (RouterAI, step-3.5-flash), расширенный полным вертикальным
> срезом MCP-подсистемы (соединение с реальным MCP-сервером по Streamable HTTP,
> handshake initialize, discovery tools/list, нормализация тулов во внутреннюю модель
> ToolDescriptor, каталогизация в ToolRegistry с атомарным snapshot и персистентностью
> через Store, настоящий вызов инструмента tools/call через ToolExecutor с policy и
> аудитом и полный LLM tool-use) и RAG-модулем (индексация корпуса, локальные
> эмбеддинги bge-m3, гибридный поиск BM25⊕dense→RRF→реранк→MMR, блок `[rag]` в промпте
> со ссылками и проверка опоры ответа); результат — вывод списка инструментов
> (`--mcp-probe` / `/mcp tools`), вызов инструмента по запросу пользователя и ответ со
> ссылками на источники.

#### Полная картина архитектуры с механикой частей

Общая формула: пять основ (память → персонализация → состояние → инварианты →
контролируемый жизненный цикл) + интеграционный модуль MCP как внешний источник
инструментов, подключённый к универсальному ToolRegistry и защищённый существующими
правилами, + RAG-модуль как слой доступа к локальным знаниям с проверкой опоры.

1. **Хранилище (storage/)** — «где всё лежит». Каноническая иерархия `users/<id>/…` +
   ветка `integrations/mcp/`: `servers.json` (какие серверы, транспорт, таймауты,
   allowed/denied_tools) и `catalog.json` (снимок каталога: schema_version, version,
   tools, created_at). Механика устойчивости — битый/отсутствующий файл → схема по
   умолчанию, не падение. Gateway JSON напрямую не пишет — только через фасад Store.
   `tasks/<task>/tool_audit.jsonl` — история вызовов (task-scope), отдельно от
   `transition_log`.

2. **Память (memory/)** — «что агент помнит». 4 слоя, MERGE/append только через
   MemoryManager, дозированная доставка + токен-бюджет. MCP-политика памяти: сырой ответ
   → только текущий execution context; краткое резюме → short_term; нормализованный итог
   → working (`external_actions[]`); важный факт → long_term только по политике; секреты
   — никогда; профиль MCP менять не может.

3. **Ядро (core/)** — «кто решает». Прежние сущности без регрессии. Инструменты:
   - `tools.py` — контракты: ToolDescriptor (name, description, input_schema, source,
     provider, original_name + policy-поля risk_level / allowed_stages /
     requires_confirmation), ToolCallRequest / ToolExecutionResult, ToolExecutionState,
     ToolProvider (ABC), ToolCatalogSnapshot.
   - `tool_registry.py` — каталог: add_provider / unregister_provider / get /
     available_for / snapshot / refresh. Механика refresh: discover() у всех провайдеров
     → валидация схем → разрешение коллизий → сборка нового snapshot → атомарный swap.
     Реестр не проверяет бизнес-правила и не зовёт StateMachine. Недоступный провайдер →
     его тулы исключаются, остальные живы.
   - `tool_policy.py` — проверки вызова: enabled → схема → стадия → инварианты →
     подтверждение → PolicyDecision.
   - `tool_executor.py` — исполнение: policy → gateway.call_tool → результат → аудит
     tool_audit.jsonl; StateMachine не вызывает.
   - `tool_routing.py` / `tool_pipeline.py` — выбор инструмента и пайплайн.
   - `llm_client.py` — LLMReply + complete_with_tools (нативный tool-use + fallback);
     `prompt_builder.py` — блоки [tools]/[rag]; `agent.py` — агентный цикл
     _respond_with_tools + RAG-слой; `invariants.py` — ProposedAction + MCP-поля +
     правило tool.deny.*.

4. **Интеграции (integrations/)** — «как достучаться до внешнего мира».
   - mcp/config: MCPServerConfig + загрузка servers.json с дефолтами (time + weather +
     scheduler + pipeline + demo).
   - mcp/transport: ABC + StdioMCPTransport (обёртка над mcp SDK) + HttpMCPTransport
     (Streamable HTTP) + FakeMCPTransport (программируемые списки/отказы/таймауты).
     Фабрика make_transport; SDK импортируется только в transport.py (+ demo_server.py).
   - mcp/client: initialize / list_tools / call_tool; сбой → MCPConnectionError.
   - mcp/gateway: start/stop/status/discover/call_tool; MCPConnectionState; фильтр
     allowed/denied_tools; НЕ знает о TaskStage/профилях/памяти. Синхронный фасад
     MCPGatewaySync — постоянная фоновая задача для REPL и --mcp-probe.
   - mcp/provider: нормализация → ToolDescriptor (`mcp.<server>.<tool>`).
   - mcp/demo_server + mcp/scheduler_server + mcp/pipeline_server + scheduler/ — локальные
     MCP-серверы и ядро планировщика.

5. **RAG (rag/)** — «что агент знает из документов». config/validate (только
   `127.0.0.1:11434`) → corpus/chunking (fixed|structural) → embedding (Ollama bge-m3 +
   HashingEmbedder-фолбэк) → index (плоский: BM25-постинги + векторы, save/load) →
   retrieval/rerank (bm25|dense|hybrid: RRF + MMR) → cache (LRU+TTL, инвалидация по
   mtime) → grounding/eval/compare → service (RagService). Блок `[rag]` в промте — после
   `[tools]`, до `[long_term]`; связь с ядром — только через DI.

6. **Оркестратор и CLI** — «как этим пользуются». Agent — расширение: self.mcp_gateway /
   self.tool_registry / self.tool_policy / self.tool_executor (None при выключенном MCP)
   + агентный tool-use цикл; жизненный цикл не изменён (/plan → /approve → /step|/run →
   validation → done; инварианты; профили; память). DI: build_agent() при mcp_enabled
   строит MCPGatewaySync + MCPToolProvider + ToolPolicy + ToolExecutor, регистрирует
   провайдер, добавляет слой tools в доставку и делает стартовое gateway.start()/
   registry.refresh(); RagService собирается в Kod.py при `--rag`. Команды: `/mcp …`,
   `/rag …`; флаги `--mcp`, `--mcp-probe`, `--scheduler*`, `--rag*`. `/mcp`- и
   `/rag`-команды токенов LLM не тратят.

7. **Служебное пространство (dev/)** — «проект про проект». Миграция по процессной модели
   «план-эталон → рабочие планы этапов → журнал»; красный гейт → карточка ошибки.
   Тестовый контур: L1 импорт; L2 unit_runner (412 OK); L3 smoke; L4 scenario; гейт
   58/58; приёмка 48 критериев — всё без живого ключа и сети, в `.tmp/`, `users/` не
   затрагивается.

**Инвариант всей системы**: детерминизм недетерминированной LLM даёт код — внешний мир
подключается через адаптер, который не имеет права менять внутреннее состояние агента.

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

**MCP-инструменты:**

- `/mcp status` — состояние MCP-подключения + версия каталога;
- `/mcp servers` — сконфигурированные MCP-серверы;
- `/mcp tools` — **список доступных инструментов** (результат задания);
- `/mcp refresh` — re-discovery + атомарный swap + сейв catalog.json;
- `/mcp connect <id>` — поднять соединение с MCP-сервером (по умолчанию — все);
- `/mcp call <tool> [{json}]` — вызвать инструмент вручную через `ToolExecutor`;
- `/mcp disconnect` — закрыть MCP-соединения;
- `/mcp summary [N]` — последняя сохранённая сводка планировщика (без нового запроса к LLM);
- `/mcp jobs` — задачи планировщика (`state`/`interval`/`runs`);
- `/mcp pipeline <запрос>` — пайплайн `search → summarize → saveToFile`;
- `/mcp route <текст>` — объяснить выбор инструмента/сервера (без вызова).

**RAG:**

- `/rag status` — состояние RAG (вкл/выкл, режим, топ-k, grounding, индекс);
- `/rag on|off` — включить/выключить RAG в сессии;
- `/rag ingest` — проиндексировать корпус (инкрементально);
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

# MCP
python Kod.py --mcp-probe                  # one-shot: подключиться → список тулов → выйти
./run.sh --user alice --mcp                # REPL с MCP-слоем + полным LLM tool-use (/mcp …)
MCP_SERVER_URL=http://91.188.212.77:8000/mcp python Kod.py --mcp-probe  # сервер задания (get_time)
MCP_WEATHER_URL=https://weatherapi.projecteol.ru/mcp/ python Kod.py --mcp-probe  # явный endpoint погоды
python -m integrations.mcp.demo_server     # локальный MCP-сервер (stdio) отдельно

# Планировщик 24/7 и новые серверы
python Kod.py --mcp --scheduler            # фоновый worker 24/7 (сбор + сводка)
python Kod.py --mcp --scheduler --scheduler-interval 5   # укороченный интервал (демо)
python -m integrations.mcp.scheduler_server             # MCP-сервер планировщика (HTTP :8010)
python -m integrations.mcp.pipeline_server              # MCP-сервер пайплайна (HTTP :8020)

# RAG
./run.sh --rag-ingest                       # проиндексировать корпус
./run.sh --rag-ask "как считается бюджет токенов"   # ответ + источники + цитаты
./run.sh --rag-verify                       # проверка источников/цитат на 10 вопросах
./run.sh --rag --user alice                 # REPL с блоком [rag]


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
**Флаги локальных LLM и доступа (Ревизия 8):** `--model <id>` (модель/сервис сессии),
`--model-list` (печать реестра и выход), `--model-profile <name>` (`default`/`rag-strict`/`fast`),
`--local-gen` (переключить модель агента на локальную ⇒ генератор RAG локальный),
`--embed-provider {ollama,lmstudio,hashing}`, `--embed-model <name>`, `--embed-url <url>`
(провайдер/модель эмбеддингов RAG), `--temperature F`, `--max-tokens N`, `--context-window N`
(разовое переопределение параметров), `--local-template` (строгий prompt-шаблон под локальный
RAG-кейс), `--oneshot "<задача>"` (один обмен → ответ → выход), `--subagent-run "<задача>"`,
`--subagent-service {ollama,lmstudio}`, `--local-only` (запрет облачных моделей в сессии),
`--rag-gen-compare` + `--gen-modes cloud,local` + `--gen-profile <name>` + `--repeat N` +
`--gen-report <файл>` + `--gen-resources` (сравнение генераторов и замеры ресурсов).

> **НЕ ТРОГАТЬ (следы функционала).** Флаги `--temperature F`, `--max-tokens N`,
> `--context-window N` (разовое переопределение параметров) и связанная с ними информация
> (профили `temperature` / `max_tokens` / `context_window`) — следы функционала Дня 5
> (`ND/tasks/n_1/005_День 5/`), **ошибочно затёртого в одной из прошлых ревизий**.
> Их **не удалять, не переписывать и не «чистить»**: предстоит **восстановление
> в следующей ревизии**. Любое расхождение с текущим `Kod.py` — ожидаемо и не является
> поводом для правки.

**Фасад и шлюз (Ревизия 8):** `python serve.py [--mock] [--port 8090]` — тонкий HTTP-вход
агента на хосте (только `127.0.0.1`); `python -m gateway.app` — веб-шлюз на VPS (публичный
порт `8080`), обращается к фасаду через SSH reverse tunnel. Подробности — в разделе
«Локальные LLM и доступ к агенту» и `dev/vps/README_gateway.md`.

Все пути строятся от `BASE_DIR`; ключ — `API_KEY` из `.env` (`load_dotenv()`).
При `--mock`, отсутствии ключа или `API_KEY=test-key` автоматически выбирается `MockClient`.
`run.desktop` содержит абсолютные `Exec=`/`Path=` — после переноса на другой хост
его нужно пересоздать (в `.desktop` переменные окружения не раскрываются).

---

## Локальные LLM и доступ к агенту

> **Ревизия 8.** Эта возможность позволяет агенту работать не только с облачным
> провайдером (RouterAI), но и с локальной нейросетью на вашем компьютере —
> без интернета, без отправки данных в облако. Также добавлен веб-шлюз,
> через который к агенту можно подключиться с другого устройства.

### Что это даёт

- **Приватность.** Запросы с конфиденциальными данными не уходят в облако —
  они обрабатываются на вашем компьютере.
- **Работа без интернета.** Если отключить сеть, агент продолжает отвечать
  через локальную модель.
- **Доступ с телефона/другого ПК.** Через веб-шлюз на VPS-сервере любой
  пользователь может зайти на сайт, зарегистрироваться и общаться с агентом.

### Как это устроено (простыми словами)

```
Ваш компьютер                          VPS-сервер (91.188.212.77)
┌─────────────────────┐                ┌──────────────────────────┐
│  LM Studio          │                │  Веб-шлюз (порт 8080)    │
│  (локальная модель) │                │  (вход, чат, лимиты)     │
│  порт 1234          │                │                          │
│                     │  SSH-туннель   │                          │
│  Ollama             │◄──────────────►│                          │
│  (эмбеддинги)       │  (туннель)     │                          │
│  порт 11434         │                │                          │
│                     │                │                          │
│  Фасад (serve.py)   │                │                          │
│  порт 8090          │                │                          │
│  (только localhost) │                │                          │
│                     │                │                          │
│  Агент AI_9         │                │                          │
│  (память, задачи,   │                │                          │
│   профили, RAG)     │                │                          │
└─────────────────────┘                └──────────────────────────┘
```

1. **Локальная модель** (LM Studio) отвечает на запросы прямо на вашем компьютере.
2. **Фасад** (`serve.py`) — тонкая прослойка: принимает HTTP-запрос, передаёт агенту,
   возвращает ответ. Не хранит данные сам — всё в агенте.
3. **SSH-туннель** — ваш компьютер сам подключается к VPS и пробрасывает порт 8090
   наружу. Роутер трогать не нужно.
4. **Веб-шлюз** на VPS — сайт, куда заходят пользователи. Он пересылает запросы
   через туннель к фасаду, а ответ возвращает в браузер.

### Быстрый старт: локальная модель

#### Шаг 1. Поднять LM Studio

LM Studio — программа, которая запускает нейросеть на вашем компьютере.

```bash
# 1. Запустить HTTP-сервер (именно это и нужно агенту)
~/.lmstudio/bin/lms server start

# 2. (Опционально) Загрузить модель заранее — чтобы первый ответ был быстрее
~/.lmstudio/bin/lms load mradermacher/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-GGUF:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated.Q6_K.gguf --gpu 0 --context-length 8192

# 3. Проверить, что всё работает
~/.lmstudio/bin/lms server status   # → "running on port 1234"
~/.lmstudio/bin/lms ps              # → загруженная модель
curl -s http://127.0.0.1:1234/v1/models  # → HTTP 200, список моделей
```

> **Важно:** `lms chat` — это ручной чат в терминале, агенту он не нужен.
> Главное — `lms server start`. Без него агент не работает.
>
> LM Studio может «заснуть» или упасть. Если агент пишет «Сервис временно
> недоступен» — повторите `lms server start`.

#### Шаг 2. Переключить модель в агенте

```bash
# Посмотреть список доступных моделей
python Kod.py --model-list

# В REPL:
/model list          # все модели
/model use lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K
# или сразу при запуске:
python Kod.py --model lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K
```

#### Шаг 3. Субагенты (вспомогательные сессии)

Команда «сделай локально в LM Studio: <задача>» запускает отдельную сессию
на локальной модели. Также вручную:

```
/subagent run "проанализируй этот код" --service lmstudio
```

### Полностью локальный RAG

```bash
# Поиск по документам + ответ локальной моделью (без интернета)
python Kod.py --rag --local-gen --user alice
```

Эмбеддинги берутся из Ollama (`bge-m3`), генерация — из LM Studio.
Ни одного запроса в интернет.

### Сравнение: облако vs локальная модель

```bash
# Автоматическое сравнение на 10 вопросах × 3 повтора
python Kod.py --rag-gen-compare --gen-modes cloud,local --repeat 3
# Отчёт: dev/logs_reports/stages/rag_local_compare.md
```

### Оптимизация: профили параметров

> **НЕ ТРОГАТЬ.** Описание профилей (`temperature`, `max_tokens`, `context_window`) —
> следы функционала Дня 5 (`ND/tasks/n_1/005_День 5/`), ошибочно затёртого ранее;
> подлежат восстановлению в следующей ревизии. Не удалять и не переписывать.

В `models.json` три профиля:

- `default` — `temperature` и `max_tokens` берутся как есть у сервиса. Это точка «до»
  оптимизации, с ней сравнивают улучшения.
- `rag-strict` — `temperature` = 0.1, `max_tokens` = 700. Для ответов по источникам,
  где важна точность (фактология).
- `fast` — `temperature` = 0.3, `max_tokens` = 256. Для черновиков и субагентов.

Применить: `/model profile rag-strict` или `--model-profile rag-strict`.

### Доступ извне: веб-шлюз

#### Для пользователя

1. Открыть `http://91.188.212.77:8080`
2. Зарегистрироваться (логин + пароль)
3. Пройти интервью (стиль, ограничения, контекст)
4. Выбрать модель из выпадающего списка (LM Studio / Qwen2.5-Coder-3B…)
5. Задавать вопросы — ответ придёт с подписью модели

**Лимиты:** 6 запросов в минуту, максимум 8000 символов в запросе.

#### Для администратора (развёртывание на VPS)

Подробная инструкция — `dev/vps/README_gateway.md`. Кратко:

1. Создать отдельный venv: `/home/t/doc/.venv`
2. Установить `flask` и `requests`
3. Скопировать `gateway/` на VPS
4. Настроить systemd-юниты шлюза и туннеля
5. Проверить фаервол (порт 8080)

### Команды управления моделью

- `/model` — текущая модель, сервис, профиль;
- `/model list` — все модели реестра + статус;
- `/model use <id>` — переключить модель;
- `/model status` — проверить, жив ли сервис;
- `/model profile <name>` — применить профиль параметров;
- `/gen local` / `/gen cloud` — быстро переключить генератор RAG;
- `/embed status` — провайдер эмбеддингов;
- `/embed use ollama:bge-m3` — переключить эмбеддер.

### Учёт токенов и модель

Модель видна везде:
- Баннер при старте: `[Сессия] модель: lmstudio/Qwen2.5-Coder-3B…`
- Префикс ответа: `[lmstudio/Qwen2.5-Coder-3B…] Агент: …`
- Лог `Den_log.md`: `model=lmstudio/…`
- CSV `tokens.csv`: колонка `model`
- HTTP-ответ: поле `model`

### Конфигурационные файлы

**`models.json`** — реестр моделей и профилей (секретов нет):

```json
{
  "current": "cloud:stepfun/step-3.5-flash",
  "profiles": {
    "default": {},
    "rag-strict": {"temperature": 0.1, "max_tokens": 700, "context_window": 8192, "top_p": 0.9},
    "fast": {"temperature": 0.3, "max_tokens": 256, "context_window": 4096, "top_p": 0.9}
  },
  "models": [
    {"id": "cloud:stepfun/step-3.5-flash", "service": "cloud", "local": false, ...},
    {"id": "lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K",
     "service": "lmstudio", "local": true,
     "model": "mradermacher/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-GGUF:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated.Q6_K.gguf",
     "base_url": "http://127.0.0.1:1234", "quant": "Q6_K", "context_window": 8192,
     "profile": "rag-strict", "timeout_seconds": 600}
  ]
}
```

**`gateway/gateway.json`** — настройки шлюза (секретов нет):

```json
{
  "host_facade_url": "http://127.0.0.1:8090",
  "public_port": 8080,
  "limits": {"requests_per_minute": 6, "max_query_chars": 8000},
  "session": {"secret_env": "GATEWAY_SECRET", "secret_file": "gateway/.secret"}
}
```

### Ограничения

- **Скорость.** Локальная модель на CPU (без GPU) медленнее облачной в ~7 раз.
  Боевая модель — 3B параметров, Q6_K квантование, файл ~2,5 ГБ.
- **Rate-limit шлюза in-memory.** При перезапуске шлюза счётчик сбрасывается.
- **LM Studio может «заснуть».** Повторный `lms server start` лечит.
- **Квантование.** У боевой модели на диске один тег (Q6_K). Сравнение
  квантов невозможно — зафиксировано как ограничение среды.
- **Фасад обрабатывает один запрос одновременно.** Второй ждёт.
  Это ожидаемо — локальная модель считает одна.

### Как читать отчёты сравнения и логи

Все живые прогоны сохраняются в `dev/logs_reports/stages/` — это обычные текстовые
файлы, их можно открыть глазами. Главные из них:

- **`final_live_runs.md`** — сводка финальных прогонов всех пяти частей задания.
  С него удобно начинать: видно, что и где проверялось.
- **`rag_local_compare.md`** — сравнение «облако против локальной модели».
  В таблице каждая строка — один ответ. Разбираем колонки:
  - `must_contain` — сколько обязательных слов из вопроса реально попало в ответ
    (это качество): `2/2` — всё на месте, `1/2` — половина;
  - `Латентность, мс` — сколько ждали ответ в миллисекундах (это скорость):
    30000 мс = 30 секунд;
  - повторы одного вопроса с одинаковым ответом — это стабильность.
- **`optimize_before_after.md`** — замер «до/после» оптимизации. Сравнивайте
  `Латентность` и `must_contain` до применения профиля `rag-strict` и после него.
- **`subagent_*.md`** — логи субагентов. В начале — id, сервис и модель
  (`model=lmstudio/…`), дальше — весь обмен целиком.
- **`access_resilience.md`** — обрывы туннеля и параллельные запросы. Видно, как
  «убитый» туннель поднимается за 5–12 секунд, а седьмой запрос за минуту получает `429`.
- **`access_peer_confirm.md`** — подтверждение внешнего пользователя (ккк): живая
  переписка с чужого устройства через веб-шлюз.

Как читать «вердикт» (опору ответа на источники):

- `ok` — ответ целиком опирается на найденные источники;
- `partial` — опирается частично;
- `hallucination` — в ответе есть то, чего в источниках нет (модель «додумала»).

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
выход:  save_state() + сейв task_state.json (включая transition_log)


LLM за интерфейсом: `LLMClient (ABC)` → `RouterAIClient` (живой: POST + Bearer,
retry на HTTP 429 с задержками 2 → 4 → 8 сек, таймаут 30 сек, любой сбой → `None`)
и `MockClient` (детерминированная заглушка). Агент зависит только от абстракции —
провайдер инжектится на старте.

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
- **Интеграция (живой прогон, не гейт).** Команда: `timeout 60 python Kod.py --mcp-probe`
  (реальный HTTP-сервер). Результат: READY → 4 тула (1 `time` + 3 `weather`) →
  DISCONNECTED, exit 0.
- **Живой tool-use (не гейт).** Команда:
  `printf 'который час в Москве?\n/exit\n' | python Kod.py --user u --mcp`.
  Результат: LLM вызывает `mcp.time.get_time` → ответ.
- **Живой RAG (не гейт).** Команда:
  `python Kod.py --rag-ask "…"` / `--rag-eval` / `--rag-verify` (ключ из `.env`).
  Результат: ответ + источники + цитаты; hit-rate@5 = 0.8824; источники/цитаты 10/10.

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
- `unit/test_llm_local.py` — `OpenAICompatClient`/`OllamaClient` (12 тестов);
- `unit/test_model_switch.py` — `/model` + отображение модели (9 тестов);
- `unit/test_subagents.py` — запуск/таймаут/безопасность (10 тестов);
- `unit/test_rag_local_gen.py` — локальная генерация в RAG (19 тестов);
- `unit/test_rag_gen_compare.py` — сравнение генераторов (10 тестов);
- `unit/test_llm_optimize.py` — профили + prompt-шаблон (15 тестов);
- `unit/test_llm_resources.py` — замеры ресурсов (12 тестов);
- `unit/test_facade.py` — фасад: маршруты, очередь, подпись (15 тестов);
- `unit/test_gateway.py` — вход, регистрация, лимиты, прокси, вопросы интервью (20 тестов);
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
[`dev/Проверка.md`](dev/Проверка.md):

- **Часть 1 (5 критериев): локальная LLM запущена** — `lms server` отвечает, модель
  отвечает по HTTP и из CLI, ≥ 3 запроса разной сложности через `--oneshot`,
  справка о боевой модели в `ND/models/`;
- **Часть 2 (10 критериев): интеграция локальных LLM** — `ModelRegistry` импортируется,
  `models.json` ≥ 2 моделей, `/model list|use`, подпись модели в баннере, в префиксе
  ответа, в `Den_log.md`, в `tokens.csv`, субагент и его лог с подписью;
- **Часть 3 (6 критериев): полностью локальный RAG** — `--rag --local-gen` отвечает,
  ответ без интернета, нет внешних соединений, сравнение cloud/local, отчёт по трём
  осям, индекс не изменён (117 чанков);
- **Часть 4 (6 критериев): оптимизация** — три профиля загружаются, параметры в теле
  запроса, prompt-шаблон для локального RAG, облачный промпт не изменён, отчёт
  «до/после», боевая конфигурация в `models.json`;
- **Часть 5 (13 критериев): приватный AI-сервис и доступ извне** — фасад и `/ask`,
  `/models`, очередь под параллелью, вход и регистрация на шлюзе, лимит 6/мин,
  отклонение запроса > 8000 символов, туннель под systemd и его авторестарт,
  подтверждение внешнего пользователя, автономность без интернета, сохранность MCP;
- **Документация (8 критериев):** без `--model` промпт прежний, `TaskStage` не затронут,
  гейт зелёный, раздел R8 в README, понятный язык, секретов в конфигах нет,
  `.tmp` пуст, логи в `.gitignore`.

Машиночитаемый дубль — `dev/tests_debug/check_acceptance.sh`. Сценарии живой
демонстрации куратору — `dev/Проверка.md` (48 критериев Ревизии 8).

### Демонстрации задания

**MCP — подключение и инструменты:**

- **Соединение устанавливается.** Как посмотреть: `python Kod.py --mcp-probe`.
  Что видно: «[MCP] Соединение установлено (READY)» — handshake `initialize` прошёл
  (реальный сервер).
- **Список инструментов корректно возвращается.** Как: `--mcp-probe` или `/mcp tools`
  после `/mcp refresh`. Что видно: 4 тула — `mcp.time.get_time` плюс
  `mcp.weather.search_locations`, `get_forecast_metadata`, `get_weather_forecast`
  (имя, description, input-схема).
- **Список выводится кодом.** Как: `python Kod.py --mcp-probe` (exit 0).
  Что видно: печать каждого тула + «Всего инструментов: 4» + чистое закрытие (DISCONNECTED).
- **Настоящий вызов инструмента.** Как:
  `/mcp call mcp.weather.search_locations {"query":"Москва"}`.
  Что видно: результат с координатами Москвы (55.75204, 37.61781).
- **Полный LLM tool-use.** Как: `--mcp` → «найди город Москва».
  Что видно: LLM сам вызывает `search_locations` → ответ с координатами Москвы.
- **Инструмент задания.** Как: `--mcp` → «который час в Москве?».
  Что видно: LLM сам вызывает `mcp.time.get_time` → ответ (результат использован).
- **Ручной вызов `get_time`.** Как:
  `/mcp call mcp.time.get_time {"timezone_name":"Europe/Moscow"}`.
  Что видно: ISO 8601 `2026-09-27T12:52:07+03:00`; `{}` → время в `UTC`.
- **REPL-флоу MCP.** Как: `--mcp` → `/mcp connect` → `/mcp tools` → `/mcp refresh` →
  `/mcp status` → `/mcp disconnect`. Что видно: READY → каталог (4 тула) → атомарный
  refresh + сейв catalog.json → статус → DISCONNECTED.
- **Изоляция прав.** Как: `denied_tools` в `servers.json` → `/mcp refresh` → `/mcp tools`.
  Что видно: запрещённый тул не попадает в discovery.
- **Недоступный сервер — деградация.** Как: `/mcp connect` при упавшем сервере.
  Что видно: FAILED/DEGRADED, тулов нет, REPL жив.
- **Планировщик 24/7.** Как: `python Kod.py --mcp --scheduler` → `/mcp jobs` →
  `/mcp summary`. Что видно: фоновые задачи поднимаются внешним worker; сводка отдаётся
  без запроса к LLM.
- **Пайплайн инструментов.** Как: `/mcp pipeline <запрос>`. Что видно: цепочка
  `search → summarize → saveToFile`, данные передаются между шагами, аудит — 3 записи
  `succeeded`.
- **Несколько серверов.** Как: `/mcp servers` / `/mcp tools` / `/mcp route <текст>`.
  Что видно: инструменты квалифицированы `mcp.<server>.<tool>`, маршрутизация и
  объяснение выбора.

**Память, инварианты, состояние:**

- **Какие данные попадают в слой.** Как: `/memory`, журнал `Den_log.md`.
  Что видно: `[Память] … ← …` по каждому слою.
- **Как память влияет на ответы.** Как: `/compare`. Что видно: два ответа — с `long_term`
  и без него.
- **Дозированная доставка.** Как: `/deliver profile,working`. Что видно: слой `long_term`
  физически отсутствует в промте.
- **Недопустимый переход блокируется кодом.** Как: `/plan <цель>` → `/goto implementation`
  → `/state`. Что видно: «ОТКАЗАНО», правило, состояние не изменилось, запись `allowed: false`.
- **Утверждение плана — контрольный пункт.** Как: `/plan` → `/run` (остановка) →
  `/approve` → `/run`. Что видно: `/run` не обходит утверждение.
- **Конфликт запроса и инварианта.** Как: «Перепиши наш API на FastAPI» (при инварианте
  Django). Что видно: отказ — id правила, причина, альтернатива.

**RAG:**

- **RAG: индексация корпуса.** Как: `./run.sh --rag-ingest`. Что видно: дельта индексации
  + число чанков (117 / 9 документов).
- **RAG: гибридный поиск.** Как: `./run.sh --rag-search "как считается бюджет токенов"`.
  Что видно: топ-5 источников со скорами и метаданными (`source`/`section`/`chunk_id`).
- **RAG: ответ с источниками и цитатами.** Как:
  `./run.sh --rag-ask "как считается бюджет токенов"`. Что видно: ответ + список
  источников (`source`+`section`/`chunk_id`) + дословные цитаты из чанков.
- **RAG: проверка формата на 10 вопросах.** Как: `./run.sh --rag-verify`.
  Что видно: источники 10/10, цитаты 10/10, смысл = цитаты (отчёт).
- **RAG: режим «не знаю».** Как:
  `./run.sh --rag-ask "квантовые киты в борще" --rag-threshold 0.99`.
  Что видно: `insufficient`, «В источниках нет ответа…», LLM не вызывается.
- **RAG: блок `[rag]` в промпте.** Как: `./run.sh --rag --user demo` → вопрос.
  Что видно: блок `[rag]` после `[tools]`, до `[long_term]`; ответ со ссылками
  `[doc_id#chunk_id]`.
- **RAG: проверка опоры (grounding).** Как: `/rag check <ответ с выдуманным числом>`.
  Что видно: `Вердикт: hallucination`, «числа вне источников».
- **RAG: метрики и сравнение.** Как: `./run.sh --rag-eval` / `--rag-compare`.
  Что видно: recall/hit-rate/mrr/ndcg; таблица «стратегия × режим» + вердикт.
- **RAG: длинные диалоги.** Как: `python dev/tests_debug/dialog_runner.py`.
  Что видно: 2 сценария (12 и 13 сообщений) — поиск на каждом обмене, источники в каждом
  ответе, цель/термины в памяти.
- **RAG: без `--rag` — регрессия.** Как: `./run.sh --user demo` (без флага).
  Что видно: блок `[rag]` отсутствует, `rag` не импортируется.

**Локальные LLM и доступ (Ревизия 8):**

- **Локальная модель.** Как: `python Kod.py --model-list`. Что видно: список моделей из
  `models.json` (lmstudio, ollama, routerai).
- **Переключение модели.** Как: `python Kod.py --model lmstudio:Qwen2.5-Coder-3B`.
  Что видно: баннер показывает подпись модели; промпт без `api_key`.
- **Субагент на локальной модели.** Как:
  `python Kod.py --subagent-run "проанализируй код" --service lmstudio`.
  Что видно: отдельная сессия, лог в `dev/tests_debug/.tmp/`.
- **Локальный RAG.** Как: `python Kod.py --rag --local-gen --user alice`.
  Что видно: эмбеддинги из Ollama, генерация из LM Studio, без интернета.
- **Сравнение генераторов.** Как:
  `python Kod.py --rag-gen-compare --gen-modes cloud,local --repeat 3`.
  Что видно: отчёт — три оси (качество, скорость, стабильность).
- **Профиль параметров.** Как: `python Kod.py --model-profile rag-strict`.
  Что видно: профиль в теле запроса (temperature, max_tokens, context_window).
- **Фасад (HTTP-вход).** Как: `python serve.py` → `curl http://127.0.0.1:8090/ask`.
  Что видно: запрос → агент → ответ; подпись модели в ответе.
- **Шлюз (веб-вход).** Как: `python -m gateway.app` → браузер `http://<VPS>:8080`.
  Что видно: регистрация, чат, лимит 6/мин, прокси к фасаду.
- **Одношаговый режим.** Как: `python Kod.py --oneshot "какой сегодня день?"`.
  Что видно: один обмен → ответ → выход (exit 0).

---

## Служебное пространство `dev/` (проект про проект)

### Дерево `dev/`


AI_9/dev/
├── migr_plan.md                  # план-эталон миграции
├── migr_plan_0.md … migr_plan_12.md  # исполняемые планы этапов (конец этапа — гейт в следующий)
├── review/                       # ревью документации (migr_review.md + рабочие планы 0–9)
├── migr_log.md                   # журнал миграции «было → стало → проверка → статус»
├── Проверка.md                   # чек-лист приёмки (48 критериев Ревизии 8)
├── old_vers/                     # история прошлых ревизий (1…8)
├── meta_promt/                   # метапромты (вспомогательные промты)
├── tests_debug/
│   ├── check_acceptance.sh       # гейт приёмки (58 проверок)
│   ├── unit_runner.py            # L2-раннер (без pytest)
│   ├── smoke.py                  # L3-смоук (+ MCP-прогон + tool-use)
│   ├── scenario.py               # L4-сценарии (+ mcp_discovery, llm_tool_use, tool_denied, multiserver_flow)
│   ├── dialog_runner.py          # прогон 2 длинных диалоговых сценариев (часть 4)
│   ├── unit/                     # 42 модуля test_*.py (канонический раннер — unit_runner.py)
│   │   ├── … прежние модули (MCP/RAG off)
│   │   ├── test_mcp.py           # контракты + реестр + gateway + call_tool + policy + tool-use
│   │   ├── test_rag_*.py         # integration / grounding / cache / rerank / verify / working_memory
│   │   └── Ревизия 8 (9 модулей):
│   │       ├── test_llm_local.py         # локальные клиенты + ModelRegistry
│   │       ├── test_model_switch.py      # /model, отображение, регрессия
│   │       ├── test_subagents.py         # запуск/таймаут/безопасность
│   │       ├── test_rag_local_gen.py     # локальная генерация в RAG
│   │       ├── test_rag_gen_compare.py   # сравнение генераторов
│   │       ├── test_llm_optimize.py      # профили, шаблон, метрики
│   │       ├── test_llm_resources.py     # замеры ресурсов
│   │       ├── test_facade.py            # фасад: маршруты, очередь, подпись
│   │       └── test_gateway.py           # вход, регистрация, лимиты, прокси
│   ├── scenario/                 # 9 сценариев ручной демонстрации
│   │   ├── scen_1.md             # сценарий ручной демонстрации MCP
│   │   ├── scen_rag.md           # сценарий ручной демонстрации RAG
│   │   ├── scen_dialog_A.md      # длинный диалог A (12 сообщений, RAG-модуль)
│   │   ├── scen_dialog_B.md      # длинный диалог B (13 сообщений, инварианты)
│   │   ├── scen_local_llm.md     # локальная модель + субагент (Ревизия 8)
│   │   ├── scen_rag_local.md     # полностью локальный RAG (Ревизия 8)
│   │   ├── scen_optimize.md      # профили параметров + prompt-шаблон (Ревизия 8)
│   │   ├── scen_multiserver_flow.md # мультисерверный поток (Ревизия 7)
│   │   └── scen_access.md        # фасад + шлюз + туннель (Ревизия 8)
│   ├── fixtures/                 # фикстуры (пусто — заполняется по мере надобности)
│   └── .tmp/                     # единственное место прогонов (.gitignore)
├── logs_reports/                 # stages/ (56 файлов) + errors/ + archive/
└── vps/                          # инфраструктурный контур VPS
    ├── deploy_services.sh        # выкатка сервисов
    ├── mcp_vps.sh                # управление MCP на VPS
    ├── services.list             # список сервисов
    ├── ssh_config.snippet        # конфиг SSH-туннеля (хост)
    ├── sshd_gateway.snippet      # справка по GatewayPorts (VPS)
    ├── README_vps.md             # инструкция по VPS
    ├── README_gateway.md         # инструкция по шлюзу
    ├── units/                    # 5 systemd-юнитов:
    │   ├── ai9-gateway.service           # шлюз на VPS (:8080)
    │   ├── ai9-tunnel.service            # SSH reverse tunnel (хост)
    │   ├── mcp-time-server.service       # MCP :8000
    │   ├── mcp-scheduler-server.service  # MCP :8010
    │   └── mcp-pipeline-server.service   # MCP :8020
    └── evidence/                 # артефакты проверки MCP на VPS (5 probe/call)


### `tests_debug/` — что именно протестировать (канон задания)

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
- **MCP off по умолчанию**: без `--mcp` реестр пуст, агент отвечает как в предыдущей ревизии (день 15);
- **RAG**: импорт `rag`; индекс строится и переживает save/load; поиск отдаёт хит с
  метаданными; две стратегии чанкинга; отчёт сравнения; без `--rag` нет `[rag]`;
  `TaskStage` не затронут; `--rag-eval` hit-rate@5 ≥ 0.80.

Интеграционный тест (не гейт, живой прогон): `HttpMCPTransport` подключается к реальному
серверу `weatherapi` → initialize → list_tools → 3 тула; `call_tool("search_locations",
{"query":"Москва"})` → координаты Москвы. `HttpMCPTransport` к серверу задания
`http://91.188.212.77:8000/mcp` → READY → list_tools → 1 тул `get_time`;
`call_tool("get_time", {"timezone_name":"Europe/Moscow"})` → ISO 8601. Живой LLM tool-use
(«найди город Москва», «который час в Москве?») — тоже вне гейта (приёмка). Транскрипты —
`dev/logs_reports/stages/`.

### `logs_reports/`

- `migr_log.md` — журнал миграции «было → стало → проверка → статус» по этапам
  (М0–М12 и т.д.), результаты `test_mcp.py`, RAG-тестов, сценариев и живых прогонов;
- `errors/error_<timestamp>.md` — карточки ошибок (красный гейт этапа → карточка);
- `stages/` (+ `rag_*` транскрипты), `archive/` — живой прогон, отчёты этапов.

---

## Карта артефактов

### Рабочие артефакты (продукт)

- `Kod.py` + `core/` + `memory/` + `storage/` — агент дней 11–15 без регрессии, плюс
  каталог инструментов, tool-use и RAG.
- `core/tools.py` — внутренняя модель: ToolDescriptor, ToolCallRequest, ToolExecutionResult,
  ToolExecutionState, ToolProvider, ToolCatalogSnapshot.
- `core/tool_registry.py` — ToolRegistry: каталогизация, атомарный snapshot, refresh.
- `core/tool_policy.py` — ToolPolicy: проверки вызова (enabled, схема, стадия, инварианты,
  подтверждение).
- `core/tool_executor.py` — ToolExecutor: policy → вызов → аудит.
- `core/tool_routing.py` и `core/tool_pipeline.py` — выбор инструмента и пайплайн из
  инструментов.
- `integrations/mcp/*` — MCP-слой: config, transport (stdio + HTTP + fake), client, gateway,
  provider, demo_server, scheduler_server, pipeline_server, time_server, auth.
- `integrations/scheduler/*` — ядро планировщика (на stdlib): models, store, runner,
  aggregator.
- `rag/*` — RAG-модуль: config, corpus, chunking, embedding, index, retrieval, rerank,
  rewrite, cache, grounding, eval, compare, sources, citations, verify, service.
- `core/model_registry.py` + `models.json` — реестр моделей (Ревизия 8): провайдеры,
  параметры, профили.
- `core/llm_client.py` — клиенты LLM: `OpenAICompatClient` (LM Studio), `OllamaClient`,
  RouterAI.
- `core/subagents.py` — субагенты: запуск отдельной сессии, таймаут, лог с подписью модели.
- `core/profile_router.py` и `core/resources.py` — профили параметров и замеры ресурсов
  (Ревизия 8).
- `serve.py` — фасад: HTTP-вход агента на хосте (`127.0.0.1:8090`), `/ask` и `/models`.
- `gateway/*` — веб-шлюз на VPS: `app.py` (чат, прокси), `users.py` (регистрация),
  `questions.py` + `questions.json` (интервью, единый источник истины),
  `sync_questions.py` (обновление снапшота вопросов), `config.py` + `gateway.json`
  (лимиты, адрес фасада), `templates/` (login, register, interview, chat).
- `dev/vps/*` — инфраструктура доступа: скрипты деплоя (`deploy_services.sh`,
  `mcp_vps.sh`), `services.list`, `ssh_config.snippet`, `sshd_gateway.snippet`,
  `units/` (5 systemd-юнитов: шлюз, туннель, 3 MCP-сервера), `evidence/`
  (артефакты проверки MCP на VPS), `README_vps.md`, `README_gateway.md`.
- `users/<id>/integrations/mcp/{servers,catalog}.json` — конфиг серверов и снимок каталога
  (через Store).
- `users/<id>/tasks/<task>/tool_audit.jsonl` — история вызовов инструментов (через Store).
- `ND/models/*_params.md` — справки по моделям: окно контекста, параметры, доступные
  кванты, требования по RAM (боевая — `Qwen2.5-Coder-3B-…-abliterated_params.md`).
- `run.sh` и `run.desktop` — запуск (без изменений / пересоздать при переносе).
- `README.md` — единый источник данных о проекте (этот файл).

### Служебные артефакты (процесс)

- `dev/Проверка.md` — чек-лист приёмки: 48 критериев Ревизии 8.
- `dev/migr_plan.md` и `migr_plan_*.md` — план-эталон и рабочие планы миграции.
- `dev/migr_log.md` — журнал миграции и итоги ревизий (+ журнал ревью документации).
- `dev/review/migr_review.md` и `migr_review_*.md` — мастер-план и рабочие планы
  ревью документации (приведение README к реальной картине проекта).
- `dev/tests_debug/*` — L2 (42 модуля, +9 новых R8), L3, L4 (9 сценариев), гейт 58/58.
- `dev/logs_reports/stages/*` — транскрипты живых прогонов (56 файлов).
- `agents.md` — краткая памятка агенту (вспомогательный документ, 20 строк).
- `ND/tasks/n_1 … n_7` — задания куратора по неделям (источник требований).
- `ND/other/tunel_plan.md` — наработки по туннелю (учтены в `dev/vps/`).

---

## Порядок достижения итогового состояния

Порядок по зависимостям (от контрактов к CLI):

1. **Базовый агент дней 11–15** — память, профили, инварианты, машина состояний, LLM-клиент.
2. **Контракты инструментов** — `core/tools.py` (без SDK) → `core/tool_registry.py`
   (реестр + snapshot) → `integrations/mcp/` (config → transport + fake + HTTP → client →
   gateway → provider → demo_server).
3. **Контроль и исполнение** — `core/tool_policy.py` + `core/tool_executor.py`.
4. **LLM tool-use** — `core/llm_client.py` (tool-use) → `core/prompt_builder.py`
   (блок `[tools]`) → `core/agent.py` (агентный цикл) → `storage/store.py` (каталог + аудит).
5. **CLI** — `Kod.py` (DI + `/mcp`-семейство + `--mcp`/`--mcp-probe`).
6. **День 20** — `integrations/scheduler/` + `scheduler_server.py` (планировщик),
   `core/tool_pipeline.py` + `pipeline_server.py` (пайплайн), мультисерверность
   (`config.py` + `agent.py` + `tool_routing.py`).
7. **RAG** — `rag/` (config → corpus → chunking → embedding → index → retrieval → rerank
   → rewrite → cache → grounding → eval → compare → sources → citations → verify → service)
   + DI-фасад в `Kod.py` + блок `[rag]` в `prompt_builder.py` + `core/agent.py`
   (grounding, источники/цитаты, память задачи) + `memory/working.py` (goal/terms).
8. **Финал** — прогон всех проверок (L1→L2→L3→L4→гейт), приёмка, живой прогон (реальный
   сервер + реальный LLM), запись итога в `dev/migr_log.md`, предложение коммита (коммит —
   только по явной команде пользователя).

**Ревизия 8 (локальные LLM и доступ к агенту):**
0. **Реестр моделей** — `core/model_registry.py` + `models.json` (add/remove/switch/list);
   `--model-list` / `--model <id>` / `--model-profile <name>`; подпись модели в баннере;
   без `--model` промпт байт-в-байт прежний.
1. **Локальная генерация** — `--local-gen` переключает модель агента на локальную ⇒
   генератор RAG локальный; `--embed-provider` / `--embed-model` / `--embed-url` настраивают
   эмбеддинги; `--local-template` — строгий prompt-шаблон.
2. **Сравнение генераторов** — `--rag-gen-compare` + `--gen-modes` + `--gen-profile` +
   `--repeat` + `--gen-report` + `--gen-resources` (три оси: качество, скорость, стабильность).
3. **Субагенты** — `--subagent-run` / `--subagent-service` (отдельная сессия, лог с подписью).
4. **Одношаговый режим** — `--oneshot` (один обмен → ответ → выход).
5. **Фасад** — `serve.py` (HTTP-вход на хосте, `127.0.0.1:8090`, только localhost).
6. **Шлюз** — `gateway.app` (веб-вход на VPS, порт `8080`, регистрация, лимит 6/мин,
   прокси к фасаду через SSH reverse tunnel).
7. **Финал** — прогон всех проверок (L1→L2→L3→L4→гейт), приёмка, живой прогон, запись итога.

---

## Риски и откат

- **Регрессия ядра дней 11–15** — снимается тем, что MCP/RAG выключены по умолчанию
  (`mcp_enabled=False`, `--rag`); без флагов поведение = предыдущая ревизия (день 15), прежние тесты и
  критерии проходят без сети. Откат — не включать флаги.
- **Зависимость от внешнего MCP-сервера** — недоступный сервер → `FAILED`/`DEGRADED`,
  тулы исключаются, REPL жив (деградация, не падение). Откат — `/mcp disconnect`.
- **Зависимость от Ollama (RAG)** — при недоступности `127.0.0.1:11434` деградация на
  `HashingEmbedder`; юниты и гейт от Ollama не зависят. Откат — не использовать `--rag`.
- **Протечка модели MCP в `core`** — исключена: SDK импортируется только в
  `integrations/mcp/`; `ToolDescriptor` — внутренняя модель. Проверяется тестами.
- **Загрязнение рабочих данных** — тесты пишут только в `dev/tests_debug/.tmp/`,
  `users/` не затрагивается (проверяется идемпотентным гейтом).
- **Недетерминированность LLM** — детерминированный тестовый контур на `MockClient` +
  `FakeMCPTransport`; живой LLM — только приёмка.
- **Зависимость от LM Studio (Ревизия 8)** — при недоступности `127.0.0.1:1234` понятная
  ошибка «Сервис временно недоступен» (LM Studio мог «заснуть»), REPL жив; откат —
  `--model routerai:...` (облако). Юниты и гейт от LM Studio не зависят (`FakeTransport`).
- **Регрессия при переключении модели (Ревизия 8)** — без `--model` промпт строится
  байт-в-байт как в Ревизии 7 (проверяется тестом равенства промпта); реестр моделей —
  только добавление слоя, контракты `LLMClient` не тронуты.
- **Публичный доступ (Ревизия 8)** — фасад слушает **только** `127.0.0.1:8090` и наружу не
  выходит; извне доступен только шлюз (`8080`) с аутентификацией и лимитом 6 запросов/мин;
  SSH reverse tunnel инициируется хостом (входящих правил фаервола для хоста не создаётся).
- **Секреты в конфигурации (Ревизия 8)** — `models.json`, `gateway.json` и `.env` не
  содержат ключей (ключ только в `.env`, в `.gitignore`); проверяется отдельной проверкой гейта.

---

## Известные шероховатости и заделы

**Заделы по замыслу (программа следующих дней недели 4):**

- **`ToolMemoryPolicy`**: сырые ответы MCP никогда не пишутся в память автоматически
  (только нормализованные `external_actions` + аудит);
- **`ToolPromptPolicy` + блок `[external_context]`** (MCP resources): дозированная
  доставка описаний тулов под токен-бюджет (базовые лимиты `max_tools`/
  `max_schema_tokens` реализованы); сравнение токен-флоу MCP vs Skill + CLI — цель недели;
- **полный async core**: async gateway за синхронным фасадом `MCPGatewaySync`
  (меньше регрессионного риска при том же контракте);
- **параллелизм read-only тулов**; **local-провайдер** (`local.*` — только безопасные
  доменные операции, никогда `local.set_stage` / `local.write_task_state_file`);
- **расширение policy pipeline** (риск-уровни, подтверждения, `ToolPolicy` как
  полноценный движок) — реализован минимальный набор ступеней;
- `PolicyEngine` в `memory/base.py` — пустой интерфейс-задел (рабочий слой
  инвариантов — отдельный модуль `core/invariants.py`);
- `parent_id` сообщений — задел ветвления диалога; `skills[]` — декларативный
  пайплайн (движок оркестрации — следующие дни); `transition_log` растёт без
  ограничения (сжатие — следующие дни).

**Расхождения spec/кода (на поведение не влияют):**

- `mcp` SDK импортируется в `transport.py` и `demo_server.py` (уровень транспорта),
  а не в `client.py`: фактический API SDK 2.2.0 (`stdio_client` + `ClientSession`) живёт
  на уровне транспорта, клиент делегирует; инвариант «SDK только в `integrations/mcp/`»
  соблюдён;
- `handle_mcp_command` (`/mcp servers`, `/mcp connect`) читает приватное
  `gateway.gateway._servers` — допустимо для CLI-слоя, кандидат на публичный accessor;
- смоуки этапов миграции (`m*_smoke.py` в `dev/tests_debug/.tmp/`) — рабочие артефакты
  этапов, вне дерева §3.1; оставлены как доказательства этапов.

**Косметика:**

- каталоги `dev/tests_debug/fixtures/` и `smoke/` созданы каркасом и остались пустыми;
  в `.tmp/` накапливаются каталоги прошлых прогонов (в `.gitignore`);
- `dev/meta_promt/` в этой копии содержит `МЕТА-ПРОМТ_den_N.md`, `PROMT_otch.md`
  и `screen-ASKII.txt`;
- изменения миграции не закоммичены (коммит — только по явной команде пользователя).

---

## Результат

- **Код, подключающийся к MCP и выводящий список доступных инструментов** — `--mcp-probe`
  (one-shot, exit 0/1) и `/mcp tools` (REPL); соединение устанавливается (handshake
  `initialize` → `READY`), список корректно возвращается (`tools/list` → нормализация →
  каталог) — **на реальных серверах** `https://weatherapi.projecteol.ru/mcp/` (3 инструмента)
  и сервере задания `http://91.188.212.77:8000/mcp` (`get_time`).
- **Настоящий вызов инструмента и полный LLM tool-use**: `tools/call` на живом сервере
  (`search_locations({"query":"Москва"})` → координаты Москвы; `get_time({"timezone_name":
  "Europe/Moscow"})` → `2026-09-27T12:52:07+03:00`); в REPL сообщение «найди город
  Москва» / «который час в Москве?» → LLM сам вызывает инструмент → ответ с результатом.
- **Планировщик, пайплайн, мультисерверность**: фоновый worker 24/7 (не LLM); цепочка
  `search → summarize → saveToFile` с передачей данных; выбор и маршрутизация инструмента
  по `mcp.<server>.<tool>`, длинный флоу в одном запросе.
- **RAG-модуль**: индексация корпуса (117 чанков / 9 документов), гибридный поиск
  (BM25⊕dense → RRF → реранк → MMR → порог), query rewrite, блок `[rag]` со ссылками
  `[doc_id#chunk_id]`, **источники** (`source`+`section`/`chunk_id`) и **дословные цитаты**
  из чанков, режим «не знаю» при слабом контексте, grounding (`ok|partial|hallucination`)
  и одна авто-перегенерация в `strict`; сравнение 4 режимов (no_rag/rag/rag_filter/
  rag_filter_rewrite) на 10 контрольных вопросах; RAG в каждом обмене + память задачи
  (цель/уточнения/ограничения/термины) + 2 длинных диалоговых сценария.
- **Не скрипт, а вертикальный срез подсистемы**: `MCPGateway` (адаптер, не контролёр)
  → `MCPToolProvider` (нормализация во внутреннюю `ToolDescriptor`) → `ToolRegistry`
  (каталог + атомарный snapshot + персистентность через `Store`) → `ToolExecutor`
  (policy + аудит) → LLM tool-use.
- **Ревизия 8 — локальные LLM и доступ к агенту**: реестр моделей (`models.json` +
  `core/model_registry.py`); `--model-list` / `--model <id>` / `--model-profile <name>`;
  `--local-gen` переключает генератор на локальную модель; `--embed-provider` /
  `--embed-model` / `--embed-url` настраивают эмбеддинги; `--local-template` — строгий
  prompt-шаблон; `--oneshot` — один обмен → ответ → выход; субагенты (`--subagent-run`)
  с логированием; `serve.py` — фасад (HTTP, `127.0.0.1:8090`); `gateway.app` — веб-шлюз
  на VPS (порт `8080`, регистрация, лимит 6/мин, прокси к фасаду через SSH reverse tunnel);
  сравнение генераторов (`--rag-gen-compare`), профили параметров, замеры ресурсов.
- **Пять «кубиков» дней 11–15 без регрессии**: память, профили, инварианты, строгая
  машина состояний, LLM-клиент — контракты не тронуты; MCP и RAG выключены по умолчанию.
- **Инструмент ≠ переход**: `TaskStage` (8 стадий) не меняется от вызовов MCP/RAG;
  успех вызова не создаёт запись в `transition_log`.
- **Изоляция прав через тулинг**: `allowed_tools`/`denied_tools` в конфиге сервера;
  модель MCP не протекает в `core`; `MCPGateway` не знает о стадиях/профилях/памяти.
- **Деградация, не падение**: недоступный сервер → FAILED/DEGRADED, REPL жив;
  недоступная Ollama → `HashingEmbedder`.
- **Проверяемость**: L1 OK / L2 412 OK / L3 SMOKE OK / L4 SCENARIO OK, гейт **58/58**,
  приёмка **48 критериев** — без живого ключа и сети; живой прогон (реальный HTTP-сервер +
  реальный LLM) — отдельно.
- **Заделы с зарезервированными местами**: `ToolMemoryPolicy`, `ToolPromptPolicy`/resources,
  параллелизм read-only тулов, local-провider, полный async core, сравнение токен-флоу
  MCP vs Skill + CLI.
