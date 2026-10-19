Ниже — единый план реализации итогового продукта:

> **AI_9 Developer Factory** — AI-сервис, который принимает пользовательскую идею, уточняет требования, проектирует решение, создаёт код в изолированной рабочей области, запускает тесты, выполняет ревью и готовит проверяемый результат к передаче пользователю.

План учитывает уже существующие в проекте память, профили, RAG, MCP, инварианты, `TaskStage`, `ToolRegistry`, `ToolExecutor` и файловую структуру [1]. Важный принцип безопасности: агент предлагает и подготавливает изменения, но не должен сам утверждать собственный код, сливать PR, удалять данные или выполнять production-деплой [2][3].

***

# 1. Итоговая цель

## 1.1. Название продукта

Рабочее название:

```text
AI_9 Developer Factory
```

Альтернативы:

```text
AI_9 Software Builder
AI_9 App Factory
AI_9 Autonomous Development Assistant
```

## 1.2. Формулировка цели

```text
Создать AI-сервис для автоматизированной разработки ПО под нужды пользователя.

Пользователь описывает требуемую программу естественным языком.
AI_9 проводит интервью, формирует требования, предлагает архитектуру,
создаёт план, реализует код в изолированной рабочей области, запускает тесты,
выполняет ревью, обновляет документацию и передаёт пользователю diff,
commit или pull request для окончательного подтверждения.
```

## 1.3. Что считается результатом

Для каждой задачи сервис должен уметь сформировать:

```text
requirements.md
architecture.md
implementation_plan.md
исходный код
тесты
test_report.md
review.md
project_wiki.md
changes.diff
```

Итогом считается не просто текстовый ответ LLM, а воспроизводимый пакет:

```text
ProjectResult {
    project_id,
    requirements,
    architecture,
    plan,
    workspace,
    changed_files,
    test_report,
    review_report,
    documentation,
    diff,
    approval_status
}
```

***

# 2. Границы первого релиза

## 2.1. Что входит в MVP

Первый релиз должен уметь:

- принять описание приложения;
- провести уточняющее интервью;
- создать требования;
- предложить технологический стек;
- сформировать план;
- дождаться подтверждения плана;
- создать проект в отдельной рабочей области;
- изменить несколько файлов;
- написать базовые тесты;
- запустить проверки;
- выполнить code review;
- обновить документацию;
- показать diff;
- записать аудит действий;
- не менять основную ветку без подтверждения.

## 2.2. Что пока не входит

Не включай в первый MVP:

- полностью автономный production-деплой;
- удаление файлов без подтверждения;
- произвольное выполнение shell-команд;
- автоматическое слияние PR;
- работу с платёжными системами;
- изменение серверных секретов;
- самостоятельную смену архитектурных правил;
- доступ ко всей файловой системе хоста.

Для важных операций должен оставаться человек: push, merge, deploy, удаление данных, изменение прав и обращение к новым сетевым ресурсам [2].

***

# 3. Главный пользовательский сценарий

Пользователь запускает:

```text
/create-app
```

И вводит:

```text
Мне нужно приложение для расчёта и сравнения вариантов формул.
Пользователь должен создавать шаблоны, задавать произвольное число
переменных, сохранять расчёты и экспортировать результаты в CSV.
```

AI_9 проходит следующий путь:

```text
1. Интервью
2. Требования
3. Архитектурные варианты
4. Подтверждение архитектуры
5. План реализации
6. Подтверждение плана
7. Создание workspace
8. Реализация по шагам
9. Тестирование
10. Исправление ошибок
11. Code review
12. Обновление Wiki
13. Формирование diff
14. Подтверждение изменений
15. Commit или PR
```

***

# 4. Целевая архитектура

```text
┌────────────────────────────────────────┐
│ CLI / Web UI / HTTP API                │
└───────────────────┬────────────────────┘
                    │
┌───────────────────▼────────────────────┐
│ Development Workflow                   │
│ intake → interview → plan → build      │
│ → validate → review → approval         │
└───────────────────┬────────────────────┘
                    │
┌───────────────────▼────────────────────┐
│ AI_9 Agent Core                        │
│ memory · profiles · state · invariants │
│ prompt · LLM · approvals · audit       │
└───────────┬───────────┬────────────────┘
            │           │
           RAG         MCP
            │           │
┌───────────▼───┐ ┌────▼────────────────┐
│ Wiki + code   │ │ Git + files + CRM   │
│ project docs  │ │ external services   │
└───────────────┘ └─────────────────────┘
                    │
          ┌─────────▼─────────┐
          │ Project workspace │
          │ source/tests/docs │
          └───────────────────┘
```

## 4.1. Разделение ответственности

| Подсистема | Ответственность |
|---|---|
| LLM | анализ, планирование, генерация предложений |
| Memory | требования, решения, контекст пользователя |
| RAG | поиск по Wiki, README и коду |
| MCP | Git, файлы, CRM и другие внешние инструменты |
| ToolPolicy | проверка разрешённости действия |
| InvariantChecker | запрет опасных действий |
| ToolExecutor | фактическое выполнение и аудит |
| StateMachine | разрешённые переходы |
| Workspace | изолированная среда проекта |
| Validator | тесты и проверки |
| Reviewer | анализ diff и архитектуры |
| Human approval | подтверждение важных операций |

MCP не должен превращаться в слой управления состоянием: он предоставляет инструменты, но не должен сам менять стадии задачи, память или профили [1].

***

# 5. План каталогов

Добавь следующие каталоги:

```text
docs/
├── WIKI.md
├── product_goal.md
├── product_scope.md
├── roadmap.md
├── wiki/
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
└── adr/
    ├── ADR-001-workspace.md
    ├── ADR-002-approval-model.md
    ├── ADR-003-project-scoped-rag.md
    └── ADR-004-file-tools.md

core/
├── project_models.py
├── project_manager.py
├── project_context.py
├── interview.py
├── requirements_service.py
├── architecture_service.py
├── development_planner.py
├── code_builder.py
├── file_actions.py
├── project_validator.py
├── review_models.py
├── project_reviewer.py
├── approval_service.py
└── delivery.py

integrations/
├── mcp/
│   ├── project_server.py
│   ├── project_tools.py
│   └── project_config.py
└── support/
    └── crm_server.py

pipelines/
├── create_application.py
├── code_review.py
├── docs_sync.py
├── support_answer.py
└── validation.py

workspace/
└── .gitkeep

tests/
├── test_project_models.py
├── test_interview.py
├── test_planner.py
├── test_file_policy.py
├── test_project_mcp.py
├── test_validation.py
├── test_review_pipeline.py
└── test_end_to_end_project.py
```

***

# 6. Этап 0. Зафиксировать продуктовую спецификацию

## Шаг 0.1. Создать `docs/product_goal.md`

Файл должен содержать:

```markdown
# AI_9 Developer Factory

## Проблема

Пользователь умеет описать нужную программу, но не всегда умеет
превратить идею в требования, архитектуру, код и проверяемый результат.

## Решение

AI_9 превращает естественно-языковое описание в проект,
который проходит через требования, планирование, реализацию,
тестирование, ревью и подтверждение.

## Пользователь

Разработчик, аналитик, специалист предметной области или автор идеи.

## Результат

Изолированная рабочая область с кодом, тестами, документацией,
отчётами и diff.
```

## Шаг 0.2. Создать `docs/product_scope.md`

Разделы:

- поддерживаемые типы приложений;
- поддерживаемые языки;
- поддерживаемые способы запуска;
- ограничения по доступу;
- запрещённые операции;
- критерии успешной генерации;
- требования к подтверждению.

## Шаг 0.3. Создать `docs/roadmap.md`

Раздели roadmap:

```text
MVP:
- CLI;
- Python-проекты;
- локальный workspace;
- RAG;
- MCP Git/file tools;
- tests;
- review;
- diff.

R2:
- Web UI;
- GitHub PR;
- несколько языков;
- Docker;
- локальные LLM;
- support assistant.

R3:
- deployment;
- командная работа;
- шаблоны проектов;
- marketplace;
- мониторинг.
```

## Гейт этапа

Переходи дальше, если:

- цель сформулирована;
- пользовательский сценарий описан;
- определён MVP;
- перечислены ограничения;
- есть критерии готовности.

***

# 7. Этап 1. Создать Wiki проекта

## Шаг 1.1. Разделить README

Перенеси содержимое README по тематическим страницам:

- обзор;
- архитектура;
- память;
- профили;
- состояния;
- инварианты;
- MCP;
- RAG;
- инструменты;
- CLI;
- storage;
- тестирование;
- деплой;
- безопасность;
- Developer Factory.

В README оставь только:

- краткое описание;
- возможности;
- быстрый запуск;
- ссылку на Wiki.

## Шаг 1.2. Создать главный `docs/WIKI.md`

Пример:

```markdown
# AI_9 Wiki

## Документация

- [Обзор](wiki/00_overview.md)
- [Архитектура](wiki/01_architecture.md)
- [Память](wiki/02_memory.md)
- [Профили](wiki/03_profiles.md)
- [Машина состояний](wiki/04_state_machine.md)
- [Инварианты](wiki/05_invariants.md)
- [MCP](wiki/06_mcp.md)
- [RAG](wiki/07_rag.md)
- [Инструменты](wiki/08_tools.md)
- [CLI](wiki/09_cli.md)
- [Хранилище](wiki/10_storage.md)
- [Тестирование](wiki/11_testing.md)
- [Развёртывание](wiki/12_deployment.md)
- [Developer Factory](wiki/13_developer_factory.md)
- [Безопасность](wiki/14_security.md)
```

## Шаг 1.3. Добавить стандарт страницы

Каждый файл Wiki должен содержать:

```markdown
# Название

## Назначение

## Ответственность

## Основные сущности

## Поток выполнения

## Хранение

## Ограничения

## Примеры

## Проверки

## Связанные документы
```

## Шаг 1.4. Добавить проверку ссылок

Создай скрипт:

```text
dev/check_docs_links.py
```

Он должен:

- найти Markdown-файлы;
- извлечь относительные ссылки;
- проверить существование целей;
- вывести список битых ссылок;
- завершиться с кодом `1`, если ссылка не найдена.

Команда:

```bash
python dev/check_docs_links.py
```

## Гейт Wiki

```text
✓ README краткий
✓ WIKI.md содержит полный указатель
✓ каждый раздел имеет отдельный файл
✓ ссылки работают
✓ описаны взаимосвязи
✓ описаны правила и запреты
```

***

# 8. Этап 2. Расширить RAG для проекта

Текущий RAG уже поддерживает корпус, чанкинг, гибридный поиск, источники, grounding и режим «не знаю» [1].

## Шаг 2.1. Разделить области знаний

Введи два scope:

```text
global:
    README AI_9
    Wiki AI_9
    архитектурные правила AI_9

project:
    requirements конкретного проекта
    код конкретного проекта
    тесты конкретного проекта
    документация конкретного проекта
```

Не смешивай их в один неразличимый индекс.

## Шаг 2.2. Создать конфигурацию корпуса

```json
{
  "global_roots": [
    "README.md",
    "docs/wiki",
    "core",
    "memory",
    "storage",
    "integrations",
    "rag",
    "Kod.py"
  ],
  "project_roots": [
    "workspace"
  ],
  "extensions": [
    ".md",
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".sh"
  ],
  "exclude": [
    ".git",
    ".venv",
    "__pycache__",
    "users",
    "rag/index",
    "dev/logs_reports",
    ".env"
  ]
}
```

## Шаг 2.3. Добавить тип источника

Каждый документ должен иметь:

```json
{
  "source": "core/tool_executor.py",
  "scope": "global",
  "kind": "code",
  "module": "core",
  "language": "python"
}
```

Для пользовательского проекта:

```json
{
  "source": "workspace/todo-app/source/storage.py",
  "scope": "project",
  "kind": "project_code",
  "project_id": "todo-app"
}
```

## Шаг 2.4. Индексировать после изменений

После записи файлов:

```text
file operation
→ invalidate affected documents
→ incremental ingest
→ new index version
```

Не переиндексируй весь корпус при каждом изменении.

## Шаг 2.5. Поддержать типы запросов

```text
архитектурный:
    какие границы есть между core и integrations?

проектный:
    где реализуется хранение шаблонов?

требовательный:
    соответствует ли код требованиям?

операционный:
    какие файлы изменены?

проверочный:
    есть ли тест для этой функции?
```

## Гейт RAG

Проверить:

```bash
./run.sh --rag-ingest
./run.sh --rag-search "как выполняется ToolExecutor"
./run.sh --rag-search "какие требования у текущего проекта"
./run.sh --rag-ask "соответствует ли архитектура правилам MCP"
```

У каждого ответа должны быть:

- источники;
- пути к файлам;
- scope;
- честный отказ при отсутствии данных.

***

# 9. Этап 3. Добавить Project MCP

## Шаг 3.1. Определить инструменты

Минимальный набор:

```text
get_git_branch
get_git_status
get_git_diff
list_project_files
read_project_file
search_project
create_patch
write_project_file
run_project_check
```

Раздели их по риску.

| Инструмент | Риск | Подтверждение |
|---|---:|---:|
| `get_git_branch` | low | нет |
| `get_git_status` | low | нет |
| `get_git_diff` | low | нет |
| `list_project_files` | low | нет |
| `read_project_file` | low | нет |
| `search_project` | low | нет |
| `run_project_check` | medium | желательно |
| `create_patch` | medium | нет, только preview |
| `write_project_file` | high | да |
| `delete_project_file` | critical | запретить |
| `execute_shell` | critical | запретить в MVP |

## Шаг 3.2. Создать конфигурацию

```json
{
  "server_id": "project",
  "transport": "stdio",
  "enabled": true,
  "root": ".",
  "allowed_tools": [
    "get_git_branch",
    "get_git_status",
    "get_git_diff",
    "list_project_files",
    "read_project_file",
    "search_project",
    "create_patch",
    "run_project_check"
  ],
  "denied_tools": [
    "delete_project_file",
    "execute_shell"
  ]
}
```

Инструмент записи подключай только в режиме, где включено подтверждение.

## Шаг 3.3. Ограничить корень

Все пути нормализуются:

```python
root = project_root.resolve()
candidate = (root / requested_path).resolve()

if not candidate.is_relative_to(root):
    raise PermissionError("Path escapes project root")
```

Запретить:

```text
.git/
.env
.env.*
users/
secrets/
ssh/
credentials/
workspace outside current project
```

## Шаг 3.4. Ограничить размер

Для чтения:

```text
max_file_bytes = 1_000_000
max_diff_bytes = 5_000_000
max_search_results = 200
```

Если результат усечён, инструмент обязан сообщить:

```json
{
  "truncated": true,
  "original_size": 12500000
}
```

## Шаг 3.5. Добавить аудит

Каждый вызов должен записывать:

```json
{
  "execution_id": "exec-123",
  "actor": "user:alice",
  "tool": "mcp.project.read_project_file",
  "arguments_hash": "...",
  "path": "core/agent.py",
  "status": "succeeded",
  "timestamp": "2026-10-19T..."
}
```

Сырые секреты и содержимое `.env` в аудит не записывать.

## Гейт MCP

Проверить:

```text
/mcp connect project
/mcp tools
/mcp call mcp.project.get_git_branch {}
/mcp call mcp.project.get_git_status {}
/mcp call mcp.project.get_git_diff {}
/mcp call mcp.project.search_project {"query": "ToolExecutor"}
```

Дополнительные тесты:

```text
../../secret.txt → отказ
.git/config → отказ
.env → отказ
outside-root/file.py → отказ
```

***

# 10. Этап 4. Реализовать `/help`

## Шаг 4.1. Создать `ProjectContext`

```python
@dataclass
class ProjectContext:
    project_id: str
    root: str
    branch: str | None
    commit: str | None
    dirty: bool
    changed_files: list[str]
    sources: list[dict]
```

## Шаг 4.2. Создать `ProjectHelpService`

```python
class ProjectHelpService:
    def answer(self, question: str, context: ProjectContext) -> str:
        ...
```

Поток:

```text
question
→ git branch/status
→ RAG search
→ context block
→ LLM
→ grounding check
→ answer with sources
```

## Шаг 4.3. Поддержать вопросы

```text
/help что делает ToolExecutor?
/help какие ограничения есть у MCP?
/help где реализована память?
/help какие файлы сейчас изменены?
/help какие переходы разрешены из planning?
```

## Шаг 4.4. Требования к ответу

Каждый ответ должен:

- приводить пути;
- отличать Wiki от кода;
- ссылаться на источники;
- не придумывать отсутствующие функции;
- сообщать об отсутствии данных;
- показывать текущую ветку при вопросах о состоянии проекта.

## Гейт `/help`

```text
✓ вопрос о структуре получает ответ
✓ ответ использует RAG
✓ есть ссылки на источники
✓ учитывается git-контекст
✓ неизвестный вопрос не вызывает выдуманный ответ
```

***

# 11. Этап 5. Создать модель проекта

## Шаг 5.1. Создать `core/project_models.py`

```python
@dataclass
class Project:
    project_id: str
    name: str
    owner_id: str
    goal: str
    status: str
    created_at: str
    active_task_id: str | None = None

@dataclass
class Workspace:
    workspace_id: str
    project_id: str
    root: str
    branch: str | None
    created_at: str
    mode: str  # plan, preview, execute

@dataclass
class ProjectArtifact:
    artifact_id: str
    project_id: str
    kind: str
    path: str
    version: int
    created_at: str
```

## Шаг 5.2. Добавить хранение

Рекомендуемая структура:

```text
users/<user_id>/
└── projects/
    └── <project_id>/
        ├── project.json
        ├── requirements.json
        ├── decisions.json
        ├── workflow.json
        ├── artifacts/
        ├── approvals/
        ├── reviews/
        └── audit.jsonl
```

Workspace лучше хранить отдельно:

```text
workspace/<project_id>/<workspace_id>/
```

## Шаг 5.3. Добавить методы Store

```python
create_project(...)
read_project(...)
write_project(...)
project_path(...)
workspace_path(...)
save_artifact(...)
load_artifact(...)
append_project_audit(...)
save_approval(...)
load_approval(...)
```

Все операции выполняются через `Store`, а не прямой записью из бизнес-логики.

***

# 12. Этап 6. Создать интервью требований

## Шаг 6.1. Добавить состояния интервью

```python
class InterviewState(str, Enum):
    NOT_STARTED = "not_started"
    ACTIVE = "active"
    READY = "ready"
    CONFIRMED = "confirmed"
```

## Шаг 6.2. Добавить обязательные поля

```text
goal
target_users
platform
main_features
data_storage
integrations
security_requirements
acceptance_criteria
constraints
```

Не все поля обязаны быть заполнены для любого проекта, но агент должен явно отметить:

```text
known
unknown
assumption
not_applicable
```

## Шаг 6.3. Реализовать `/create-app`

Поток:

```text
/create-app
→ создать проект
→ получить цель
→ определить пробелы
→ задать вопросы
→ сохранить ответы
→ показать резюме
→ получить подтверждение
```

Пример:

```text
Интервью завершено.

Цель:
Создать desktop-калькулятор формул.

Зафиксированные ограничения:
- Linux;
- локальное хранение;
- экспорт CSV;
- произвольное число переменных.

Неопределённые вопросы:
- GUI-фреймворк;
- поддерживаемый синтаксис формул.

Продолжить с архитектурными вариантами? [да/нет]
```

## Шаг 6.4. Записывать решения

Каждое важное решение:

```json
{
  "id": "decision-001",
  "text": "Использовать SQLite для хранения шаблонов",
  "status": "proposed",
  "source": "user",
  "created_at": "..."
}
```

## Гейт интервью

Интервью готово, если:

- цель не пуста;
- известны пользователи;
- определены основные функции;
- зафиксированы ограничения;
- неясные места помечены;
- пользователь подтвердил резюме.

***

# 13. Этап 7. Формировать требования

## Шаг 7.1. Создать `requirements.md`

```markdown
# Требования проекта

## 1. Цель

## 2. Пользователи

## 3. Пользовательские сценарии

## 4. Функциональные требования

## 5. Нефункциональные требования

## 6. Ограничения

## 7. Безопасность

## 8. Критерии приёмки

## 9. Открытые вопросы

## 10. Допущения
```

## Шаг 7.2. Генерировать идентификаторы

Каждое требование:

```text
FR-001
FR-002
NFR-001
SEC-001
ACC-001
```

Пример:

```markdown
### FR-001

Пользователь может создать шаблон с произвольным количеством переменных.

### ACC-001

При создании шаблона с 2, 5 и 10 переменными система корректно сохраняет
и выполняет расчёт.
```

## Шаг 7.3. Проверить требования

Создай детерминированный валидатор:

```text
requirements has goal
requirements has acceptance criteria
every feature has identifier
every open question has status
no conflicting constraints
```

## Гейт требований

Переход к архитектуре разрешён только после:

```text
requirements_valid == true
requirements_confirmed == true
```

***

# 14. Этап 8. Сформировать архитектуру

## Шаг 8.1. Получить варианты

Агент должен предложить не менее двух вариантов, если задача это допускает:

```text
A: CLI + SQLite
B: desktop GUI + SQLite
C: web app + API + database
```

Для каждого варианта:

- технологии;
- плюсы;
- минусы;
- зависимости;
- риски;
- соответствие ограничениям;
- стоимость реализации;
- тестируемость.

## Шаг 8.2. Создать `architecture.md`

```markdown
# Архитектура

## Выбранный вариант

## Компоненты

## Потоки данных

## Хранение

## API

## Ошибки

## Безопасность

## Тестирование

## Ограничения

## Невыбранные альтернативы
```

## Шаг 8.3. Создать ADR

```markdown
# ADR-001: Технологический стек

## Статус

Accepted

## Контекст

## Решение

## Рассмотренные альтернативы

## Последствия

## Связанные требования
```

## Шаг 8.4. Получить подтверждение

```text
/architecture approve
```

До подтверждения кодирование запрещено.

***

# 15. Этап 9. Создать план реализации

## Шаг 9.1. Модель плана

```python
@dataclass
class PlanStep:
    step_id: str
    title: str
    description: str
    files_to_create: list[str]
    files_to_modify: list[str]
    tests: list[str]
    dependencies: list[str]
    risks: list[str]
```

## Шаг 9.2. План должен содержать

- порядок шагов;
- создаваемые файлы;
- изменяемые файлы;
- тесты;
- критерии завершения;
- риски;
- зависимости;
- точки остановки.

## Шаг 9.3. Проверить план

```text
нет циклических зависимостей
каждый функциональный пункт покрыт шагом
каждый шаг имеет проверку
запрещённые файлы не затрагиваются
технологии соответствуют ADR
```

## Шаг 9.4. Получить approval

Используй существующую идею остановки в `planning`: агент строит план, но не перепрыгивает в реализацию без `/approve` [1].

```text
/approve plan
```

После подтверждения создаётся workspace.

***

# 16. Этап 10. Создать изолированный workspace

## Шаг 10.1. Структура workspace

```text
workspace/<project_id>/<workspace_id>/
├── source/
├── tests/
├── docs/
├── artifacts/
│   ├── requirements.md
│   ├── architecture.md
│   ├── implementation_plan.md
│   └── decisions.md
├── reports/
├── patches/
└── workspace.json
```

## Шаг 10.2. Правила workspace

Агент может:

- читать только разрешённые файлы;
- писать только в workspace;
- создавать файлы в пределах workspace;
- запускать только разрешённые проверки;
- готовить diff;
- сохранять отчёты.

Агент не может:

- менять основную ветку;
- читать секреты;
- удалять `.git`;
- писать за пределами workspace;
- менять системные файлы;
- отправлять данные в неизвестные сети.

## Шаг 10.3. Связь с Git

В MVP выбери один вариант:

```text
вариант 1: копия проекта в workspace
вариант 2: git worktree
вариант 3: отдельная временная ветка
```

Лучший вариант для Git-проекта:

```text
git worktree add workspace/<project_id>/<workspace_id> \
    -b ai9/<project_id>/<workspace_id>
```

Но команду должен выполнять не LLM напрямую, а контролируемый адаптер Git с allowlist операций.

***

# 17. Этап 11. Реализовать генерацию кода

## Шаг 11.1. Генерировать изменения по одному шагу

Не проси модель сразу создать весь проект. Цикл:

```text
1. взять один PlanStep;
2. прочитать нужные файлы;
3. получить RAG-контекст;
4. предложить FileOperations;
5. проверить операции;
6. сформировать diff;
7. применить после approval;
8. запустить локальные проверки;
9. перейти к следующему шагу.
```

## Шаг 11.2. Модель операции

```python
@dataclass
class FileOperation:
    operation_id: str
    action: str  # create | modify
    path: str
    expected_hash: str | None
    content: str
    reason: str
    related_requirements: list[str]
    related_plan_step: str
```

Удаление файлов в MVP не поддерживать. Если позже добавишь удаление, оно должно быть отдельным инструментом с максимальным уровнем риска.

## Шаг 11.3. Генерировать патч, а не blind overwrite

Порядок:

```text
read current file
→ generate proposed change
→ validate path
→ validate expected hash
→ produce unified diff
→ show user
→ apply exact patch
```

Если файл изменился после чтения, операция должна остановиться из-за конфликта hash.

## Шаг 11.4. Контекст генерации

В prompt передавать:

```text
[goal]
[requirements]
[architecture]
[current_plan_step]
[relevant_files]
[rag_sources]
[invariants]
[existing_tests]
[project_context]
```

Не передавай весь репозиторий целиком: ограничивай контекст файлами текущего шага и связанными источниками.

## Шаг 11.5. Контроль области изменений

До применения проверить:

```text
changed path belongs to workspace
path is allowed for current plan step
no secret files touched
no forbidden directory touched
file count is within limit
diff size is within limit
```

# 18. Этап 12. Реализовать тестирование

## Шаг 12.1. Генерировать тесты вместе с кодом

Для каждого функционального требования должен существовать хотя бы один тест или объяснение, почему автоматический тест неприменим.

```text
FR-001 → test_template_with_many_variables
FR-002 → test_template_persistence
FR-003 → test_csv_export
```

## Шаг 12.2. Создать Validator

Проверки:

```text
compile/import
unit tests
integration tests
lint
format
type check
documentation links
requirements coverage
security rules
unexpected file changes
```

## Шаг 12.3. Ограничить команды

Вместо произвольного `shell` используй зарегистрированные операции:

```text
run_python_tests
run_py_compile
run_ruff
run_mypy
run_doc_link_check
run_project_specific_check
```

Команды должны запускаться через sandbox/subprocess adapter с:

- таймаутом;
- ограничением памяти;
- ограничением вывода;
- разрешённым рабочим каталогом;
- запрещённой сетью, если она не нужна;
- сохранением exit code.

## Шаг 12.4. Формат отчёта

```markdown
# Test Report

## Summary

Passed: 12
Failed: 0
Skipped: 1

## Checks

| Check | Status | Duration |
|---|---|---|
| compile | passed | 0.4s |
| unit tests | passed | 3.1s |
| lint | passed | 0.8s |

## Failures

## Warnings

## Requirements coverage
```

## Гейт валидации

```text
implementation → validation
```

разрешён только после завершения всех обязательных проверок.

Если тесты не проходят:

```text
validation_failed
→ агент получает отчёт
→ предлагает исправление
→ создаётся новый diff
→ повторная проверка
```

Ограничь число циклов, например:

```text
max_fix_attempts = 3
```

После лимита — остановка и передача человеку.

***

# 19. Этап 13. Реализовать AI Code Review

## Шаг 13.1. Получить diff

Code review должен анализировать:

- diff;
- изменённые файлы;
- связанные файлы;
- требования;
- архитектуру;
- Wiki;
- инварианты;
- результаты тестов.

## Шаг 13.2. Проверки reviewer

### Потенциальные баги

- неправильная обработка ошибок;
- пустые значения;
- несовместимые типы;
- неверные границы;
- потеря данных;
- race conditions;
- неправильная сериализация.

### Архитектура

- импорт не из того слоя;
- циклическая зависимость;
- нарушение DI;
- прямой доступ к storage;
- протекание MCP SDK в `core`;
- смешение RAG и state machine.

### Безопасность

- секреты в коде;
- небезопасные пути;
- shell injection;
- отсутствие подтверждения;
- чрезмерные права;
- неограниченное чтение файлов.

### Качество

- отсутствуют тесты;
- устарела Wiki;
- не обновлены примеры;
- нет миграции;
- нет обработки ошибок.

OWASP рекомендует ограничивать агенту доступ к инструментам и файлам по принципу наименьших привилегий, а также проверять каждую изменённую область отдельно [4][3].

## Шаг 13.3. Формат finding

```python
@dataclass
class ReviewFinding:
    finding_id: str
    severity: str
    category: str
    title: str
    file: str
    line_start: int | None
    line_end: int | None
    evidence: str
    explanation: str
    recommendation: str
    requirement_refs: list[str]
```

## Шаг 13.4. Итоговый отчёт

```markdown
# AI Code Review

## Summary

## Critical findings

## High findings

## Medium findings

## Low findings

## Architecture review

## Security review

## Test review

## Documentation review

## Recommendation

- approve
- approve with changes
- request changes
- blocked
```

## Гейт review

Нельзя переходить к delivery, если:

```text
critical findings > 0
high findings > 0
tests failed
requirements coverage incomplete
approval missing
```

# 20. Этап 14. Обновить документацию автоматически

## Шаг 14.1. Создать Docs Sync Pipeline

```text
get changed files
→ determine affected modules
→ find related Wiki pages
→ compare code and docs
→ propose documentation changes
→ generate patch
→ review patch
→ approval
→ apply
```

## Шаг 14.2. Правила обновления

Автоматически предлагать изменение документации, если:

- появилась новая команда;
- изменился публичный API;
- добавился MCP-инструмент;
- изменился формат хранения;
- добавилась стадия workflow;
- изменились инварианты;
- поменялся запуск;
- изменился технологический стек.

## Шаг 14.3. Не разрешать слепое обновление

Документация не должна переписывать правила только на основании текста LLM. Сначала сравни:

```text
code facts
+ existing Wiki
+ proposed change
```

Затем сформируй diff и запроси подтверждение.

***

# 21. Этап 15. Реализовать approval-модель

## Шаг 15.1. Уровни риска

```text
LOW:
    чтение Wiki
    поиск
    получение Git status

MEDIUM:
    запуск тестов
    создание diff
    создание отчёта

HIGH:
    запись файлов
    изменение конфигурации
    создание commit

CRITICAL:
    удаление
    push
    merge
    deploy
    изменение секретов
```

## Шаг 15.2. Правила

```text
LOW       → автоматическое выполнение
MEDIUM    → автоматическое выполнение в sandbox
HIGH      → exact action approval
CRITICAL  → отдельное подтверждение + человек с правом
```

Подтверждение должно быть связано не просто с флагом `approved`, а с конкретным действием: пользователем, инструментом, нормализованными аргументами, временем и сроком действия [3].

## Шаг 15.3. Модель approval

```python
@dataclass
class Approval:
    approval_id: str
    actor_id: str
    action_hash: str
    tool_name: str
    normalized_arguments: dict
    created_at: str
    expires_at: str
    consumed: bool
```

Перед выполнением:

```text
1. пересчитать hash действия;
2. найти approval;
3. проверить actor;
4. проверить срок;
5. проверить tool;
6. проверить аргументы;
7. атомарно пометить approval consumed;
8. выполнить действие.
```

## Шаг 15.4. Команды

```text
/approve requirements
/approve architecture
/approve plan
/approve changes
/approve commit
/reject changes
```

Не используй один универсальный approval для всех фаз.

***

# 22. Этап 16. Delivery: diff, commit, PR

## Шаг 16.1. MVP delivery

В первой версии:

```text
создать diff
сохранить отчёты
создать архив workspace
вывести инструкции
```

## Шаг 16.2. Commit

После отдельного подтверждения:

```text
/approve commit
```

сервис может создать commit в ветке:

```text
ai9/<project_id>/<task_id>
```

## Шаг 16.3. Pull Request

После реализации GitHub-интеграции:

```text
create branch
push branch
create pull request
attach requirements
attach test report
attach review
attach diff summary
```

Основная ветка должна быть защищена. GitHub branch protection позволяет требовать статус-проверки и одобрения перед merge [5][6][7].

Агент не должен сам одобрять или вливать собственный PR [2].

# 23. Этап 17. Добавить support assistant

Этот этап можно реализовать после основного Developer Factory.

## Шаг 17.1. CRM MCP

Инструменты:

```text
get_user
get_ticket
list_user_tickets
add_ticket_note
```

## Шаг 17.2. Контекст тикета

```python
@dataclass
class TicketContext:
    ticket_id: str
    user_id: str
    user_data: dict
    history: list[dict]
    metadata: dict
```

## Шаг 17.3. Ответ

```text
ticket context
+ product Wiki
+ project documentation
+ user profile
→ support answer
```

## Шаг 17.4. Ограничения

Support assistant не должен:

- менять CRM без подтверждения;
- раскрывать секреты;
- обещать выполненную операцию без результата MCP;
- придумывать продуктовые функции;
- смешивать внутреннюю документацию AI_9 с пользовательской документацией продукта.

***

# 24. Этап 18. HTTP/API и Web UI

После CLI реализуй сервисный слой.

## API

```text
POST /projects
GET  /projects/<id>
POST /projects/<id>/interview
POST /projects/<id>/requirements
POST /projects/<id>/architecture
POST /projects/<id>/plan
POST /projects/<id>/approve
POST /projects/<id>/run
GET  /projects/<id>/status
GET  /projects/<id>/diff
GET  /projects/<id>/review
GET  /projects/<id>/artifacts
POST /help
POST /review
POST /support
```

## Авторизация

Каждый запрос должен проверять:

```text
API key / Bearer token
user_id
project ownership
operation scope
```

Пользователь не должен иметь доступ к чужому `project_id`.

## Web UI

Минимальные экраны:

```text
1. список проектов
2. интервью
3. требования
4. архитектура
5. план
6. ход реализации
7. тесты
8. review
9. diff
10. approval
```

***

# 25. Этап 19. Реальный демонстрационный проект

Для итоговой защиты выбери один проект. Рекомендуемый вариант:

> **Переносное приложение для расчёта и сравнения вариаций формул с произвольным числом переменных, пользовательскими шаблонами и экспортом CSV.**

## Требования демонстрации

Пользователь говорит:

```text
Создай приложение для расчёта и сравнения вариантов формул.
Нужно поддержать произвольное число переменных, шаблоны,
сохранение и экспорт результатов в CSV.
```

AI_9 должен создать:

```text
source/
├── app.py
├── formula_parser.py
├── template_store.py
├── calculator.py
└── exporter.py

tests/
├── test_formula_parser.py
├── test_calculator.py
├── test_template_store.py
└── test_exporter.py

docs/
├── README.md
├── architecture.md
└── usage.md
```

## Демонстрационный прогон

```text
1. /create-app
2. ввести цель
3. пройти интервью
4. подтвердить требования
5. выбрать архитектуру
6. подтвердить план
7. запустить реализацию
8. показать diff
9. запустить тесты
10. выполнить review
11. обновить Wiki
12. подтвердить commit
```

***

# 26. Этап 20. Тестовая стратегия

## Уровень L1 — импорты

```bash
python -m compileall core memory storage integrations rag
```

## Уровень L2 — unit-тесты

Проверить:

- модели проекта;
- интервью;
- требования;
- планировщик;
- path policy;
- approval;
- RAG scope;
- Git tools;
- review models.

## Уровень L3 — integration

Проверить:

```text
project manager + Store
project help + RAG
project MCP + ToolExecutor
file action + InvariantChecker
validator + workspace
review + diff
```

## Уровень L4 — end-to-end

Полный сценарий:

```text
goal
→ interview
→ requirements
→ architecture
→ plan
→ approval
→ workspace
→ code
→ tests
→ review
→ docs
→ diff
```

## Отдельные security-тесты

```text
path traversal
secret read
.env indexing
.git access
outside workspace write
double approval replay
expired approval
wrong actor approval
tool substitution
oversized file
oversized diff
unapproved write
```

***

# 27. Этап 21. Критерии приёмки

## Product

- Пользователь описывает цель обычным языком.
- Сервис задаёт уточняющие вопросы.
- Формируются требования и критерии приёмки.
- Пользователь утверждает требования.

## Architecture

- Предлагается архитектура.
- Решения сохраняются в ADR.
- Технологический стек не меняется молча.
- План связан с требованиями.

## Implementation

- Создаётся отдельный workspace.
- Агент работает минимум с несколькими файлами.
- Все изменения представлены как операции и diff.
- Запись защищена политиками.

## RAG

- Индексируются README, Wiki и код.
- Источники отображаются в ответах.
- Можно искать по глобальной и проектной базе отдельно.
- При недостатке контекста агент сообщает об этом.

## MCP

- Получаются branch, status и diff.
- Работает поиск и чтение файлов.
- Запись выполняется только через ToolExecutor.
- Недоступность MCP не ломает приложение.

## Validation

- Запускаются тесты.
- Проверяется компиляция.
- Проверяется документация.
- Генерируется test report.
- Ошибки приводят к исправлению или остановке.

## Review

- Формируется code review.
- Указываются файлы и строки.
- Есть категории и severity.
- Проверяются архитектура, безопасность, тесты и документация.

## Delivery

- Создаётся diff.
- Commit и PR требуют approval.
- Агент не merge-ит свой PR.
- История действий сохраняется.

# 28. Порядок выполнения по коммитам

Удобно реализовывать по небольшим независимым коммитам.

```text
1. docs: add product goal and scope
2. docs: split README into Wiki
3. rag: add project corpus and scopes
4. mcp: add project read-only server
5. core: add ProjectContext and /help
6. core: add project models and storage
7. workflow: add interview state
8. workflow: add requirements generation
9. workflow: add architecture and ADR
10. workflow: add development planner
11. workspace: add isolated workspace manager
12. tools: add safe file operations
13. approval: add exact action approvals
14. validation: add project validator
15. review: add AI code review pipeline
16. docs: add documentation synchronization
17. delivery: add diff and commit preparation
18. support: add CRM MCP
19. api: add project HTTP endpoints
20. tests: add end-to-end acceptance scenario
```

После каждого коммита запускай минимальную проверку:

```bash
python -m compileall .
pytest -q
python dev/check_docs_links.py
```

# 29. Итоговый порядок разработки

Фактически работай в такой последовательности:

```text
Шаг 1. Зафиксировать продуктовую цель.
Шаг 2. Определить MVP и запреты.
Шаг 3. Перенести README в Wiki.
Шаг 4. Проверить Markdown-ссылки.
Шаг 5. Разделить global/project RAG.
Шаг 6. Индексировать Wiki и код.
Шаг 7. Добавить read-only Project MCP.
Шаг 8. Реализовать /help.
Шаг 9. Добавить модели Project и Workspace.
Шаг 10. Добавить интервью.
Шаг 11. Генерировать requirements.md.
Шаг 12. Добавить архитектурные варианты и ADR.
Шаг 13. Добавить планировщик разработки.
Шаг 14. Реализовать approval плана.
Шаг 15. Создать изолированный workspace.
Шаг 16. Добавить безопасные операции с файлами.
Шаг 17. Реализовать генерацию по шагам.
Шаг 18. Добавить запуск тестов и валидатор.
Шаг 19. Добавить AI code review.
Шаг 20. Добавить синхронизацию Wiki.
Шаг 21. Добавить diff и delivery.
Шаг 22. Добавить commit/PR после approval.
Шаг 23. Добавить CRM и support.
Шаг 24. Добавить HTTP API.
Шаг 25. Провести полный end-to-end прогон.
Шаг 26. Описать результат в Wiki и отчёте.
```

# 30. Финальная формулировка для отчёта

Можно использовать такой текст:

> В рамках проекта AI_9 реализуется AI-сервис автоматизированной разработки программного обеспечения. Пользователь задаёт цель на естественном языке, после чего агент проводит интервью, формирует требования, предлагает архитектуру, строит план и создаёт код в изолированной рабочей области. RAG предоставляет знания из Wiki, README и исходного кода, MCP обеспечивает доступ к Git и файловым операциям, а ToolPolicy, InvariantChecker, approval-механизм и аудит ограничивают опасные действия. После реализации агент запускает тесты, выполняет автоматическое code review, обновляет документацию и формирует diff или pull request. Финальное принятие изменений, merge и production-деплой остаются за человеком.

Это даст не набор несвязанных функций, а цельный продуктовый конвейер:

```text
идея пользователя
→ требования
→ архитектура
→ план
→ код
→ тесты
→ ревью
→ документация
→ diff/PR
→ подтверждение
→ готовый программный продукт
```




Связать машину состояний AI_9 с планом нужно не через добавление множества разрозненных `if`, а через превращение всего процесса создания ПО в **управляемый workflow**, где:

- машина состояний определяет, **какой этап сейчас активен**;
- переходы определяют, **какой следующий этап разрешён**;
- guard-проверки определяют, **можно ли переход выполнить сейчас**;
- RAG, MCP и LLM выполняют работу внутри этапа;
- инварианты запрещают опасные действия;
- approval-механизм управляет контрольными точками;
- журнал переходов обеспечивает воспроизводимость и аудит.

Это соответствует общей модели AI-agent workflow: агент интерпретирует цель, планирует действия, вызывает инструменты, наблюдает результаты и обновляет состояние; опасные действия должны проходить отдельное человеческое подтверждение [1][2]. В классической конечной машине состояния переход разрешается только при выполнении guard-условий, а сам переход и побочные эффекты должны быть разделены [3][4].

# 1. Не смешивать два вида состояния

В AI_9 уже есть `TaskStage`:

```python
NEW
PLANNING
PLAN_APPROVED
IMPLEMENTATION
VALIDATION
DONE
PAUSED
FAILED
```

Он описывает **технический жизненный цикл задачи AI_9**.

Для Developer Factory нужен второй уровень — **бизнес-состояние создания программного продукта**:

```python
INTAKE
INTERVIEW
SPECIFICATION
ARCHITECTURE
PLANNING
IMPLEMENTATION
VALIDATION
REVIEW
APPROVAL
DELIVERY
COMPLETED
FAILED
PAUSED
```

## Рекомендуемая модель

Не удаляй текущий `TaskStage`. Добавь отдельный workflow:

```text
TaskState
    └── DevelopmentWorkflowState
```

То есть:

```python
@dataclass
class TaskState:
    task_id: str
    stage: TaskStage
    transition_log: list[TransitionRecord]
    development: DevelopmentWorkflowState | None
```

Но для первого этапа лучше сделать `development` отдельной сущностью:

```python
@dataclass
class DevelopmentWorkflow:
    project_id: str
    workflow_id: str
    stage: DevelopmentStage
    current_step_id: str | None
    previous_stage: DevelopmentStage | None
    attempts: int
    transition_log: list[TransitionRecord]
```

Так ты сохранишь обратную совместимость с текущими задачами AI_9.

# 2. Роли двух машин

## Текущая `TaskStage`

Она отвечает за общие задачи агента:

```text
NEW
→ PLANNING
→ PLAN_APPROVED
→ IMPLEMENTATION
→ VALIDATION
→ DONE
```

## Новая `DevelopmentStage`

Она отвечает за создание приложения:

```text
INTAKE
→ INTERVIEW
→ SPECIFICATION
→ ARCHITECTURE
→ PLANNING
→ IMPLEMENTATION
→ VALIDATION
→ REVIEW
→ APPROVAL
→ DELIVERY
→ COMPLETED
```

## Связь между ними

| `DevelopmentStage` | Внутренний `TaskStage` |
|---|---|
| `INTAKE` | `NEW` |
| `INTERVIEW` | `PLANNING` |
| `SPECIFICATION` | `PLANNING` |
| `ARCHITECTURE` | `PLANNING` |
| `PLANNING` | `PLANNING` |
| `IMPLEMENTATION` | `IMPLEMENTATION` |
| `VALIDATION` | `VALIDATION` |
| `REVIEW` | `VALIDATION` |
| `APPROVAL` | `VALIDATION` или отдельная approval-фаза |
| `DELIVERY` | `IMPLEMENTATION` или `DONE` после завершения |
| `COMPLETED` | `DONE` |
| `FAILED` | `FAILED` |
| `PAUSED` | `PAUSED` |

Важно: это не значит, что каждый переход верхней машины обязан вызывать переход `TaskStage`. Связь должна быть через координатор, а не через взаимные вызовы машин:

```text
DevelopmentWorkflowCoordinator
    ├── DevelopmentStateMachine
    └── TaskStateMachine
```

Не делай так:

```text
DevelopmentStateMachine → TaskStateMachine → DevelopmentStateMachine
```

Иначе появится цикл зависимостей и будет трудно понять, кто управляет переходом.

# 3. Полная карта состояний

## 3.1. Состояния

```python
class DevelopmentStage(str, Enum):
    INTAKE = "intake"
    INTERVIEW = "interview"
    SPECIFICATION = "specification"
    ARCHITECTURE = "architecture"
    PLANNING = "planning"
    IMPLEMENTATION = "implementation"
    VALIDATION = "validation"
    REVIEW = "review"
    APPROVAL = "approval"
    DELIVERY = "delivery"
    COMPLETED = "completed"
    PAUSED = "paused"
    FAILED = "failed"
```

## 3.2. Разрешённые переходы

```python
ALLOWED_DEVELOPMENT_TRANSITIONS = {
    DevelopmentStage.INTAKE: {
        DevelopmentStage.INTERVIEW,
        DevelopmentStage.PAUSED,
        DevelopmentStage.FAILED,
    },

    DevelopmentStage.INTERVIEW: {
        DevelopmentStage.SPECIFICATION,
        DevelopmentStage.PAUSED,
        DevelopmentStage.FAILED,
    },

    DevelopmentStage.SPECIFICATION: {
        DevelopmentStage.ARCHITECTURE,
        DevelopmentStage.INTERVIEW,
        DevelopmentStage.PAUSED,
        DevelopmentStage.FAILED,
    },

    DevelopmentStage.ARCHITECTURE: {
        DevelopmentStage.PLANNING,
        DevelopmentStage.SPECIFICATION,
        DevelopmentStage.PAUSED,
        DevelopmentStage.FAILED,
    },

    DevelopmentStage.PLANNING: {
        DevelopmentStage.IMPLEMENTATION,
        DevelopmentStage.ARCHITECTURE,
        DevelopmentStage.PAUSED,
        DevelopmentStage.FAILED,
    },

    DevelopmentStage.IMPLEMENTATION: {
        DevelopmentStage.VALIDATION,
        DevelopmentStage.PLANNING,
        DevelopmentStage.PAUSED,
        DevelopmentStage.FAILED,
    },

    DevelopmentStage.VALIDATION: {
        DevelopmentStage.REVIEW,
        DevelopmentStage.IMPLEMENTATION,
        DevelopmentStage.PAUSED,
        DevelopmentStage.FAILED,
    },

    DevelopmentStage.REVIEW: {
        DevelopmentStage.APPROVAL,
        DevelopmentStage.IMPLEMENTATION,
        DevelopmentStage.PAUSED,
        DevelopmentStage.FAILED,
    },

    DevelopmentStage.APPROVAL: {
        DevelopmentStage.DELIVERY,
        DevelopmentStage.IMPLEMENTATION,
        DevelopmentStage.REVIEW,
        DevelopmentStage.PAUSED,
        DevelopmentStage.FAILED,
    },

    DevelopmentStage.DELIVERY: {
        DevelopmentStage.COMPLETED,
        DevelopmentStage.FAILED,
        DevelopmentStage.PAUSED,
    },

    DevelopmentStage.COMPLETED: set(),

    DevelopmentStage.PAUSED: set(),

    DevelopmentStage.FAILED: {
        DevelopmentStage.PLANNING,
        DevelopmentStage.IMPLEMENTATION,
        DevelopmentStage.REVIEW,
    },
}
```

Главные запреты:

```text
INTAKE → IMPLEMENTATION запрещён
INTERVIEW → IMPLEMENTATION запрещён
PLANNING → DELIVERY запрещён
IMPLEMENTATION → COMPLETED запрещён
VALIDATION → DELIVERY запрещён
REVIEW → DELIVERY запрещён
```

Так код физически не позволит агенту перейти от идеи к готовому приложению без требований, плана, реализации, тестов, ревью и approval.

# 4. Состояние — это не действие

Очень важно разделять:

```text
state = где мы находимся
event = что произошло
command = что попросили сделать
guard = можно ли это сделать
side effect = что выполнить после перехода
```

Пример:

```text
state: PLANNING
event: PLAN_APPROVED
guard: план валиден и подтверждён
transition: PLANNING → IMPLEMENTATION
side effect: создать workspace
```

Не нужно считать, что вызов MCP автоматически меняет стадию:

```text
get_git_diff() ≠ переход в REVIEW
```

MCP только возвращает данные. Переход осуществляет координатор после проверки результата.

# 5. События workflow

Создай отдельное перечисление событий:

```python
class DevelopmentEvent(str, Enum):
    PROJECT_CREATED = "project_created"
    INTERVIEW_STARTED = "interview_started"
    INTERVIEW_COMPLETED = "interview_completed"
    REQUIREMENTS_GENERATED = "requirements_generated"
    REQUIREMENTS_APPROVED = "requirements_approved"
    ARCHITECTURE_GENERATED = "architecture_generated"
    ARCHITECTURE_APPROVED = "architecture_approved"
    PLAN_GENERATED = "plan_generated"
    PLAN_APPROVED = "plan_approved"
    IMPLEMENTATION_STARTED = "implementation_started"
    STEP_COMPLETED = "step_completed"
    VALIDATION_STARTED = "validation_started"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    REVIEW_STARTED = "review_started"
    REVIEW_PASSED = "review_passed"
    REVIEW_FAILED = "review_failed"
    CHANGES_APPROVED = "changes_approved"
    DELIVERY_STARTED = "delivery_started"
    DELIVERY_COMPLETED = "delivery_completed"
    USER_PAUSED = "user_paused"
    USER_RESUMED = "user_resumed"
    RETRY_REQUESTED = "retry_requested"
```

Переход должен выглядеть не так:

```python
workflow.stage = DevelopmentStage.IMPLEMENTATION
```

а так:

```python
workflow.apply(
    event=DevelopmentEvent.PLAN_APPROVED,
    actor="user:alice",
    metadata={"plan_hash": plan_hash},
)
```

# 6. Guard-проверки

Матрица переходов отвечает на вопрос:

```text
Разрешено ли такое направление перехода вообще?
```

Guard отвечает на вопрос:

```text
Выполнены ли условия для перехода сейчас?
```

## 6.1. Guards по этапам

### `INTAKE → INTERVIEW`

```text
project exists
goal is not empty
owner is authenticated
```

### `INTERVIEW → SPECIFICATION`

```text
interview completed
required fields known or explicitly marked unknown
user confirmed interview summary
```

### `SPECIFICATION → ARCHITECTURE`

```text
requirements.md exists
requirements are structurally valid
acceptance criteria exist
no unresolved blocking questions
```

### `ARCHITECTURE → PLANNING`

```text
architecture.md exists
technology decision exists
ADR exists
user approved architecture
```

### `PLANNING → IMPLEMENTATION`

```text
plan exists
plan is valid
all requirements map to plan steps
workspace is created
plan is approved
```

### `IMPLEMENTATION → VALIDATION`

```text
all mandatory plan steps completed
changed files are inside workspace
no forbidden file changed
diff is generated
```

### `VALIDATION → REVIEW`

```text
compile passed
mandatory tests passed
security checks passed
documentation links are valid
```

### `REVIEW → APPROVAL`

```text
review report exists
no critical findings
no unresolved high findings
test report is current for current diff
```

### `APPROVAL → DELIVERY`

```text
user approved exact changes
approval hash matches current diff
approval has not expired
actor has permission
```

### `DELIVERY → COMPLETED`

```text
diff or commit exists
artifacts saved
audit saved
delivery result recorded
```

# 7. Реализация переходов

Создай:

```text
core/development_state_machine.py
```

## 7.1. Модели

```python
@dataclass(frozen=True)
class TransitionRecord:
    transition_id: str
    workflow_id: str
    from_stage: str
    to_stage: str
    event: str
    allowed: bool
    actor: str
    reason: str
    metadata: dict
    created_at: str
```

```python
@dataclass
class DevelopmentWorkflowState:
    workflow_id: str
    project_id: str
    stage: DevelopmentStage
    previous_stage: DevelopmentStage | None
    current_step_id: str | None
    transition_log: list[TransitionRecord]
    failure_reason: str | None = None
```

## 7.2. Интерфейс

```python
class DevelopmentStateMachine:
    def can_transition(
        self,
        state: DevelopmentStage,
        event: DevelopmentEvent,
    ) -> bool:
        ...

    def try_transition(
        self,
        workflow: DevelopmentWorkflowState,
        event: DevelopmentEvent,
        actor: str,
        context: dict,
    ) -> DevelopmentWorkflowState:
        ...
```

## 7.3. Порядок проверки

```text
1. определить target stage по current stage + event;
2. проверить наличие дуги;
3. проверить guard;
4. если отказ — записать allowed=false;
5. если успех — изменить stage;
6. записать allowed=true;
7. выполнить side effect через координатор.
```

Не выполняй внешние вызовы внутри чистого `can_transition`. Guard должен быть предсказуемым и не должен сам изменять состояние; такое разделение повышает тестируемость и аудитируемость [4][5].

# 8. Координатор workflow

Создай:

```text
core/development_workflow.py
```

Он соединяет:

```text
DevelopmentStateMachine
ProjectManager
MemoryManager
RagService
ToolExecutor
Validator
Reviewer
ApprovalService
```

## 8.1. Основной интерфейс

```python
class DevelopmentWorkflowCoordinator:
    def start_project(self, goal: str) -> Project: ...
    def start_interview(self, project_id: str) -> None: ...
    def complete_interview(self, project_id: str) -> None: ...
    def generate_requirements(self, project_id: str) -> None: ...
    def approve_requirements(self, project_id: str) -> None: ...
    def generate_architecture(self, project_id: str) -> None: ...
    def approve_architecture(self, project_id: str) -> None: ...
    def generate_plan(self, project_id: str) -> None: ...
    def approve_plan(self, project_id: str) -> None: ...
    def implement_next_step(self, project_id: str) -> None: ...
    def validate(self, project_id: str) -> None: ...
    def review(self, project_id: str) -> None: ...
    def approve_changes(self, project_id: str) -> None: ...
    def deliver(self, project_id: str) -> None: ...
```

## 8.2. Внутренний поток

```text
command
→ coordinator
→ load workflow state
→ prepare context
→ generate result or execute tool
→ persist artifact
→ apply event
→ persist new state
→ write audit
```

Машина состояния не должна сама генерировать код, вызывать LLM или читать файлы. Она только решает, разрешён ли переход.

# 9. Связь с существующим `TaskStage`

Есть два практических варианта.

## Вариант 1 — адаптер

Создай:

```text
core/development_task_adapter.py
```

Он отображает этапы:

```python
DEVELOPMENT_TO_TASK_STAGE = {
    DevelopmentStage.INTAKE: TaskStage.NEW,
    DevelopmentStage.INTERVIEW: TaskStage.PLANNING,
    DevelopmentStage.SPECIFICATION: TaskStage.PLANNING,
    DevelopmentStage.ARCHITECTURE: TaskStage.PLANNING,
    DevelopmentStage.PLANNING: TaskStage.PLANNING,
    DevelopmentStage.IMPLEMENTATION: TaskStage.IMPLEMENTATION,
    DevelopmentStage.VALIDATION: TaskStage.VALIDATION,
    DevelopmentStage.REVIEW: TaskStage.VALIDATION,
    DevelopmentStage.APPROVAL: TaskStage.VALIDATION,
    DevelopmentStage.DELIVERY: TaskStage.IMPLEMENTATION,
    DevelopmentStage.COMPLETED: TaskStage.DONE,
    DevelopmentStage.PAUSED: TaskStage.PAUSED,
    DevelopmentStage.FAILED: TaskStage.FAILED,
}
```

После успешного изменения `DevelopmentStage` адаптер пытается синхронизировать `TaskStage`.

## Вариант 2 — не менять `TaskStage` во время внутренних подэтапов

Можно оставить `TaskStage.PLANNING` активным на всём этапе:

```text
INTERVIEW
SPECIFICATION
ARCHITECTURE
PLANNING
    ↓
TaskStage.PLANNING
```

Затем:

```text
IMPLEMENTATION
    ↓
TaskStage.IMPLEMENTATION
```

Это проще и безопаснее для обратной совместимости.

Рекомендую именно этот вариант для первой реализации.

# 10. Как связать команды CLI

Добавь команды:

```text
/project create <цель>
/project status
/project interview
/project requirements
/project architecture
/project plan
/project implement
/project validate
/project review
/project approve
/project deliver
/project pause
/project resume
/project retry
```

И короткие aliases:

```text
/create-app
/plan
/approve
/run
/review
/diff
/deliver
```

## Пример полного CLI-цикла

```text
/create-app
```

Переход:

```text
NEW → INTERVIEW
```

```text
/project interview
```

Переход:

```text
INTERVIEW → SPECIFICATION
```

```text
/project requirements
```

Сначала создаётся артефакт, затем:

```text
SPECIFICATION → ARCHITECTURE
```

```text
/project architecture
/approve architecture
```

```text
ARCHITECTURE → PLANNING
```

```text
/project plan
/approve plan
```

```text
PLANNING → IMPLEMENTATION
```

```text
/project implement
```

После завершения плана:

```text
IMPLEMENTATION → VALIDATION
```

```text
/project validate
```

После успешных проверок:

```text
VALIDATION → REVIEW
```

```text
/project review
```

После успешного review:

```text
REVIEW → APPROVAL
```

```text
/approve changes
```

```text
APPROVAL → DELIVERY
```

```text
/project deliver
```

После сохранения результата:

```text
DELIVERY → COMPLETED
```

# 11. Подключение RAG и MCP по состояниям

Не все инструменты должны быть доступны на всех стадиях.

## Матрица инструментов

| Инструмент | Интервью | План | Реализация | Валидация | Review | Delivery |
|---|---:|---:|---:|---:|---:|---:|
| `get_git_branch` | да | да | да | да | да | да |
| `get_git_status` | да | да | да | да | да | да |
| `read_project_file` | нет | да | да | да | да | да |
| `search_project` | да | да | да | да | да | да |
| `get_git_diff` | нет | нет | да | да | да | да |
| `create_patch` | нет | нет | да | да | да | да |
| `write_project_file` | нет | нет | после approval | после approval | нет | нет |
| `run_project_check` | нет | нет | да | да | да | да |
| `create_commit` | нет | нет | нет | нет | нет | после approval |
| `create_pr` | нет | нет | нет | нет | нет | после approval |

## RAG по стадиям

### Интервью

Искать:

```text
домен пользователя
шаблоны требований
ограничения проекта
```

### Архитектура

Искать:

```text
архитектурные правила
ADR
технологические ограничения
существующие компоненты
```

### Реализация

Искать:

```text
связанные модули
примеры кода
API
тесты
```

### Review

Искать:

```text
инварианты
правила слоёв
критерии качества
безопасность
```

### Support

Искать:

```text
Wiki продукта
инструкции
тикет
историю пользователя
```

# 12. Связь с инвариантами

Машина состояния отвечает за порядок процесса:

```text
нельзя начать реализацию без approved plan
```

`InvariantChecker` отвечает за содержание действия:

```text
нельзя записать за пределами workspace
нельзя прочитать .env
нельзя изменить системную схему
нельзя удалить файл
```

Пример:

```text
state guard:
    current stage == IMPLEMENTATION

invariant:
    proposed path belongs to workspace

tool policy:
    write_project_file requires confirmation

approval:
    hash matches current diff
```

Все четыре проверки должны пройти до записи:

```text
state transition allowed
+ tool policy allowed
+ invariants passed
+ approval valid
```

Не объединяй их в одну функцию. Это разные уровни контроля.

# 13. Пауза, ошибка и повтор

## Пауза

Разрешить:

```text
INTERVIEW → PAUSED
PLANNING → PAUSED
IMPLEMENTATION → PAUSED
VALIDATION → PAUSED
REVIEW → PAUSED
APPROVAL → PAUSED
```

При паузе сохранять:

```json
{
  "previous_stage": "implementation",
  "current_step_id": "step-003",
  "workspace_id": "ws-001",
  "pending_approval": null
}
```

Возобновление:

```text
PAUSED → previous_stage
```

Текущая архитектура AI_9 уже предусматривает отдельное состояние паузы и сохранение предыдущей стадии [6].

## Ошибка

При ошибке:

```text
любая рабочая стадия → FAILED
```

Сохранять:

```json
{
  "error_code": "TESTS_FAILED",
  "error_message": "...",
  "failed_step": "step-003",
  "attempt": 2
}
```

## Повтор

Разрешить только осмысленные переходы:

```text
FAILED → PLANNING
FAILED → IMPLEMENTATION
FAILED → REVIEW
```

Не разрешать:

```text
FAILED → COMPLETED
FAILED → DELIVERY
```

# 14. Вложенное состояние шага реализации

Внутри `IMPLEMENTATION` нужен второй уровень:

```python
class ImplementationStepState(str, Enum):
    PENDING = "pending"
    CONTEXT_LOADING = "context_loading"
    PROPOSING = "proposing"
    PREVIEW = "preview"
    WAITING_APPROVAL = "waiting_approval"
    APPLYING = "applying"
    CHECKING = "checking"
    PASSED = "passed"
    FAILED = "failed"
```

Поток одного шага:

```text
PENDING
→ CONTEXT_LOADING
→ PROPOSING
→ PREVIEW
→ WAITING_APPROVAL
→ APPLYING
→ CHECKING
→ PASSED
```

Если проверка не прошла:

```text
CHECKING → FAILED
FAILED → PROPOSING
```

Это позволяет не смешивать:

```text
DevelopmentStage.IMPLEMENTATION
```

с конкретной операцией над одним файлом.

# 15. Вложенное состояние approval

Для опасных операций:

```python
class ApprovalState(str, Enum):
    NOT_REQUIRED = "not_required"
    REQUIRED = "required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONSUMED = "consumed"
```

Пример:

```text
IMPLEMENTATION
→ WAITING_APPROVAL
→ APPROVED
→ APPLYING
```

Если пользователь отказал:

```text
WAITING_APPROVAL → PROPOSING
```

Если approval просрочен:

```text
WAITING_APPROVAL → WAITING_APPROVAL
```

с созданием нового approval-запроса.

# 16. Персистентность

Для каждого workflow храни:

```text
users/<user_id>/projects/<project_id>/
├── project.json
├── development_state.json
├── transition_log.jsonl
├── approvals.jsonl
├── requirements.json
├── architecture.json
├── plan.json
├── validation_report.json
├── review_report.json
└── audit.jsonl
```

`development_state.json`:

```json
{
  "schema_version": 1,
  "workflow_id": "wf-001",
  "project_id": "calculator",
  "stage": "validation",
  "current_step_id": "step-004",
  "previous_stage": "implementation",
  "attempts": 1,
  "failure_reason": null
}
```

`transition_log.jsonl` должен быть append-only:

```json
{
  "transition_id": "tr-001",
  "from": "planning",
  "to": "implementation",
  "event": "plan_approved",
  "allowed": true,
  "actor": "user:alice",
  "metadata": {
    "plan_hash": "..."
  },
  "created_at": "..."
}
```

Записывай как успешные, так и отклонённые попытки. Это уже соответствует текущей идее `transition_log` в AI_9 [6].

# 17. Обновить PromptBuilder

В каждый промпт добавь блок состояния:

```text
[development_workflow]
project_id: calculator
stage: implementation
current_step: step-003
allowed_events:
- step_completed
- pause
- fail

[stage_rules]
- Работай только над текущим шагом.
- Не изменяй файлы вне workspace.
- Не создавай commit на этой стадии.
- После изменения подготовь diff.
- Перед записью проверь approval.
```

Но не полагайся только на prompt. Prompt сообщает модели правила, а код физически проверяет их через state machine и policy. Это соответствует принципу AI_9: «код запрещает, промпт рекомендует» [6].

# 18. Обновить `ToolPolicy`

Добавь в policy контекст:

```python
@dataclass
class ToolContext:
    task_stage: TaskStage
    development_stage: DevelopmentStage | None
    project_id: str | None
    workspace_id: str | None
    actor_id: str
    approval_id: str | None
```

Проверка:

```python
decision = policy.check(
    request=request,
    descriptor=descriptor,
    context=tool_context,
)
```

Проверять:

```text
tool.enabled
tool.allowed_stages
workspace scope
project scope
invariants
confirmation
approval hash
```

# 19. Обновить `/state`

Команда `/state` должна показывать оба уровня:

```text
TaskStage:
  validation

DevelopmentStage:
  review

Project:
  calculator

Current step:
  step-004

Allowed events:
  review_passed
  implementation_requested
  pause
  fail

Pending approval:
  none

Last transition:
  validation → review

Failed transitions:
  1
```

Отдельно:

```text
/transitions
```

должна показывать:

- карту допустимых переходов;
- журнал;
- причины отказов;
- actor;
- время;
- metadata.

# 20. Что считать переходом, а что нет

## Является переходом

```text
интервью подтверждено
требования приняты
архитектура утверждена
план утверждён
реализация завершена
тесты прошли
ревью пройдено
изменения подтверждены
доставка завершена
```

## Не является переходом

```text
LLM сгенерировал текст
RAG нашёл документ
MCP вернул branch
MCP вернул diff
создан промежуточный prompt
инструмент выполнил read-only вызов
```

Это принципиально: внешний инструмент может быть успешно вызван, но задача при этом не обязана перейти на следующий этап.

# 21. Обновлённый `run`

Текущий `/run` должен работать только по разрешённым переходам:

```python
while True:
    state = load_development_state()

    if state.stage in TERMINAL_STAGES:
        break

    event = coordinator.next_event(state)

    if event is None:
        break

    coordinator.apply_event(event)

    if requires_human_approval(state, event):
        break
```

`/run` не должен автоматически проходить:

```text
PLAN → IMPLEMENTATION
```

если нужен пользовательский approval.

Также `/run` не должен автоматически выполнять high-risk запись, даже если модель предложила её.

# 22. Основной сценарий с машиной состояний

Полный процесс:

```text
INTAKE
  event PROJECT_CREATED
  guard goal != empty
  ↓
INTERVIEW
  event INTERVIEW_COMPLETED
  guard required fields known
  ↓
SPECIFICATION
  event REQUIREMENTS_APPROVED
  guard requirements valid + user approval
  ↓
ARCHITECTURE
  event ARCHITECTURE_APPROVED
  guard ADR exists + architecture valid
  ↓
PLANNING
  event PLAN_APPROVED
  guard plan valid + approval
  ↓
IMPLEMENTATION
  event IMPLEMENTATION_STARTED
  guard workspace exists
  ↓
VALIDATION
  event VALIDATION_PASSED
  guard tests pass + diff valid
  ↓
REVIEW
  event REVIEW_PASSED
  guard no blocking findings
  ↓
APPROVAL
  event CHANGES_APPROVED
  guard exact diff approval
  ↓
DELIVERY
  event DELIVERY_COMPLETED
  guard artifact saved
  ↓
COMPLETED
```

# 23. Тесты машины состояний

Добавь тесты именно на граф переходов.

## Положительные

```python
test_intake_to_interview()
test_interview_to_specification()
test_specification_to_architecture()
test_architecture_to_planning()
test_planning_to_implementation_after_approval()
test_implementation_to_validation()
test_validation_to_review()
test_review_to_approval()
test_approval_to_delivery()
test_delivery_to_completed()
```

## Отрицательные

```python
test_cannot_implement_before_plan()
test_cannot_deliver_before_review()
test_cannot_complete_before_delivery()
test_cannot_approve_without_current_diff()
test_cannot_write_without_workspace()
test_cannot_resume_from_terminal_state()
test_failed_cannot_jump_to_delivery()
```

## Интеграционные

```python
test_mcp_diff_does_not_change_development_stage()
test_rag_search_does_not_change_development_stage()
test_file_write_requires_implementation_stage()
test_review_requires_current_validation_report()
test_delivery_requires_exact_approval_hash()
```

# 24. Порядок внедрения

Не переделывай сразу всю машину состояний. Делай по шагам.

## Шаг 1

Создать:

```text
core/development_models.py
core/development_state_machine.py
```

Только модели, стадии и карту переходов.

## Шаг 2

Добавить unit-тесты графа:

```bash
pytest tests/test_development_state_machine.py -q
```

## Шаг 3

Добавить `DevelopmentWorkflowCoordinator`.

## Шаг 4

Подключить хранение:

```text
development_state.json
transition_log.jsonl
```

## Шаг 5

Подключить текущий `TaskStage` через адаптер.

## Шаг 6

Подключить CLI-команды:

```text
/create-app
/project status
/project plan
/project implement
/project validate
/project review
/project deliver
```

## Шаг 7

Подключить guards для требований, плана, тестов и review.

## Шаг 8

Подключить approval.

## Шаг 9

Подключить file tools.

## Шаг 10

Подключить RAG и MCP как исполнителей внутри состояний.

## Шаг 11

Добавить pause/resume/retry.

## Шаг 12

Провести end-to-end тест полного цикла.

# 25. Итоговое правило архитектуры

Зафиксируй в Wiki такую формулу:

```text
StateMachine отвечает за порядок процесса.
Guard отвечает за готовность перейти.
InvariantChecker отвечает за запрет опасного действия.
ToolPolicy отвечает за разрешённость инструмента.
ToolExecutor отвечает за выполнение и аудит.
RAG отвечает за контекст и знания.
MCP отвечает за внешний доступ.
LLM отвечает за предложения и генерацию.
Human approval отвечает за принятие рискованных решений.
```

Итоговая схема:

```text
LLM предложил действие
        ↓
RAG дал контекст
        ↓
MCP подготовил данные
        ↓
StateMachine проверила текущий этап
        ↓
Guard проверил готовность
        ↓
ToolPolicy проверила инструмент
        ↓
InvariantChecker проверил запреты
        ↓
Approval проверил подтверждение
        ↓
ToolExecutor выполнил действие
        ↓
Audit записал результат
        ↓
StateMachine зафиксировала следующий этап
```

Таким образом, машина состояний AI_9 становится **скелетом всей фабрики разработки**: она не занимается генерацией кода и не заменяет RAG или MCP, но гарантирует, что агент не сможет перепрыгнуть от идеи к изменению файлов, от кода к delivery или от собственного review к merge без необходимых проверок и человеческого approval.
