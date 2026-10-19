# migr_review_1.md — Этап 1. Обновление «Дерева модулей» (R1)

> Рабочий план **одного этапа** на основе `dev/migr_review.md` (**редакция v1.2**, §4 «Этап 1»).
> Контур: **R1 (деревья)**. Метка цели: **R1**. Зависит: **0**.
> Порядок выполнения: **пошагово с оператором** — агент даёт правку, оператор подтверждает.
> **Коммиты — только за оператором**.

## Цель этапа

Привести раздел «Дерево модулей» (стр. 405) в соответствие с фактической структурой
`core/`, `integrations/`, `gateway/`, `serve.py`, `models.json`.

## Расхождения (из этапа 0)

| Файл/каталог | Статус | Действие |
|---|---|---|
| `serve.py` | ❌ нет в дереве | добавить в корень |
| `gateway/` (+ `templates/`, `questions.py`, `sync_questions.py`) | ❌ нет в дереве | добавить в корень |
| `models.json` | ❌ нет в дереве | добавить в корень |
| `core/model_registry.py` | ❌ нет в дереве | добавить в core/ |
| `core/subagents.py` | ❌ нет в дереве | добавить в core/ |
| `core/resources.py` | ❌ нет в дереве | добавить в core/ |
| `integrations/mcp/time_server.py` | ❌ нет в дереве | добавить в mcp/ |
| `integrations/mcp/auth.py` | ❌ нет в дереве | добавить в mcp/ |
| `core/` — 14 файлов в README, 16 на диске | расхождение | обновить |
| `integrations/mcp/` — 9 файлов в README, 11 на диске | расхождение | обновить |

## Фактические данные (из этапа 0)

```
core/ (16 файлов):
  __init__.py, agent.py, invariants.py, llm_client.py, model_registry.py,
  profile_router.py, prompt_builder.py, resources.py, state_machine.py,
  subagents.py, tool_executor.py, tool_pipeline.py, tool_policy.py,
  tool_registry.py, tool_routing.py, tools.py

integrations/mcp/ (11 файлов):
  __init__.py, auth.py, client.py, config.py, demo_server.py,
  gateway.py, pipeline_server.py, provider.py, scheduler_server.py,
  time_server.py, transport.py

gateway/ (6 py + templates):
  __init__.py, app.py, config.py, gateway.json, questions.json,
  questions.py, sync_questions.py, users.py
  templates/chat.html, templates/interview.html, templates/login.html, templates/register.html
```

---

## Шаги

### ШАГ 1.1 — Обновить `core/` в дереве модулей

**Текущий блок (стр. 405–476):**

```
├── core/                        # ядро агентности
│   ├── agent.py                 # оркестратор: + mcp_gateway/tool_registry/tool_executor/tool_policy
│   │                            #   (None при MCP off) + агентный tool-use цикл (_respond_with_tools)
│   │                            #   + ленивый RAG-слой (check_grounding, _grounding_guard)
│   ├── llm_client.py            # LLMClient (ABC) + RouterAIClient + MockClient +
│   │                            #   complete_with_tools (нативный tool-use + fallback-протокол)
│   ├── profile_router.py        # ProfileRouter — детерминированный выбор профиля
│   ├── prompt_builder.py        # BLOCK_ORDER + DELIVERABLE + budget + блоки [tools], [rag]
│   ├── state_machine.py         # строгая машина состояний (MCP/RAG её не трогают)
│   ├── invariants.py            # Invariant + ConstraintSet + InvariantChecker + ProposedAction
│   │                            #   (MCP-поля action_type/tool_name/arguments; правило tool.deny.*)
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
```

**Правка:** добавить 3 новых модуля в алфавитном порядке:

```
│   ├── model_registry.py        # ModelRegistry + ModelSpec: реестр моделей (Ревизия 8)
│   ├── resources.py             # замеры ресурсов (Ревизия 8)
│   ├── subagents.py             # SubagentRunner: запуск дочерних CLI-сессий (Ревизия 8)
```

(Вставить после `state_machine.py` и перед `tools.py`.)

### ШАГ 1.2 — Добавить `serve.py` в корень дерева

**Текущий блок (стр. 403–404):**

```
AI_9/
├── Kod.py                       # точка входа: DI-композиция (+ mcp_enabled, RagService) + REPL
```

**Правка:** добавить после `Kod.py`:

```
├── serve.py                     # фасад: HTTP-вход агента на хосте (Flask, 127.0.0.1:8090)
```

### ШАГ 1.3 — Добавить `models.json` в корень дерева

**Правка:** добавить после `serve.py`:

```
├── models.json                  # реестр моделей и профилей (Ревизия 8)
```

### ШАГ 1.4 — Добавить `gateway/` в корень дерева

**Правка:** добавить после `gateway/` (или после `core/`):

```
├── gateway/                     # веб-шлюз на VPS (Flask)
│   ├── app.py                   # маршруты: чат, прокси, сессии, лимиты
│   ├── config.py                # настройки шлюза
│   ├── gateway.json             # конфиг: лимиты, адрес фасада, таймауты
│   ├── questions.json           # снапшот вопросов интервью
│   ├── questions.py             # чтение/сверка отпечатка вопросов
│   ├── sync_questions.py        # обновление questions.json из канона
│   ├── users.py                 # регистрация, хэш пароля, вход
│   └── templates/               # login.html, register.html, interview.html, chat.html
```

### ШАГ 1.5 — Обновить `integrations/mcp/` в дереве

**Текущий блок (стр. 424–444):**

```
│   ├── mcp/
│   │   ├── config.py            # MCPServerConfig (server_id, transport, command/endpoint, enabled,
│   │   │                        #   trust_level, allowed/denied_tools, timeout, max_result_bytes)
│   │   │                        #   + load_servers_config (дефолты: time + weather + scheduler +
│   │   │                        #   pipeline + demo; битый файл не роняет)
│   │   ├── transport.py         # MCPTransport (ABC) + StdioMCPTransport + HttpMCPTransport
│   │   │                        #   (Streamable HTTP, mcp SDK) + FakeMCPTransport; make_transport
│   │   ├── client.py            # MCPClient: initialize / list_tools / call_tool
│   │   ├── gateway.py           # MCPGateway: start/stop/connection_state, discover(), call_tool();
│   │   │                        #   MCPGatewaySync — синхронный фасад (постоянная фоновая задача)
│   │   ├── provider.py          # MCPToolProvider: discover() + нормализация → ToolDescriptor
│   │   ├── demo_server.py       # локальный stdio MCP-сервер (get_time, echo, weather_stub)
│   │   ├── scheduler_server.py  # MCP-сервер планировщика (HTTP :8010)
│   │   └── pipeline_server.py   # MCP-сервер пайплайна (search/summarize/saveToFile, HTTP :8020)
```

**Правка:** добавить 2 новых модуля:

```
│   │   ├── auth.py              # аутентификация MCP-серверов (Ревизия 8)
│   │   ├── time_server.py       # MCP-сервер времени (HTTP :8000)
```

(Вставить после `config.py` и перед `transport.py`.)

### ШАГ 1.6 — Проверка правок

```bash
# Проверить, что все файлы из нового дерева существуют
for f in core/model_registry.py core/resources.py core/subagents.py \
         serve.py models.json \
         gateway/app.py gateway/config.py gateway/questions.py \
         gateway/sync_questions.py gateway/users.py \
         gateway/templates/chat.html gateway/templates/interview.html \
         gateway/templates/login.html gateway/templates/register.html \
         integrations/mcp/auth.py integrations/mcp/time_server.py; do
  if [ -f "$f" ]; then echo "OK: $f"; else echo "MISSING: $f"; fi
done
```

**Записать в `migr_log.md`:** результат проверки.

### ШАГ 1.7 — Перечитывание `migr_review.md`

Перечитать `dev/review/migr_review.md` целиком.

**Предлагаемый текст коммита** (выполняет **только** оператор):

```
docs(readme): обновить «Дерево модулей» — добавить serve.py, gateway/, models.json,
core/model_registry.py, core/subagents.py, core/resources.py, mcp/auth.py, mcp/time_server.py
```

---

## Выход этапа

- `README.md` — раздел «Дерево модулей» обновлён;
- `dev/migr_log.md` — запись этапа 1;
- `dev/review/migr_review.md` — перечитан.

## Гейт 1→2 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `core/` — 16 файлов в дереве | ✅ |
| 2 | `serve.py` в дереве | ✅ |
| 3 | `models.json` в дереве | ✅ |
| 4 | `gateway/` в дереве | ✅ |
| 5 | `integrations/mcp/` — 11 файлов в дереве | ✅ |
| 6 | Все файлы из нового дерева существуют | ✅ |
| 7 | Запись в migr_log.md | ✅ |
| 8 | Перечитывание migr_review.md | ✅ |

## Откат

`git checkout HEAD -- README.md` — выполняет оператор.

## Что передаём дальше

- **Этапу 2 (R2):** обновлённое дерево модулей — контекст для обновления «Дерева `dev/`».
