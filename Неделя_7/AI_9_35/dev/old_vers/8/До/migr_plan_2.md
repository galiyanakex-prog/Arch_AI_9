# migr_plan_2.md — Этап 2. `ModelRegistry` + локальные клиенты (L1)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (**Ревизия 8, v1.1**, §4 «Этап 2»).
> Контур: **L (локальные LLM)**. Метка цели: **L1**. Зависимости: **этап 1** (LM Studio поднят).
> Порядок: **пошагово с оператором**. **Коммиты — только за оператором** (ШАГ 2.6).

## Цель этапа

Создать `core/model_registry.py` (`ModelRegistry`, `ModelSpec`) и два локальных клиента —
`OpenAICompatClient` (**основной**, LM Studio) и `OllamaClient` (**альтернативный**) —
реализации существующего `LLMClient`. Реестр строит клиент по `ModelSpec`; `Agent`
по-прежнему **не знает** конкретных провайдеров.

## Предусловия (после этапа 1)

- LM Studio `127.0.0.1:1234` отвечает; боевая модель в `/v1/models`.
- `core/llm_client.py`: `LLMClient` (ABC, `complete`), `RouterAIClient`, `MockClient`.
- `Kod.py::build_agent` создаёт клиент в одном месте (строки ~244/248).
- `Agent.__init__(llm, …)`; `self.llm`; `self.executor = LLMExecutor(llm, …)`.

## Границы этапа

- **Не** меняем контракт `LLMClient.complete(messages) -> str`.
- **Не** добавляем `if provider == …` в `core/agent.py`.
- **Не** трогаем `rag/` (это этап 5).
- **Не** добавляем pip-зависимостей (только stdlib + `requests`).
- Локальные клиенты — **только loopback**; не-loopback → `ValueError`.

---

## Шаги

### ШАГ 2.1 — `core/model_registry.py` (агент)

- **`ModelSpec`** (dataclass): `id`, `service` (`lmstudio|ollama|cloud|mock`), `model`,
  `base_url`, `context_window`, `quant`, `params` (`temperature`, `max_tokens`, `top_p`,
  `num_ctx`, `keep_alive`), `profile` (`default|rag-strict|fast`), `local: bool`,
  `timeout`, `label`, `role` (`chat|embedding`).
- **`ModelRegistry`**: `load(path)` (+ env `AI9_MODEL`/`LMSTUDIO_URL`/`OLLAMA_CHAT_URL`),
  `list()`, `get(id)` (KeyError со списком), `current()`, `use(id)` (валидация + запись
  выбора в `users/<user>/model_state.json`), `build(spec) -> LLMClient`, `probe(id)`
  (живой health-check), `describe(id)`.
- **`build`**: `lmstudio` → `OpenAICompatClient`; `ollama` → `OllamaClient`;
  `cloud` → `RouterAIClient`; `mock` → `MockClient`.

### ШАГ 2.2 — `OpenAICompatClient` (основной локальный клиент, решение №21)

- `POST {base}/v1/chat/completions` (`model`, `messages`, `temperature`, `max_tokens`,
  `top_p`, опц. `tools`).
- Повторяет retry-логику `RouterAIClient`, но **без** внешнего хоста и **без** `Authorization`.
- Поле `model` — полный id LM Studio (`mradermacher/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-GGUF:…`).
- **Только loopback**; не-loopback → `ValueError`.

### ШАГ 2.3 — `OllamaClient` (альтернативный локальный клиент)

- `POST {base}/api/chat` телом `{"model","messages","stream":false,"options":{temperature,
  num_ctx,num_predict,top_p},"keep_alive"}`; `requests`, таймаут, повтор ×2; **только loopback**.
- `complete_with_tools` — базовый fallback-протокол (`parse_fallback_tool_call`).

### ШАГ 2.4 — `Agent.set_model` / `Agent.model_label` (агент)

- `Agent.set_model(client, label)` — замена `self.llm` **и** `self.executor.llm` в одном месте.
- `Agent.model_label()` — единый источник подписи для CLI/лога/HTTP.
- `Kod.py::build_agent` — строит клиент через `ModelRegistry` (по `--model` / `model_state.json` / cloud).

### ШАГ 2.5 — `models.json` + тесты

- `models.json` (секретов нет) — по §6.2 мастер-плана: `current` = облако; боевой id
  `lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K`; `ollama:bge-m3` с `role: "embedding"`;
  профили `default`/`rag-strict`/`fast`; секция `subagents`.
- `dev/tests_debug/unit/test_llm_local.py`: запрос собран с правильным путём/полем `model`/
  `options`; не-loopback URL → `ValueError`; таймаут → `None`, не исключение;
  `complete_with_tools` fallback разбирает `{"tool":…}`; `ModelRegistry.use(неизвестный)` →
  понятная ошибка со списком. **Плюс живой прогон на реальной локальной модели** (не mock).

### ШАГ 2.6 — Запись в журнал + перечитывание плана

Внести запись «Этап 2» в `dev/migr_log.md` по шаблону §7.3.

**Предлагаемый текст коммита** (выполняет **только** оператор):

```
feat(llm): ModelRegistry + OpenAICompatClient (LM Studio) + OllamaClient (этап 2, Ревизия 8)

Причина: часть 2 Задание.txt требует выбора/переключения облачных и локальных моделей.
Реестр строит клиент по ModelSpec; Agent не знает провайдеров. Локальные клиенты —
только loopback; контракт LLMClient.complete неизменяем.
```

---

## Выход этапа

- `core/model_registry.py` — создан; `core/llm_client.py` — расширен двумя клиентами;
- `core/agent.py` — `set_model`/`model_label`; `Kod.py::build_agent` — через реестр;
- `models.json` — создан (секретов нет);
- `dev/tests_debug/unit/test_llm_local.py` — создан;
- запись «Этап 2» в `dev/migr_log.md`.

## Гейт 2→3 (живой, все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `unit_runner.py` | зелёный (290 OK + новые) |
| 2 | `ModelRegistry.build()` для каждого спека | объект `LLMClient` |
| 3 | **живой ответ от локальной модели** | получен (не mock) |
| 4 | не-loopback URL в локальном клиенте | `ValueError` |
| 5 | `Agent` не знает провайдеров | грепом импортов: нет `RouterAIClient`/`OpenAICompatClient` в `core/agent.py` |
| 6 | `models.json` валиден, секретов нет | ✅ |
| 7 | прежний контур (L3/L4/гейт) | без регрессии |
| 8 | `git diff --stat requirements.txt` | пусто |
| 9 | запись «Этап 2» + перечитывание `migr_plan.md` | ✅ |

## Откат

`git checkout -- core/llm_client.py core/agent.py Kod.py`; удалить `core/model_registry.py`,
`models.json`, `test_llm_local.py`. Запись помечается ❌.

## Что передаём дальше

- **Этапу 3 (L2):** `ModelRegistry` + `Agent.set_model`/`model_label` — основа `/model` и подписи.
- **Этапу 5 (G1):** `build(spec)` — источник клиента для `--local-gen`.
- **Этапу 9 (S1):** `GET /models` фасада отдаёт список из реестра.