# AI_9 — День 27. Интеграция локальной LLM в агента

> **Неделя 6, День 27.** Агент научился работать и с облачными, и с локальными моделями:
> переключение одной командой `/model`, субагенты на локальных LLM, а какая модель
> отвечает — видно всегда и везде.

---

## Что изменилось за день

| Было (День 26) | Стало (День 27) |
|---|---|
| Локальная модель отвечала сама по себе, через `curl` | Агент сам отправляет ей запросы и получает ответы |
| Провайдер LLM один — облако (`RouterAIClient`) | Четыре провайдера за одним интерфейсом: облако, LM Studio, Ollama, mock |
| Модель выбиралась один раз при старте и незаметна | Переключение командой `/model use <id>` прямо посреди диалога |
| Непонятно, кто именно ответил | Модель/сервис видны в баннере, в префиксе каждой реплики, в логе и в CSV |
| — | Субагенты: «сделай локально в LM Studio …» → дочерняя CLI-сессия |

Ядро агента (память, профили, инварианты, машина состояний, MCP, RAG) **не тронуто**:
`Agent` по-прежнему знает только абстракцию `LLMClient` и не содержит ни одного
`if provider == ...`.

---

## Как этим пользоваться

### Переключение модели — одна команда

```bash
./run.sh --user alice                                    # старт: облако (по умолчанию)
./run.sh --user alice --model lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K
                                                          # старт сразу на локальной модели
./run.sh --model-list                                     # посмотреть, что вообще есть
```

Внутри сессии:

```
> /model list
  cloud:stepfun/step-3.5-flash                    облако   ctx 262144  профиль default
> lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K
                                                  локально q6_K ctx 8192 профиль rag-strict
  ollama:bge-m3                                   локально embedding (в чате не участвует)
  mock                                            локально тестовая заглушка

> /model use lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K
[Модель] Переключено: lmstudio/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K
         (локально, q6_K, ctx 8192, профиль rag-strict)

> который час в Москве?
[lmstudio/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K]
  Без обращения к инструментам точное время назвать не могу…
```

Выбор переживает перезапуск — он пишется в `users/<user>/model_state.json`.

### Субагент — «сделай локально в …»

```
> сделай локально в lm studio: перечисли модули проекта и назначение каждого
[Субагент] id=sub_a1b2, сервис=lmstudio, модель=Qwen2.5-Coder-3B-Instruct-…-Q6_K, pid=41823
[Субагент] готов (8,4 с) → dev/logs_reports/stages/subagent_a1b2.md

[Субагент] Итог: core/ — ядро агентности; memory/ — четыре слоя памяти; …
```

Можно и явной командой:

```
/subagent run <задача> [--service lmstudio|ollama] [--model <id>] [--wait|--async]
/subagent list
/subagent log <id>
```

### Команды дня

| Команда | Действие | Тратит токены? |
|---|---|---|
| `/model` / `/model current` | текущая модель, сервис, профиль, параметры, квант, окно | нет |
| `/model list` | все модели реестра + отметка текущей + `local/cloud` | нет |
| `/model use <id>` | переключить модель в текущей сессии | нет |
| `/model status` | живой health-check сервиса (латентность, версия, доступность) | нет |
| `/model profile <name>` | применить профиль параметров (`default` / `rag-strict` / `fast`) | нет |
| `/subagent run <задача> …` | поднять вспомогательную CLI-сессию на локальной модели | да (в субагенте) |
| `/subagent list` | активные и завершённые субагенты, пути к логам | нет |
| `/subagent log <id>` | показать лог субагента (с его собственной подписью модели) | нет |

Флаги запуска: `--model <id>`, `--model-list`, `--model-profile <name>`, `--local-only`
(запретить облачные модели в этой сессии и у субагентов).

---

## Какая модель подключена — видно всегда

Это отдельное требование задания, и оно закрыто в пяти местах:

1. **Баннер** при старте и после `/model use`:
   `[Сессия] модель: lmstudio/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K (локально, q6_K, ctx 8192, профиль rag-strict)`
2. **Префикс каждой реплики** ассистента: `[lmstudio/Qwen2.5-Coder-3B-Instruct-…-Q6_K]`
3. **`Den_log.md`** — каждая запись ответа несёт `model=…`
4. **`tokens.csv`** — новая колонка `model` (старые строки не переписываются)
5. **Субагентные сессии** наследуют всё вышеперечисленное автоматически —
   потому что это тот же `Kod.py`, просто дочерний процесс

Подпись — это **вывод CLI**, а не содержимое промпта: в `messages` она не попадает,
поэтому промпт без `--model` остаётся байт-в-байт прежним.

---

## Как устроено

### Одна абстракция, много провайдеров

```
                      LLMClient (ABC)   complete(messages) -> str
                             │
     ┌───────────────┬───────┴────────┬──────────────────┐
RouterAIClient   OpenAICompatClient  OllamaClient     MockClient
  (облако)        LM Studio, любой    /api/chat       (тесты)
                  OpenAI-совместимый
                  локальный сервер
```

Контракт `LLMClient.complete(messages) -> str` **не изменялся** — все новые клиенты
просто реализуют тот же интерфейс. Поэтому прежние тесты, сценарии и `MockClient`
не переписывались.

- **`OpenAICompatClient`** — основной локальный путь. `POST {base}/v1/chat/completions`
  с полями `model`, `messages`, `temperature`, `max_tokens`, `top_p`. Повторяет
  retry-логику облачного клиента, но без внешнего хоста и без `Authorization`.
- **`OllamaClient`** — `POST {base}/api/chat` с `options` (`temperature`, `num_predict`,
  `num_ctx`) и `keep_alive`.
- **Оба локальных клиента ходят только на loopback** (`127.0.0.1`). Любой другой адрес —
  `ValueError` на этапе валидации конфига, ещё до первого запроса. Внешний хост разрешён
  только облачному клиенту.

### Реестр моделей — `core/model_registry.py`

```python
reg = ModelRegistry.load("models.json")     # + переопределения из окружения
reg.list()                                  # все ModelSpec
spec = reg.get("lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K")
client = reg.build(spec)                    # → конкретный LLMClient
reg.use("lmstudio:…")                       # валидация + запись выбора
reg.current()                               # → ModelSpec
reg.probe("lmstudio:…")                     # → {"ok": true, "latency_ms": 41, "version": "…"}
```

`Agent.set_model(client, label)` меняет модель в одном месте (и у агента, и у его
исполнителя); `Agent.model_label()` — единый источник подписи для CLI, лога и HTTP.

### Конфигурация — `models.json` (секретов здесь нет)

```json
{
  "current": "cloud:stepfun/step-3.5-flash",
  "profiles": {
    "default":    {},
    "rag-strict": {"temperature": 0.1, "max_tokens": 700, "context_window": 8192, "top_p": 0.9},
    "fast":       {"temperature": 0.3, "max_tokens": 256, "context_window": 4096, "top_p": 0.9}
  },
  "models": [
    {"id": "cloud:stepfun/step-3.5-flash", "service": "cloud", "local": false,
     "model": "stepfun/step-3.5-flash", "context_window": 262144, "profile": "default"},
    {"id": "lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K",
     "service": "lmstudio", "local": true,
     "model": "mradermacher/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-GGUF:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated.Q6_K.gguf",
     "base_url": "http://127.0.0.1:1234",
     "quant": "Q6_K", "context_window": 8192, "profile": "rag-strict", "timeout_seconds": 180},
    {"id": "ollama:bge-m3", "service": "ollama", "local": true,
     "model": "bge-m3:latest", "base_url": "http://127.0.0.1:11434",
     "role": "embedding", "context_window": 8192, "profile": "default", "keep_alive": "10m"},
    {"id": "mock", "service": "mock", "local": true, "model": "Mock", "profile": "default"}
  ],
  "subagents": {"max_parallel": 2, "timeout_seconds": 180,
                "default_service": "lmstudio", "user_prefix": "sub_"}
}
```

Все числа (`temperature`, `max_tokens`, `context_window`, таймауты) живут **только здесь** —
в коде они не дублируются. Ключ `API_KEY` по-прежнему только в `.env` и нигде не печатается.

Запись `ollama:bge-m3` помечена `role: "embedding"`: она честно описывает загрузку Ollama,
но **не** предлагается как чат-модель и не участвует в генерации.

### Субагент — это дочерний процесс, а не новый цикл

`core/subagents.py` только запускает, ждёт и собирает результат:

```
"сделай локально в lm studio: <задача>"
  → детерминированный анализатор фразы (без LLM) → подтверждение у пользователя
  → SubagentRunner.run(task, service="lmstudio")
  → дочерний процесс: .venv/bin/python Kod.py --user sub_a1b2 \
        --model lmstudio:Qwen2.5-Coder-3B-Instruct-…-Q6_K --oneshot "<задача>" \
        --log dev/logs_reports/stages/subagent_a1b2.md
  → таймаут / статус / итог → сводка в основной сессии
```

Никакого второго агентного цикла нет — переиспользуются тот же REPL, та же память,
те же проверки. Ограничения: жёсткий таймаут (по умолчанию 180 с) с `kill` по истечении,
не более 2 одновременных субагентов, запись только в `users/sub_*/` и `stages/`,
аргументы передаются списком (без `shell=True`), облачный флаг запрещён, если запрошен
локальный сервис.

**Субагент ≠ переход:** его запуск не меняет `TaskStage` основной задачи и не пишет
записей в `transition_log` — по тому же канону, что и вызовы инструментов MCP.

---

## Границы (чего специально нет)

- **Ядро не знает провайдеров** — в `core/agent.py` нет ни одной проверки «это Ollama
  или LM Studio»; выбор делается в DI (`Kod.py`) и в REPL.
- **Локальные клиенты не ходят наружу** — не-loopback адрес отклоняется конфигом.
- **Субагент не имеет своего агентного цикла** — это тот же `Kod.py` дочерним процессом.
- **Реестр не подменяет `/model`** — переключение возможно только через `ModelRegistry`,
  «в обход» реестра моделей не бывает.
- **Новых pip-зависимостей нет** — только stdlib + `requests`, как и раньше.

---

## Проверки

- ✅ **Агент отправляет и получает запросы локальной LLM** — `/model use lmstudio:…` →
  вопрос → ответ с подписью локальной модели (живой прогон, транскрипт
  `dev/logs_reports/stages/local_llm_switch.md`)
- ✅ **Выбор и переключение облако ↔ локальная — одной командой** — в одной сессии
  `cloud → lmstudio → cloud`, в выводе каждого из трёх ответов видна своя модель
- ✅ **Во всех CLI-сессиях видно, какая модель подключена** — баннер, префикс реплики, `Den_log.md`, колонка `model` в `tokens.csv`; у субагента — то же самое в его логе
- ✅ **Субагент по команде «сделай локально в LM Studio …»** отработал на боевой
  локальной модели, в его логе видна `Qwen2.5-Coder-3B-Instruct-…-Q6_K`, в основной
  сессии — итог и путь к логу
- ✅ **Регрессия** — без `--model` поведение и промпт байт-в-байт прежние; `TaskStage`
  от переключения модели и запуска субагента не меняется; прежние тесты зелёные

---

## Артефакты дня

| Файл | Что это |
|---|---|
| `core/model_registry.py` | `ModelRegistry`, `ModelSpec`, профили параметров, состояние выбора |
| `core/llm_client.py` | + `OpenAICompatClient` (LM Studio), + `OllamaClient` |
| `core/subagents.py` | `SubagentRunner` — запуск дочерних CLI-сессий |
| `core/agent.py` | `set_model(...)`, `model_label(...)`, вызов субагента |
| `models.json` | реестр моделей и профилей параметров (без секретов) |
| `Kod.py` | флаги `--model*` / `--local-only`, семейства команд `/model`, `/subagent` |
| `users/<user>/model_state.json` | выбранная модель — переживает перезапуск |
| `dev/tests_debug/unit/test_llm_local.py` | клиенты + реестр |
| `dev/tests_debug/unit/test_model_switch.py` | `/model`, отображение, регрессия |
| `dev/tests_debug/unit/test_subagents.py` | запуск, таймаут, безопасность |
| `dev/tests_debug/scenario/scen_local_llm.md` | сценарий ручной демонстрации |
| `dev/logs_reports/stages/local_llm_switch.md` | живой прогон переключения |
| `dev/logs_reports/stages/local_llm_subagent.md` | живой прогон субагента |

---

## Запуск

```bash
# Облако (по умолчанию — поведение как раньше)
./run.sh --user alice

# Сразу на локальной модели
./run.sh --user alice --model lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K

# Список моделей без входа в сессию
./run.sh --model-list

# Только локальные модели, облако запрещено
./run.sh --user alice --local-only

# Субагент из командной строки
./run.sh --subagent-run "объясни назначение core/tool_policy.py" --subagent-service lmstudio
```

Перед локальными прогонами оператор поднимает LM Studio:

```bash
~/.lmstudio/bin/lms server start
~/.lmstudio/bin/lms load mradermacher/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-GGUF:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated.Q6_K.gguf --gpu 0 --context-length 8192
```

---

## Что дальше

Полный план недели 6 — [`dev/migr_plan.md`](../dev/migr_plan.md).

- **День 26** — локальная LLM запущена и отвечает ([`README_1.md`](README_1.md))
- **День 27** — интеграция в агента: `/model`, субагенты, видимость модели *(этот день)*
- **День 28** — локальная LLM в RAG: retrieval и генерация полностью локально
- **День 29** — оптимизация модели под задачу: параметры, шаблон, квантование
- **День 30** — локальная LLM как сервис с доступом извне через VPS

