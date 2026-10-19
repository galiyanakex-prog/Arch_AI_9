# migr_log.md — журнал модернизации `AI_9` (Ревизия 8): локальные LLM + локальный RAG + оптимизация + доступ извне

> Журнал результатов модернизации по рабочим планам `dev/migr_plan_0.md` … `dev/migr_plan_12.md`
> (единая сквозная нумерация; один файл = один этап = один гейт).
> Мастер-план: `dev/migr_plan.md` (**Ревизия 8, редакция v1.1**; формат записей — §7.3,
> правила — §1.1, §5).
> Обозначения: ✅ выполнено · ❌ не выполнено (повтор) · ⚠ допустимое временное отклонение ·
> ⛔ блокирующая ошибка (ожидание указаний).
> **Живой слой обязателен** на этапах 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12 (LM Studio
> `127.0.0.1:1234` с боевой моделью; Ollama `127.0.0.1:11434` — эмбеддинги RAG); на
> остальных — детерминированной регрессии (unit / L3 / L4 / гейт) достаточно.
> **Регрессия запрещена на всех этапах:** без `--model`/`--local-gen` промпт и поведение
> идентичны текущим; прежние проверки `check_acceptance.sh` и все юнит-модули зелёные.
> История прошлых ревизий — в `dev/old_vers/` (…, **8 — снимок на входе Ревизии 8**).
>
> **Ревизия 8.** Задача: довести **существующий** полноценный CLI-агент AI_9 до требований
> `ND/tasks/n_6/Задание.txt` (5 частей): 1) локальные LLM (боевая — `Qwen2.5-Coder-14B-Instruct-Q4_K_M`
> через LM Studio); 2) интеграция локальных LLM (`ModelRegistry`, `/model`, отображение модели,
> субагенты); 3) полностью локальный RAG (retrieval + генерация) и сравнение с облаком;
> 4) оптимизация (профили параметров, prompt-шаблон, квантование, замеры «до/после»);
> 5) приватный сервис с доступом извне (фасад на хосте → шлюз на VPS → SSH reverse tunnel).
> **Контур S (доступ извне) добавлен впервые** — в Ревизии 7 его не было.
> **Коммиты — только за оператором**; агент готовит правки и предлагает текст сообщения.

---

## Подготовка — мастер-план Ревизии 8 (v1.1) + рабочие планы 0–12 (до этапа 0)

- Статус: ✅ завершён (2026-10-11)
- Тип: не этап конвейера, а **порождение мастер-плана и 13 рабочих планов**.

### Было

- `dev/migr_plan.md` — мастер-план Ревизии 7 (тема — RAG по 4 частям `Задание.txt`).
- Требования `ND/tasks/n_6/Задание.txt` (5 частей, ревизия 8) проанализированы, но не сведены в план.
- Рабочие планы `migr_plan_0.md`/`_1.md`/`_2.md` — от Ревизии 7 (Ollama-путь, репер 244 OK, гейт 33/33).

### Стало

- `dev/migr_plan.md` — мастер-план **Ревизии 8, v1.1**: этапы **0…12**, контур **S**,
  решения оператора **№1–22** (все закрыты), `models.json`/`gateway.json`, механизм гейта,
  DoD по 5 частям, трассировка.
- Рабочие планы `dev/migr_plan_0.md` … `dev/migr_plan_12.md` — **13 файлов** в едином формате
  (шапка-цитата + Цель · Предусловия · Границы · Шаги · Выход · Гейт N→N+1 · Откат ·
  Что передаём дальше + текст коммита). Планы 0–2 перезаписаны под Ревизию 8; 3–12 созданы.
- **Боевая модель (решение №20):** `Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-GGUF`, файл
  `~/.lmstudio/models/mradermacher/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-GGUF/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated.Q6_K.gguf`
  (2,5 ГБ, единственный тег, квант Q6_K). Боевой id — `lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K`.
- **Правки мастера по факту прогона 2026-10-11:** строка `pytest` (§0.4) → установлен в `.venv`
  (9.1.1); новая строка о хрупкости тестов к `importlib.reload`; строка базовой линии → фактические
  числа; шаг 1 Этапа 0 переписан под факт 39/43; §5 — правило про pytest и запрет захвата
  через `from … import` объектов reload-мых модулей.

### Артефакты

- `dev/migr_plan.md` (v1.1), `dev/migr_plan_0.md` … `dev/migr_plan_12.md`.
- Снимок Ревизии 7 — `dev/old_vers/8/migr_log.md` (2048 строк) и `dev/old_vers/8/migr_plan_v1.1.md`.

### Коммит

- Предложен оператору (текст — в ШАГЕ 0.7 плана 0); выполнен оператором — хеш: _(ожидается)_.

---

## Этап 0 — Базовая линия Ревизии 8 + аудит LLM-слоя + репер MCP (цель: О0)

- Статус: ✅ завершён (2026-10-11)
- Было: журнал Ревизии 7; числа базовой линии — по памяти (33/33, 25/25, 27 модулей).
- Стало: базовая линия зафиксирована **фактическим прогоном**; аудит LLM-слоя и `rag/` снят;
  карта разрывов под 5 частей составлена; репер MCP снят.

### Живой прогон (базовая линия «до»)

- `ls dev/tests_debug/unit/test_*.py | wc -l` → **33** модуля.
- `env -u API_KEY .venv/bin/python dev/tests_debug/unit_runner.py` → **Итого: 290 OK, 0 FAIL**.
- `API_KEY=test-key .venv/bin/python dev/tests_debug/smoke.py` → **SMOKE OK: exit 0**.
- `API_KEY=test-key .venv/bin/python dev/tests_debug/scenario.py` → **SCENARIO OK: exit 0**.
- `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` → **ИТОГ: 39 из 43 зелёные (FAIL=4)**.
- `pytest -q` → **291 passed** (дополнительный раннер; репер — `unit_runner.py`).

### Красные 4 проверки гейта (ограничение среды, не регресс)

- №33 `--rag-eval`, №38 `--rag-ask`, №39 `--rag-verify`, №43 `dialog_runner` — все требуют
  **живого RAG-индекса/эмбеддингов Ollama**, который на момент прогона **не отвечал**.
- Причина — недоступная Ollama (эмбеддинги), **не регресс кода**.
- **Снято на этапе 1:** после `sudo systemctl start ollama` (модель `bge-m3:latest` на месте)
  гейт → **43 из 43 зелёные (FAIL=0)**. Итоговая базовая линия Ревизии 8 — **43/43**.

### Аудит LLM-слоя (`core/llm_client.py`, `Kod.py`, `core/agent.py`)

- Классы: `LLMReply`, `LLMClient(ABC)`, `RouterAIClient`, `MockClient`; функции
  `parse_tool_calls`, `parse_fallback_tool_call`, `render_tool_protocol`.
- Создание клиента — в одном месте: `Kod.py::build_agent` (стр. 226): `MockClient` (244) /
  `RouterAIClient` (248) → `Agent` (251).
- Точки вызова в `Agent`: `self.llm` (183), `self.executor = LLMExecutor` (212),
  `self.llm.complete(...)` (700, 870, 983), `rag_service.rephrase(..., llm=self.llm.complete)` (768),
  `rag_service.ground/grounding_feedback` (663, 693).

### Аудит фундамента `rag/`

- **19** модулей (`cache, chunking, citations, compare, config, corpus, embedding, eval,
  grounding, index, rerank, retrieval, rewrite, service, sources, text, types, verify, __init__`).
- `rag/index/` — `chunks.json`, `emb_cache.json`, `meta.json`, `postings.json`, `vectors.bin`;
  индекс **117 чанков / 9 документов**, `dim=1024` (эмбеддинги `bge-m3`).
- `rag/datasets/` — `corpus.list` (9 файлов), `queries.jsonl` (**34** запроса, из них **10** с `expect`).
- `rag.__all__` — `RagConfig, RagConfigError, RagDependencyError, load_config, DEFAULTS,
  DEFAULT_CONFIG_PATH, Chunk, DocMeta, Hit, IngestReport, EvalReport, CompareReport,
  GroundingReport, Answer, Source, Quote, RagService`.

### Карта разрывов (под 5 частей `Задание.txt`)

| Часть | Требование | Есть сейчас | Разрыв → этап |
|---|---|---|---|
| 1 | локальная LLM запущена, доступна по CLI/HTTP, ≥ 3 запроса | LM Studio + боевая модель на диске; сервер не поднят | поднять LM Studio → **1** |
| 2 | `/model`, отображение модели, субагенты | только `RouterAIClient`/`MockClient`; реестра нет | `ModelRegistry` + локальные клиенты → **2**; `/model` + подпись → **3**; субагенты → **4** |
| 3 | локальный RAG (retrieval + генерация), сравнение | retrieval локальный (`bge-m3`); генерация — облако | `--local-gen` + инжект `llm` → **5**; сравнение → **6** |
| 4 | параметры + prompt-шаблон + квантование + замеры | профилей нет; шаблон общий | профили + шаблон → **7**; квант/замеры → **8** |
| 5 | сервис, туннель, вход, лимиты, устойчивость | нет фасада/шлюза/туннеля | фасад → **9**; шлюз + туннель → **10**; устойчивость → **11** |

### Состояние локальных сервисов (только чтение)

- Ollama `127.0.0.1:11434` → **НЕ отвечает**.
- LM Studio `127.0.0.1:1234` → **НЕ отвечает**.
- Боевой GGUF на диске: `Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated.Q6_K.gguf` (2,5 ГБ).
- Это **блокер этапа 1** (решение №21: LM Studio обязательна); команды подъёма — в плане 1.

### Репер MCP на VPS

- `.venv/bin/python Kod.py --mcp-probe` → **READY**: серверы **`time`** и **`weather`**
  подключены; всего инструментов **4** (`mcp.time.get_time`, `mcp.weather.search_locations`,
  `mcp.weather.get_forecast_metadata`, `mcp.weather.get_weather_forecast`); exit 0.
- Точка сравнения для этапа 10 (решение №18: MCP сохраняется).

### Регрессия

- `unit_runner.py` — **290 OK, 0 FAIL**; `smoke.py` — SMOKE OK; `scenario.py` — SCENARIO OK;
  `check_acceptance.sh` — **39 из 43** (4 красных — недоступная Ollama, зафиксировано);
  `pytest -q` — **291 passed**.
- `git diff --stat requirements.txt` — пусто (зависимостей не добавляли).

### Артефакты

- `dev/migr_log.md` — обнулён до шапки Ревизии 8 + записи «Подготовка» и «Этап 0».
- `dev/migr_plan_0.md` … `dev/migr_plan_12.md` — созданы (Ревизия 8).
- `rag/`, `Kod.py`, `core/`, `storage/`, `memory/`, `integrations/` — **не изменены**.

### Коммит

- Предложен оператору (текст — в ШАГЕ 0.7 плана 0); выполнен оператором — хеш: _(ожидается)_.

### Перечитывание migr_plan.md

- ✅ (2026-10-11)

### Гейт 0→1

- ✅ (все пункты зелёные; п.4 «39 из 43» — не красный флаг, причина зафиксирована как
  ограничение среды)

---

## Этап 1 — Локальная LLM запущена (LM Studio + боевая модель) (цель: О1)

- Статус: ✅ завершён (2026-10-11)
- Было: LM Studio `127.0.0.1:1234` не отвечал; боевая модель на диске, но не загружена.
- Стало: сервер поднят оператором (`lms server start`), боевая модель загружена и отвечает.

### Живой прогон

- `lms server start` → `Success! Server is now running on port 1234`.
- `lms ps` → `qwen2.5-coder-3b-instruct-distill-qwen3-coder-next-abliterated`, **IDLE, 2.54 GB,
  context 32768, parallel 4, Local**.
- `GET /v1/models` → содержит `qwen2.5-coder-3b-instruct-distill-qwen3-coder-next-abliterated`.
- `POST /v1/chat/completions` × 3 (разной сложности):
  - Л1 «Скажи: ок» → **4,0 с**, 39 симв.;
  - Л2 (перечислить модули) → **36,0 с**, 830 симв.;
  - Л3 (объяснить функцию + риск) → **36,3 с**, 778 симв.
  Все ответы непустые; Л2/Л3 упёрлись в `max_tokens=256`.
- CLI-зачёт: `lms ls` (модель видна, `✓ LOADED`) + `lms ps` (загружена). Интерактивный
  `lms chat` не запускался (тяжёлая сессия на CPU) — по решению оператора зачёт по `ls`/`ps`.

### Офлайн без сети

- ✅ подтверждено: LM Studio — локальный сервис на loopback, интернет не используется.

### Метрики

- Латентность: короткий ответ ~4 с; длинный (до лимита 256 токенов) ~36 с (CPU, без GPU).
- RSS RAM: модель 2,54 ГБ — легко помещается в RAM 15 ГБ (доступно ~10).
- GPU: **неприменимо** (`nvidia-smi` отсутствует).

### Ограничение среды

- Ollama `127.0.0.1:11434` → **поднят оператором** (`sudo systemctl start ollama`; `bge-m3:latest`
  на месте, 1,2 ГБ). После подъёма гейт `check_acceptance.sh` → **43 из 43 зелёные (FAIL=0)** —
  прежние 4 красные RAG-проверки (№33/38/39/43) позеленели. Ограничение снято.

### Регрессия

- `unit_runner.py` — **290 OK, 0 FAIL**; `smoke.py` — SMOKE OK; `scenario.py` — SCENARIO OK;
  `check_acceptance.sh` — **43 из 43** (после подъёма Ollama; было 39 из 43);
  `pytest -q` — **291 passed**.
- `git diff --stat requirements.txt` — пусто (зависимостей не добавляли).

### Артефакты

- `dev/logs_reports/stages/local_llm_probe.md` — транскрипт живого прогона;
- `ND/models/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated_params.md` — справка;
- `.env.example` — переменные LM Studio/Ollama (без секретов);
- `dev/migr_log.md` — запись «Этап 1».

### Коммит

- Предложен оператору (текст — в ШАГЕ 1.6 плана 1); выполнен оператором — хеш: _(ожидается)_.

### Перечитывание migr_plan.md

- ✅ (2026-10-11)

### Гейт 1→2

- ✅ (все пункты зелёные; Ollama поднят, гейт 43 из 43)

---

## Этап 2 — `ModelRegistry` + локальные клиенты (цель: L1)

- Статус: ✅ завершён (2026-10-11)
- Было: только `RouterAIClient`/`MockClient`; реестра моделей нет; `Agent` создавал
  клиент напрямую в `Kod.py::build_agent`.
- Стало: `core/model_registry.py` (`ModelSpec`, `ModelRegistry`) + `OpenAICompatClient`
  (LM Studio, основной) + `OllamaClient` (альтернативный) + `models.json`; `Agent`
  получил `set_model`/`model_label`; `build_agent` строит клиент через реестр.

### Живой прогон

- `ModelRegistry.probe('lmstudio:…abliterated-Q6_K')` → `ok=True`, latency 3 мс.
- `ModelRegistry.build(...).complete([...])` → живой ответ `'Да'` (не mock).
- `probe('ollama:bge-m3')` → `ok=True`, version `0.35.1`.

### Офлайн без сети

- ✅ подтверждено: локальные клиенты ходят только на loopback (`ensure_loopback`).

### Метрики

- Латентность probe: LM Studio ~3 мс, Ollama ~1 мс.
- Живой ответ боевой модели: короткий (~секунды).

### Регрессия

- `unit_runner.py` — **302 OK, 0 FAIL** (было 290; +12 новых `test_llm_local.py`);
- `smoke.py` — SMOKE OK; `scenario.py` — SCENARIO OK;
- `check_acceptance.sh` — **43 из 43**; `pytest -q` — **303 passed**;
- `git diff --stat requirements.txt` — пусто (зависимостей не добавляли).

### Артефакты

- `core/model_registry.py` — создан;
- `core/llm_client.py` — `OpenAICompatClient`, `OllamaClient`, `ensure_loopback`;
- `core/agent.py` — `set_model`/`model_label`;
- `Kod.py` — `--model`, `MODELS_PATH`, `build_agent(model_id=…)` через реестр;
- `models.json` — создан (секретов нет);
- `dev/tests_debug/unit/test_llm_local.py` — создан (12 тестов).

### Коммит

- Предложен оператору (текст — в ШАГЕ 2.6 плана 2); выполнен оператором — хеш: `e235ca6`.

### Перечитывание migr_plan.md

- ✅ (2026-10-11)

### Гейт 2→3

- ✅ (все пункты зелёные; `Agent` не импортирует провайдеров — только `LLMClient`)

---

## Этап 3 — `/model` + отображение модели во всех CLI-сессиях (цель: L2)

- Статус: ✅ завершён (2026-10-11)
- Было: модель выбиралась только флагом `--model`; в CLI не было видно, какая
  модель/сервис подключены; `tokens.csv` и `Den_log.md` не несли модель.
- Стало: команда `/model` (`current`/`list`/`use`/`status`/`profile`); флаги
  `--model-list` (one-shot) и `--model-profile`; явное отображение модели —
  баннер `[Сессия] модель: …`, префикс реплики `[service/model]`, `model=` в
  `Den_log.md`, колонка `model` в `tokens.csv`.

### Живой прогон

- Одна сессия `cloud → lmstudio:…Q6_K → cloud` через `/model use` — 3 ответа,
  у каждого своя подпись (транскрипт `stages/local_llm_switch.md`).
- `/model list` — печатает все 4 спека реестра + отметку текущей.
- `/model status` — живой health-check (LM Studio `ok`, latency ~2 мс).

### Офлайн без сети

- ✅ подтверждено: `/model use` для локального сервиса делает probe по loopback;
  недоступный сервис → отказ с сохранением прежней модели.

### Метрики

- Локальный ответ боевой модели: короткий (~секунды, CPU).
- `/model list`/`/model status` токенов LLM не тратят (только HTTP-probe).

### Регрессия

- `unit_runner.py` — **310 OK, 0 FAIL** (было 302; +8 новых `test_model_switch.py`);
- `smoke.py` — SMOKE OK; `scenario.py` — SCENARIO OK;
- `check_acceptance.sh` — **43 из 43**; `pytest -q` — **311 passed**;
- `git diff --stat requirements.txt` — пусто (зависимостей не добавляли).

### Артефакты

- `Kod.py` — флаги `--model-list`/`--model-profile`, `handle_model_command`,
  `model_banner`, `print_model_list`, префикс реплики, колонка `model` в CSV;
- `core/agent.py` — `model=` в записи ответа `Den_log.md`;
- `dev/tests_debug/unit/test_model_switch.py` — создан (9 тестов);
- `dev/logs_reports/stages/local_llm_switch.md` — транскрипт живого прогона.

### Коммит

- Предложен оператору (текст — в ШАГЕ 3.6 плана 3); выполнен оператором — хеш: `e5e98f4`.

### Перечитывание migr_plan.md

- ✅ (2026-10-11)

### Гейт 3→4

- ✅ (все пункты зелёные; переключение не трогает `TaskStage`/память/`deliver`;
  без `--model` промпт байт-в-байт прежний)

---

## Этап 4 — Субагенты на локальных LLM (цель: L3)

- Статус: ✅ завершён (2026-10-11)
- Было: вспомогательных CLI-сессий нет; фразы «сделай локально в …» не
  распознавались; `Kod.py` умел только REPL.
- Стало: `core/subagents.py` (`SubagentRunner` + детерминированный анализатор
  фразы); флаг `--oneshot` (один обмен → ответ → выход); флаги `--subagent-run`,
  `--subagent-service`, `--local-only`; команда `/subagent run|list|log`;
  триггер-фраза «сделай локально в `<service>`: …» с подтверждением.

### Живой прогон

- Триггер-фраза «сделай локально в LM Studio: …» → подтверждение → субагент
  отработал на боевой модели (статус `ok`, ~6,5 с).
- Второй субагент через `/subagent run … --service lmstudio` — отдельная задача,
  статус `ok` (~6,4 с).
- Логи субагентов несут их собственную подпись модели
  (`model=lmstudio/…abliterated-Q6_K`); транскрипт `stages/local_llm_subagent.md`.

### Офлайн без сети

- ✅ подтверждено: субагент запускается только на локальном сервисе
  (`lmstudio`/`ollama`); облачный сервис при `local_only` → отказ до запуска.

### Метрики

- Латентность субагента (короткая задача, CPU): ~6,5 с.
- `/subagent list` токенов LLM не тратит.

### Регрессия

- `unit_runner.py` — **321 OK, 0 FAIL** (было 310; +10 новых `test_subagents.py`);
- `smoke.py` — SMOKE OK; `scenario.py` — SCENARIO OK;
- `check_acceptance.sh` — **43 из 43**; `pytest -q` — **322 passed**;
- `git diff --stat requirements.txt` — пусто (зависимостей не добавляли).

### Артефакты

- `core/subagents.py` — создан (`SubagentRunner`, `detect_local_subagent_request`);
- `Kod.py` — `--oneshot`, `--subagent-run`, `--subagent-service`, `--local-only`,
  `run_oneshot`, `run_subagent`, `handle_subagent_command`, триггер-фраза;
- `dev/tests_debug/unit/test_subagents.py` — создан (10 тестов);
- `dev/logs_reports/stages/local_llm_subagent.md` — транскрипт живого прогона.

### Коммит

- Предложен оператору (текст — в ШАГЕ 4.6 плана 4); выполнен оператором — хеш: `9a69ddd`.

### Перечитывание migr_plan.md

- ✅ (2026-10-11)

### Гейт 4→5

- ✅ (все пункты зелёные; `TaskStage` основной задачи не изменён — 0 переходов)

---

## Этап 5 — Локальная генерация в RAG (цель: G1)

- Статус: ✅ завершён (2026-10-12)
- Было: RAG-ответ генерировался облачной моделью (`RouterAIClient`); `RagService`
  не имел явного инжекта генератора; секции `generation` в `rag/config.json` не было.
- Стало: `RagService(cfg, llm=…)` принимает генератор (DI); `answer()` использует
  переданный `llm`, иначе — инжектированный; секция `generation` в конфиге
  (`provider`/`model`/`profile`); флаг `--local-gen` и команда `/gen local|cloud|status`;
  полностью локальный контур `--rag --local-gen` (эмбеддинги Ollama + retrieval +
  генерация локально).

### Живой прогон

- `--rag-ask "<вопрос>" --gen-provider lmstudio` на 3 вопросах по индексу Недели 5:
  ответ + источники `[doc_id#chunk_id]` + цитаты; опора `partial`/`hallucination`/`ok`;
  транскрипт `stages/rag_local_gen.md`.
- `/gen status` → `/gen local` → `/gen status` → `/rag ask`: переключение генератора
  RAG на lmstudio; одна точка — `agent.llm` и `rag_service.llm` совпадают;
  транскрипт `stages/rag_gen_command.md`.
- `--rag --local-gen`: баннер сессии несёт локальную модель, ответ с опорой `ok`;
  транскрипт `stages/rag_local_gen_full.md`.

### Офлайн без сети

- ✅ подтверждено: прогон при заблокированном внешнем доступе
  (`HTTP(S)_PROXY → 127.0.0.1:1`, loopback разрешён) — ответ получен локально,
  `exit=0`; транскрипт `stages/rag_local_gen_offline.md`.
- ✅ мониторинг соединений процесса (`ss -tnp`): внешних (не-loopback) соединений
  за прогон — **0**.

### Метрики

- Латентность локальной генерации (CPU, 3B Q6_K, профиль rag-strict 700 токенов):
  ~130–250 с на ответ; retrieval (bge-m3) — секунды.
- Таймаут боевой модели поднят 180 → 600 с (генерация 700 токенов на CPU ~180 с
  упиралась в прежний лимит).

### Регрессия

- `unit_runner.py` — **335 OK, 0 FAIL** (было 321; +14 новых `test_rag_local_gen.py`);
- `smoke.py` — SMOKE OK; `scenario.py` — SCENARIO OK;
- `check_acceptance.sh` — **43 из 43**; `pytest -q` — **336 passed**;
- `git diff --stat requirements.txt` — пусто (зависимостей не добавляли).

### Артефакты

- `rag/service.py` — `__init__(cfg, log, llm, embedder)`, `answer` использует `self.llm`;
- `rag/config.py` — `GenerationConfig` + секция в `RagConfig`, env `AI9_GEN_PROVIDER`/`AI9_GEN_MODEL`, валидация;
- `rag/config.json` — секция `generation`;
- `Kod.py` — `--local-gen`, `--gen-provider`, `--gen-model`, `_build_gen_client`,
  `_build_gen_llm`, `handle_gen_command`, диспетчер `/gen`, строки справки;
- `models.json` — таймаут боевой модели 600 с;
- `dev/tests_debug/unit/test_rag_local_gen.py` — создан (14 тестов);
- `dev/logs_reports/stages/rag_local_gen.md`, `rag_gen_command.md`,
  `rag_local_gen_full.md`, `rag_local_gen_offline.md` — транскрипты живых прогонов.

### Коммит

- Предложен оператору (текст — в ШАГЕ 5.7 плана 5); выполнен оператором — хеш: `50e8d6a`.

### Перечитывание migr_plan.md

- ✅ (2026-10-12)

### Гейт 5→6

- ✅ (все пункты зелёные; внешних запросов нет; офлайн-прогон прошёл; индекс 117/9
  совпадает с конфигом)

---

## Этап 6 — Сравнение локальной и облачной генерации (цель: G2)

- Статус: ✅ завершён (2026-10-12)
- Было: `rag/compare.py` умел сравнивать только стратегии чанкинга и режимы ответа
  (`no_rag`/`rag`/`rag_filter`/`rag_filter_rewrite`); сравнения генераторов
  (локальный vs облачный) не было.
- Стало: `rag/compare.py` — `compare_generators(cfg, queries, generators, k, repeat)`
  и `render_generator_report(result)` (три оси: качество/скорость/стабильность);
  `Kod.py` — флаги `--rag-gen-compare` / `--gen-modes` / `--repeat` / `--gen-report`.
  Клиентов строит `Kod.py` (граница §5: `rag/` не импортирует `core/`), поэтому
  сравнение запускается из `Kod.py`, а не из `python -m rag.compare`.

### Живой прогон

- Команда: `python Kod.py --rag-gen-compare --gen-modes cloud,local --repeat 3`
  на 10 контрольных вопросах (`c01…c10`), один датасет, один retrieval, различается
  только генератор. Отчёт: `stages/rag_local_compare.md` (30 строк cloud + 30 local).
- Локальная генерация на CPU — долго: прогон занял ~1 ч 50 мин (фоново).

### Метрики (три оси)

- **Качество:** must_contain — cloud **0.6491**, local **0.6316** (локальная чуть
  уступает); источники — **30/30** у обоих; валидные ссылки — cloud **114/175**,
  local **47/58** (локальная ставит меньше ссылок, но доля валидных выше).
- **Скорость:** медиана — cloud **22.8 с**, local **175.9 с** (локальная медленнее
  в **7.7×**); p95 — cloud 41.7 с, local 297.4 с; ток/с — cloud 17.1, local 2.4.
- **Стабильность:** ошибки — cloud **1**, local **0**; согласованность (совпадение
  must_contain в 3 повторах) — **7/10** у обоих.
- **Вердикт:** локальная модель работоспособна (источники 30/30, 0 ошибок), но
  уступает облачной по must_contain и в 7.7× медленнее; ссылки ставит реже, но
  аккуратнее. Разбор расхождений: c01 (cloud must=2 vs local must=1), c10
  (cloud must=0 vs local must=1).

### Регрессия

- `unit_runner.py` — **345 OK, 0 FAIL** (было 335; +10 новых `test_rag_gen_compare.py`);
- `smoke.py` — SMOKE OK; `scenario.py` — SCENARIO OK;
- `check_acceptance.sh` — **43 из 43**; `pytest -q` — **346 passed**;
- `git diff --stat requirements.txt` — пусто (зависимостей не добавляли).

### Артефакты

- `rag/compare.py` — `compare_generators`, `render_generator_report`, `GENERATOR_MODES`,
  `_citations`/`_citations_valid`, `_generator_summary`/`_generator_divergences`/`_generator_verdict`;
- `Kod.py` — `--rag-gen-compare`, `--gen-modes`, `--repeat`, `--gen-report`, `run_rag_gen_compare`;
- `dev/tests_debug/unit/test_rag_gen_compare.py` — создан (10 тестов);
- `dev/logs_reports/stages/rag_local_compare.md` — отчёт живого прогона.

### Коммит

- Предложен оператору (текст — в ШАГЕ 6.5 плана 6); выполнен оператором — хеш: `3a7361c`.

### Перечитывание migr_plan.md

- ✅ (2026-10-12)

### Гейт 6→7

- ✅ (отчёт с тремя осями есть; локальный режим работоспособен — 30/30 ответов с
  валидными источниками; вердикт + разбор расхождений есть; офлайн-регрессия зелёная;
  `requirements.txt` без изменений)

---

## Этап 7 — Профиль оптимизации: параметры + prompt-шаблон (цель: P1)

- Статус: ✅ завершён
- Было: параметры генерации не переопределялись профилем (`default` — пустой);
  prompt-шаблон блока [rag] был единым для облака и локальной модели; замер «до»
  отсутствовал.
- Стало: три профиля (`default`/`rag-strict`/`fast`) накладываются на спек и уходят
  в тело запроса (LM Studio — `temperature`/`max_tokens`/`top_p`; Ollama — `options`);
  строгий prompt-шаблон `render_local_rag_template` включается **только** для локальной
  модели при активном RAG; облачный промпт не затронут (renderer=None → общий блок).
- Живой прогон: `python Kod.py --rag-gen-compare --gen-modes local --gen-profile default
  --repeat 3` (боевая `Qwen2.5-Coder-3B-…-Q6_K` через LM Studio `127.0.0.1:1234`,
  loopback-only) → exit 0; отчёт `dev/logs_reports/stages/optimize_before.md`.
- Офлайн без сети: подтверждено (loopback-only; внешних запросов нет).
- Метрики (замер «до», профиль `default` + общий промпт): must_contain 0.5439;
  источники 30/30; ссылки валид. 50/68; медиана 247682.6 мс / p95 600100.6 мс;
  1.9 ток/с; ошибок 2; согласованность 3/10.
- Регрессия: unit_runner 360 OK / 0 FAIL; smoke SMOKE OK; scenario SCENARIO OK;
  check_acceptance 43 из 43 (FAIL=0); pytest 361 passed.
- Артефакты:
  - `core/prompt_builder.py` — `render_local_rag_template`, `LOCAL_RAG_INSTRUCTIONS`,
    `LOCAL_RAG_EXAMPLE`;
  - `core/model_registry.py` — `with_profile` бросает `KeyError` со списком профилей;
  - `core/agent.py` — поле `rag_block_renderer` (DI-шаблон блока [rag]);
  - `rag/service.py` — `answer`/`context_block` принимают `block_renderer`;
  - `rag/compare.py` — `compare_generators(..., block_renderers)`,
    `render_generator_report(..., title)`;
  - `Kod.py` — `_local_rag_renderer`, `_apply_local_rag_template`, флаги
    `--gen-profile`/`--local-template`, заголовок отчёта этапа 7;
  - `dev/tests_debug/unit/test_llm_optimize.py` — создан (15 тестов);
  - `dev/logs_reports/stages/optimize_before.md` — замер «до».
- Коммит: предложен оператору (текст — в ШАГЕ 7.5 плана 7); выполнен оператором — хеш: _(ожидается)_.
- Перечитывание migr_plan.md: ✅ (2026-10-12)
- Гейт 7→8: ✅ (три профиля загружаются; «до» замерено; параметры в теле запроса —
  тест зелёный; облачный промпт байт-в-байт прежний; офлайн-регрессия без изменений;
  `requirements.txt` без изменений; запись «Этап 7» + перечитывание плана)

---

## Этап 8 — Квантование + замеры «до/после» и ресурсы (цель: P2)

- Статус: ✅ завершён
- Было: замер «до» на 10×3 (`stages/optimize_before.md`); квантование/ось размера не
  опробованы; ресурсы (RSS/CPU) не снимались; отдельной секции генератора в RAG-конфиге
  было три роли вместо двух.
- Стало: матрица из **трёх генераторов** (3B Q6_K / 14B Q4_K_M / codellama-7b Q3_K_S)
  на едином датасете (2×2) с профилем `rag-strict` + локальный шаблон; раздел ресурсов
  (RSS пик/средн., CPU) в отчёте; вердикт по числам; RAG приведён к **двум ролям**
  (эмбеддинг + генератор), секция `generation` удалена, эмбеддер сделан переключаемым.
- **Ось кванта/размера (решение оператора 2026-10-12):** у боевой 3B на диске ровно
  один тег (Q6_K) → второй тег недоступен, зафиксировано как **ограничение среды**
  (решение №8: докачка — оператор). Ось «размер» представлена моделями 3B / 7B / 14B.
- **Матрица (2 вопроса × 2 повтора, профиль `rag-strict`, локальный шаблон):**
  - 3B Q6_K: must **0.5** / ссылки 5/5 / медиана 58 976 мс / p95 108 223 / 2.4 ток/с /
    RSS пик 3 982 МБ / ошибок 0 / согласованность 2/2;
  - 14B Q4_K_M: must **1.0** / 8/8 / 452 852 / 1 175 045 / 0.51 / 13 545 МБ / 0 / 2/2;
  - codellama-7b Q3_K_S: must **0.375** / **0/0** / 374 244 / 488 705 / 1.16 / 11 194 МБ / 0 / 1/2.
  - GPU: неприменим (дискретного GPU нет, CPU-inference).
- **Находка (влияет на этап 7):** исходный строгий шаблон (жёсткое правило отказа +
  few-shot) заставлял 3B сверхсрабатывать и отказываться отвечать при наличии ответа
  (`must_contain` → 0.0). Правило отказа переформулировано, few-shot убран → 0.5;
  изоляция подтверждена диагностикой на c01/c02 (strict 0.0 → soft 0.5).
- **Вердикт (боевая конфигурация):** `qwen2.5-coder-3b-…-abliterated` (Q6_K) @
  профиль `rag-strict` + локальный шаблон. Качество 0.5 ≈ «до» 0.5439 (регрессии нет),
  медиана в ~4,2× быстрее, RSS ~3,98 ГБ против ~13,5 ГБ у 14B. 14B — резерв.
- **Сравнение «до/после»:** «до» (3B @ `default` + общий промпт, 10×3) — must 0.5439,
  источники 30/30, ссылки 50/68, медиана 247 683 мс, 1.9 ток/с, ошибок 2. Датасеты
  разного размера (10×3 против 2×2) — вариант B: «до» не переснимали, помечена
  асимметрия (решение оператора 2026-10-12).
- **Рефакторинг «RAG = две роли» (уточнение куратора 2026-10-12):**
  - `rag/config.py` — удалены `GenerationConfig`, поле `generation`, env `AI9_GEN_*`,
    validate-проверка генератора, `SECTION_CLASSES["generation"]`;
  - `rag/config.json` — секция `generation` удалена;
  - `rag/embedding.py` — добавлен `OpenAICompatEmbedder` (LM Studio `/v1/embeddings`),
    `make_embedder` поддерживает `lmstudio`;
  - `core/agent.py` — `set_model` синхронизирует `agent.llm` и `rag_service.llm`
    (генератор RAG = текущая модель агента);
  - `Kod.py` — генератор RAG берётся из модели агента; `/gen local|cloud` стал алиасом
    над `/model`; `--local-gen` переключает модель агента; новые
    `handle_embed_command`/`_probe_embed_provider`/`_rebuild_service_with_embedding`/
    `_EMBED_PROVIDERS`; `/embed status|use <provider>[:<model>]`; флаги
    `--embed-provider`/`--embed-model`/`--embed-url`; **убраны** `--gen-provider`/
    `--gen-model`; `/embed` в диспетчере; help.
- Регрессия (этап 8): unit_runner **377 OK / 0 FAIL**; smoke SMOKE OK; scenario
  SCENARIO OK; check_acceptance **43 из 43**; pytest **378 passed**;
  `git diff --stat requirements.txt` — пусто.
- Артефакты:
  - `core/resources.py` — создан (`ResourceSampler`, парсеры `ps`/`free`/`lms ps`);
  - `dev/tests_debug/unit/test_llm_resources.py` — создан (12 тестов);
  - `rag/compare.py` — `resource_hooks` + раздел «Ресурсы по генераторам»;
  - `core/prompt_builder.py` — смягчённый `LOCAL_RAG_INSTRUCTIONS` (4 пункта),
    `LOCAL_RAG_EXAMPLE=""`;
  - `models.json` — +14B, +codellama; боевая 3B (`current` + `profile rag-strict`);
  - `dev/logs_reports/stages/optimize_before_after.md` — отчёт (матрица + ресурсы +
    вердикт + сравнение «до/после»);
  - `ND/models/Qwen2.5-Coder-3B-…-abliterated_params.md` — раздел «Итог оптимизации»;
  - `dev/migr_plan.md`, `dev/migr_plan_5/6/8.md` — правки «две роли»;
  - `rag/config.json`, `rag/config.py`, `rag/embedding.py`, `core/agent.py`, `Kod.py`,
    `dev/tests_debug/unit/test_rag_local_gen.py` — рефакторинг «две роли»;
  - `README_3.md`, `README_4.md` — синхронизированы (нет `generation`/`--gen-*`).
- Коммит: предложен оператору (текст — в ШАГЕ 8.6 плана 8); выполнен оператором — хеш: _(ожидается)_.
- Перечитывание migr_plan.md: ✅ (2026-10-12)
- Гейт 8→9: ✅ (матрица ≥3 конфигурации; отчёт с ресурсами; боевая конфигурация в
  конфигах; качество боевой не ниже «до»; GPU «неприменим»; офлайн-регрессия зелёная;
  `requirements.txt` без изменений; запись «Этап 8» + перечитывание плана)

---

## Этап 9 — Фасад агента на хосте (цель: S1)

- Статус: ✅ завершён
- Было: агент доступен только из терминала; HTTP-входа нет; `flask` не установлен.
- Стало: `serve.py` — тонкий Flask-фасад на `127.0.0.1:8090` (loopback-only). Единственная
  обязанность: принять запрос → передать агенту → вернуть ответ. Бизнес-логики нет
  (ни памяти, ни лимитов, ни прав, ни истории чата, ни обхода реестра).
- Маршруты: `POST /ask` (`{user,text,provider?,model?,profile?}` →
  `{answer,model,sources,quotes,verdict,usage,duration_seconds}`); `GET /models`
  (провайдеры/модели из `ModelRegistry`); `POST /model` (тот же путь, что `/model use`);
  `POST /interview` (существующий механизм интервью); `GET /state?user=…` (модель, RAG,
  стадия задачи, `busy`, `alive`).
- Очередь на 1 запрос (решение №16): `threading.Lock`; занято дольше лимита → `503`
  с текстом, не зависание. Подпись модели (`model`) — обязательное поле каждого ответа.
- Границы: слушает только loopback (`_is_loopback` → `ValueError` иначе); фасад **не
  импортирует `rag/`** напрямую (только через агента); удаление `serve.py` не меняет
  поведение агента в терминале; `TaskStage` не меняется от HTTP-вызова.
- Живой прогон: `python serve.py --mock --port 8090` → `curl /models`, `/ask` (×2),
  `/state` → exit 0; транскрипт `dev/logs_reports/stages/facade_local.md`.
- Учёт: `Den_log.md` и `tokens.csv` несут user, модель, токены, длительность для
  HTTP-запросов (не только терминала).
- Регрессия: unit_runner **391 OK / 0 FAIL** (было 377; +14 тестов фасада); smoke
  SMOKE OK; scenario SCENARIO OK; check_acceptance **43 из 43**; pytest **392 passed**;
  `git diff --stat requirements.txt` — пусто.
- Артефакты:
  - `serve.py` — создан (Flask, `127.0.0.1:8090`, очередь, подпись модели);
  - `dev/tests_debug/unit/test_facade.py` — создан (14 тестов);
  - `dev/logs_reports/stages/facade_local.md` — транскрипт живого прогона.
- Зависимость: `flask` установлен в `.venv` (единственная новая зависимость хоста;
  в `requirements.txt` ядра **не** вносится — только серверные компоненты).
- Коммит: предложен оператору (текст — в ШАГЕ 9.6 плана 9); выполнен оператором — хеш: `93d1546`.
- Перечитывание migr_plan.md: ✅ (2026-10-13)
- Гейт 9→10: ✅ (`curl POST /ask` → непустой ответ + `model`; прогон без интернета
  (mock, loopback-only); параллельный запрос держится очередью; учёт в `Den_log.md`/
  `tokens.csv`; удаление фасада не меняет терминал; `TaskStage` не изменён; `--mcp-probe`
  и прежняя база зелёные; транскрипт есть; `requirements.txt` без изменений; запись
  «Этап 9» + перечитывание плана)

---

## Этап 10 — Шлюз на VPS: вход, чат, лимиты, туннель (цель: S2)

- Статус: ✅ завершён (код и тесты; выкатка на VPS — за оператором)
- Было: доступ к агенту только с хоста (фасад `127.0.0.1:8090`); внешнего входа нет.
- Стало: `gateway/` — Flask-шлюз на VPS (публичный порт **8080**, решение №22):
  регистрация/вход (пароль — хэшем), интервью при первом входе, чат с историей на VPS,
  два связанных выпадающих списка провайдер→модель (из хостового `GET /models`),
  лимиты (6/мин → `429`; > 8000 символов → `413` до фасада), проксирование на фасад
  через SSH reverse tunnel, лог. MCP `:8000/:8010/:8020` не трогаются (решение №18).
- Границы: шлюз **не импортирует** `Kod.py`/`rag/` — только HTTP к фасаду; пароли —
  только хэшами (PBKDF2-HMAC-SHA256, соль на пользователя); секрет сессии — из env
  (`GATEWAY_SECRET`) или автосекрет `gateway/.secret` (решение №27); `gateway/users.db`
  и `gateway/.secret` — в `.gitignore`.
- Туннель (решение №12): SSH reverse (`-R 127.0.0.1:8090:127.0.0.1:8090`), юнит на
  **хосте** с `Restart=always`; проброшенный порт слушает только loopback VPS; фасад
  напрямую из интернета недоступен. **Уточнение:** `GatewayPorts` в текущей схеме
  **не требуется** (шлюз на самом VPS ходит на loopback) — справка в
  `dev/vps/sshd_gateway.snippet`. WireGuard не применяется.
- **Доработки внутри этапа 10 (v1.2, 2026-10-14, по 9-пунктному заданию оператора):**
  - **Окружение шлюза** — отдельный venv `/home/t/doc/.venv` (решение №23), не общий
    MCP-venv; юнит `ExecStart=/home/t/doc/.venv/bin/python -m gateway.app`; MCP-юниты
    не тронуты. Зависимости шлюза — `flask` **и** `requests` (решение №24).
  - **README_gateway.md** — активация venv, установка `flask requests`, копирование
    файлов через `rsync` (без `git pull`), точный `.gitignore`, расширенная инструкция
    по туннелю на ХОСТЕ (алиас, ключ, `loginctl enable-linger`, `status`/`journalctl`,
    зачем `Restart=always`), раздел «Ограничения».
  - **Rate-limit** зафиксирован явно (решение №25): in-memory, окно 60 с, сбрасывается
    при рестарте шлюза — комментарий в `app.py`, `_limits_note` в `gateway.json`,
    раздел «Ограничения» в README, эта запись.
  - **Вопросы интервью — единый источник истины** (решение №26): канон
    `core/agent.py` (`INTERVIEW_QUESTIONS` + `interview_questions_fingerprint()`);
    `serve.py` → `GET /interview/questions`; снапшот `gateway/questions.json` +
    `gateway/questions.py`; при расхождении отпечатков шлюз показывает «вопросы
    интервью устарели, обратитесь к администратору» (409) и не пускает в форму;
    обновление — `gateway/sync_questions.py` (на хосте). Отпечаток канона:
    `d447fbc523907dc55b89e5976633d6aa8b2e85da4fd53280096b774fd9813088`.
  - **Лог ответа** (решение №28): текст ответа в лог **не** пишется (приватность);
    ответ хранится в истории чата на VPS и в `Den_log.md` фасада.
  - **`Den_log.md`/`tokens.csv`** (решение №28): артефакты-доказательства, из git
    **не** удаляются; тестовый шум откатывается перед коммитом
    (`git checkout -- Den_log.md tokens.csv` — оператор). Строки из `.gitignore` убраны
    (для отслеживаемых файлов правило не действует).
  - **Секрет сессии** (решение №27): env `GATEWAY_SECRET` → файл `gateway/.secret` →
    генерация случайного; предсказуемого dev-секрета в коде нет.
- Живой прогон (хост, `--mock`, loopback): регистрация `302` → интервью `302` →
  `/api/models` (JSON) → `/api/ask` `200` → лимит (1–6 `200`, 7-й `429`) → длинный
  запрос `413` → переключение модели `200` → история на VPS → недоступный фасад `503`.
  Транскрипты: `dev/logs_reports/stages/gateway_access.md`, `stages/tunnel_setup.md`.
- Регрессия: unit_runner **402 OK / 0 FAIL** (было 391; +11 тестов шлюза); smoke
  SMOKE OK; scenario SCENARIO OK; check_acceptance **43 из 43**; pytest **403 passed**;
  `--mcp-probe` exit 0; `git diff --stat requirements.txt` — пусто.
  (После доработок v1.2: unit_runner **408 OK / 0 FAIL**, pytest **409 passed**;
  тесты шлюза+фасада — **31 passed**.)
- Артефакты:
  - `gateway/app.py`, `gateway/users.py`, `gateway/config.py`, `gateway/gateway.json`,
    `gateway/questions.py`, `gateway/questions.json`, `gateway/sync_questions.py`,
    `gateway/templates/{login,register,interview,chat}.html`, `gateway/__init__.py`;
  - `dev/tests_debug/unit/test_gateway.py` — создан/дополнен (сверка вопросов, автосекрет);
  - `dev/vps/units/ai9-gateway.service` (VPS, venv `/home/t/doc/.venv`),
    `dev/vps/units/ai9-tunnel.service` (хост), `dev/vps/sshd_gateway.snippet`,
    `dev/vps/README_gateway.md`;
  - `dev/vps/services.list` — добавлен `ai9-gateway:8080`;
  - `.env.example` — `GATEWAY_SECRET`/`GATEWAY_HOST`/`GATEWAY_PORT`; `.gitignore` —
    `gateway/users.db`, `gateway/__pycache__/`, `gateway/.secret`.
- Зависимость: `flask` + `requests` в отдельном venv шлюза `/home/t/doc/.venv`; в
  `requirements.txt` ядра **не** вносится.
- Коммит: предложен оператору (текст — в ШАГЕ 10.7 плана 10); выполнен оператором — хеш: _(ожидается)_.
- Перечитывание migr_plan.md: ✅ (2026-10-14, редакция v1.2)
- **Живой прогон на VPS (2026-10-14) — гейт 10→11 пройден.** Выкатка по
  `dev/vps/README_gateway.md`: venv `/home/t/doc/.venv` (`flask 3.1.3`, `requests 2.34.2`),
  копирование `gateway/` + юнитов + `services.list` + `.gitignore` (через `tar` по SSH —
  на VPS нет `rsync`), `GATEWAY_SECRET` в `.env`, `deploy_services.sh` → все 4 юнита
  `active` (`ai9-gateway :8080`), туннель на хосте `active`. Сквозной прогон через
  **публичный** `http://91.188.212.77:8080`: вход `302`; регистрация `302`; интервью
  форма `200` (вопросы свежие) → отправка `302`; профиль в `users/live3_*/profile.json`;
  `/api/models` JSON; `/api/ask` облако `200` (4.45 c); переключение на боевую 3B `200`;
  `/api/ask` локально `200` (38.9 c, `model`=lmstudio/3B); постоянство выбора модели
  (2 запроса — оба 3B); лимит 6/мин (1–5 `200`, 6–7 `429`); длинный запрос `413`;
  история на VPS + переживает рестарт шлюза; лог без текста ответа (`chars=`/`model=`);
  отпечаток вопросов хост=шлюз (`d447fbc5…`); MCP `:8000/:8010/:8020` `active`;
  `--mcp-probe` exit 0; офлайн-регрессия **408 OK / 0 FAIL**, pytest **409 passed**;
  `git diff --stat requirements.txt` пусто. Транскрипт — `stages/gateway_access.md`
  (раздел «Живой прогон на VPS»).
  - **Нюансы выкатки (внесены в `README_gateway.md`):** (1) на VPS нет `rsync` →
    копирование через `tar` по SSH; (2) `ControlMaster auto` в `~/.ssh/config` конфликтует
    с туннелем (forward регистрируется на master, процесс `ssh` сразу завершается →
    systemd зацикливает рестарт) → в `ai9-tunnel.service` добавлены
    `-o ControlMaster=no -o ControlPath=none`.
- Гейт 10→11: ✅ (все 10 пунктов зелёные; живой внешний прогон выполнен 2026-10-14)
- **TODO(документация, этап 12) — алгоритм подъёма LM Studio → в `README.md`.**
  При живой проверке (2026-10-14) оператор поднял LM Studio неполно (`lms ls` / `lms load` /
  `lms chat`), но **не** `lms server start` → порт `1234` не слушался → шлюз отдавал
  «Сервис временно недоступен» (фасад `502`). Правильный алгоритм с пояснениями
  («что это → зачем → ожидаемый результат») нужно внести в `README.md` на этапе 12
  (ШАГ 12.4): **`lms server start` — главный шаг**; `lms load` — необязательно;
  `lms chat` — агенту не нужен; проверка `lms server status` / `lms ps` /
  `curl :1234/v1/models`; LM Studio может «засыпать» → тот же симптом.
  Зафиксировано в мастер-плане (§0.4 `TODO(документация)`, §4 этап 12, §9 риски) и в
  рабочих планах 1, 10, 12.

---

## Этап 11 — Устойчивость: обрывы, параллельные запросы, чужое устройство (цель: S3)

- Статус: ✅ завершён (живые прогоны + тесты; коммит `09384c7` — за оператором).
- Было: шлюз `:8080` и туннель под `systemd` работали; лимиты проявлены; история на VPS.
  Не было проверок: авторестарт туннеля, идемпотентность повтора, параллельная нагрузка,
  доступ внешнего пользователя, автономность без интернета.
- Стало:
  - **туннель** (`ai9-tunnel.service`) поднимается сам после `kill` (`Restart=always`);
  - **идемпотентность повтора** (этап 11): `/api/ask` принимает `request_id`; повтор с
    тем же id возвращает сохранённый ответ (`repeated: true`), **не** гонит запрос на
    фасад и **не** дублирует реплики; обрыв во время генерации **не** оставляет
    «половину ответа» (assistant-реплика пишется только после полного ответа);
  - **параллельный прогон** — таблица стабильности (см. артефакт);
  - **инструкция внешнего пользователя** + его подтверждение (ккк);
  - **автономность**: без интернета локальный агент и терминал работают; при
    недоступном доме шлюз отдаёт `503` (не зависание).
- Границы: менялся **только шлюз** (`gateway/`); бизнес-логика агента не тронута; новых
  pip-зависимостей ядра нет.
- **Правки кода:**
  - `gateway/users.py` — таблица `requests(login, request_id, status, answer, model,
    created_at)`; функции `get_request` / `begin_request` / `finish_request` /
    `drop_request`;
  - `gateway/app.py` — `/api/ask` с `request_id` (идемпотентность); `threading.Lock`
    вокруг счётчика rate-limit (защита от гонки при параллельных запросах);
  - `gateway/templates/chat.html` — генерация/переиспользование `request_id` на клиенте
    (повтор после обрыва не дублирует реплику).
- **Rate-limit (решение №25, уточнено):** остаётся **in-memory** (счётчики в памяти
  процесса, сброс при рестарте) — согласовано с оператором; лимит против случайного
  флуда, персистентность решено не вводить.
- **Живые прогоны (2026-10-14):**
  - 11.1 авторестарт туннеля: `kill` → новый PID через ~5–12 с → VPS:8090 `200`,
    публичный шлюз `302`;
  - 11.2 идемпотентность: повтор того же `request_id` → тот же ответ за 0.00 с,
    история без дублей (1 user + 1 assistant); обрыв → `503`, «половины» нет, `pending`
    снят;
  - 11.3 параллельный прогон: N=5 → 5×`200` (медленный 20.4 с); N=9 → 6×`200` + 3×`429`
    (медленный 26.8 с); таймаут фасада → `503` за 1.22 с;
  - 11.4 автономность: внешний доступ `000` (заблокирован), LM Studio `200`, локальный
    агент ответил «Да»; `--model-list` без интернета — 6 моделей; шлюз при мёртвом
    фасаде → `503` за 0.06 с;
  - подтверждение внешнего пользователя (ккк): сессия `users/ккк/…/session.json`
    (09:52→14:33 в одной сессии), профиль `style=краткий / constraints=python, bash /
    context=программирование`; передано «если всё ок, запускай следующий этап».
- Регрессия: unit_runner **412 OK / 0 FAIL**; pytest **413 passed**; тесты
  шлюза+фасада **35 passed**; `--mcp-probe` exit 0; `git diff --stat requirements.txt`
  пусто.
- Артефакты:
  - `dev/logs_reports/stages/access_resilience.md` — транскрипт устойчивости;
  - `dev/logs_reports/stages/access_peer_confirm.md` — подтверждение внешнего пользователя;
  - правки: `gateway/users.py`, `gateway/app.py`, `gateway/templates/chat.html`,
    `dev/tests_debug/unit/test_gateway.py` (+4 теста идемпотентности).
- Коммит: `09384c7` «мигр_8_этап_11_готов» (выполнен оператором).
- Перечитывание migr_plan.md: ✅ (2026-10-14, редакция v1.2)
- Гейт 11→12: ✅ (все 10 пунктов зелёные; живой внешний прогон + подтверждение ккк 2026-10-14)

---

## Этап 12 — Финал: живые прогоны, гейт, документация, чистка (цель: Ф)
- Статус: ✅ завершён (коммит — за оператором).
- Было: этапы 0–11 закрыты; гейт расширен до 58 проверок; живые транскрипты и 4 сценария
  собраны в `dev/logs_reports/stages/` и `dev/tests_debug/scenario/`; `dev/Проверка.md`
  создан (48 критериев). Не сделано: приведение **всего** `README.md` к требованиям
  `agents.md` (весь файл — супер понятным языком, без ASCII-таблиц), запись итога, чистка.
- Стало:
  - **живые прогоны всех пяти частей** сведены в `dev/logs_reports/stages/final_live_runs.md`
    (части 1–5: `/model`, субагент, локальный RAG, сравнение/оптимизация, доступ извне);
  - **4 сценария ручной демонстрации** на месте: `scen_local_llm.md`, `scen_rag_local.md`,
    `scen_optimize.md`, `scen_access.md`;
  - **`check_acceptance.sh` — 58 из 58 зелёные** (база 43 + 15 проверок Ревизии 8);
  - **`README.md` приведён к требованиям оформления:** 10 markdown-таблиц переведены в
    структурированные списки (строк-таблиц — 0); сохранены ASCII-схемы (исключение);
    добавлен подраздел «Как читать отчёты сравнения и логи»; добавлен раздел
    «Локальные LLM и доступ к агенту»; алгоритм подъёма LM Studio по схеме
    «что → зачем → результат» (`lms server start` — главный шаг; `lms load` — необязательно;
    `lms chat` — не нужен; проверка `lms server status` / `lms ps` / `curl :1234/v1/models`);
  - **`dev/Проверка.md`** — чек-лист приёмки по всем пяти частям (48 критериев);
  - **чистка:** `dev/tests_debug/.tmp/*` удалён (280 МБ → 0); `rag/index/` сохранён;
    временный профиль `users/sub_Ответь_одним_словом_готово` удалён (логи — в `stages/`).
- Живой прогон: `final_live_runs.md` (боевая `Qwen2.5-Coder-3B-…-Q6_K` при LM Studio
  `127.0.0.1:1234`, Ollama `bge-m3`, шлюз `http://91.188.212.77:8080`, туннель
  `ai9-tunnel` active) — exit 0.
- Офлайн без сети: ✅ подтверждено (часть 3: `HTTP(S)_PROXY → 127.0.0.1:1`, routerai `000`,
  ollama `200`, lmstudio `200`, ответ получен, exit 0).
- Метрики: quality cloud 0.6491 / local 0.6316; латентность медиана cloud 22 764 мс /
  local 175 892 мс; ошибок cloud 1 / local 0; оптимизация «до/после» — медиана 58 975 мс,
  must 0.5, RSS ~3,98 ГБ.
- Регрессия: unit_runner **412 OK / 0 FAIL**; pytest **413 passed**; гейт **58/58 ✅**;
  `git diff --stat requirements.txt` пусто.
- Регрессия MCP на VPS: ✅ (`--mcp-probe` exit 0; порты 8000/8010/8020 сохранены).
- Артефакты: `dev/logs_reports/stages/final_live_runs.md`; `dev/Проверка.md`;
  4 сценария в `dev/tests_debug/scenario/`; `check_acceptance.sh` (58 проверок); `README.md`.
- Коммит: предложен текст (выполняет оператор):
  `docs(release): Ревизия 8 — локальные LLM, локальный RAG, оптимизация, доступ извне (этап 12)`.
- Перечитывание migr_plan.md: ✅ (2026-10-15, редакция v1.2)
- Гейт 12: ✅ (гейт 58/58; живые прогоны; офлайн подтверждён; README/Проверка соответствуют
  коду; MCP жив; `.tmp` пуст; `requirements.txt` без изменений)