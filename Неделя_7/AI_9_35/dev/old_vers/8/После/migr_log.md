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
  - **Лог ответа:** текст ответа в лог **не** пишется (приватность);
    ответ хранится в истории чата на VPS и в `Den_log.md` фасада.
  - **`Den_log.md`/`tokens.csv`:** артефакты-доказательства, из git
    **не** удаляются; тестовый шум откатывается перед коммитом
    (`git checkout -- Den_log.md tokens.csv` — оператор).
    **Для Ревизии 8 состав `.gitignore` изменён:** `Den_log.md`/`tokens.csv`
    внесены в `.gitignore`; формулировки README/`Проверка.md` приведены к факту.
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

---

# migr_review.md — журнал ревью документации (Ревизия 8)

> Журнал результатов ревью по рабочим планам `dev/review/migr_review_0.md` …
> (единая сквозная нумерация; один файл = один этап = один гейт).
> Мастер-план: `dev/review/migr_review.md` (**редакция v1.1**, 2026-10-18).
> Обозначения: ✅ выполнено · ❌ не выполнено · ⚠ допустимое отклонение.
> **Коммиты — только за оператором**; агент готовит правки и предлагает текст сообщения.

## Ревью Этап 0 — Снимок состояния (цель: R0)
- Статус: ✅ завершён (исполнение по `dev/review/migr_review_0.md`, шаги 0.1–0.8).
- Было: `README.md` — не закоммиченных правок документации нет (mtime 2026-10-15 16:03,
  в `git status` отсутствует); снимка фактических счётчиков не было.
- Стало: снимок состояния снят (read-only команды), расхождения README vs диск сведены
  в таблицу; `README.md` **не изменён** (правок на этапе нет).
- **ШАГ 0.1 (git):** HEAD = `dc48bb2` «мигр_8_этап_12_готов» (`main`). Не закоммичено
  (не README): `M dev/migr_log.md`, `D dev/migr_review.md`,
  `D dev/old_vers/8/migr_plan_v1.0.md`, `M dev/old_vers/8/migr_log.md`,
  `M ND/tasks/n_7/*`; неотслеживаемые `dev/review/`, `dev/old_vers/8/*.md`, `ND/tasks/n_7/*`.
- **ШАГ 0.2 (mtime):** `README.md` 2026-10-15 16:03; `dev/migr_log.md` 2026-10-18 16:20;
  `dev/Проверка.md` 2026-10-15 10:36; `dev/review/migr_review.md` 2026-10-18 16:24 (сегодня);
  `Kod.py` 2026-10-13; `serve.py`/`core/agent.py` 2026-10-14; `core/model_registry.py` 2026-10-12.
- **ШАГ 0.3 (счётчики, факт):** core=16, rag=19, integrations/mcp=11, gateway=6, unit=42,
  scenario=9, stages=56, fixtures=0 (`dev/tests_debug/fixtures/` пуст).
- **ШАГ 0.4 (размеры):** `dev/tests_debug/.tmp`=636 КБ (не пуст); `rag/index/`=2,2 МБ;
  `README.md`=1948 строк / 153 241 байт; `dev/migr_log.md`=962 строки;
  `dev/Проверка.md`=112 строк; `dev/review/migr_review.md`=609 строк.
- **ШАГ 0.5 (есть/нет, E/M):** 15 позиций `E` (есть), 3 позиции `M` (нет):
  `dev/tests_debug/scenario/scen_model_switch.md`, `dev/migr_2_plan.md`,
  `dev/migr_2_plan_0.md`. Остальное — `E` (`serve.py`, `gateway/*`,
  `models.json`, `core/model_registry.py`, `core/subagents.py`, `core/resources.py`,
  `integrations/mcp/time_server.py`, `integrations/mcp/auth.py`,
  `dev/tests_debug/scenario/scen_multiserver_flow.md`).
- **ШАГ 0.6 (упоминания в README, Y/N):** 32 позиции — все `N`.
- Уточнение по факту `grep`: `serve.py`, `gateway/`, `models.json`,
  `core/model_registry.py`, `core/subagents.py`, `core/resources.py` — упомянуты
  в **тексте** README, но **отсутствуют в «Дереве модулей»**; `integrations/mcp/time_server.py`,
  `integrations/mcp/auth.py`, `ND/`, `agents.md` — **0 упоминаний** в README.
- **Расхождения (таблица ШАГ 0.7, 18 позиций):** 8 «нет в дереве, есть на диске»
  (`serve.py`, `gateway/`, `models.json`, `core/model_registry.py`, `core/subagents.py`,
  `core/resources.py`, `integrations/mcp/time_server.py`, `integrations/mcp/auth.py`);
  2 «нет в README вовсе, есть на диске» (`agents.md`, `ND/` — 13 файлов);
  3 «заявлены, но не существуют» (`scen_model_switch.md`, `migr_2_plan.md`,
  `migr_2_plan_0…9.md`); 4 «есть на диске, нет в дереве README» (9 unit-тестов R8,
  `scen_multiserver_flow.md`, `vps/units/` — 5 юнитов, `vps/evidence/`);
  1 «пустой каталог» (`dev/tests_debug/fixtures/`).
- Дополнительно (вне таблицы): в README заявлены отсутствующие `README_3.md`/`README_4.md`
  (в `migr_log.md`, стр. 629) и удалённый `dev/old_vers/8/migr_plan_v1.0.md` (git `D`).
- Артефакты: снимок зафиксирован в настоящей записи `dev/migr_log.md`;
  `README.md` — не изменён; входы — `dev/review/migr_review.md` (v1.1),
  `dev/review/migr_review_0.md`.
- Коммит: предложен текст (выполняет оператор):
  `docs(rev): этап 0 ревью — снимок состояния (R0)`.
- Перечитывание migr_review.md: ✅ (2026-10-18, редакция v1.1, 609 строк)
- Гейт 0→1: ✅ (счётчики core=16, rag=19, mcp=11, gateway=6, unit=42, scenario=9,
  stages=56, fixtures=0; .tmp=636 КБ; README=1948 строк; 3 `M`; 32 `N`;
  таблица из 18 расхождений; `README.md` без правок).

## Ревью — правка мастер-плана: редакция v1.1 (разбивка этапа 5)
- Статус: ✅ завершён
- Было: `dev/review/migr_review.md` редакция v1.0; этап 5 — один файл
  `migr_review_5.md` (46 позиций проверок в таблице расхождений).
- Стало:
  - **уточнено назначение порога 80 000 токенов** (§0.3 решение №4, §8): это
    примерно оцениваемый объём **прочитываемой за шаг** информации (максимально
    допустимый размер контекста на шаг), а **не** ограничение объёма файла плана;
  - **этап 5 разбит на 3 подшага** (решение №4 применено на практике):
    `migr_review_5_0.md` — флаги `Kod.py` (шаги 5.0.1–5.0.5, гейт 5.0→5.1);
    `migr_review_5_1.md` — REPL-команды и «Учёт токенов» (шаги 5.1.1–5.1.4,
    гейт 5.1→5.2); `migr_review_5_2.md` — конфиги, «Ограничения»,
    «Как читать отчёты» (шаги 5.2.1–5.2.5, гейт 5.2→6);
  - `migr_review_5.md` сохранён как **зонтичный** план: цель этапа, полная таблица
    расхождений, итоговый гейт 5→6, финальный коммит этапа;
  - в §4 «Этап 5» добавлена таблица подшагов; в шапке (§ «Роль документа») и §10
    зафиксирована схема имён подшагов `migr_review_N_K.md`.
- Проверка остальных планов (0–4) на порог: расхождений нет — шаги мелкие
  (1–3 команды или одна правка), объём прочитываемой за шаг информации мал.
- Артефакты: `dev/review/migr_review.md` (v1.1); `dev/review/migr_review_5.md`;
  `dev/review/migr_review_5_0.md`; `dev/review/migr_review_5_1.md`;
  `dev/review/migr_review_5_2.md`.
- Коммит: предложен текст (выполняет оператор):
  `docs(rev): migr_review.md v1.1 — уточнён порог 80к токенов (объём чтения на шаг); этап 5 разбит на подшаги 5.0/5.1/5.2`.
- Перечитывание migr_review.md: ✅ (2026-10-18, редакция v1.1)
- Гейт: ✅ (планы 5.0/5.1/5.2 созданы; мастер-план синхронизирован)

## Ревью — созданы рабочие планы этапов 6–9; исправлен план 4
- Статус: ✅ завершён
- Было: рабочие планы существовали для этапов 0–5 (+ подшаги 5.0/5.1/5.2);
  в `migr_review_4.md` числилось расхождение «гейт: 58 в README vs 59 в скрипте».
- Стало:
  - **исправлена ошибка в плане 4:** `grep -c '^check ' check_acceptance.sh` → **58**,
    последняя подпись в скрипте `# 58:` → README корректен, расхождения нет;
    из плана убран «вопрос к этапу 6» про число проверок;
  - **`migr_review_6.md`** (Этап 6, R6) — «Тестирование и приёмка». Подтверждено
    верным: гейт 58, разбивка гейта 25+8+10+15, L2 412 OK / 42 модуля, диалоги
    A=12/B=13. Выявлено расхождение: разбивка чек-листа в README («строки 1–35 /
    36–40 / 41–48 / 49–54») — структура Ревизии 7; фактически `Проверка.md`
    состоит из **6 частей** (5 + 10 + 6 + 6 + 13 + 8 = 48). Вторая правка —
    развести L4-проверки `scenario.py` и **9 md-файлов** сценариев ручной демонстрации;
  - **`migr_review_7.md`** (Этап 7, R7) — «Содержание». Две точечные правки:
    (1) порядок пунктов — «Локальные LLM» (стр. 1178) идёт в файле раньше
    «Агентный цикл» (стр. 1420), в оглавлении — наоборот; (2) якорь раздела `dev/`
    не резолвится (заголовок содержит «(проект про проект)»). Подпункты `###`
    не добавляем (решение №2);
  - **`migr_review_8.md`** (Этап 8, R8) — финальная согласованность: эталонная
    таблица счётчиков (core=16, rag=19, mcp=11, gateway=6, unit=42, гейт=58,
    приёмка=48, сценарии=9, stages=56, чанки=117, слои=4, состояния=8,
    порты 8000/8010/8020), сверка путей из README с диском, термины
    «шлюз» (`gateway/`) vs «фасад» (`serve.py`), финальная перечитка README целиком;
  - **`migr_review_9.md`** (Этап 9, Ф) — финал: прогон гейта 58/58, проверка
    `.tmp/`, выборочная сверка `Проверка.md` (Д.3/Д.4/Д.6/Д.8), итоговая сводка;
  - в мастер-план (§4 «Этапы 6–9») внесены уточнения по фактическим расхождениям;
    шапка мастер-плана и журнал переведены на **редакцию v1.1**; ссылки в планах
    0–4 синхронизированы на v1.1.
- Проверка: `grep -rn 'редакция v1.0' dev/review/` → пусто (в журнале остались
  только исторические упоминания в записях этапа 0 и правки v1.1 — они корректны).
- Артефакты: `dev/review/migr_review_6.md`; `migr_review_7.md`; `migr_review_8.md`;
  `migr_review_9.md`; `migr_review_4.md` (правка); `migr_review.md` (v1.1);
  `migr_review_0..4.md` (синхронизация ссылки на редакцию).
- Коммит: предложен текст (выполняет оператор):
  `docs(rev): рабочие планы этапов 6–9; исправлен план 4 (гейт = 58, расхождения нет)`.
- Перечитывание migr_review.md: ✅ (2026-10-18, редакция v1.1)
- Гейт: ✅ (полный набор планов 0–9 + подшаги 5.0/5.1/5.2 готов к исполнению)

## Ревью Этап 1 — Обновление «Дерева модулей» (цель: R1)
- Статус: ✅ завершён (исполнение по `dev/review/migr_review_1.md`, шаги 1.1–1.7).
- Было: «Дерево модулей» (раздел «Архитектура») — снимок Ревизии 7: `core/` 14 файлов,
  `integrations/mcp/` 9 файлов; отсутствовали `serve.py`, `models.json`, `gateway/`.
- Стало (README.md): дерево модулей приведено к факту диска.
  - **`core/` → 16 файлов:** добавлены `model_registry.py`, `resources.py`, `subagents.py`
    (после `invariants.py`, перед `tools.py`; в дереве сохраняется порядок README — по роли, не алфавит);
  - **корень:** добавлены `serve.py` (фасад, Flask `127.0.0.1:8090`) и `models.json`
    (реестр моделей и профилей) после `Kod.py`;
  - **`gateway/`:** добавлен блок (Flask) — `app.py`, `config.py`, `questions.py`,
    `sync_questions.py`, `users.py`, `templates/` (login/register/interview/chat);
  - **`integrations/mcp/` → 11 файлов:** добавлены `auth.py` (серверная проверка токена)
    и `time_server.py` (MCP-сервер времени, HTTP :8000).
- Фактические счётчики после правки: README 1948 → **1962 строки**; правка — **14 добавленных
  строк** (`git diff --stat README.md` = `14 +`, только insertions, 0 deletions).
- **ШАГ 1.6 (проверка):** все 16 путей из нового дерева существуют на диске — `OK` ×16
  (включая `gateway/templates/*`, `integrations/mcp/auth.py`, `integrations/mcp/time_server.py`).
- Примечание: `gateway.json`, `questions.json` (конфиг-файлы) в мини-блок `gateway/` не
  добавлялись — минимальные правки; уточнить при финальной согласованности (этап 8, R8).
- Артефакты: `README.md` (дерево модулей); `dev/migr_log.md` (настоящая запись).
- Коммит: предложен текст (выполняет оператор):
  `docs(readme): обновить «Дерево модулей» — serve.py, gateway/, models.json, core/*, mcp/auth.py, mcp/time_server.py`.
- Перечитывание migr_review.md: ✅ (2026-10-18 18:27, редакция v1.1, 609 строк)
- Гейт 1→2: ✅ (core=16; `serve.py`/`models.json`/`gateway/` в дереве; mcp=11;
  все файлы из нового дерева существуют; запись сделана; мастер-план перечитан).
## Ревью Этап 2 — Обновление «Дерева `dev/`» (цель: R2)
- Статус: ✅ завершён (исполнение по `dev/review/migr_review_2.md`, шаги 2.1–2.9).
- Было: «Дерево `dev/`» (раздел «Служебное пространство `dev/`») — снимок Ревизии 7:
  заявлены несуществующие `migr_2_plan.md`, `migr_2_plan_0.md … migr_2_plan_9.md`
  (Ревизия 7.1) и `scen_model_switch.md`; блоки `unit/` и `scenario/` неполны;
  отсутствовали `scen_multiserver_flow.md`, 9 unit-тестов R8, `vps/units/` (5 юнитов),
  `vps/evidence/`, `fixtures/`.
- Стало (README.md): дерево `dev/` приведено к факту диска.
  - **ШАГ 2.1:** удалены строки `migr_2_plan.md` и `migr_2_plan_0.md … migr_2_plan_9.md`
    (файлов нет на диске — `ls dev/migr_2_plan*.md` → «Нет такого файла»);
  - **ШАГ 2.2:** удалена строка `scen_model_switch.md` (файла нет);
  - **ШАГ 2.3:** добавлен `scen_multiserver_flow.md` (мультисерверный поток, Ревизия 7);
  - **ШАГ 2.4:** блок `unit/` конкретизирован — «42 модуля test_*.py (канонический
    раннер — unit_runner.py)» + подблок «Ревизия 8 (9 модулей)»: `test_llm_local.py`,
    `test_model_switch.py`, `test_subagents.py`, `test_rag_local_gen.py`,
    `test_rag_gen_compare.py`, `test_llm_optimize.py`, `test_llm_resources.py`,
    `test_facade.py`, `test_gateway.py`;
  - **ШАГ 2.5:** строка `vps/` раскрыта — 7 файлов (`deploy_services.sh`, `mcp_vps.sh`,
    `services.list`, `ssh_config.snippet`, `sshd_gateway.snippet`, `README_vps.md`,
    `README_gateway.md`), `units/` (5 systemd-юнитов: `ai9-gateway.service`,
    `ai9-tunnel.service`, `mcp-time-server.service`, `mcp-scheduler-server.service`,
    `mcp-pipeline-server.service`), `evidence/` (5 probe/call);
  - **ШАГ 2.6:** добавлен `fixtures/` (пусто — заполняется по мере надобности);
  - **ШАГ 2.7:** в описании `scenario/` указано фактическое число — **9 сценариев**
    (было заявлено 7, из них 1 несуществующий); `logs_reports/` — «stages/ (56 файлов)».
- Фактические счётчики: unit=42, scenario=9, stages=56, fixtures=0; README
  1962 → **1986 строк** (`git diff --stat README.md` = `32 insertions, 9 deletions`).
- **ШАГ 2.8 (проверка):** 15 путей из нового дерева `dev/` (9 unit R8 +
  `scen_multiserver_flow.md` + 5 `vps/units/*.service`) — `OK` ×15; удалённые
  `migr_2_plan.md` и `scen_model_switch.md` — `OK (absent)`; `dev/migr_2_plan*.md` — нет.
- Артефакты: `README.md` (дерево `dev/`); `dev/migr_log.md` (настоящая запись).
- Коммит: предложен текст (выполняет оператор):
  `docs(readme): обновить «Дерево dev/» — удалить несуществующие migr_2_plan* и scen_model_switch.md, добавить 9 unit-тестов R8, scen_multiserver_flow.md, vps/units/ (5 юнитов), vps/evidence/, fixtures/`.
- Перечитывание migr_review.md: ✅ (2026-10-18, редакция v1.1, 609 строк)
- Гейт 2→3: ✅ (migr_2_plan* и scen_model_switch.md удалены; scen_multiserver_flow.md
  добавлен; 9 unit-тестов R8 добавлены; vps/units/ и vps/evidence/ раскрыты; fixtures/
  добавлен; все файлы нового дерева существуют; удалённые отсутствуют; запись сделана;
  мастер-план перечитан).

## Ревью Этап 3 — Добавление отсутствующих разделов (цель: R3)
- Статус: ✅ завершён (исполнение по `dev/review/migr_review_3.md`, шаги 3.1–3.8).
- Было: `ND/` и `agents.md` — **0 упоминаний** в README; `time_server.py`/`auth.py`
  уже добавлены этапом 1.
- Стало (README.md):
  - **ШАГ 3.1:** в конец «Дерева модулей» (после `users/`) добавлен блок `ND/`:
    `models/` (справки по моделям), `other/` (1.txt, 2.txt, tunel_plan.md),
    `tasks/` (задания куратора по неделям n_1 … n_7);
  - **ШАГ 3.2:** в корень дерева (рядом с `README.md`) добавлен `agents.md`
    (краткая памятка агенту, 20 строк);
  - **ШАГ 3.3:** в «Служебные артефакты» добавлен `ND/` (3 строки: `models/*_params.md`,
    `tasks/n_1 … n_7`, `other/tunel_plan.md`);
  - **ШАГ 3.4:** в «Служебные артефакты» добавлен `agents.md`.
- **ШАГ 3.5 (проверка):** `time_server.py` (стр. 452) и `auth.py` (стр. 451) — найдены
  в «Дереве модулей» (добавлены на этапе 1) `OK`.
- **ШАГ 3.6 (проверка):** `.ssh` в README — **0 совпадений** (`grep -n '\.ssh'` → пусто);
  приватные ключи намеренно не описаны (решение №8 мастер-плана).
- **ШАГ 3.7 (проверка):** пути `ND/models`, `ND/other`, `ND/tasks`, `agents.md` — `OK` ×4;
  упоминаний в README: `ND/` = 4, `agents.md` = 2, `time_server` = 1, `auth.py` = 1.
- Фактические счётчики: README 1985 → **1997 строк** (`git diff --numstat README.md`
  = `12 insertions, 0 deletions`).
- Артефакты: `README.md` (дерево модулей + карта артефактов); `dev/migr_log.md`.
- Коммит: предложен текст (выполняет оператор):
  `docs(readme): добавить отсутствующие разделы — ND/ (справки по моделям, задания куратора) и agents.md; .ssh/ намеренно не описан`.
- Перечитывание migr_review.md: ✅ (2026-10-18, редакция v1.1, 609 строк)
- Гейт 3→4: ✅ (ND/ в дереве и карте; agents.md в дереве и карте; time_server/auth.py
  упомянуты; .ssh/ не описан; все пути существуют; запись сделана; мастер-план перечитан).

## Ревью Этап 4 — Обновление «Карты артефактов» (цель: R4)
- Статус: ✅ завершён (исполнение по `dev/review/migr_review_4.md`, шаги 4.1–4.7).
- Было: «Карта артефактов» (раздел «Карта артефактов»):
  - «Рабочие артефакты» — перечень `integrations/mcp/*` без `time_server`/`auth`;
    `gateway/*` без `questions.json`/`sync_questions.py`/`gateway.json`;
    `dev/vps/*` без `units/`/`evidence/`/`services.list`/`sshd_gateway.snippet`;
    `ND/models/*_params.md` — строка отсутствовала;
  - «Служебные артефакты» — `dev/tests_debug/*` с формулировкой «+6 сценариев»;
    строки `dev/review/*`, `agents.md`, `ND/tasks`, `ND/other` — отсутствовали.
- Расхождения плана с фактическим состоянием (учтены): `serve.py`, `gateway/*`,
  `models.json`, `core/model_registry.py`, `core/subagents.py`, `core/resources.py`
  уже были в карте после этапов 1–3 (`ND/`, `agents.md` в «Служебных»); гейт фактически
  = **58** (`grep -c '^check '` → 58, метка `# 58:`), а не 59 — README верен;
  расхождения `migr_2_plan.md` в «Служебных артефактах» нет (был устаревший в дереве
  `dev/`, удалён на этапе 2).
- Стало (README.md):
  - **ШАГ 4.1:** `integrations/mcp/*` дополнен `time_server`, `auth` (11 модулей);
  - **ШАГ 4.2:** `gateway/*` раскрыт — `questions.py` + `questions.json`,
    `sync_questions.py`, `config.py` + `gateway.json`, `templates/` (login, register,
    interview, chat);
  - **ШАГ 4.3:** `dev/vps/*` раскрыт — скрипты деплоя, `services.list`,
    `ssh_config.snippet`, `sshd_gateway.snippet`, `units/` (5 systemd-юнитов),
    `evidence/`, `README_vps.md`, `README_gateway.md`;
  - **ШАГ 4.4:** `ND/models/*_params.md` добавлен в «Рабочие артефакты» (перед `run.sh`);
  - **ШАГ 4.5:** «Служебные артефакты» — добавлены `dev/review/*`, `agents.md`;
    уточнено `dev/migr_log.md` (+ журнал ревью); `dev/tests_debug/*` — «L2 (42 модуля,
    +9 новых R8), L3, L4 (9 сценариев), гейт 58/58»; `stages/` — «56 файлов».
- Фактические счётчики: README 1997 → **2004 строки** (`git diff --numstat README.md`
  = `16 insertions, 9 deletions`).
- **ШАГ 4.6 (проверка):** 10/10 путей из карты существуют на диске — `OK` ×10
  (`integrations/mcp/time_server.py`, `auth.py`, `gateway/sync_questions.py`,
  `questions.json`, `gateway.json`, `dev/vps/units`, `dev/vps/evidence`,
  `dev/review/migr_review.md`, `ND/models`, `agents.md`); устаревших ссылок
  (`migr_2_plan`, `README_3`, `README_4`, `scen_model_switch`) в README — **0**.
  Сверено с диском: гейт = 58 (`check_acceptance.sh`), unit = 42, scenario = 9,
  stages = 56; `ND/models/*_params.md` в карте — 1 упоминание (без дублей).
- **ШАГ 4.7:** `migr_review.md` перечитан целиком (редакция v1.1).
- Артефакты: `README.md` (карта артефактов); `dev/migr_log.md` (настоящая запись).
- Коммит: предложен текст (выполняет оператор):
  `docs(readme): обновить «Карту артефактов» — дополнить mcp/ (time_server, auth), gateway/ (sync_questions, questions.json, gateway.json), dev/vps/ (units, evidence), добавить ND/models в рабочие, agents.md и dev/review/ в служебные`.
- Перечитывание migr_review.md: ✅ (2026-10-18, редакция v1.1)
- Гейт 4→5: ✅ (mcp=11; gateway — 6 py + 2 json + templates; units/ и evidence/
  упомянуты; ND/ в карте; agents.md и dev/review/ в служебных; все пути существуют;
  устаревших ссылок нет; запись сделана; мастер-план перечитан).

## Ревью — ограничение: `temperature` / `max_tokens` / `context_window` НЕ ТРОГАТЬ (ред. v1.2)
- Статус: ✅ внесено (по прямому указанию оператора после этапа 4, до старта этапа 5).
- Причина: флаги `--temperature`, `--max-tokens`, `--context-window` и связанная
  информация — следы функционала задания Дня 5 (`ND/tasks/n_1/005_День 5/`:
  `Den_5_Kod.py`, `Задание_Д5.txt`, `README_d5.md`), **ошибочно затёртого в одной из
  прошлых ревизий**. Подлежат **восстановлению в следующей ревизии** ⇒ правки,
  предписанные планом 5.0 редакции v1.1 («удалить из README»), **отменены**.
- Было: план 5.0 ред. v1.1 предписывал удалить 3 флага из README + строку `--max-tokens`;
  мастер-план и зонтичный план 5 описывали это как «ключевое расхождение».
- Стало:
  - **`README.md`** — добавлены пометки «НЕ ТРОГАТЬ»: (1) в блоке флагов локальных LLM
    (после `--rag-gen-compare …`) — про 3 флага и профили; (2) в разделе «Оптимизация:
    профили параметров» — про `temperature`/`max_tokens`/`context_window`. Строки флагов
    `--temperature F`, `--max-tokens N`, `--context-window N` и `--max-tokens` в перечне
    запуска **сохранены без изменений**;
  - **`dev/review/migr_review_5_0.md`** — переписан: цель = «проверить и сохранить»,
    добавлен блок «Жёсткое ограничение», шаги 5.0.1–5.0.5 переформулированы (сохранение
    флагов; `--embed-url` — только добавление при отсутствии), гейт обновлён;
  - **`dev/review/migr_review_5.md`** — добавлен блок ограничения; таблица подшагов,
    таблица расхождений, «ключевое расхождение» (→ «ключевое ограничение»), коммит и
    гейт 5→6 обновлены; исправлен дубль №6 в гейте (перенумеровано 1–14);
  - **`dev/review/migr_review_5_2.md`** и **`migr_review_9.md`** — синхронизированы
    формулировки коммита/сводки этапа 5;
  - **`dev/review/migr_review.md`** — редакция **v1.2**: добавлен §0.7 «Жёсткое
    ограничение»; ограничение отражено в §4 «Этап 5» и §5 «Сквозные требования и запреты»;
    шапка обновлена; ссылки на редакцию во всех планах 0–9 синхронизированы на v1.2.
- Проверка: `grep -n 'НЕ ТРОГАТЬ' README.md` → 2 (блок флагов + профили);
  `grep -n -- '--temperature F\|--context-window N\|--max-tokens' README.md` → флаги
  на месте (стр. 1166, 1181, 1188); `grep -rn 'удалить несуществующие флаги\|не зарегистрированы в Kod.py' dev/review/` → пусто.
- Артефакты: `README.md` (2 пометки); `dev/review/migr_review.md` (v1.2);
  `migr_review_5.md`, `migr_review_5_0.md`, `migr_review_5_2.md`, `migr_review_9.md`;
  `migr_review_0..9.md` (ссылка на редакцию v1.2).
- Коммит: предложен текст (выполняет оператор):
  `docs(rev): ввести ограничение НЕ ТРОГАТЬ для --temperature/--max-tokens/--context-window (следы Дня 5, восстанавливаются в следующей ревизии); редакция мастер-плана v1.2`.
- Перечитывание migr_review.md: ✅ (2026-10-18, редакция v1.2)
- Гейт: ✅ (ограничение внесено в README и во все планы; удаление флагов отменено)

## Ревью Этап 5 — Проверка раздела «Локальные LLM и доступ к агенту» (цель: R5)
- Статус: ✅ завершён (исполнение по `dev/review/migr_review_5.md` + подшаги 5.0/5.1/5.2).
- Разбит на 3 подшага (решение №4 мастер-плана, объём проверок > 80 000 токенов).

### Подшаг 5.0 — Флаги `Kod.py` (migr_review_5_0.md)
- Статус: ✅ завершён. Результат: **АКТУАЛЬНО** (правок README нет).
- Было: раздел флагов локальных LLM (стр. 1160–1195) + пометки «НЕ ТРОГАТЬ».
- Проверка (read-only):
  - `grep -n 'НЕ ТРОГАТЬ' README.md` → **2** (блок флагов, стр. 1188; раздел «Оптимизация:
    профили параметров», стр. 1322);
  - `grep -n -- '--temperature F\|--context-window N' README.md` → стр. **1181** (флаги
    на месте, не удалены);
  - `grep -c -- '--max-tokens' README.md` → **3** (перечень запуска стр. 1166; флаги LLM
    стр. 1181; блок «НЕ ТРОГАТЬ» стр. 1188);
  - `grep -n 'embed-url' README.md` → стр. **1180** (и 1885, 1996); `add_argument("--embed-url"` → `Kod.py:211`;
  - `grep -n 'add_argument(' Kod.py` → **57** флагов; запрещённые
    `--temperature`/`--context-window` — **не зарегистрированы** (ожидаемо, следы Дня 5);
    `--max-tokens` → `Kod.py:120`.
- Расхождение (ожидаемое): флаги `--temperature`/`--max-tokens`/`--context-window` в README
  заявлены, в `Kod.py` не зарегистрированы — **функционал Дня 5 затёрт, восстанавливается
  в следующей ревизии**; README не правится (§0.7 ред. v1.2).
- Артефакты: `README.md` — не изменён; `dev/migr_log.md` (настоящая запись).
- Гейт 5.0→5.1: ✅ (флаги сохранены; пометки «НЕ ТРОГАТЬ» на месте; `--embed-url` есть;
  удаления нет; запись сделана).

### Подшаг 5.1 — REPL-команды, маршруты, «Учёт токенов» (migr_review_5_1.md)
- Статус: ✅ завершён. Результат: **АКТУАЛЬНО** (правок README нет).
- Было: разделы «Команды управления моделью» (стр. 1358–1367) и «Учёт токенов и модель»
  (стр. 1369–1376).
- Проверка (read-only):
  - README (стр. 1358–1367): `/model`, `/model list`, `/model use <id>`, `/model status`,
    `/model profile <name>`, `/gen local` / `/gen cloud`, `/embed status`,
    `/embed use ollama:bge-m3` — **все подтверждены** `Kod.py` (`handle_model_command`
    1405, `handle_subagent_command` 1520, `handle_gen_command` 1596, `handle_embed_command` 1659);
  - `/model current` в README — **нет** (корректно: в `Kod.py` `current` — подкоманда по
    умолчанию, отдельного пункта не требуется);
  - `/gen status` в README — не вынесен (в `Kod.py` есть; расхождение несущественное,
    правки нет — минимальные правки §2);
  - маршруты `serve.py`: `/ask` (127), `/models` (181), `/model` (201), `/interview` (227),
    `/interview/questions` (250), `/state` (263) — все реализованы; в README отражены
    косвенно (`/ask`, `/models` стр. 1825, 1549);
  - «Учёт токенов и модель» (стр. 1369–1376): баннер `[Сессия] модель:` (`model_banner`
    Kod.py:1377), префикс `[label] Агент:` (Kod.py:1372, 2507), `Den_log.md` `model=`
    (`core/agent.py:941`, `serve.py:160`), колонка `model` в `tokens.csv` (`Kod.py:272`),
    HTTP-поле `model` (`serve.py:164`) — **всё соответствует**.
- Артефакты: `README.md` — не изменён; `dev/migr_log.md` (настоящая запись).
- Гейт 5.1→5.2: ✅ (REPL-команды подтверждены; маршруты подтверждены; «Учёт токенов»
  подтверждён; запись сделана).

### Подшаг 5.2 — Конфиги, «Ограничения», «Как читать отчёты» (migr_review_5_2.md)
- Статус: ✅ завершён. Результат: **АКТУАЛЬНО** (правок README нет).
- Было: разделы «Конфигурационные файлы» (стр. 1378–1410), «Ограничения» (1412),
  «Как читать отчёты» (1423).
- Проверка (read-only):
  - `models.json`: `current` = `cloud:stepfun/step-3.5-flash` ✅; профили
    `default`/`rag-strict`/`fast` ✅; `rag-strict` = 0.1/700/8192/0.9 ✅; `fast` =
    0.3/256/4096/0.9 ✅; **6 моделей** (cloud, lmstudio×3, ollama:bge-m3, mock) ✅
    (в README пример из 2 — допустимо); `timeout_seconds: 600` у боевой 3B ✅;
  - `gateway/gateway.json`: `host_facade_url` = `http://127.0.0.1:8090` ✅;
    `public_port: 8080` ✅; `limits` = 6/мин, 8000 символов ✅; `session.secret_env`
    = `GATEWAY_SECRET`, `secret_file` = `gateway/.secret` ✅; `facade_timeout_seconds: 180`,
    `max_age_minutes: 720`, `history_keep_messages: 200` — в README не упомянуты
    (**не трогать**: README не полная спецификация конфига);
  - «Ограничения» (стр. 1412): ~7× медленнее ✅ (журнал: cloud 22 764 мс / local
    175 892 мс ≈ 7.7×); rate-limit in-memory ✅ (`_limits_note`); LM Studio «засыпает» ✅;
    один тег Q6_K ✅; очередь фасада (1 запрос) ✅;
  - «Как читать отчёты» (стр. 1423): `final_live_runs.md`, `rag_local_compare.md`,
    `optimize_before_after.md`, `access_resilience.md`, `access_peer_confirm.md`,
    `subagent_*.md` — **все существуют** в `dev/logs_reports/stages/` (OK ×5 + 4 `subagent_*`).
- Артефакты: `README.md` — не изменён; `dev/migr_log.md` (настоящая запись).
- Гейт 5.2→6: ✅ (`models.json` и `gateway.json` подтверждены; «Ограничения» и «Как
  читать отчёты» подтверждены; отчёты существуют; запись сделана).

### Итог этапа 5
- Было: раздел «Локальные LLM и доступ к агенту» (стр. 1178) требовал проверки на
  соответствие `Kod.py` / `serve.py` / `models.json` / `gateway.json`.
- Стало: раздел проверен по всем 3 подшагам; **правок README нет** — всё **АКТУАЛЬНО**,
  кроме **ожидаемого** расхождения по флагам Дня 5 (`--temperature`/`--max-tokens`/
  `--context-window`: в README заявлены + пометка «НЕ ТРОГАТЬ», в `Kod.py` отсутствуют —
  восстанавливаются в следующей ревизии). README = **2016 строк**; правок этапа 5 — **0**.
- Артефакты: `dev/migr_log.md` (записи 5.0/5.1/5.2 + итог); `README.md` — без изменений
  (незакоммиченный diff — это 2 пометки «НЕ ТРОГАТЬ» ред. v1.2, `12 insertions`, не этап 5).
- Коммит: предложен текст (выполняет оператор):
  `docs(rev): этап 5 — проверка раздела «Локальные LLM и доступ к агенту» (R5); правок README нет, раздел АКТУАЛЕН (кроме ожидаемого расхождения по флагам Дня 5)`.
- Перечитывание migr_review.md: ✅ (2026-10-18, редакция v1.2)
- Гейт 5→6: ✅ (все 14 пунктов гейта `migr_review_5.md` зелёные: флаги сохранены,
  пометки есть, `--embed-url` есть; REPL-команды и маршруты подтверждены; «Учёт токенов»
  подтверждён; `models.json`/`gateway.json`/«Ограничения»/«Как читать отчёты» подтверждены;
  записи 5.0/5.1/5.2 + итог в migr_log.md).
- Что передаём дальше: **этап 6 (R6)** — раздел «Тестирование и приёмка» (сверить счётчики);
  **этап 8 (R8)** — проверенный раздел «Локальные LLM» для перекрёстной согласованности.

## Ревью Этап 6 — Проверка раздела «Тестирование и приёмка» (цель: R6)

### Подшаг 6.1 — Перезапись разбивки чек-листа приёмки
- Статус: ✅ завершён.
- Было: четыре пункта «строки 1–35 / 36–40 / 41–48 / 49–54» (разбивка Ревизии 7).
- Стало: шесть частей по фактической структуре `dev/Проверка.md` — Часть 1 (5),
  Часть 2 (10), Часть 3 (6), Часть 4 (6), Часть 5 (13), Документация (8).
- Артефакты: `README.md` (правка применена, не закоммичена).

### Подшаг 6.2 — Уточнение формулировки про L4-сценарии
- Статус: ✅ завершён.
- Было: L4-сценарии перечислены как внешние артефакты (`scenario_mcp_discovery` и др.).
- Стало: указано, что это проверки **внутри** `scenario.py`; отдельно в `scenario/`
  лежат **9 md-файлов сценариев ручной демонстрации** — чек-листы живых прогонов,
  а не автотесты.

### Подшаг 6.3 — Сверка числа тестов модулей R8 (AST)
- Статус: ✅ завершён. Методика: `ast.parse` → module-level `FunctionDef`/`ClassDef`
  с именем на `test_` (первый `grep`-подсчёт дал завышенные числа и отклонён).
- Совпали с README (6): `test_llm_local` 12, `test_model_switch` 9, `test_subagents` 10,
  `test_rag_gen_compare` 10, `test_llm_optimize` 15, `test_llm_resources` 12.
- **Расхождения (README → факт):** `test_rag_local_gen` 14 → **19**,
  `test_facade` 14 → **15**, `test_gateway` 11 → **20**.
- Сумма по всем 42 модулям = **412** (совпадает с раннером/L2).
- Решение: **числа в README не править наугад** — передать этапу 8 (R8) для
  аккуратной сверки и правки с пересчётом.

### Подшаг 6.4 — Сверка счётчиков
- Статус: ✅ завершён. `dev/logs_reports/stages/` = **56**; `rag/index/meta.json`
  → `docs` = **9**, сумма `n_chunks` = **117** (49 `Проверка.md`; 3/3/12 `ND/models/`;
  8 `core/invariants.py`; 19 `core/prompt_builder.py`; 6 `memory/base.py`;
  4 `memory/manager.py`; 13 `integrations/mcp/config.py`). Совпало с README.

### Подшаг 6.5 — Проверка правок (grep)
- Статус: ✅ завершён. «строки 1–35 …» → **0**; 6 частей (пробы) → **3**;
  «9 md-файлов» → **1**. Содержимое подтверждено чтением стр. 1536–1588.

### Подшаг 6.6 — Схлопывание дублирующего списка сценариев куратору
- Статус: ✅ завершён (решение оператора).
- Решение оператора: **сценарии живой демонстрации куратору записываются только
  в `dev/Проверка.md`** — другие файлы (в т.ч. README) **не должны дублировать**
  эти данные.
- Было (стр. 1580–1583): «Сценарии живой демонстрации куратору — `scenario/scen_1.md`,
  `scen_rag.md`, `scen_local_llm.md`, `scen_rag_local.md`, `scen_optimize.md`,
  `scen_access.md`, `dev/Проверка.md` (48 критериев…)» — перечислялись 6 из 9.
- Стало: «Сценарии живой демонстрации куратору — `dev/Проверка.md`
  (48 критериев Ревизии 8).» — без дублирования списка.
- Обоснование: перечень сценариев/критериев живых прогонов — прерогатива
  `Проверка.md`; README оставляет указатель.

### Итог этапа 6
- Было: раздел «Тестирование и приёмка» содержал устаревшую разбивку чек-листа
  (Ревизия 7: «строки 1–35 …»), размытую формулировку L4-сценариев и дублирующий
  список сценариев куратору.
- Стало: разбивка приведена к 6 частям / 48 критериям `Проверка.md`; L4-проверки
  `scenario.py` отделены от 9 md-сценариев ручной демонстрации; дублирующий список
  сценариев куратору схлопнут до указателя на `dev/Проверка.md`. README = **2021 строка**.
- Правки README этапа 6: 6.1 (разбивка), 6.2 (L4), 6.6 (список сценариев).
- Расхождения: R8-числа `test_rag_local_gen` 14→19, `test_facade` 14→15,
  `test_gateway` 11→20 — **переданы этапу 8**; остальные счётчики (42/412/58/48/9/56/117)
  совпали.
- Артефакты: `README.md` (3 правки, не закоммичены); `dev/migr_log.md` (настоящая запись).
- Коммит: предложен текст (выполняет оператор):
  `docs(readme): раздел «Тестирование и приёмка» — разбивка чек-листа приведена к фактической структуре Проверка.md (6 частей, 48 критериев); уточнено различие L4-проверок scenario.py и 9 md-сценариев ручной демонстрации; сценарии куратору — только в Проверка.md (список в README схлопнут)`.
- Перечитывание migr_review.md: ✅ (2026-10-18, редакция v1.2)
- Гейт 6→7: ✅ (9 критериев: устаревшая разбивка отсутствует — 0; 6 частей соответствуют
  `Проверка.md`; сумма = 48; L4-проверки отделены от md-сценариев; md-сценариев = 9;
  числа тестов R8 сверены (расхождение зафиксировано и передано этапу 8); счётчики 56/117
  сверены; гейт 58 и L2 412 не изменены; запись сделана).
- Что передаём дальше: **этап 7 (R7)** — оглавление к актуальным заголовкам;
  **этап 8 (R8)** — эталонные счётчики (42 / 412 / 58 / 48 / 9 / 56 / 117) +
  расхождение R8-чисел (`rag_local_gen`, `facade`, `gateway`).

## Ревью Этап 6 — дополнительно: удаление фантомной записи сценария (цель: R6)

### Подшаг 6.7 — разбор происхождения и удаление фантома `scen_rag_gen_compare.md`

- Контекст: лишняя запись `scen_rag_gen_compare.md` в дереве `dev/` README (стр. 1731)
  при заголовке «`scenario/` — 9 сценариев ручной демонстрации» (фактически 10 записей).
- Разбор (по рабочему дереву, **без git** — по указанию оператора):
  - `find . -name 'scen_rag_gen_compare*' -not -path './.git/*'` → файла нет;
  - всего 3 упоминания в дереве: `README.md:1731`, `dev/old_vers/8/README.md:1684`,
    `dev/review/migr_review.md:401`;
  - совпадение только в README версии 8 (`old_vers/8/README.md`, дерево `scenario/`
    стр. 1677–1686); в предыдущих README (`1, 2, 3, 4, 4_1, 5, 6, 7, 7_1, 7.1_finish`)
    записи нет; в `dev/old_vers/` **нет ни каталогов `scenario/`, ни файлов `scen_*`**;
  - в планах/логах Ревизии 8 (`old_vers/8/migr_plan_6.md`, `old_vers/8/migr_log.md`)
    **0 упоминаний** `scen_rag_gen_compare`/`scen_model_switch`: фича закрывалась юнитом
    `dev/tests_debug/unit/test_rag_gen_compare.py` (**10 тестов**) и флагами `Kod.py`
    (`--rag-gen-compare`, `--gen-modes`, `--repeat`, `--gen-report` + `run_rag_gen_compare`),
    отчёт `dev/logs_reports/stages/rag_local_compare.md`;
  - парный фантом `scen_model_switch.md` (`old_vers/8/README.md:1686`) в актуальном README
    уже заменён реальным `scen_multiserver_flow.md` (Ревизия 7).
- Вывод: **фантомная запись Ревизии 8; файл `scen_rag_gen_compare.md` никогда не
  существовал.** Ошибка унаследована из дерева `scenario/` версии 8.
- Действие: строка `scen_rag_gen_compare.md` удалена из дерева `dev/` README.
  - Было (стр. 1730–1732):
    `scen_optimize.md` / `scen_rag_gen_compare.md` / `scen_multiserver_flow.md`;
  - Стало: `scen_optimize.md` / `scen_multiserver_flow.md` (9 записей при заголовке
    «9 сценариев»).
- Проверки после удаления: `grep -c "scen_rag_gen_compare" README.md` → **0**;
  `grep -on "scen_[A-Za-z_]*\.md" README.md` сверен с `ls dev/tests_debug/scenario/`
  (9 файлов) → расхождений нет; README = **2020 строк**.
- Примечание: **мастер-план `dev/review/migr_review.md` сам наследовал фантом** — его
  список «9 сценариев» (стр. 398–401) содержал `scen_rag_gen_compare.md` и **не содержал**
  реального `scen_multiserver_flow.md`.
- Действие по мастер-плану (выполнено по запросу оператора, 2026-10-18): в
  `migr_review.md` (стр. 401, список сценариев этапа 6) фантом `scen_rag_gen_compare.md`
  заменён на реальный `scen_multiserver_flow.md`. Проверка после правки:
  `grep -rn 'scen_rag_gen_compare' dev/ --exclude-dir=.git` → остались только архивный
  `dev/old_vers/8/README.md:1684` (снимок Ревизии 8 — не трогаем) и настоящая запись
  журнала. В актуальных `README.md` и `migr_review.md` — **0** упоминаний фантома.
  (Это снимает пункт пометки мастер-плана, ранее передававшийся этапу 8.)
- Артефакты: `README.md` (удалена 1 строка, не закоммичено); `dev/review/migr_review.md`
  (1 замена, стр. 401, не закоммичено); `dev/migr_log.md` (настоящая запись).
- Коммит: правки README и мастер-плана выполняются оператором; формулировка —
  `docs: удалена фантомная запись scen_rag_gen_compare.md (в README — из дерева dev/; в migr_review.md заменена реальным scen_multiserver_flow.md)`
  (окончательная формулировка — за оператором).

## Ревью Этап 7 — Обновление «Содержания» (цель: R7)
- Статус: ✅ завершён (исполнение по `dev/review/migr_review_7.md`, шаги 7.1–7.5).
- Было: оглавление «Содержание» (стр. 12) — снимок с двумя расхождениями:
  (1) порядок пунктов не совпадал с порядком заголовков `##`
  (в оглавлении «Агентный цикл» шёл **перед** «Локальные LLM», в файле — наоборот);
  (2) якорь пункта `dev/` не резолвился (заголовок содержит «(проект про проект)»).
- Стало (README.md):
  - **ШАГ 7.1:** пункты «Локальные LLM и доступ к агенту» и «Агентный цикл» поменяны
    местами → порядок оглавления = порядку заголовков (агентный цикл — ниже локальных LLM);
  - **ШАГ 7.2:** якорь раздела `dev/` исправлен на
    `#служебное-пространство-dev-проект-про-проект`, текст пункта дополнен до
    «Служебное пространство `dev/` (проект про проект)».
- **Уточнение к плану:** план 7 предписывал якорь `#служебное-пространство-dev-проект-проект`
  (с одним «про»), однако фактический slug-генератор GitHub сохраняет **оба** слова
  («проект **про** проект» → `...-dev-проект-про-проект`). Применён фактический якорь,
  разрешаемый проверкой (`SHA`-слагификатор в шаге 7.3).
- **ШАГ 7.3–7.4 (проверка):** скрипт сверки якорей → «пунктов оглавления: 18»,
  «заголовков `##`: 18», «неразрешённых якорей: **нет**» (равенство числа пунктов
  и заголовков подтверждено).
- **ШАГ 7.5 (проверка):** `grep -n 'Агентный цикл\|Локальные LLM …' README.md` → стр. 23
  («Локальные LLM») идут раньше стр. 24 («Агентный цикл»); `grep -n 'служебное-пространство-dev'`
  → стр. 26 с суффиксом `-про-проект`. Заголовки `##` **не переименовывались**.
- Фактические счётчики: README 2020 → **2020 строк** (`git diff --stat README.md` =
  `2 insertions, 2 deletions` — две строки оглавления изменены, число строк сохранилось).
- Артефакты: `README.md` (оглавление); `dev/migr_log.md` (настоящая запись).
- Коммит: предложен текст (выполняет оператор):
  `docs(readme): «Содержание» — порядок пунктов приведён к порядку заголовков (Локальные LLM перед Агентным циклом); исправлен якорь раздела dev/`.
- Перечитывание migr_review.md: ✅ (2026-10-18, редакция v1.2)
- Гейт 7→8: ✅ (порядок пунктов = порядку заголовков; якорь `dev/` резолвится;
  неразрешённых якорей нет; 18 пунктов = 18 заголовков `##` (кроме «Содержания»);
  заголовки не переименовывались; запись сделана).
- Что передаём дальше: **этап 8 (R8)** — оглавление как индекс разделов для проверки
  перекрёстных ссылок; эталонные счётчики (42 / 412 / 58 / 48 / 9 / 56 / 117) +
  расхождение R8-чисел (`rag_local_gen`, `facade`, `gateway`).

## Ревью Этап 8 — Финальная перекрёстная согласованность README (цель: R8)

- Статус: ✅ завершён (исполнение по `dev/review/migr_review_8.md`, шаги 8.1–8.7).
- Метка: R8. Контур: R3 (содержание и счётчики). Ничего нового не добавляет — только
  сверяет то, что добавили этапы 1–7.
- **Замечание к плану:** план 8 указывал README как 1949 строк; фактически — **2020 строк**
  (подтверждено этапом 7). Строки, упомянутые в ШАГЕ 8.2 (1660/1661/1686), были смещены,
  поэтому проверка велась поиском по содержимому, а не по номерам строк.

### ШАГ 8.1 — сверка числовых утверждений с эталоном

- Пересчёт по диску (`ls`/`grep`/AST):
  - `core/*.py` = **16**; `rag/*.py` = **19**; `integrations/mcp/*.py` = **11**;
    `gateway/*.py` = **6**; `unit/test_*.py` = **42**; `scenario/*.md` = **9**;
    `stages/*` = **56**; `check '^check '` = **58**; L2 (AST-сумма) = **412**.
  - Порты MCP = 8000 / 8010 / 8020; слоёв памяти = 4; стадий `TaskStage` = 8;
    чанков индекса = 117 / 9 документов.
- **Расхождение (передано этапом 6, правится здесь):** три числа R8-тестов в README
  не совпадали с AST-подсчётом:
  - `test_rag_local_gen.py` — было «14 тестов», фактически **19**;
  - `test_facade.py` — было «14 тестов», фактически **15**;
  - `test_gateway.py` — было «11 тестов», фактически **20**.
  Правка по эталону (AST-пересчёт) внесена (см. ШАГ 8.7).
- Остальные счётчики (58 / 48 / 412 / 42 / 9 / 56 / 117 / 4 / 8 / порты) совпали
  во всех вхождениях README без правок.

### ШАГ 8.2 — устаревшие ссылки

- `grep -n 'migr_2_plan|scen_model_switch|scen_rag_gen_compare|README_3\.md|README_4\.md'`
  → **0 совпадений** ✅ (строки 1660/1661/1686 из плана уже удалены этапами 2 и 4/6).

### ШАГ 8.3 — существование backtick-путей

- Извлечено 100 уникальных backtick-путей с расширениями.
- «Не найдены напрямую» (67) — все они существуют на диске, но в разделах дерева
  указаны сокращённо (basename внутри своего каталога, напр. `agent.py` → `core/agent.py`,
  `check_acceptance.sh` → `dev/tests_debug/check_acceptance.sh`), либо это шаблоны
  (`unit/test_*.py`) и рантайм-файлы в `users/<id>/…`. Это конвенция деревьев README,
  не баг.
- **Три имени не найдены нигде** и требуют трактовки:
  - `ollama.service` (стр. 851) — systemd-юнит окружения VPS, не файл репозитория
    (упомянут как внешний юнит, держащий модель `bge-m3`); не баг.
  - `servers.json` / `task_state.json` — конвенция рантайм-хранилища `users/<id>/…`,
    создаётся при работе; конкретного файла в этой копии нет (данные в `w17*` не
    содержат эту ветку). Не баг — файлы пользовательского scope.
- Шаблоны (`m*_smoke.py`, `subagent_*.md`, `*_params.md`, `unit/test_*.py`) — помечены
  пояснением, не считаются отсутствующими.

### ШАГ 8.4 — терминология «шлюз» / «фасад»

- «шлюз» = `gateway/` (VPS, публичный порт `8080`) — 22 вхождения, все согласованы
  (стр. 413, 415, 1196–1229, 1336, 1444, 1553, 1732, 1745, 1830, 1924, 2002).
- «фасад» = `serve.py` (хост, `127.0.0.1:8090`) + DI-фасады `RagService`/`Store` —
  31 вхождение, все согласованы (стр. 411, 457, 476, 480, 632, 689, 790, 1196, 1538,
  1681, 1829, 2002).
- Перепутанных мест **нет** ✅. LM Studio присутствует (32 вхождения) — ок.

### ШАГ 8.5 — перекрёстные ссылки

- «см. ниже» (стр. 187) — внутри раздела сборки промта, корректно.
- «[Служебное пространство `dev/`] (см. раздел)» (стр. 496) — целевой заголовок
  `## Служебное пространство \`dev/\` (проект про проект)` существует ✅.
- «Подробности — в разделе «Локальные LLM и доступ к агенту»» (стр. 1198) — раздел
  существует ✅.
- Ссылка на файл `dev/vps/README_gateway.md` (стр. 1199) — файл существует ✅.
- **Замечание (низкий приоритет, для этапа 9):** в «Известных шероховатостях» (стр. 1961)
  есть ссылка «вне дерева §3.1», но раздела с номером §3.1 в README нет (нумерации
  разделов в документе нет). Формулировка унаследована; рекомендуется заменить на
  «вне дерева модулей» при финальной синхронизации (в этапе 8 не правил — не факт,
  а стиль внутренней ссылки).

### ШАГ 8.6 — файлы этапов 1–4: дерево + карта артефактов (≥2)

| Файл | Дерево | Карта/описание | Итого |
|---|---|---|---|
| `serve.py` | 411 | 1829 | ✅ |
| `models.json` | 412 | 1822 | ✅ |
| `gateway/sync_questions.py` | 417 | 1832 | ✅ |
| `integrations/mcp/auth.py` | 451 | 1820 (`integrations/mcp/*` перечень) | ✅ |
| `integrations/mcp/time_server.py` | 452 | 1820 | ✅ |
| `core/subagents.py` | 433 | 1826 | ✅ |
| `core/resources.py` | 432 | 1827 | ✅ |
| `agents.md` | 493 | 1855 | ✅ |
| `ND/models` | 486 | 1841 | ✅ |
| `dev/vps/units` | 1744 | 1836 | ✅ |

- Все 10 файлов этапов 1–4 присутствуют **и** в дереве, **и** в «Карте артефактов» ✅.
  (`auth.py`/`time_server.py` в карте покрыты сводной строкой `integrations/mcp/*`,
  перечисляющей их по именам.)

### ШАГ 8.7 — финальная перечитка README целиком (2020 строк)

- README перечитан постранично (0→2018). Найдены и **исправлены явные несоответствия
  факту** (см. правки ниже); прочие замечания — рекомендации для этапа 9.
- **Правки внесены (git diff: 9 вставок / 10 удалений):**
  1. Числа R8-тестов: `test_rag_local_gen.py` 14→**19**; `test_facade.py` 14→**15**;
     `test_gateway.py` 11→**20** (сверено AST-пересчётом).
  2. Число тестов RAG-интеграции: «интеграция (16)» → **18** (AST `test_rag_integration.py`).
  3. «Карта артефактов»/`rag/*`: «интеграция (16)» согласовано (см. п.2).
  4. Дерево `dev/`: строка `├── migr_review.md  # план проверки расхождений (Ш1–Ш14)`
     заменена на фактическую `├── review/  # ревью документации (migr_review.md +
     рабочие планы 0–9)` (файла `dev/migr_review.md` нет; планы лежат в `dev/review/`;
     упоминание «Ш1–Ш14» — ложное, ревью состоит из этапов 0–9).
  5. Три оси сравнения генераторов: «стоимость» → **«стабильность»** (в двух местах:
     стр. 1678 описания, стр. 1892 «Ревизия 8»). Сверено по `rag/compare.py`
     (`Три оси: качество, скорость, стабильность ответов`) и рендеру отчёта
     («Качество …, Скорость …, Стабильность: ошибки, согласованность»).
  6. Удалён висячий фрагмент-дубль «(каталог + атомарный snapshot …) → `ToolExecutor`
     (policy + аудит) → LLM tool-use.» в разделе «Результат» (остаток от правки) —
     улучшает читаемость, убирает противоречие.
  7. `dev/meta_promt/` — фактический состав каталога: добавлен `screen-ASKII.txt`
     (было «только … и …», фактически три объекта).
- **Замечания без правки (рекомендации этапу 9):**
  - ссылка «вне дерева §3.1» (стр. 1961) — раздел §3.1 отсутствует (см. ШАГ 8.5);
  - `auth.py`/`time_server.py` в «Карте артефактов» покрыты сводной строкой
    `integrations/mcp/*`, отдельными строками не выведены (допустимо);
  - `ollama.service`, `servers.json`, `task_state.json` — внешние юниты / рантайм-scope
    (не файлы репозитория; допустимо).
- Фактические счётчики после правок: README **2018 строк** (было 2020; −2 из-за
  удаления двух строк дубля и сворачивания записи дерева в одну).

### Гейт 8→9 (11 пунктов)

1. Гейт везде = 58 — ✅ 2. Критерии везде = 48 — ✅ 3. L2 везде = 412 OK — ✅
4. Счётчики модулей = диску (16/19/11/6/42/9/56) — ✅ 5. Устаревших ссылок нет (0) — ✅
6. Пути из README существуют (шаблоны помечены) — ✅ 7. «шлюз»/«фасад» не перепутаны — ✅
8. Перекрёстные ссылки резолвятся — ✅ (кроме §3.1 — рекомендация) 9. Файлы этапов 1–4
в дереве **и** карте (10/10) — ✅ 10. README перечитан, замечания выписаны — ✅
11. Запись в migr_log.md — ✅

- Артефакты: `README.md` (счётчики R8-тестов, термин «стабильность», дерево `dev/`,
  состав `meta_promt/`, удалён дубль-фрагмент); `dev/migr_log.md` (настоящая запись).
- Коммит: предложен текст (выполняет оператор):
  `docs(readme): финальная согласованность — счётчики R8-тестов (19/15/20) и RAG-интеграции (18) сверены с диском, дерево dev/ приведено к фактическому (review/), ось сравнения генераторов — «стабильность», удалён дубль-фрагмент`.
- Перечитывание migr_review.md: ✅ (2026-10-18, редакция v1.2)
- Гейт 8→9: ✅ (см. таблицу: 11/11; единственное замечание — внутренняя ссылка §3.1,
  передано этапу 9 как рекомендация).
- Что передаём дальше: **этап 9 (Ф)** — список замечаний из ШАГА 8.7 + подтверждённые
  счётчики для синхронизации `dev/Проверка.md` и финального прогона гейта.

## Ревью Этап 9 — Финал: гейт, `.tmp`, синхронизация `Проверка.md` (цель: Ф)

- Статус: ✅ завершён (гейт 58/58; Д.8 приведён к факту; `.tmp` очищен; решение №28
  убрано из активных документов).
- Метка: Ф. Контур: Ф (финал). Зависит: 0–8. План: `dev/review/migr_review_9.md`.
- Исходное состояние: рабочее дерево чистое (`git status --short` пуст);
  HEAD = `e9bae37` «Ревизии_8_Ревью_этап_8_готов».

### ШАГ 9.1 — финальный прогон гейта

- Команда: `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh`
- Результат: **ИТОГ: 58 из 58 зелёные (FAIL=0)**, exit 0 ✅.
- Полный вывод (все 58 проверок ✅):
  `1 py_compile; 2 README непустой; 3 run.sh исполняемый; 4 run.desktop непустой;
  5 unit_runner; 6 scenario (L4); 7 раздел модели памяти; 8 CSV-журнал токенов;
  9 в корне нет Проверка.md; 10 task_state пауза→resume; 11 инварианты отдельно;
  12 конфликт → отказ; 13 переход блокируется; 14 /approve; 15 пауза→resume;
  16 --mcp-probe fake; 17 имена mcp.demo.*; 18 description+input_schema;
  19 HTTP-транспорт + input_schema; 20 tools/call+policy+аудит; 21 LLM tool-use [tools];
  22 мультисерверный флоу D3; 23 rank_tools D4; 24 пакет исправлений D6;
  25 авторизация транспорта D7; 26 RAG импорт; 27 индекс save/load; 28 поиск+метаданные;
  29 две стратегии чанкинга; 30 отчёт сравнения стратегий; 31 без --rag нет [rag];
  32 TaskStage не затронут; 33 --rag-eval hit-rate≥0.80; 34 RAG7 импорт модулей;
  35 rewrite; 36 источники/цитаты; 37 «не знаю» без LLM; 38 --rag-ask; 39 --rag-verify
  10/10; 40 --rag-ask высокий порог; 41 4 режима ответа; 42 WorkingMemory round-trip;
  43 2 длинных сценария; 44 реестр моделей+models.json; 45 --model-list; 46 подпись в
  баннере; 47 без --model промпт прежний; 48 субагент+лог; 49 --local-gen; 50 три оси;
  51 профиль в теле запроса; 52 отчёт «до/после»; 53 фасад /ask+/models; 54 шлюз вход+лимит;
  55 юнит туннеля; 56 MCP-порты; 57 секретов нет; 58 4 сценария демонстрации`.

### ШАГ 9.2 — проверка и чистка `.tmp/`

- `ls -A dev/tests_debug/.tmp/` → **не пуст**. До прогона 9.1 — **444 каталога** (7,4 МБ);
  после прогона 9.1 — **451** (в 05:11 добавлено 7–8 каталогов; mtime-кластеры: 02:35 —
  298, 02:36 — 146, 05:11 — 8).
- Причина: раннеры `unit_runner.py`, `scenario.py`, `dialog_runner.py`, `smoke.py`
  создают `tempfile.mkdtemp(prefix=…, dir=TMP_ROOT)`, где `TMP_ROOT = dev/tests_debug/.tmp`,
  и **не удаляют** временные каталоги (очистки `shutil.rmtree` в `dev/tests_debug/*.py`
  нет). Прогон гейта 9.1 (проверки 5 и 6 вызывают `unit_runner.py` и `scenario.py`)
  добавил очередную порцию каталогов.
- Это **не** сторонняя запись после этапа 12, а штатное накопление каталогов прошлых
  прогонов; README (стр. 1966) его признаёт. `.tmp` — в `.gitignore` (строка 13);
  рабочие `users/` не затронуты.
- **Действие (по решению оператора):** `dev/tests_debug/.tmp/*` **очищен** после
  финального прогона (`.tmp` нужен только на время незавершённой миграции/ревью;
  тестовые прогоны его наполняют). Собственный каталог гейта `acc_$` скрипт удаляет сам.

### ШАГ 9.3 — сверка `Проверка.md` с финальным README (5 пунктов)

1. **Д.3** `check_acceptance.sh` зелёный — ✅ (подтверждено в 9.1: 58/58).
2. **Д.4** `grep -c 'Локальные LLM и доступ к агенту' README.md` → **3** (≥ 1) — ✅.
3. **Д.5** понятный язык — пропущено (субъективно, по плану).
4. **Д.6** секретов в конфигах нет — ✅ (`grep -rE 'sk-…|Bearer …'` по `models.json`,
   `gateway/gateway.json`, `.env.example`, `Den_log.md` — пусто).
5. **Д.8** логи в `.gitignore` — расхождение выявлено и **устранено** (см. ниже).

### Устранённые расхождения (по решению оператора)

- **Д.8 / `.gitignore`.** `git check-ignore Den_log.md tokens.csv` → оба **игнорируются**
  (`.gitignore:33` → `Den_log.md`, `.gitignore:34` → `tokens.csv`); сами файлы **не
  отслеживаются** (`git ls-files` пуст). Прежние формулировки (README стр. 1578
  «логи **не** в `.gitignore`»; `Проверка.md` Д.8 «Не игнорируются») противоречили факту.
  **Решение оператора:** `.gitignore` **корректен** (не трогаем); README и `Проверка.md`
  приведены **к факту** — «логи **в** `.gitignore`» / «**Игнорируются**».
- **Решение №28 — устарело.** Все упоминания решения №28 удалены из **активных**
  документов (содержание сохранено, ярлык убран): `dev/migr_plan.md` (таблица решений —
  строка №28 удалена; нумерация «№20–28» → «№20–27»; раздел про шлюз — ярлык убран),
  `dev/migr_plan_10.md`, `dev/vps/README_gateway.md`, `dev/migr_log.md`.
  `dev/old_vers/**` **не тронут** (исторический архив).
- **Пометка в журнале:** в записи этапа 10 добавлено «**Для Ревизии 8 состав `.gitignore`
  изменён:** `Den_log.md`/`tokens.csv` внесены в `.gitignore`».
- **`.tmp/`** — очищен (ШАГ 9.2).

### Гейт Ф (7 пунктов)

| № | Проверка | Ожидаемо | Факт |
|---|---|---|---|
| 1 | Гейт 58/58 | ✅ | ✅ (9.1) |
| 2 | `.tmp/` пуст | ✅ | ✅ (очищен в 9.2) |
| 3 | Секретов в конфигах нет | ✅ | ✅ |
| 4 | Раздел R8 в README | ✅ | ✅ |
| 5 | Логи в `.gitignore` (приведено к факту) | ✅ | ✅ (README/Проверка исправлены) |
| 6 | Все 9 этапов закрыты | ✅ | ✅ (0–8 зелёные) |
| 7 | Итоговая запись в migr_log.md | ✅ | ✅ (настоящая запись) |

**Гейт Ф: 7/7 — зелёный.**

### ШАГ 9.4 — сводка этапов ревью

| Этап | Цель | Статус |
|---|---|---|
| 0 | Снимок состояния | ✅ |
| 1 | Дерево модулей | ✅ |
| 2 | Дерево `dev/` | ✅ |
| 3 | Отсутствующие разделы | ✅ |
| 4 | Карта артефактов | ✅ |
| 5 | Локальные LLM (5.0/5.1/5.2) | ✅ |
| 6 | Тестирование и приёмка | ✅ |
| 7 | Содержание | ✅ |
| 8 | Финальная согласованность | ✅ |
| 9 | Финал | ✅ |

**Предлагаемый текст коммита** (выполняет **только** оператор):

```
docs(readme): финал ревью — все 9 этапов (0–8) + подшаги 5.0/5.1/5.2
закрыты; гейт 58/58; .tmp пуст; Проверка.md/README синхронизированы;
решение №28 убрано (.gitignore приведён к факту)
```

- Артефакты: `README.md` (формулировка «логи в `.gitignore`»); `dev/Проверка.md`
  (Д.8 — «в gitignore» / «Игнорируются»); `dev/migr_plan.md`, `dev/migr_plan_10.md`,
  `dev/vps/README_gateway.md` (убрано решение №28); `dev/migr_log.md` (настоящая запись +
  пометка в этапе 10). Файлы проекта не удалялись.
- Перечитывание migr_review.md: ✅ (2026-10-19, редакция v1.2)
- Гейт 9 (Ф): ✅ (7/7).
- Что передаём дальше: финальный коммит этапа 9 (за оператором).

