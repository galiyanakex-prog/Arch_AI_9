# AI_9 — Developer Factory (Неделя 7, Ревизия 9)

> AI_9 — персонализированный CLI stateful-агент (память → профили → инварианты →
> контролируемый жизненный цикл) с RAG-поиском по документам, MCP-интеграцией и
> **сквозным конвейером автоматизированной разработки ПО** — от интервью и требований
> до кода, тестов, ревью, документации и diff/PR.

---

## Содержание

- [Суть проекта](#суть-проекта)
- [Модель памяти](#модель-памяти)
- [Персонализация](#персонализация)
- [Инварианты и ограничения состояния](#инварианты-и-ограничения-состояния)
- [Контролируемые переходы состояний](#контролируемые-переходы-состояния)
- [Второй уровень FSM: DevelopmentStage](#второй-уровень-fsm-developmentstage)
- [Модульность и слои](#модульность-и-слои)
- [Архитектура](#архитектура)
- [Команды REPL](#команды-repl)
- [Запуск](#запуск)
- [Агентный цикл](#агентный-цикл)
- [Тестирование и приёмка](#тестирование-и-приёмка)
- [Служебное пространство `dev/`](#служебное-пространство-dev)
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
**подключением к внешнему миру через MCP** и **RAG-модулем** — расширенный
**сквозным конвейером автоматизированной разработки ПО** (`Developer Factory`).

Конвейер охватывает полный цикл:
`идея → требования → архитектура → план → код → тесты → ревью → документация → diff/PR → подтверждение`.

Память разделена на четыре физически отдельных слоя (краткосрочная / рабочая /
долговременная / профиль), запись идёт только явным вызовом `memory.remember(layer,
...)`, а набор слоёв, попадающих в промт, — параметр `deliver: set[str]`.
Поверх памяти — мультипрофильность с профиль-роутером, затем строгая машина
состояний (`TaskStage` — 8 стадий) и слой инвариантов (`InvariantChecker`).

**Вторая машина состояний** — `DevelopmentStage` (workflow продукта) — работает
независимо от `TaskStage` и связана через `DevelopmentWorkflowCoordinator`.
Переходы между стадиями разработки (`INTAKE → REQUIREMENTS → ARCHITECTURE → PLAN →
IMPLEMENTATION → VALIDATION → DELIVERY → COMPLETED`) контролируются **Guards**
(матрица готовности), **Approval** (exact-action) и **InvariantChecker**.

**Шестой, интеграционный «кубик»** — MCP как внешний источник инструментов.
К нему подключён **Project-MCP** (git-ветка, статус, diff, список/поиск файлов)
и сервер задания `time` (сервер `time`). **RAG-модуль** добавляет седьмой слой —
поиск по локальному корпусу документов, WIKI и коду с гибридным ранжированием.

**Задачи недели 7 (31–35):**

| Задача | Требование | Ключевой результат |
|---|---|---|
| **31** | WIKI проекта; RAG по WIKI/README/коду; MCP-помощник; `/help` | Ассистент разработчика |
| **32** | Пайплайн AI-ревью PR (diff + RAG → findings) | Автоматическое AI-ревью кода |
| **33** | Мини-сервис поддержки (RAG + CRM-MCP) | AI-сервис поддержки |
| **34** | Ассистент работы с файлами (≥2 сценария, безопасность) | AI-ассистент с файловыми операциями |
| **35** | Реальная задача: автомат по созданию ПО (E2E-цикл) | Реальное AI-приложение |

---

## Модель памяти

Память агента — это четыре разных «склада» для данных. Ниже — что каждый склад хранит,
где физически лежит и почему сделано именно так.

- **Краткосрочная память** (`ShortTermMemory`, область видимости — `session`).
  Что хранит: текущий диалог — сами сообщения, у каждого свой `id` и `parent_id`.
  Где лежит: `users/<id>/tasks/<task>/sessions/<sid>/session.json`.
- **Рабочая память** (`WorkingMemory`, область видимости — `task`).
  Что хранит: состояние задачи — `description`, `refs`, `lifecycle_summary`, `decisions`,
  `constraints`, `facts`, `open_questions`, `current_state`, **`goal`**, **`clarifications`**,
  **`terms`**, а также **`project_id`**, **`workspace_id`**, **`development_stage`**,
  **`current_step_id`**, **`external_actions`**.
  Где лежит: `users/<id>/tasks/<task>/working_memory.json`.
- **Долговременная память** (`LongTermMemory`, область видимости — `user`).
  Что хранит: `profile_ref`, `tasks[]`, `decisions[]`, `knowledge[]`.
  Где лежит: `users/<id>/long_term_memory.json`.
- **Профиль** (`Profile`, область видимости — `user`).
  Что хранит: несколько профилей — `profile_id`, `name`, `domain`, `triggers[]`,
  `style`, `constraints`, `context`, `skills[]`.
  Где лежит: SQLite `profiles(user_id, profile_id)` + зеркала `users/<id>/profiles/<pid>.json`.

Единая точка входа — `MemoryManager`: `remember()`, `recall()`, `build_blocks()`, `report()`.

### Иерархия хранения


users/<user_id>/
├── profile.json                 # зеркало профиля default
├── profiles/                    # зеркала всех профилей
├── long_term_memory.json        # profile_ref + задачи + решения + знания
├── integrations/mcp/            # ветка MCP
│   ├── servers.json
│   ├── catalog.json
│   └── scheduler/
├── projects/<pid>/              # проекты Developer Factory
│   ├── project.json             # Project (цель, требования, архитектура)
│   ├── workspace/<wsid>/        # изолированная рабочая область
│   │   ├── <файлы проекта>
│   │   └── .ai9/                # служебные файлы AI_9
│   ├── artifacts/               # артефакты (requirements.md, architecture.md, ADR, plan)
│   ├── approvals.jsonl          # журнал approval-решений
│   └── development_state.json   # DevelopmentStage + transition_log
└── tasks/<task_name>/
    ├── invariants.json
    ├── task_state.json
    ├── working_memory.json
    ├── sessions_resume.md
    ├── tool_audit.jsonl
    └── sessions/<session_id>/
        └── session.json


**Проекты и workspace** — новые ветки, добавленные Ревизией 9:
`projects/<pid>/` хранит состояние продукта (требования, архитектура, план, артефакты),
`workspace/<wsid>/` — изолированную среду для генерации и модификации кода.
`development_state.json` — состояние `DevelopmentStage` + журнал переходов.
`approvals.jsonl` — журнал exact-action approval-решений.

База профилей — `users/profiles.db`. Все пути знает `storage/store.py` — расширен
методами для проектов: `project_path`, `read_project`, `write_project`,
`workspace_path`, `save_artifact`, `load_artifact`, `append_approval`, `load_approvals`.

### Сборка промта (явные блоки + дозированная доставка + бюджет)


[system: роль] → [system: profile] → [system: invariants] → [system: tools, опц.] →
[system: long_term] → [system: working] → [system: summary, опц.] →
[messages: short_term (окно 10)] → [user: текущий запрос] → [резерв под ответ]


- `BLOCK_ORDER = ("role", "profile", "invariants", "tools", "long_term", "working",
  "summary", "short_term", "current")`; блок `[rag]` вставляется после `[tools]`, до
  `[long_term]`;
- доставляемое подмножество задаётся `DELIVERABLE` из `core/prompt_builder.py`;
- `short_term` идёт отдельными сообщениями;
- бюджет: `--budget <N>` — токен-бюджет, роль и запрос не урезаются;
- блок `[tools]` — каталог инструментов (`ToolPromptPolicy`);
- блок `[rag]` — найденные источники со ссылками `[doc_id#chunk_id]`;
- блок `[project]` — контекст проекта (DevelopmentStage, текущий шаг, требования,
  архитектура, план) — добавлен Ревизией 9.

---

## Персонализация

Поверх модели памяти — **несколько профилей на пользователя**. Профиль определяет
стиль, ограничения, контекст, доменную область и порядок скиллов.

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


- `profile_id` — короткое имя профиля; первый/единственный — `default`;
- **профиль = декларативный пайплайн скиллов**;
- **хранение**: SQLite + зеркала JSON;
- **запись слиянием**: `Profile.write()` обновляет только переданные поля;
- **память независима от профилей**;
- **профиль MCP менять не может**.

### Профиль-роутер (`core/profile_router.py`)

Выбирает профиль по тексту запроса: **+2** за триггер, **+1** за `domain`;
победитель = максимум (>0); ничья → `None`. Режим `/profile auto on` запускает
роутер на каждый запрос.

---

## Инварианты и ограничения состояния

Слой **неизменяемых правил**: агент не имеет права нарушать заданные инварианты.

- `Invariant` — одно правило: `id`, `description`, `category`, `severity`, `active`.
- `ConstraintSet` — набор правил, **отдельная сущность**.
- `ProposedAction` — предлагаемое действие (расшиreno MCP-полями и полями проекта:
  `project_id`, `workspace_id`, `operation` (read/write/create/delete), `path`).
- `InvariantChecker` — интерфейс проверки; `RuleBasedChecker` — детерминированная реализация.
- `update_invariant` — изменение правила только с `--yes`.

**Новые инварианты Ревизии 9:**

- `fs.workspace_isolation` — запись только в пределах `workspace/<pid>/<wsid>/`;
- `fs.no_secrets` — запрет чтения `.git/`, `.env/`, `ssh/`, `secrets/`, `users/`;
- `fs.no_delete` — удаление файлов запрещено в MVP;
- `fs.no_shell` — произвольный shell запрещён в MVP;
- `fs.size_limit` — ограничение размера файла/диффа;
- `approval.high_risk` — HIGH/CRITICAL операции требуют approval;
- `approval.exact_action` — approval привязан к конкретному действию (hash).

Хранение — `users/<id>/tasks/<task>/invariants.json` + `users/<id>/projects/<pid>/approvals.jsonl`.

---

## Контролируемые переходы состояний

### TaskStage (8 стадий — без изменений)

```
NEW → PLANNING → PLAN_APPROVED → IMPLEMENTATION → VALIDATION → DONE
                ↑          ↓              ↓           ↓
                └──── PAUSED ←────────────┴───────────┘
                FAILED → PLANNING (через /task retry)
```

### DevelopmentStage (9 стадий — Ревизия 9)

```
INTAKE → REQUIREMENTS → ARCHITECTURE → PLAN → IMPLEMENTATION → VALIDATION → DELIVERY → COMPLETED
    ↑                                                                                   ↓
    └──────────────────────────── PAUSED ←──────────────────────────────────────────────┘
    FAILED → PLAN (через /retry)
```

**Guards** — матрица готовности для каждого перехода:
- `INTAKE → REQUIREMENTS`: интервью завершено, `requirements_valid && requirements_confirmed`;
- `REQUIREMENTS → ARCHITECTURE`: требования валидны;
- `ARCHITECTURE → PLAN`: архитектура и план утверждены (`/approve architecture`, `/approve plan`);
- `PLAN → IMPLEMENTATION`: план валиден (нет циклов, каждый FR покрыт, стек соответствует ADR);
- `IMPLEMENTATION → VALIDATION`: код сгенерирован, diff корректен, конфликт хэша — стоп;
- `VALIDATION → DELIVERY`: тесты/линт/типы прошли, `test_report.md` сформирован;
- `DELIVERY → COMPLETED`: diff/commit подготовлены, approval получен.

**`DevelopmentWorkflowCoordinator`** — оркестратор второго уровня FSM:
- координирует переходы `DevelopmentStage`;
- вызывает Guards для проверки готовности;
- запрашивает Approval для HIGH/CRITICAL операций;
- связывает `TaskStage` и `DevelopmentStage` через адаптер (не трогает FSM на подэтапах).

---

## Второй уровень FSM: DevelopmentStage

**Второй уровень состояния: `DevelopmentStage`** (workflow продукта) отдельно от `TaskStage`;
связь через координатор/адаптер — добавление подсистемы, а не замена FSM.

### Модели (`core/project_models.py`)

```python
@dataclass
class Project:
    project_id: str
    user_id: str
    goal: str
    requirements: list[Requirement]
    architecture: Architecture | None
    implementation_plan: list[PlanStep] | None
    status: str  # "draft" | "active" | "completed" | "failed"
    created_at: str
    updated_at: str

@dataclass
class Workspace:
    workspace_id: str
    project_id: str
    path: str  # users/<id>/projects/<pid>/workspace/<wsid>/
    git_ref: str | None
    created_at: str

@dataclass
class Requirement:
    req_id: str
    text: str
    type: str  # "FR" | "NFR" | "SEC" | "ACC"
    status: str  # "draft" | "validated" | "confirmed"

@dataclass
class Approval:
    approval_id: str
    action_hash: str
    actor: str
    tool: str
    arguments: dict
    expires: str
    consumed: bool
    created_at: str
```

### Хранилище проектов

```
users/<user_id>/projects/<pid>/
├── project.json              # Project
├── workspace/<wsid>/         # изолированная рабочая область
│   ├── .ai9/                 # служебные файлы AI_9
│   │   ├── development_state.json
│   │   └── transition_log.jsonl
│   └── <файлы проекта>
├── artifacts/                # requirements.md, architecture.md, ADR, plan
├── approvals.jsonl           # журнал approval-решений
└── audit.jsonl               # история операций
```

---

## Модульность и слои

Направление зависимостей однонаправленное: `Kod.py` → `core/` → `memory/` → `storage/`;
`integrations/` и `rag/` — сбоку, подключаются только DI-композицией в `Kod.py`.

**Хранилище** (`storage/`) — расширен методами для проектов:
`project_path`, `read_project`, `write_project`, `workspace_path`,
`save_artifact`, `load_artifact`, `append_approval`, `load_approvals`.

**Память** (`memory/`) — 4 слоя + `ProjectContext` (branch/commit/dirty/changed_files/sources).

**Ядро** (`core/`) — прежние сущности без регрессии + новые:
- `project_models.py` — Project, Workspace, Requirement, Approval, PlanStep;
- `development_models.py` — DevelopmentStage, DevelopmentEvent;
- `development_state_machine.py` — машина состояний разработки + Guards;
- `development_coordinator.py` — DevelopmentWorkflowCoordinator;
- `tools.py` — ToolDescriptor + policy-поля;
- `tool_registry.py` — каталог + атомарный snapshot;
- `tool_policy.py` — проверки вызова;
- `tool_executor.py` — исполнение + аудит;
- `tool_routing.py` / `tool_pipeline.py` — выбор и пайплайн;
- `llm_client.py` — LLMReply + complete_with_tools;
- `prompt_builder.py` — блоки [tools]/[rag]/[project];
- `agent.py` — агентный цикл + RAG-слой + ProjectHelpService;
- `invariants.py` — ProposedAction + MCP-поля + fs-инварианты;
- `profile_router.py` — детерминированный выбор профиля;
- `model_registry.py` — реестр моделей;
- `subagents.py` — субагенты;
- `resources.py` — замеры ресурсов.

**Интеграции** (`integrations/`) — MCP-слой + планировщик:
- `mcp/config.py` — MCPServerConfig + Project-MCP (git-ветка, diff, файлы);
- `mcp/transport.py` — StdioMCPTransport + HttpMCPTransport + FakeMCPTransport;
- `mcp/client.py` — initialize / list_tools / call_tool;
- `mcp/gateway.py` — MCPGateway + MCPConnectionState;
- `mcp/provider.py` — MCPToolProvider;
- `mcp/demo_server.py` — локальный demo-сервер;
- `mcp/scheduler_server.py` — MCP-сервер планировщика;
- `mcp/pipeline_server.py` — MCP-сервер пайплайна;
- `mcp/time_server.py` — сервер времени (сервер задания);
- `mcp/auth.py` — серверная проверка токена;
- `scheduler/` — ядро планировщика (models/store/runner/aggregator).

**RAG** (`rag/`) — гибридный поиск по корпусу документов, WIKI и коду:
- `config.py` / `config.json` — RagConfig + области global/project;
- `types.py` / `text.py` — Chunk/DocMeta/Hit/Source/Quote/Answer;
- `corpus.py` / `chunking.py` — сбор корпуса, дельта;
- `embedding.py` — OllamaEmbedder + HashingEmbedder;
- `index.py` — плоский индекс;
- `retrieval.py` / `rerank.py` — BM25⊕dense → RRF → реранк → MMR;
- `rewrite.py` — query rewrite;
- `cache.py` — SearchCache;
- `grounding.py` / `eval.py` / `compare.py` — опора ответа;
- `sources.py` / `citations.py` — источники и цитаты;
- `verify.py` — проверка формата ответа;
- `service.py` — RagService (DI-фасад).

**CLI** (`Kod.py`) — DI с `mcp_enabled=False` по умолчанию; семейство `/mcp`, `/rag`,
`/help`, `/create-app`, `/approve`; флаги `--mcp`, `--mcp-probe`, `--rag`,
`--local-gen`, `--oneshot`, `--subagent-run`.

**Служебное** (`dev/`) — «проект про проект»: мастер-план → рабочие планы этапов → журнал.

---

## Архитектура

### Дерево модулей


AI_9/
├── Kod.py                       # точка входа: DI-композиция + Developer Factory
├── serve.py                     # фасад: HTTP-вход агента (Flask, 127.0.0.1:8090)
├── models.json                  # реестр моделей и профилей
├── gateway/                     # веб-шлюз на VPS (Flask)
├── core/                        # ядро агентности + Developer Factory
│   ├── agent.py                 # оркестратор: + mcp_gateway/tool_registry/tool_executor
│   │                            #   + ProjectHelpService + RAG-слой
│   ├── llm_client.py            # LLMClient (ABC) + RouterAIClient + MockClient
│   ├── profile_router.py        # ProfileRouter
│   ├── prompt_builder.py        # BLOCK_ORDER + DELIVERABLE + budget + блоки [tools], [rag], [project]
│   ├── state_machine.py         # TaskStage (без изменений)
│   ├── development_models.py    # DevelopmentStage, DevelopmentEvent
│   ├── development_state_machine.py  # DevelopmentStateMachine + Guards
│   ├── development_coordinator.py   # DevelopmentWorkflowCoordinator
│   ├── project_models.py        # Project, Workspace, Requirement, Approval, PlanStep
│   ├── invariants.py            # Invariant + ConstraintSet + InvariantChecker
│   ├── model_registry.py        # ModelRegistry + ModelSpec
│   ├── resources.py             # замеры ресурсов
│   ├── subagents.py             # SubagentRunner
│   ├── tools.py                 # ToolDescriptor + ToolCallRequest + ToolExecutionResult
│   ├── tool_registry.py         # ToolRegistry
│   ├── tool_policy.py           # ToolPolicy
│   ├── tool_executor.py         # ToolExecutor
│   ├── tool_routing.py          # rank_tools
│   └── tool_pipeline.py         # PipelineStep/Pipeline/run_pipeline
├── integrations/                # MCP + планировщик
│   ├── mcp/
│   │   ├── config.py            # MCPServerConfig + Project-MCP
│   │   ├── auth.py              # серверная проверка токена
│   │   ├── time_server.py       # MCP-сервер времени
│   │   ├── transport.py         # MCPTransport + StdioMCPTransport + HttpMCPTransport
│   │   ├── client.py            # MCPClient
│   │   ├── gateway.py           # MCPGateway + MCPGatewaySync
│   │   ├── provider.py          # MCPToolProvider
│   │   ├── demo_server.py       # локальный stdio MCP-сервер
│   │   ├── scheduler_server.py  # MCP-сервер планировщика
│   │   └── pipeline_server.py   # MCP-сервер пайплайна
│   └── scheduler/               # ядро планировщика
├── memory/                      # 4 слоя + MemoryManager
├── rag/                         # RAG-модуль (индексация + гибридный поиск)
├── storage/
│   ├── store.py                 # фасад: + project/workspace/artifact/approval
│   └── db.py                    # ProfileRepository
├── users/                       # рантайм-хранилище
│   └── <id>/
│       ├── integrations/mcp/
│       ├── projects/<pid>/      # проекты Developer Factory
│       │   ├── project.json
│       │   ├── workspace/<wsid>/
│       │   ├── artifacts/
│       │   ├── approvals.jsonl
│       │   └── development_state.json
│       └── tasks/<task>/
├── docs/                        # WIKI проекта (задача 31)
│   ├── WIKI.md                  # индекс со ссылками
│   ├── 00_overview.md
│   ├── 01_architecture.md
│   ├── 02_memory.md
│   ├── 03_profiles.md
│   ├── 04_state_machine.md
│   ├── 05_invariants.md
│   ├── 06_mcp.md
│   ├── 07_rag.md
│   ├── 08_tools.md
│   ├── 09_cli.md
│   ├── 10_storage.md
│   ├── 11_testing.md
│   ├── 12_deployment.md
│   ├── 13_developer_factory.md
│   └── 14_security.md
├── ND/                          # справочные материалы
├── run.sh / run.desktop         # запуск
├── README.md                    # краткое описание + ссылка на WIKI
├── agents.md                    # краткая памятка агенту
├── Den_log.md                   # журнал (рантайм-артефакт)
├── tokens.csv                   # CSV-журнал токенов
└── dev/                         # служебное пространство
    ├── migr_9_plan.md           # мастер-план Ревизии 9
    ├── migr_9_plan_0.md … migr_9_plan_20.md  # рабочие планы этапов
    ├── migr_log.md              # журнал миграции
    ├── Проверка.md              # чек-лист приёмки (расширен)
    ├── tests_debug/
    │   ├── check_acceptance.sh  # гейт приёмки (расширен)
    │   ├── unit_runner.py       # L2-раннер
    │   ├── smoke.py             # L3-смоук
    │   ├── scenario.py          # L4-сценарии
    │   ├── dialog_runner.py     # диалоги
    │   ├── unit/                # 42+ модулей test_*.py
    │   ├── scenario/            # сценарии ручной демонстрации
    │   └── .tmp/                # временные файлы (.gitignore)
    ├── logs_reports/            # stages/ + errors/ + archive/
    └── vps/                     # инфраструктура VPS


### Внутренняя модель инструментов (`core/tools.py`)

```python
@dataclass(frozen=True)
class ToolDescriptor:
    name: str                    # "mcp.weather.search_locations" | "local.<tool>" | "project.<tool>"
    description: str
    input_schema: dict
    source: str                  # "local" | "mcp" | "project"
    provider: str
    original_name: str
    risk_level: str = "unknown"  # "low" | "medium" | "high" | "critical"
    allowed_stages: frozenset = ALL_WORKING_STAGES
    requires_confirmation: bool = False
    enabled: bool = True

@dataclass(frozen=True)
class ToolCallRequest:
    name: str
    arguments: dict
    call_id: str = ""

@dataclass(frozen=True)
class ToolExecutionResult:
    execution_id: str
    tool: str
    status: str                  # ToolExecutionState
    summary: str
    raw: object | None = None
    is_error: bool = False
    call_id: str = ""

class ToolExecutionState(str, Enum):
    REQUESTED = "requested"; DENIED = "denied"; WAITING_CONFIRMATION = "waiting_confirmation"
    RUNNING = "running"; SUCCEEDED = "succeeded"; FAILED = "failed"
    TIMED_OUT = "timed_out"; CANCELLED = "cancelled"
```

### Project-MCP (`integrations/mcp/`)

**Новые инструменты Ревизии 9:**

| Инструмент | Описание | Риск |
|---|---|---|
| `project.get_git_branch` | Текущая git-ветка | low |
| `project.get_git_status` | Статус репозитория (dirty, changed) | low |
| `project.get_git_diff` | Diff между ветками/коммитами | medium |
| `project.list_files` | Список файлов в проекте | low |
| `project.search_project` | Поиск по содержимому файлов | low |
| `project.read_file` | Чтение файла (с ограничением размера) | low |
| `project.write_file` | Создание/изменение файла (требует approval) | high |
| `project.create_diff` | Сборка diff изменений | medium |

**Ограничения безопасности:**
- Выход за корень проекта → отказ (`Path.is_relative_to`);
- Запрет чтения `.git/`, `.env/`, `ssh/`, `secrets/`, `users/`;
- Ограничение размера файла/диффа (флаг `truncated`);
- Аудит всех вызовов (`execution_id/actor/tool/hash/path/status`).

### MCP-слой (`integrations/mcp/`)

**Конфиг** (`config.py`) — `MCPServerConfig` + загрузка `servers.json`:
- **сервер задания** `time` (`http://91.188.212.77:8000/mcp`);
- **реальный погодный HTTP-сервер** `weather` (`https://weatherapi.projecteol.ru/mcp/`);
- `scheduler` (`:8010`) и `pipeline` (`:8020`) — включаются флагами;
- демо-сервер `demo` (stdio, `enabled=false`).

**Транспорт** (`transport.py`) — `MCPTransport` (ABC) + `StdioMCPTransport` +
`HttpMCPTransport` (Streamable HTTP) + `FakeMCPTransport`.

**Шлюз** (`gateway.py`) — `MCPGateway`:

```python
class MCPConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"

class MCPGateway:
    async def start(self) -> None
    async def stop(self) -> None
    def status(self) -> dict
    async def discover(self) -> list[ToolDescriptor]
    async def call_tool(self, provider, tool_name, arguments, execution_id="") -> ToolExecutionResult
```

### DI-композиция и CLI

```python
mcp_enabled = False   # по умолчанию

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
    agent.deliver.add("tools")
    gateway.start(); registry.refresh()

# RAG (--rag): RagService собирается в Kod.py
# Developer Factory: DevelopmentWorkflowCoordinator + ProjectHelpService
```

### RAG-слой (`rag/`)

Расширяемый RAG-модуль: индексация корпуса, WIKI и кода; гибридный поиск;
блок `[rag]` в промпте со ссылками; источники/цитаты и проверка опоры ответа.

**Области RAG (Ревизия 9):**
- `global` — WIKI, README, документация;
- `project` — код проекта, артефакты, ADR.

**Конвейер:**
```
corpus → chunking → embedding → index → rewrite → retrieval → блок [rag] → ответ со ссылками
```

**Границы модуля:**
- только stdlib; сеть — исключительно `127.0.0.1:11434` (Ollama);
- **`rag/` не импортирует `core/`**, а `core/` не импортирует `rag/`;
- индекс глобальный (`rag/index/`, в `.gitignore`);
- новых pip-зависимостей нет; `TaskStage` не затрагивается.

---

## Команды REPL

### Память и профили:

- `/memory` — снимок памяти;
- `/profile` — активный профиль;
- `/profile list` — профили пользователя;
- `/profile use <id>` — переключить профиль;
- `/profile new <id>` — создать профиль;
- `/profile route <текст>` — решение роутера;
- `/profile auto on|off` — авто-роутинг.

### Задачи и состояние:

- `/tasks` — список задач;
- `/task <имя>` — переключить задачу;
- `/task retry` — восстановление из `failed`;
- `/plan <цель>` — `new → planning`;
- `/approve` — утвердить план;
- `/goto <этап>` — явный переход;
- `/transitions` — карта переходов + журнал;
- `/step` — один проход автомата;
- `/run` — крутить автомат до `done`/`failed`/`paused`;
- `/pause` / `/resume` — пауза/возобновление;
- `/deliver <слои>` — набор доставляемых слоёв;
- `/compare` — ответ с `long_term` и без;
- `/summary` — резюме сессий;
- `/state` — снимок `TaskState`.

### Инварианты:

- `/invariants` — список инвариантов;
- `/invariant add <id> <category> <текст>`;
- `/invariant set <id> <текст> [--yes]`;
- `/invariant on|off <id>`;
- `/check <действие>` — проверка `InvariantChecker`.

### Tокены и стоимость:

- `/tokens` — оценка токенов;
- `/cost` — стоимость обменов.

### MCP-инструменты:

- `/mcp status` — состояние подключения;
- `/mcp servers` — сконфигурированные серверы;
- `/mcp tools` — список доступных инструментов;
- `/mcp refresh` — re-discovery;
- `/mcp connect <id>` — поднять соединение;
- `/mcp call <tool> [{json}]` — вызвать инструмент;
- `/mcp disconnect` — закрыть соединения;
- `/mcp jobs` — задачи планировщика;
- `/mcp pipeline <запрос>` — пайплайн;
- `/mcp route <текст>` — объяснить выбор.

### Developer Factory:

- `/create-app <цель>` — создать проект (интервью → требования → подтверждение);
- `/project list` — список проектов;
- `/project <pid>` — переключить проект;
- `/project status` — статус проекта и DevelopmentStage;
- `/approve requirements` — утвердить требования;
- `/approve architecture` — утвердить архитектуру;
- `/approve plan` — утвердить план;
- `/approve changes` — утвердить изменения кода;
- `/approve commit` — утвердить коммит;
- `/reject <reason>` — отклонить действие;
- `/review` — запустить AI-ревью;
- `/diff` — показать diff;
- `/help <вопрос>` — ответить о проекте (RAG + git-контекст).

### RAG:

- `/rag status` — состояние RAG;
- `/rag on|off` — включить/выключить;
- `/rag ingest` — проиндексировать корпус;
- `/rag find <запрос>` — поиск со скорами;
- `/rag ask <вопрос>` — ответ с RAG;
- `/rag sources` — источники последнего ответа;
- `/rag quotes` — цитаты последнего ответа;
- `/rag verify` — проверка на 10 вопросах;
- `/rag check <ответ>` — проверка опоры;
- `/rag stats` — индекс, модель, RAM, кэш, латентность;
- `/rag eval` — метрики на датасете.

### Прочее:

- `/model` — текущая модель;
- `/model list` — все модели;
- `/model use <id>` — переключить модель;
- `/model profile <name>` — профиль параметров;
- `/help` — список команд;
- `/exit` — сохранение и выход.

---

## Запуск

```bash
# Через обёртку
./run.sh                     # интерактивный REPL
./run.sh --user alice        # сразу идентификация alice

# Напрямую
python Kod.py --user alice

# Developer Factory
python Kod.py --user alice --mcp   # REPL с MCP-слоем
python Kod.py --create-app "калькулятор формул"  # создать проект

# MCP
python Kod.py --mcp-probe                  # one-shot: подключиться → список тулов → выйти
MCP_SERVER_URL=http://91.188.212.77:8000/mcp python Kod.py --mcp-probe

# RAG
./run.sh --rag-ingest                       # проиндексировать корпус
./run.sh --rag-ask "как считается бюджет токенов"
./run.sh --rag --user alice                 # REPL с блоком [rag]

# Локальные LLM
python Kod.py --local-gen --user alice      # локальная генерация
python Kod.py --rag --local-gen --user alice  # полностью локальный RAG

# Фасад и шлюз
python serve.py [--mock] [--port 8090]
python -m gateway.app                       # веб-шлюз на VPS
```

**Флаги:** `--user <id>`, `--profile <id>`, `--deliver <слои>`, `--mock`, `--fresh`,
`--log`, `--token-log`, `--max-tokens`, `--price-in` / `--price-out`, `--budget <N>`,
`--memory-dir`, `--mcp`, `--mcp-probe`, `--no-tools-block`, `--scheduler`,
`--rag`, `--no-rag-block`, `--rag-ingest`, `--rag-path`, `--rag-search`, `--rag-ask`,
`--rag-verify`, `--rag-eval`, `--rag-compare`, `--rag-mode`, `--rag-strategy`,
`--rag-top-k`, `--rag-threshold`, `--rag-unknown`, `--rag-reranker`, `--rag-rewrite`,
`--rag-config`, `--rag-grounding`, `--rag-multi-query`, `--model`, `--model-list`,
`--model-profile`, `--local-gen`, `--embed-provider`, `--embed-model`, `--embed-url`,
`--temperature F`, `--max-tokens N`, `--context-window N`, `--local-template`,
`--oneshot`, `--subagent-run`, `--subagent-service`, `--local-only`,
`--rag-gen-compare`, `--gen-modes`, `--repeat`, `--gen-report`, `--gen-resources`.

---

## Агентный цикл

```
старт → DI-сборка build_agent(mcp_enabled=--mcp) (+ RagService при --rag)
      → идентификация user_id
      ├─ профиль есть → load_state()
      └─ нет профиля  → интервью → initialize_user()
      → активный профиль (--profile) → deliver (--deliver ∩ DELIVERABLE)

обмен:  сообщение → [auto_route: ProfileRouter]
        → remember_message("user") → build_context → PromptBuilder.build(ctx, deliver, budget)
        → llm.complete(messages) → remember_message("assistant") → токен-оценка + CSV

автомат: /plan → /approve → /step|/run → validation → done|failed
         (переходы — только try_transition по карте; отказы — REFUSAL_RULES + transition_log)

MCP:    --mcp-probe → start → READY → discover → печать списка → stop → exit 0
        /mcp connect|tools|refresh|status|disconnect
        LLM tool-use: _respond_with_tools (LLM → tool call → ToolExecutor → tool-сообщение → LLM)

Developer Factory:
        /create-app <цель> → InterviewState → requirements → /approve requirements
        → архитектура → /approve architecture → план → /approve plan
        → workspace → генерация кода (патч, hash-контроль) → валидация
        → AI-ревью → diff/commit → /approve commit → COMPLETED

RAG:    --rag → RagService.search (кэш → rewrite → BM25⊕dense → RRF → реранк → MMR → порог)
        → блок [rag] в промпте → ответ со ссылками → источники/цитаты
        → grounding (strict: одна авто-перегенерация; пустой поиск → «не знаю»)

выход:  save_state() + сейв task_state.json + сейв development_state.json
```

---

## Тестирование и приёмка

Всё — **без живого ключа** (`API_KEY=test-key`, `MockClient`, `FakeMCPTransport`),
тестовые данные пишутся только в `dev/tests_debug/.tmp/` (в `.gitignore`), рабочие
`users/` не затрагиваются.

**Уровни проверок:**

- **L1 — компиляция.** `python -m py_compile Kod.py core/*.py memory/*.py storage/*.py integrations/mcp/*.py`.
- **L2 — юнит-тесты.** `env -u API_KEY python dev/tests_debug/unit_runner.py`.
  Результат: **412+ OK, 0 FAIL** (42+ модуля, расшиreno модулями Developer Factory).
- **L3 — смоук.** `API_KEY=test-key python dev/tests_debug/smoke.py`.
- **L4 — сценарии.** `API_KEY=test-key python dev/tests_debug/scenario.py`.
- **Гейт приёмки.** `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh`.
  Результат: **N из N ✅, exit 0** (расширен проверками Developer Factory).
- **Диалоги.** `API_KEY=test-key python dev/tests_debug/dialog_runner.py`.

**Состав тестовых модулей (расширен Ревизией 9):**

- `unit/test_mcp.py` — контракты, discovery, реестр, gateway, call_tool, policy, tool-use;
- `unit/test_rag_*.py` — интеграция, grounding, cache, rerank, verify, working_memory;
- `unit/test_llm_local.py` — локальные клиенты;
- `unit/test_model_switch.py` — `/model`;
- `unit/test_subagents.py` — субагенты;
- `unit/test_rag_local_gen.py` — локальная генерация в RAG;
- `unit/test_rag_gen_compare.py` — сравнение генераторов;
- `unit/test_llm_optimize.py` — профили;
- `unit/test_llm_resources.py` — замеры ресурсов;
- `unit/test_facade.py` — фасад;
- `unit/test_gateway.py` — шлюз;
- **Новые модули Ревизии 9:**
  - `unit/test_development_models.py` — DevelopmentStage, Guards, граф переходов;
  - `unit/test_development_coordinator.py` — координатор, адаптер к TaskStage;
  - `unit/test_project_models.py` — Project, Workspace, Requirement, Approval;
  - `unit/test_project_store.py` — хранилище проектов, round-trip, битый файл → дефолт;
  - `unit/test_project_mcp.py` — project-MCP инструменты, безопасность, аудит;
  - `unit/test_approval.py` — exact-action approval, replay/expired/wrong-actor;
  - `unit/test_workspace.py` — изоляция workspace, инварианты fs.*;
  - `unit/test_help_service.py` — ProjectHelpService, RAG-ответы, grounding;
  - `unit/test_docs_links.py` — link-check WIKI;
  - `unit/test_rag_scopes.py` — RAG области global/project;
- L4 сценарии — `scenario_mcp_discovery`, `scenario_llm_tool_use`, `scenario_tool_denied`,
  `scenario_multiserver_flow`, `scenario_developer_factory` (E2E-прогон),
  `scenario_file_operations` (≥2 сценария), `scenario_pr_review`, `scenario_support`;
- гейт `check_acceptance.sh` — расширен проверками: WIKI (0 битых ссылок),
  RAG-области (global/project), Project-MCP (git-ветка, diff, безопасность),
  `/help` (ответы с источниками), DevelopmentStage (граф переходов),
  Approval (exact-action), Workspace (изоляция), AI-ревью (findings с файлом/строкой).

---

## Служебное пространство `dev/`

### Дерево `dev/`


AI_9/dev/
├── migr_9_plan.md                  # мастер-план Ревизии 9
├── migr_9_plan_0.md … migr_9_plan_20.md  # рабочие планы этапов
├── migr_log.md                     # журнал миграции
├── Проверка.md                     # чек-лист приёмки (расширен)
├── old_vers/                       # история прошлых ревизий (1…8)
├── meta_promt/                     # метапромты
├── tests_debug/
│   ├── check_acceptance.sh         # гейт приёмки (расширен)
│   ├── unit_runner.py              # L2-раннер
│   ├── smoke.py                    # L3-смоук
│   ├── scenario.py                 # L4-сценарии
│   ├── dialog_runner.py            # диалоги
│   ├── unit/                       # 42+ модулей test_*.py
│   │   ├── test_mcp.py
│   │   ├── test_rag_*.py
│   │   ├── test_llm_local.py
│   │   ├── test_model_switch.py
│   │   ├── test_subagents.py
│   │   ├── test_rag_local_gen.py
│   │   ├── test_rag_gen_compare.py
│   │   ├── test_llm_optimize.py
│   │   ├── test_llm_resources.py
│   │   ├── test_facade.py
│   │   ├── test_gateway.py
│   │   ├── test_development_models.py
│   │   ├── test_development_coordinator.py
│   │   ├── test_project_models.py
│   │   ├── test_project_store.py
│   │   ├── test_project_mcp.py
│   │   ├── test_approval.py
│   │   ├── test_workspace.py
│   │   ├── test_help_service.py
│   │   ├── test_docs_links.py
│   │   └── test_rag_scopes.py
│   ├── scenario/                   # сценарии ручной демонстрации
│   │   ├── scen_1.md
│   │   ├── scen_rag.md
│   │   ├── scen_dialog_A.md
│   │   ├── scen_dialog_B.md
│   │   ├── scen_local_llm.md
│   │   ├── scen_rag_local.md
│   │   ├── scen_optimize.md
│   │   ├── scen_multiserver_flow.md
│   │   ├── scen_access.md
│   │   ├── scen_developer_factory.md
│   │   ├── scen_file_operations.md
│   │   └── scen_pr_review.md
│   └── .tmp/                       # временные файлы (.gitignore)
├── logs_reports/                   # stages/ + errors/ + archive/
└── vps/                            # инфраструктура VPS


---

## Карта артефактов

### Рабочие артефакты (продукт)

- `Kod.py` + `core/` + `memory/` + `storage/` — агент + Developer Factory.
- `core/project_models.py` — Project, Workspace, Requirement, Approval, PlanStep.
- `core/development_models.py` — DevelopmentStage, DevelopmentEvent.
- `core/development_state_machine.py` — машина состояний разработки + Guards.
- `core/development_coordinator.py` — DevelopmentWorkflowCoordinator.
- `core/tools.py` — ToolDescriptor + policy-поля.
- `core/tool_registry.py` — ToolRegistry.
- `core/tool_policy.py` — ToolPolicy.
- `core/tool_executor.py` — ToolExecutor.
- `core/tool_routing.py` / `core/tool_pipeline.py` — выбор и пайплайн.
- `core/llm_client.py` — LLMReply + complete_with_tools.
- `core/prompt_builder.py` — блоки [tools]/[rag]/[project].
- `core/agent.py` — агентный цикл + ProjectHelpService + RAG-слой.
- `core/invariants.py` — ProposedAction + fs-инварианты.
- `core/model_registry.py` + `models.json` — реестр моделей.
- `core/subagents.py` — субагенты.
- `core/profile_router.py` — профиль-роутер.
- `core/resources.py` — замеры ресурсов.
- `serve.py` — фасад (HTTP, `127.0.0.1:8090`).
- `gateway/*` — веб-шлюз на VPS.
- `integrations/mcp/*` — MCP-слой: config, transport, client, gateway, provider, demo_server,
  scheduler_server, pipeline_server, time_server, auth, **Project-MCP**.
- `integrations/scheduler/*` — ядро планировщика.
- `rag/*` — RAG-модуль (config, corpus, chunking, embedding, index, retrieval, rerank,
  rewrite, cache, grounding, eval, compare, sources, citations, verify, service).
- `docs/WIKI.md` — индекс WIKI.
- `docs/00_overview.md … 14_security.md` — страницы WIKI.
- `users/<id>/projects/<pid>/` — проекты Developer Factory.
- `users/<id>/tasks/<task>/tool_audit.jsonl` — история вызовов инструментов.
- `ND/models/*_params.md` — справки по моделям.
- `run.sh` и `run.desktop` — запуск.
- `README.md` — краткое описание + ссылка на WIKI.

### Служебные артефакты (процесс)

- `dev/Проверка.md` — чек-лист приёмки (расширен).
- `dev/migr_9_plan.md` и `migr_9_plan_*.md` — мастер-план и рабочие планы Ревизии 9.
- `dev/migr_log.md` — журнал миграции.
- `dev/tests_debug/*` — L2 (42+ модулей), L3, L4 (расширенные сценарии), гейт.
- `dev/logs_reports/stages/*` — транскрипты живых прогонов.
- `agents.md` — краткая памятка агенту.
- `ND/tasks/n_1 … n_7` — задания куратора по неделям.

---

## Порядок достижения итогового состояния

Порядок по зависимостям (от контрактов к CLI):

1. **Базовый агент дней 11–15** — память, профили, инварианты, машина состояний, LLM-клиент.
2. **Контракты инструментов** — `core/tools.py` → `core/tool_registry.py` → `integrations/mcp/`.
3. **Контроль и исполнение** — `core/tool_policy.py` + `core/tool_executor.py`.
4. **LLM tool-use** — `core/llm_client.py` → `core/prompt_builder.py` → `core/agent.py`.
5. **CLI** — `Kod.py` (DI + `/mcp`-семейство + `--mcp`/`--mcp-probe`).
6. **День 20** — `integrations/scheduler/` + `scheduler_server.py` + `pipeline_server.py`.
7. **RAG** — `rag/` + DI-фасад в `Kod.py` + блок `[rag]` в `prompt_builder.py`.
8. **Ревизия 8** — локальные LLM, фасад, шлюз, субагенты, сравнение генераторов.
9. **Ревизия 9 (Developer Factory):**
   - 0. Базовая линия + аудит + бюджет-репер;
   - 1. Продуктовая спецификация (`docs/product_*`);
   - 2. WIKI: разделение README + индекс + link-check;
   - 3. RAG: области global/project, метаданные, инкремент;
   - 4. Project-MCP (read-only): git-ветка/status/diff, файлы, поиск;
   - 5. `/help` + `ProjectContext` + `ProjectHelpService`;
   - 6. `DevelopmentStage` + Coordinator + адаптер к `TaskStage`;
   - 7. Модели `Project`/`Workspace` + `Store`;
   - 8. Интервью + требования (`/create-app`);
   - 9. Архитектура + ADR + план реализации;
   - 10. Workspace + безопасные файловые операции (≥2 сценария);
   - 11. Генерация кода по шагам (патч, hash-контроль, diff);
   - 12. Валидация: тесты/линт/типы/ссылки + `test_report`;
   - 13. Approval-модель (exact action) + pause/resume/retry;
   - 14. Delivery: diff/commit (PR — опц.);
   - 15. Пайплайн AI-ревью PR (diff + RAG → findings);
   - 16. Docs sync pipeline (код → Wiki/ADR/changelog);
   - 17. CRM-MCP + ассистент поддержки;
   - 18. HTTP API + Web UI;
   - 19. End-to-end демо-проект (реальная задача);
   - 20. Приёмка, синхронизация README/WIKI/Проверка, чистка.

---

## Риски и откат

- **Регрессия ядра дней 11–15** — MCP/RAG/Developer Factory выключены по умолчанию.
  Откат — не включать флаги.
- **Выход за контекст 100k** — правило Р0–Р5 (§0.3); дробление шагов; чтение крупных доков по разделам.
- **Запись вне workspace / секреты** — нормализация путей + инварианты + approval.
- **Опасные действия без approval** — Approval exact-action; delete/shell в MVP запрещены.
- **Второй уровень FSM ломает первый** — адаптер + вариант «не трогать FSM на подэтапах».
- **Протечка MCP-модели в `core`** — SDK только в `integrations/mcp`; `ToolDescriptor` — внутренняя модель.
- **Живой контур недоступен** — живой прогон обязателен; mock помечается.
- **Демо-проект (35) слишком крупный** — шаг 19.1 дробится по подшагам.
- **Недоступный MCP-сервер** — `FAILED`/`DEGRADED`, тулы исключаются, REPL жив.
- **Недоступная Ollama** — деградация на `HashingEmbedder`.

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
- **`PolicyEngine` в `memory/base.py`** — пустой интерфейс-задел;
- **`parent_id` сообщений** — задел ветвления диалога;
- **`skills[]`** — декларативный пайплайн (движок оркестрации — следующие дни);
- **`transition_log` растёт без ограничения** — сжатие — следующие дни;
- **GitHub-интеграция** (реальные PR, webhook) — задел для следующей ревизии;
- **production-деплой** (автослияние PR, удаление файлов, произвольный shell) — задел.

**Расхождения spec/кода (на поведение не влияют):**

- `mcp` SDK импортируется в `transport.py` и `demo_server.py` (уровень транспорта);
- `handle_mcp_command` (`/mcp servers`, `/mcp connect`) читает приватное
  `gateway.gateway._servers` — допустимо для CLI-слоя;
- смоуки этапов миграции — рабочие артефакты этапов.

**Косметика:**

- каталоги `dev/tests_debug/fixtures/` и `smoke/` созданы каркасом и остались пустыми;
- в `.tmp/` накапливаются каталоги прошлых прогонов (в `.gitignore`);
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
- **Project-MCP**: `get_git_branch`, `get_git_status`, `get_git_diff`, `list_files`,
  `search_project`, `read_file`, `write_file` (с approval); безопасность (корень,
  секреты, размер); аудит всех вызовов.
- **Планировщик, пайплайн, мультисерверность**: фоновый worker 24/7; цепочка
  `search → summarize → saveToFile`; выбор и маршрутизация инструмента
  по `mcp.<server>.<tool>`.
- **RAG-модуль**: индексация корпуса, WIKI и кода; гибридный поиск (BM25⊕dense → RRF →
  реранк → MMR → порог); query rewrite; блок `[rag]` со ссылками `[doc_id#chunk_id]`;
  **источники** (`source`+`section`/`chunk_id`) и **дословные цитаты** из чанков;
  режим «не знаю» при слабом контексте; grounding (`ok|partial|hallucination`) и одна
  авто-перегенерация в `strict`; области global/project; инкрементальная инвалидация.
- **Developer Factory (E2E-конвейер)**:
  - `/create-app <цель>` — интервью → требования → подтверждение;
  - `/approve requirements|architecture|plan` — утверждение на каждом этапе;
  - `DevelopmentStage` (9 стадий) с Guards и Coordinator;
  - Workspace-изоляция + безопасные файловые операции (≥2 сценария);
  - Генерация кода по шагам (патч, hash-контроль, diff);
  - Валидация: тесты/линт/типы/ссылки + `test_report.md`;
  - Approval exact-action (HIGH/CRITICAL требуют подтверждения);
  - AI-ревью PR (diff + RAG → findings с файлом/строкой/severity);
  - Docs sync pipeline (код → Wiki/ADR/changelog);
  - Delivery: diff/commit (PR — опц.);
  - E2E-прогон на реальной задаче (интервью → … → diff/commit).
- **WIKI проекта**: README перенесён в `docs/wiki/*`; `docs/WIKI.md` — индекс со ссылками;
  `README.md` — краткий + ссылка; `check_docs_links.py` — 0 битых ссылок.
- **`/help <вопрос>`** — отвечает о структуре проекта, ссылаясь на Wiki/код; учитывает
  git-контекст; не выдумывает отсутствующее.
- **Не скрипт, а вертикальный срез подсистемы**: `MCPGateway` (адаптер) →
  `MCPToolProvider` (нормализация) → `ToolRegistry` (каталог + snapshot) →
  `ToolExecutor` (policy + аудит) → LLM tool-use.
- **R8 — локальные LLM и доступ к агенту**: реестр моделей; `--model-list` / `--model <id>` /
  `--model-profile <name>`; `--local-gen`; `--embed-provider` / `--embed-model` /
  `--embed-url`; `--local-template`; `--oneshot`; субагенты; `serve.py` — фасад;
  `gateway.app` — веб-шлюз; сравнение генераторов; профили параметров; замеры ресурсов.
- **Пять «кубиков» дней 11–15 без регрессии**: память, профили, инварианты, строгая
  машина состояний, LLM-клиент — контракты не тронуты; MCP и RAG выключены по умолчанию.
- **Инструмент ≠ переход**: `TaskStage` (8 стадий) и `DevelopmentStage` (9 стадий) не
  меняются от вызовов MCP/RAG/файловых операций; успех вызова не создаёт запись в
  `transition_log`.
- **Изоляция прав через тулинг**: `allowed_tools`/`denied_tools` в конфиге сервера;
  модель MCP не протекает в `core`; `MCPGateway` не знает о стадиях/профилях/памяти.
- **Деградация, не падение**: недоступный сервер → FAILED/DEGRADED, REPL жив;
  недоступная Ollama → `HashingEmbedder`.
- **Проверяемость**: L1 OK / L2 412+ OK / L3 SMOKE OK / L4 SCENARIO OK, гейт N/N,
  приёмка N критериев — без живого ключа и сети; живой прогон (реальный HTTP-сервер +
  реальный LLM) — отдельно.
- **Заделы с зарезервированными местами**: `ToolMemoryPolicy`, `ToolPromptPolicy`/resources,
  параллелизм read-only тулов, local-provider, полный async core, GitHub-интеграция,
  production-деплой.
