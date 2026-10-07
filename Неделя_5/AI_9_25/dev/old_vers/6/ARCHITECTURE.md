# AI_9 — Архитектура проекта

> **AI-агент с многоуровневой памятью, MCP-инструментами и RAG-поиском.**
> Python 3.12, stdlib + `requests` + `python-dotenv` + `mcp` SDK.
> Без внешних БД (SQLite встроен), без внешних сервисов (Ollama — опционально, локально).

---

## 1. Общая схема

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Kod.py — точка входа: DI-сборка, CLI-флаги, REPL                       │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ build_agent()
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌───────────────┐    ┌─────────────────┐    ┌──────────────────┐
│   core/       │    │ integrations/   │    │     rag/         │
│   ядро        │    │ mcp/ scheduler/ │    │  поиск по док.   │
│   агентности  │    │ pipeline/       │    │  (опционально)   │
└───────┬───────┘    └────────┬────────┘    └────────┬─────────┘
        │                     │                      │
        ▼                     ▼                      ▼
┌───────────────────────────────────────────────────────────────┐
│                      storage/  (Store, db.py)                 │
│         файловое дерево users/ + SQLite profiles.db           │
└───────────────────────────────────────────────────────────────┘
```

**Направление зависимостей строго однонаправленное:**
`Kod.py` → `core/` → `memory/` → `storage/`;
`integrations/` и `rag/` подключаются только DI-композицией в `Kod.py`.

---

## 2. Слой `core/` — ядро агентности

| Модуль | Ответственность |
|---|---|
| `agent.py` | Stateful-оркестратор: память, профили, инварианты, машина состояний, tool-use цикл |
| `llm_client.py` | `LLMClient` (ABC) → `RouterAIClient` (HTTP) / `MockClient` (заглушка) |
| `prompt_builder.py` | Сборка промта блоками: `BLOCK_ORDER`, `DELIVERABLE`, бюджет |
| `state_machine.py` | `TaskStage` (8 стадий), `ALLOWED_TRANSITIONS`, `try_transition` |
| `invariants.py` | `Invariant`, `ConstraintSet`, `InvariantChecker`, `RuleBasedChecker` |
| `profile_router.py` | Детерминированный выбор профиля по триггерам (без LLM) |
| `tools.py` | `ToolDescriptor`, `ToolCallRequest`, `ToolExecutionResult`, `ToolProvider` (ABC) |
| `tool_registry.py` | Каталог инструментов: `refresh()` → атомарный `ToolCatalogSnapshot` |
| `tool_policy.py` | Цепочка проверок перед вызовом: enabled → схема → стадия → инварианты → подтверждение |
| `tool_executor.py` | Единственная точка исполнения: policy → gateway → результат → аудит |
| `tool_pipeline.py` | `PipelineStep` / `Pipeline` / `run_pipeline` — цепочка инструментов |
| `tool_routing.py` | `rank_tools` — ранжирование инструментов по запросу (без LLM) |

**Инварианты слоя:**
- `core/` никогда не импортирует `mcp` SDK, `rag/`, `integrations/`.
- `StateMachine` не вызывается из `ToolExecutor` / `MCPGateway` (инструмент ≠ переход).
- `ToolRegistry` не проверяет бизнес-правила.

---

## 3. Слой `memory/` — модель памяти

```
MemoryManager
├── ShortTermMemory    — сессия, окно 10 сообщений, parent_id (задел ветвления)
├── WorkingMemory      — пересчитываемое состояние задачи
├── LongTermMemory     — профиль + задачи + решения + знания
└── SessionResume      — резюме сессий (sessions_resume.md)
```

Каждый слой — отдельный файл в `users/<id>/tasks/<task>/`.
Очистка истории диалога не сбрасывает состояние, не удаляет инварианты.

---

## 4. Слой `integrations/` — внешние интеграции

### 4.1 `integrations/mcp/` — MCP-подсистема

```
config.py        MCPServerConfig + load_servers_config (servers.json)
transport.py     MCPTransport (ABC) + StdioMCPTransport + HttpMCPTransport + FakeMCPTransport
client.py        MCPClient: initialize / list_tools / call_tool
gateway.py       MCPGateway (async) + MCPGatewaySync (синхронный фасад)
provider.py      MCPToolProvider → ToolDescriptor (source="mcp", name="mcp.<server>.<tool>")
demo_server.py   локальный stdio MCP-сервер (get_time, echo, weather_stub)
scheduler_server.py  MCP-сервер планировщика (HTTP :8010)
pipeline_server.py   MCP-сервер пайплайна (HTTP :8020)
```

**MCP-серверы по умолчанию:**

| ID | Endpoint | Инструменты |
|---|---|---|
| `time` | `http://91.188.212.77:8000/mcp` | `get_time(timezone_name)` |
| `weather` | `https://weatherapi.projecteol.ru/mcp/` | `search_locations`, `get_forecast_metadata`, `get_weather_forecast` |
| `scheduler` | `http://127.0.0.1:8010/mcp` | `schedule_reminder`, `schedule_collection`, `record_observation`, `run_due`, `get_summary`, `latest_summary`, `list_jobs` |
| `pipeline` | `http://127.0.0.1:8020/mcp` | `search`, `summarize`, `saveToFile` |
| `demo` | stdio (локально) | `get_time`, `echo`, `weather_stub` |

### 4.2 `integrations/scheduler/` — фоновый планировщик

```
models.py    Job / Observation / Summary / JobState
store.py     SchedulerStore (через фасад Store)
runner.py    Scheduler: add_job / due_jobs / run_once / start / stop
aggregator.py  aggregate → count/min/max/avg/last
```

Фоновое выполнение — поток `threading`, **не LLM**. LLM участвует только в тексте сводки.

### 4.3 `integrations/pipeline/` — пайплайн инструментов

Цепочка `search → summarize → saveToFile`. Результат шага N → аргумент N+1 через `input_key`.

---

## 5. Слой `rag/` — поиск по документам

```
config.py      RagConfig (валидация: эмбеддинги только localhost)
corpus.py      discover / delta — сбор корпуса, deny-список
chunking.py    fixed (окно токенов) | structural (по заголовкам)
embedding.py   OllamaEmbedder (bge-m3, dim 1024) + HashingEmbedder (офлайн-фолбэк)
index.py       плоский индекс: BM25-постинги + векторы, save/load
retrieval.py   bm25 | dense | hybrid (RRF + MMR)
rerank.py      LexicalReranker (интерфейс под cross-encoder)
cache.py       LRU+TTL кэш поиска (инвалидация по mtime)
grounding.py   проверка опоры ответа на источники (off | warn | strict)
eval.py        метрики: recall / hit-rate / mrr / ndcg
compare.py     сравнение стратегий × режимов + вердикт
service.py     RagService — фасад для Kod.py / Agent
```

**Конвейер:**
```
corpus → chunking → embedding (Ollama bge-m3) → index (BM25 + dense)
  → retrieval (BM25 ⊕ dense → RRF → реранк → MMR) → блок [rag] в промпте
  → grounding (ответ обязан опираться на найденное)
```

**Инварианты слоя:**
- `rag/` не импортирует `core/`, `core/` не импортирует `rag/` — связь через DI-фасад.
- Без `--rag` промпт байт-в-байт прежний, `rag` не импортируется.
- Эмбеддинги строго локально (`127.0.0.1:11434`).

---

## 6. Слой `storage/` — хранилище

### 6.1 `store.py` — файловый фасад

Все пути знает только `Store`. Слои памяти и ядро ФС напрямую не трогают.

```
users/
├── profiles.db                  # SQLite: профили (общая база)
└── <user_id>/
    ├── profile.json             # зеркало default-профиля
    ├── profiles/<pid>.json      # зеркала профилей
    ├── long_term_memory.json
    ├── integrations/mcp/
    │   ├── servers.json         # конфиг MCP-серверов (user-scope)
    │   ├── catalog.json         # снимок ToolCatalogSnapshot
    │   └── scheduler/           # jobs / observations / summaries
    └── tasks/<task_name>/
        ├── invariants.json      # ConstraintSet
        ├── task_state.json      # TaskState + transition_log
        ├── working_memory.json
        ├── tool_audit.jsonl     # история вызовов инструментов
        ├── sessions_resume.md
        └── sessions/<session_id>/session.json
```

### 6.2 `db.py` — `ProfileRepository` (SQLite)

Таблица `profiles(user_id, profile_id, …, is_default)`.
БД старой схемы мигрируется автоматически при открытии.

---

## 7. Сборка промта

```
[system: role] → [system: profile] → [system: invariants] → [system: long_term] →
[system: working] → [system: summary, опц.] → [system: tools] → [system: rag] →
[messages: short_term (окно 10)] → [user: текущий запрос] → [резерв под ответ]
```

- `BLOCK_ORDER = ("role", "profile", "invariants", "long_term", "working", "summary", "short_term", "current")`
- `DELIVERABLE = ("profile", "invariants", "long_term", "working", "summary", "short_term")`
- Блоки `[tools]` и `[rag]` добавляются только при активных флагах `--mcp` / `--rag`.
- Бюджет: необязательный блок пропускается, если `used + tokens > budget`.

---

## 8. Машина состояний задачи

```
NEW → PLANNING → PLAN_APPROVED → IMPLEMENTATION → VALIDATION → DONE
 │        │            │               │               │
 └────────┴────────────┴───────────────┴───────────────┴──→ PAUSED
 │        │            │               │               │
 └────────┴────────────┴───────────────┴───────────────┴──→ FAILED → PLANNING
```

- Переходы — только через `try_transition()` (единственная точка смены этапа).
- Недопустимый переход → `InvalidTransitionError`, состояние НЕ меняется, запись в `transition_log`.
- MCP-вызовы и RAG-поиск **не создают** записей в `transition_log`.

---

## 9. Tool-use цикл

```
запрос пользователя
  → PromptBuilder.build(ctx, deliver, budget)  [включая блок [tools]]
  → LLM.complete_with_tools(messages, tools)
  → tool_calls?
      → ToolExecutor.execute(request)
          → ToolPolicy.check(descriptor, arguments, stage, invariants)
          → MCPGateway.call_tool(provider, tool, arguments)
          → ToolExecutionResult → аудит tool_audit.jsonl
      → tool-сообщение → LLM.complete_with_tools(...)  [повтор, лимит итераций]
  → финальный ответ
```

---

## 10. DI-композиция (`build_agent`)

```python
build_agent(user_id, mock, mcp_enabled=False, rag_enabled=False)
# mcp_enabled (--mcp):
#   gateway = MCPGatewaySync(load_servers_config(...))
#   registry = ToolRegistry(); registry.add_provider(MCPToolProvider(gateway))
#   agent.mcp_gateway = gateway; agent.tool_registry = registry
# rag_enabled (--rag):
#   rag_service = RagService(RagConfig(...))
#   agent.rag_service = rag_service
# без флагов: agent.mcp_gateway is None, agent.tool_registry is None, agent.rag_service is None
```

---

## 11. Тестирование

| Уровень | Команда | Результат |
|---|---|---|
| L1 | `python -m py_compile Kod.py core/*.py memory/*.py storage/*.py integrations/mcp/*.py` | exit 0 |
| L2 | `env -u API_KEY python dev/tests_debug/unit_runner.py` | 244 OK, 0 FAIL |
| L3 | `API_KEY=test-key python dev/tests_debug/smoke.py` | SMOKE OK, exit 0 |
| L4 | `API_KEY=test-key python dev/tests_debug/scenario.py` | SCENARIO OK, exit 0 |
| Гейт | `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` | 33/33 ✅, exit 0 |

Все тесты — без живого ключа (`API_KEY=test-key`, `MockClient`, `FakeMCPTransport`).
Тестовые данные пишутся только в `dev/tests_debug/.tmp/` (в `.gitignore`).

---

## 12. Ключевые инварианты архитектуры

1. **`mcp` SDK импортируется только в `integrations/mcp/`** — `core/`, `memory/`, `storage/` его не знают.
2. **Инструмент ≠ переход**: вызов MCP-инструмента не меняет `TaskStage` и не пишет в `transition_log`.
3. **MCP и RAG выключены по умолчанию** — без флагов поведение идентично базовой версии.
4. **`rag/` не импортирует `core/`** — связь только через DI-фасад `RagService`.
5. **Сырые ответы MCP никогда не пишутся в память** — только нормализованные `external_actions`.
6. **Профиль не может менять MCP-конфиг** — задел `tool_policy` в профиле только сужает права.
7. **Атомарность каталога**: один запрос модели никогда не видит «половину старого и половину нового» каталога.
8. **Деградация, не падение**: недоступный сервер → FAILED/DEGRADED, REPL жив.
9. **Инварианты — отдельная сущность**: не память, не профиль, не диалог; хранятся в `invariants.json`.
10. **Переходы и инварианты — разные механизмы**: `StateMachine` проверяет этапы, `InvariantChecker` — действия.
