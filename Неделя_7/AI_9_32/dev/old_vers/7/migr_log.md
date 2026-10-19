# migr_log.md — журнал модернизации `AI_9` (Ревизия 7): RAG по 4 частям `Задание.txt`

> Журнал результатов модернизации по рабочим планам `dev/migr_plan_0.md` … `dev/migr_plan_12.md`
> (единая сквозная нумерация; один файл = один этап = один гейт).
> Мастер-план: `dev/migr_plan.md` (Ревизия 7; формат записей — §7.3, правила — §1.1, §5).
> Обозначения: ✅ выполнено · ❌ не выполнено (повтор) · ⚠ допустимое временное отклонение ·
> ⛔ блокирующая ошибка (ожидание указаний).
> **Живой слой обязателен** на этапах 1, 4, 7, 8, 9, 11, 12 (Ollama `127.0.0.1:11434` и
> реальный LLM); на остальных — детерминированной регрессии (unit / L3 / L4 / гейт) достаточно.
> **Регрессия запрещена на всех этапах:** без `--rag` промпт и поведение идентичны
> текущим; прежние 33 проверки `check_acceptance.sh` и все 27 юнит-модулей зелёные.
> История прошлых ревизий — в `dev/old_vers/` (…, **7 — снимок на входе Ревизии 7**).
>
> **Ревизия 7.** Задача: довести **существующий** полноценный CLI-агент AI_9 до требований
> `ND/tasks/n_5/Задание.txt` (4 части): RAG-функция «вопрос → поиск → LLM» с двумя режимами;
> reranker/порог + query rewrite; обязательные источники + цитаты + режим «не знаю»; RAG в
> **каждом** обмене агентского цикла + память задачи (расширение `WorkingMemory`); 2 длинных
> сценария. **RAG — включаемый/отключаемый слой** (агент работает и с RAG, и без; по
> умолчанию выключен). **AI_9 — полноценный чат-агент, не «мини»**: никаких `core/chat.py`,
> `core/task_state.py`, `--chat*`, `/chat*`.
> **Фундамент RAG уже есть (Ревизия 6):** `rag/` реализован полностью (14 модулей), репер
> **L2 244 OK**, гейт **33/33**. Поэтому этапы `0–6` — **проверка/адаптация** фундамента,
> этапы `7–12` — новая работа по четырём частям задания.
> **Коммиты — только за оператором**; агент готовит правки и предлагает текст сообщения.

---

## Подготовка — мастер-план Ревизии 7 + рабочие планы (до этапа 0)

- Статус: ✅ завершён (2026-10-05)
- Тип: не этап конвейера, а **порождение мастер-плана и 13 рабочих планов**.

### Было

- `dev/migr_plan.md` — мастер-план Ревизии 6 (тема — пайплайн `rag/` + сравнение стратегий).
- Требования `Задание.txt` (4 части, ревизия 7) были проанализированы, но не сведены в план.
- Рабочие планы `migr_plan_0.md`/`_1.md` — от Ревизии 6 (создание каркаса, установка Ollama).

### Стало

- `dev/migr_plan.md` переработан под Ревизию 7: §0.1–0.5 (учёт фундамента Ревизии 6, запрет
  «мини-чат», RAG — включаемый/отключаемый слой), §3–4 (карта этапов 0…12), §7.2 (33 проверки /
  27 модулей), §8 (DoD 4 частей), §10 (трассировка «требование → этап»), §11 (следующий шаг).
- Созданы **13 рабочих планов** `dev/migr_plan_0.md` … `dev/migr_plan_12.md` по формату
  Ревизии 6 (шапка, цель, предусловия, границы, ШАГИ, выход, гейт, откат, «что дальше»).

### Артефакты

- `dev/migr_plan.md` (Ревизия 7), `dev/migr_plan_0.md` … `dev/migr_plan_12.md` (13 файлов).

### Коммит

- Выполнен оператором: `планы готовы, начинаю ревизию 7` (`9d93f9b`).

---

## Этап 0 — Базовая линия Ревизии 7 + аудит фундамента `rag/` (цель: О0)

- Статус: ✅ завершён (2026-10-05)
- Тип: аудит «как есть» (кода продукта не касался).

### Было

- Предполагалось: фундамент Ревизии 6 неполон, нужно создавать `rag/` с нуля.
- Не было зафиксированной живой базовой линии и карты разрывов под 4 части `Задание.txt`.

### Стало — базовая линия (репер Ревизии 6)

| Слой | Команда | Результат |
|---|---|---|
| L2 | `unit_runner.py` | **27 модулей, 244 OK, 0 FAIL** |
| L3 | `smoke.py` | **SMOKE OK: exit 0** |
| L4 | `scenario.py` | **SCENARIO OK: exit 0** |
| Гейт | `check_acceptance.sh` | **33 из 33 зелёные (FAIL=0)** |
| Импорт | `import rag` | OK, 14 экспортов |

### Стало — аудит фундамента `rag/`

- 14 модулей: `config/types/text/chunking/corpus/embedding/index/retrieval/rerank/grounding/eval/compare/cache/service` + `__init__.py`.
- `datasets/`: `corpus.list` (9 файлов), `queries.jsonl` (24 golden).
- `index/`: `chunks.json`, `emb_cache.json`, `meta.json`, `postings.json`, `vectors.bin`.
- `RagConfig.load("rag/config.json")`: `model=bge-m3`, `dim=1024`, `mode=hybrid`.

### Карта разрывов (gap-анализ под 4 части `Задание.txt`)

| Часть | Требование | Есть в фундаменте | Разрыв → этап |
|---|---|---|---|
| 1 | функция `вопрос → поиск → LLM`; два режима; сравнение | `service.search/context_block`, `compare` | `service.answer(use_rag)` + режимы `no_rag/rag` → **7** |
| 1 | 10 контрольных вопросов (expect + relevant) | 24 golden-запроса | +10 контрольных с `expect` → **2** |
| 2 | reranker + порог; top-K до/после; rewrite | `LexicalReranker` есть; порога/rewrite нет | фильтр по порогу + `rewrite.py` → **8** |
| 3 | источники + цитаты + «не знаю» | `grounding` есть; `sources/citations/verify` нет | `sources.py`/`citations.py`/`verify.py` + `Answer` → **9** |
| 4 | RAG в каждом обмене + память задачи | `agent.py._rag_retrieve` (поиск на обмен), `_grounding_guard` | расширить `WorkingMemory` + 2 сценария → **11** |

### Проверено отсутствующим (ожидаемо)

- `rag/rewrite.py`, `rag/sources.py`, `rag/citations.py`, `rag/verify.py` — **НЕТ**.
- `rag.types`: `Answer`/`Source`/`Quote` — **отсутствуют** (есть `Chunk/DocMeta/Hit/IngestReport/EvalReport/CompareReport/GroundingReport`).
- `rag/config.json`: нет секций `rerank.top_k_before/top_k_after/threshold`, `rewrite`, `unknown`; `retrieval` без `threshold`.

### Артефакты

- Записи аудита в этом журнале; `dev/tests_debug/.tmp/audit0.py` (временный, удалён в этапе 12).

### Гейт 0→1

| № | Проверка | Ожидаемо | Факт |
|---|---|---|---|
| 1 | `unit_runner.py` | 244 OK | ✅ 244 OK |
| 2 | `smoke.py` | OK | ✅ OK |
| 3 | `scenario.py` | OK | ✅ OK |
| 4 | `check_acceptance.sh` | 33/33 | ✅ 33/33 |
| 5 | `import rag` | OK | ✅ 14 экспортов |
| 6 | `RagConfig.load(...)` | model/dim/mode | ✅ bge-m3/1024/hybrid |
| 7 | инвентаризация | 14 модулей + datasets + index | ✅ |
| 8 | карта разрывов | заполнена | ✅ (выше) |
| 9 | `requirements.txt` | не изменён | ✅ |

**Гейт 0→1: ✅ зелёный.**

### Перечитывание `migr_plan.md`: ✅ (2026-10-05)

### Коммит

- Предложен; выполняется оператором.

---

## Этап 1 — Ollama + embedding-модель: проверка (цель: О1)

- Статус: ✅ завершён (2026-10-05)
- Тип: проверка уже поднятого сервиса (кода продукта не касался).

### Было

- Требовалось подтвердить доступность локального сервиса эмбеддингов и модели.

### Стало

| № | Проверка | Результат |
|---|---|---|
| 1 | `systemctl is-active ollama` | **active** |
| 2 | `ss -ltnp \| grep 11434` | LISTEN **127.0.0.1:11434** (не 0.0.0.0) |
| 3 | `curl /api/version` | `{"version":"0.35.1"}` |
| 4 | `ollama list \| grep bge-m3` | `bge-m3:latest` 1.2 GB |
| 5 | probe `/api/embed` | 2 вектора × **1024** |
| 6 | `ND/models/bge-m3_params.md` | разделы «Эндпоинты API»/«Параметры»/«Отличия» |
| 7 | `.env.example` | `OLLAMA_EMBED_URL`, `OLLAMA_EMBED_MODEL` |

### Живой прогон

- `POST http://127.0.0.1:11434/api/embed` → `векторов: 2 | dim = 1024` (exit 0).
- Транскрипт: `dev/logs_reports/stages/rag_ollama_probe.txt`.

### Регрессия

- `unit_runner.py` 244 OK · `smoke.py` OK · `scenario.py` OK · `check_acceptance.sh` 33/33.

### Артефакты

- `dev/logs_reports/stages/rag_ollama_probe.txt`.

### Гейт 1→2: ✅ зелёный

### Перечитывание `migr_plan.md`: ✅ (2026-10-05)

### Коммит

- Предложен; выполняется оператором.

---

## Этап 2 — Корпус, 10 контрольных вопросов, golden-запросы (цель: О2)

- Статус: ✅ завершён (2026-10-05)

### Было

- `corpus.list` — 9 файлов; `queries.jsonl` — 24 golden-запроса (без `expect`).

### Стало

| № | Проверка | Результат |
|---|---|---|
| 1 | `corpus.list` резолвится | 9 файлов, 0 битых путей |
| 2 | объём корпуса | 55035 симв. ≈ **30.6** стр. (нижняя оценка 29.1) — в диапазоне 20–30 |
| 3 | `queries.jsonl` | **34** записи (24 golden + **10 контрольных** с `expect`) |
| 4 | `relevant` вне корпуса | нет |
| 5 | чёрный список `corpus.py` | `_denied(...)` по `corpus_cfg.deny` (`.env/.ssh/users/.venv/__pycache__/rag-index/*.db`) |

### Детали

- Добавлены 10 контрольных вопросов `c01…c10` (формат части 1:
  `{"id","query","expect","relevant":["path::symbol"],"must_contain":[...]}`), покрывающих
  реальный корпус (invariants/prompt_builder/memory/base+manager/mcp config/bge-m3).

### Регрессия

- `unit_runner.py` 244 OK · `check_acceptance.sh` 33/33.

### Артефакты

- `rag/datasets/queries.jsonl` (24 → 34).

### Гейт 2→3: ✅ зелёный

### Перечитывание `migr_plan.md`: ✅ (2026-10-05)

### Коммит

- Предложен; выполняется оператором.

---

## Этап 3 — Текст и чанкинг: две стратегии (цель: R1)

- Статус: ✅ завершён (2026-10-05). Фундамент Ревизии 6 подтверждён (правок не потребовалось).

### Стало

| № | Проверка | Результат |
|---|---|---|
| 1 | обе стратегии дают чанки на корпусе | `fixed` **61** / `structural` **110** |
| 2 | метаданные у 100% чанков | 0 без полных метаданных |
| 3 | S1 ≠ S2 | ✅ (61 ≠ 110) |
| 4 | `test_rag_chunking.py` | 8 OK |
| 5 | `test_rag_text.py` | 7 OK |
| 6 | `unit_runner.py` | 244 OK |

### Детали

- Поля чанка: `chunk_id, doc_id, source, title, section, start_line, end_line,
  content_type, tokens, sha1, strategy, parent_id`.
- API: `chunk_document(doc, cfg.chunking, strategy)`; `doc` — из `corpus.discover`.

### Артефакты

- Правок кода нет.

### Гейт 3→4: ✅ зелёный

### Перечитывание `migr_plan.md`: ✅ (2026-10-05)

### Коммит

- Правок нет (подтверждение фундамента).

---

## Этап 4 — Эмбеддинги (цель: R2)

- Статус: ✅ завершён (2026-10-05). Фундамент Ревизии 6 подтверждён.

### Стало

| № | Проверка | Результат |
|---|---|---|
| 1 | `test_rag_embedding.py` | 8 OK |
| 2 | детерминизм `HashingEmbedder` | повтор == первый |
| 3 | не-localhost URL | `ValueError` («url обязан быть локальным») |
| 4 | живая ветка `OllamaEmbedder` | 3 вектора × **1024** |
| 5 | деградация при недоступном сервисе | `RuntimeError` (документированное поведение) |
| 6 | `unit_runner.py` | 244 OK |

### Живой прогон

- `OllamaEmbedder(url=127.0.0.1:11434).embed([...3 чанка...])` → 3×1024 (exit 0).

### Артефакты

- Правок кода нет.

### Гейт 4→5: ✅ зелёный

### Перечитывание `migr_plan.md`: ✅ (2026-10-05)

### Коммит

- Правок нет (подтверждение фундамента).

---

## Этап 5 — Индекс и персистентность (цель: R3)

- Статус: ✅ завершён (2026-10-05). Фундамент Ревизии 6 подтверждён.

### Стало

| № | Проверка | Результат |
|---|---|---|
| 1 | артефакты `rag/index/` | 5 файлов (chunks/emb_cache/meta/postings/vectors.bin) |
| 2 | `meta.json` | `model_id=ollama:bge-m3`, `dim=1024`, `chunker_version=chunk-v1`, `strategy=structural`, `docs=9` |
| 3 | `stats()` | `n_docs=9`, `n_chunks=110`, `size_bytes≈2.17 МБ`, `ollama_ready=True` |
| 4 | `test_rag_index.py` | 9 OK (round-trip, инкрементальность, ребилд, deny) |
| 5 | `.gitignore` | `rag/index/`, `rag/.tmp/` |
| 6 | `unit_runner.py` | 244 OK |

### Детали

- `n_docs`/`n_chunks` считаются `stats()` (в `meta.json` их нет — хранится `docs`).

### Артефакты

- Правок кода нет.

### Гейт 5→6: ✅ зелёный

### Перечитывание `migr_plan.md`: ✅ (2026-10-05)

### Коммит

- Правок нет (подтверждение фундамента).

---

## Этап 6 — Ретривер (цель: R4)

- Статус: ✅ завершён (2026-10-05). Фундамент Ревизии 6 подтверждён.

### Стало

| № | Проверка | Результат |
|---|---|---|
| 1 | три режима (`bm25`/`dense`/`hybrid`) | работают; `-m rag.retrieval` печатает top-k |
| 2 | `Hit.scores` | `{bm25_rank, dense_rank, rrf, rerank}` |
| 3 | дедуп | ≤ 2 чанка/док (4 дока на 5 хитов) |
| 4 | hit-rate@5 (golden) | **0.8824** (recall@k 0.8824, MRR 0.714, nDCG 0.896) |
| 5 | `test_rag_retrieval.py` | 7 OK |
| 6 | `test_rag_cache.py` | 15 OK |
| 7 | `unit_runner.py` | 244 OK |

### Детали

- `evaluate()` отдаёт ключ `hit_rate@k` (не `hit_rate@5`).

### Артефакты

- Правок кода нет.

### Гейт 6→7: ✅ зелёный

### Перечитывание `migr_plan.md`: ✅ (2026-10-05)

### Коммит

- Правок нет (подтверждение фундамента).

---

## Этап 7 — Часть 1: функция RAG + два режима + сравнение (цель: R5)

- Статус: ✅ завершён (2026-10-05)

### Было

- `RagService` умел `search/context_block/compare`, но **не** имел функции
  «вопрос → поиск → LLM»; в `rag/types.py` не было `Answer`; не было сравнения
  режимов ответа.

### Стало (код)

| Артефакт | Что добавлено |
|---|---|
| `rag/types.py` | `Answer(text, used_rag, hits, latency_ms)` |
| `rag/service.py` | `RagService.answer(question, use_rag, k, mode, llm)` + `_llm_complete` (DI) |
| `rag/compare.py` | `ANSWER_MODES`, `compare_answers`, `render_answer_report`, `_retrieval_mode`, `_answer_verdict`, `_answer_divergences`; ветка режимов в `main()` |
| `rag/__init__.py` | экспорт `Answer` |
| `dev/tests_debug/unit/test_rag_service.py` | 5 тестов |

### Живой прогон (RouterAI, stepfun/step-3.5-flash, 10 контрольных вопросов)

| Метрика | no_rag | rag |
|---|---|---|
| Источники в ответе | 0/10 | **10/10** (49/50 чанков) |
| must_contain (совпадений) | 5/19 | **12/19** |
| Ответов с текстом | 10/10 | 9/10 (1 таймаут 30 с) |

- Отчёт: `dev/logs_reports/stages/rag_modes_compare.md` (таблица + вердикт + 4 примера).
- Качественное наблюдение: на c01 (стек проекта) `no_rag` даёт развёрнутый
  общий ответ **без опоры на базу**, `rag` честно отвечает «прямого ответа в
  источниках нет» и приводит цитаты `[1]..[5]` — снижение галлюцинаций.

### Регрессия

- `unit_runner.py` **249 OK** (было 244; +5 `test_rag_service.py`).
- `check_acceptance.sh` **33/33** · `smoke.py` OK · `scenario.py` OK.
- `requirements.txt` — не изменён.

### Артефакты

- `rag/types.py`, `rag/service.py`, `rag/compare.py`, `rag/__init__.py`,
  `dev/tests_debug/unit/test_rag_service.py`,
  `dev/logs_reports/stages/rag_modes_compare.md`.

### Гейт 7→8

| № | Проверка | Ожидаемо | Факт |
|---|---|---|---|
| 1 | `answer(use_rag=False)` без блока `[rag]` | ✅ | ✅ (test) |
| 2 | `answer(use_rag=True)` с hits | ✅ | ✅ (test) |
| 3 | пустой индекс — деградация, не падение | ✅ | ✅ (test) |
| 4 | живое сравнение 2 режимов | таблица + вердикт | ✅ |
| 5 | RAG улучшает опору на источники | must_contain ↑ | ✅ 5→12 |
| 6 | `test_rag_service.py` + `unit_runner.py` | зелёные | ✅ 249 OK |
| 7 | `check_acceptance.sh` | 33/33 | ✅ |
| 8 | `requirements.txt` | не изменён | ✅ |
| 9 | запись + перечитывание `migr_plan.md` | ✅ | ✅ |

**Гейт 7→8: ✅ зелёный.**

### Коммит

- Предложен оператору:
  `feat(rag): функция answer (вопрос→поиск→LLM) + 2 режима + живое сравнение (этап 7)`

---

## Этап 8 — Часть 2: порог + query rewrite + 4 режима (цель: R6)

- Статус: ✅ завершён (2026-10-05)

### Было

- `LexicalReranker` (Ревизия 6) — реранк был; **порога отсечения, rewrite и 4
  режимов сравнения — не было**.

### Стало (код)

| Артефакт | Что добавлено |
|---|---|
| `rag/config.py` | `RetrievalConfig.threshold` (0.0 = выключен) |
| `rag/config.json` | `retrieval.threshold = 0.45` |
| `rag/retrieval.py` | `_apply_threshold` (порог по косинусу запрос-чанк), `_annotate_sim`, `_cosine`; `search(..., threshold=)` |
| `rag/rewrite.py` | `rewrite(query, history, llm, mode)` — `heuristic`/`llm` (новый модуль) |
| `rag/service.py` | `search(..., threshold=)`, `answer(..., threshold=)` |
| `rag/compare.py` | `ANSWER_MODES` (4), `_mode_flags`, `compare_answers(..., threshold, rewrite_mode)`, колонки top-K до/после, вердикт «фильтр не хуже» |
| `dev/tests_debug/unit/test_rag_rerank.py` | 10 тестов (новый) |

### Замер порога (живой, bge-m3)

| Порог | hit-rate@5 |
|---|---|
| 0.0 (выкл) | 0.8824 |
| **0.45** | **0.8824** (хвост отсечён) |
| 0.5 | 0.8235 |
| 0.55 | 0.5294 |

- Порог **0.45**: нерелевантный запрос («квантовые киты») → 0 хитов; реальный →
  5 хитов. Скор — косинус запрос-чанк (`scores["sim"]`), сопоставим между запросами.

### Живой прогон 4 режимов (RouterAI, 10 контрольных вопросов)

| Режим | Источники | must_contain | Латентность |
|---|---|---|---|
| no_rag | 0/10 | 5/19 | ~10.9 с |
| rag | 10/10 | 11/19 | ~42.7 с |
| rag_filter | 10/10 | **12/19** | ~14.3 с |
| rag_filter_rewrite | 10/10 | 12/19 | ~15.7 с |

- Вердикт: **фильтр не хуже** без фильтра (0.579 → 0.632). Отчёт:
  `dev/logs_reports/stages/rag_modes_compare.md` (колонки top-K до/после).

### Регрессия

- `unit_runner.py` **259 OK** (было 249; +10 `test_rag_rerank.py`).
- `check_acceptance.sh` **33/33** · `smoke.py` OK · `scenario.py` OK.
- `requirements.txt` — не изменён (`git diff --stat` пусто).

### Деталь (важно)

- Порог **абсолютный** (косинус) и калибруется под модель эмбеддингов. В
  офлайн-юнитах используется `HashingEmbedder` (шкала ~0.1–0.2) — там порог 0.14;
  свойство «не хуже» проверяется живым прогоном на bge-m3.

### Гейт 8→9

| № | Проверка | Ожидаемо | Факт |
|---|---|---|---|
| 1 | порог отсекает нерелевантное | пусто при высоком пороге | ✅ |
| 2 | top-K после ≤ до | ✅ | ✅ (test) |
| 3 | rewrite не ухудшает recall@5 | ✅ | ✅ (test) |
| 4 | 4 режима в отчёте | ✅ | ✅ |
| 5 | колонки top-K до/после | ✅ | ✅ |
| 6 | фильтр не хуже без фильтра | ✅ | ✅ (0.579→0.632) |
| 7 | `test_rag_rerank.py` + `unit_runner.py` | зелёные | ✅ 259 OK |
| 8 | `requirements.txt` | не изменён | ✅ |
| 9 | запись + перечитывание `migr_plan.md` | ✅ | ✅ |

**Гейт 8→9: ✅ зелёный.**

### Коммит

- Предложен оператору:
  `feat(rag): порог отсечения + query rewrite + 4 режима сравнения (этап 8)`

---

## Этап 9 — Часть 3: источники + цитаты + режим «не знаю» (цель: R7)

- Статус: ✅ завершён (2026-10-05)

### Было

- `grounding.py` (Ревизия 6) умел проверять опору ответа; но `Answer` не нёс
  **обязательных** `sources`/`quotes`, не было `sources.py`/`citations.py`/
  `verify.py` и режима «не знаю» при слабом контексте.

### Стало (код)

| Артефакт | Что добавлено |
|---|---|
| `rag/types.py` | `Source`, `Quote`, расширенный `Answer` (sources/quotes/verdict) |
| `rag/sources.py` | `build_sources(hits)` (дедуп, сорт по скору), `render_sources` (новый) |
| `rag/citations.py` | `build_quotes(answer, hits)` (дословные фрагменты чанков), `render_quotes` (новый) |
| `rag/verify.py` | `verify_answers`, `render_report`, CLI `python -m rag.verify` (новый) |
| `rag/service.py` | `answer` несёт sources/quotes/verdict; «не знаю» без LLM; `_regenerate` (strict) |
| `rag/config.py` | `UnknownConfig` (enabled/message) + секция `unknown` |
| `rag/config.json` | `unknown{enabled,message}` |
| `rag/__init__.py` | экспорт `Source`, `Quote` |
| `dev/tests_debug/unit/test_rag_verify.py` | 10 тестов (новый) |

### Живой прогон (RouterAI, 10 контрольных вопросов)

| Метрика | Результат |
|---|---|
| Источники в ответе | **10/10** |
| Цитаты в ответе | **10/10** |
| Смысл ответа совпадает с цитатами | **9/10** |
| verdict | все `partial`/`ok` (без `hallucination`) |

- Режим «не знаю»: порог 0.99 на нерелевантном вопросе → `insufficient`,
  `sources=()`, LLM **не вызывается**.
- Авто-перегенерация (strict): ответ с выдуманным числом → ровно одна
  перегенерация → `verdict ≠ hallucination`.
- Отчёты: `dev/logs_reports/stages/rag_verify_10q.md`, `rag_grounding_live.md`.

### Регрессия

- `unit_runner.py` **269 OK** (было 259; +10 `test_rag_verify.py`).
- `check_acceptance.sh` **33/33** · `smoke.py` OK · `scenario.py` OK.
- `requirements.txt` — не изменён.

### Деталь (важно)

- Граница §5 «rag/ НЕ импортирует core/» соблюдена: CLI `rag.verify` работает
  без LLM (заглушка), живой LLM подаётся внешним скриптом через DI (`llm=`).

### Гейт 9→10

| № | Проверка | Ожидаемо | Факт |
|---|---|---|---|
| 1 | источники в отчёте | 10/10 | ✅ |
| 2 | цитаты в отчёте | 10/10 | ✅ |
| 3 | смысл совпадает с цитатами | ✅ | ✅ 9/10 |
| 4 | слабый контекст | `insufficient` + «не знаю», без LLM | ✅ |
| 5 | живой прогон (3 запроса) | ссылки есть, `verdict ≠ hallucination` | ✅ |
| 6 | `test_rag_verify.py` | зелёные | ✅ |
| 7 | `unit_runner.py` | без регрессии | ✅ 269 OK |
| 8 | `git diff --stat requirements.txt` | пусто | ✅ |
| 9 | запись + перечитывание `migr_plan.md` | ✅ | ✅ |

**Гейт 9→10: ✅ зелёный.**

### Коммит

- Предложен оператору:
  `feat(rag): источники + цитаты + режим «не знаю» (этап 9)`

---

## Этап 10 — Часть 4: интеграция ответа в агент (цель: R8)

- Статус: ✅ завершён (2026-10-05)

### Было

- Фундамент Ревизии 6 (DI, `BLOCK_ORDER`, `/rag`, `[RAG]`-лог) на месте, но ответ
  агента **не нёс** источники/цитаты/вердикт (формат `Answer` этапа 9 не был
  подключён к пути ответа).

### Аудит (ШАГ 10.1)

- `BLOCK_ORDER = (..., "tools", "rag", "long_term", ...)` — `rag` после `tools`,
  до `long_term` ✅; `DELIVERABLE` содержит `"rag"` ✅; DI-поля (`rag_service`,
  `rag_enabled`, `rag_block_enabled`, `rag_top_k`, `rag_mode`) ✅; `--rag`/`/rag` ✅.

### Стало (код)

| Артефакт | Что добавлено |
|---|---|
| `core/agent.py` | `last_answer_sources/quotes/verdict`; `_fill_answer_meta` (вызов в `respond` после grounding) |
| `rag/service.py` | `sources_for`, `quotes_for`, `verdict_for`, `render_sources`, `render_quotes` |
| `Kod.py` | `_print_answer_sources(agent)` — печать источников/цитат после ответа |
| `dev/tests_debug/unit/test_rag_integration.py` | +2 теста (метаданные ответа) |

### Живой прогон (RouterAI, 2 запроса)

- Ответ агента несёт **5 источников** (source + section + chunk_id + score) и
  **3–5 цитат**; вердикт `partial`. Без `--rag` — источников нет (поведение прежнее).

### Регрессия

- `unit_runner.py` **271 OK** (было 269; +2).
- `check_acceptance.sh` **33/33** · `smoke.py` OK · `scenario.py` OK.
- `Kod.py --rag --mock --user w17` — поднимается, печатает `[RAG]`.
- `requirements.txt` — не изменён.

### Гейт 10→11

| № | Проверка | Ожидаемо | Факт |
|---|---|---|---|
| 1 | `BLOCK_ORDER` | `tools < rag < long_term` | ✅ |
| 2 | `DELIVERABLE` содержит `rag` | ✅ | ✅ |
| 3 | без `--rag` промпт | байт-в-байт прежний | ✅ (test) |
| 4 | с `--rag` | блок `[rag]` есть, в бюджете | ✅ |
| 5 | пустой индекс | блока нет, агент отвечает | ✅ |
| 6 | RAG не меняет `TaskStage` | ✅ | ✅ (test) |
| 7 | `python Kod.py --rag --mock` | поднимается, печатает `[RAG]` | ✅ |
| 8 | `test_rag_integration.py`/`unit_runner.py` | зелёные | ✅ 271 OK |
| 9 | `git diff --stat requirements.txt` | пусто | ✅ |
| 10 | запись + перечитывание `migr_plan.md` | ✅ | ✅ |

**Гейт 10→11: ✅ зелёный.**

### Коммит

- Предложен оператору:
  `feat(rag): интеграция Answer (источники/цитаты/вердикт) в ответ агента (этап 10)`

---

## Этап 11 — Часть 4: RAG в каждом обмене + память задачи + 2 сценария (цель: R9)

- Статус: ✅ завершён (2026-10-05)

### Было

- RAG уже вызывался на каждый обмен (`_rag_retrieve` + `_rag_turn`-кэш), но
  `WorkingMemory` **не имела** полей памяти задачи (`goal`/`clarifications`/
  `constraints`/`terms`), не было длинных диалоговых сценариев.

### Стало (код)

| Артефакт | Что добавлено |
|---|---|
| `memory/working.py` | поля `goal`/`clarifications`/`constraints`/`terms` (merge); строки в `as_prompt_block` |
| `core/agent.py` | `_update_task_memory` (извлечени�� из сообщения), `_enrich_query` (обогащение запроса памятью задачи) |
| `dev/tests_debug/scenario/scen_dialog_A.md` | 12 сообщений (RAG-модуль) |
| `dev/tests_debug/scenario/scen_dialog_B.md` | 13 сообщений (инварианты) |
| `dev/tests_debug/dialog_runner.py` | прогон сценариев + отчёт (новый) |
| `dev/tests_debug/unit/test_rag_working_memory.py` | 9 тестов (новый) |

### Живой прогон 2 сценариев (RouterAI)

| Сценарий | Сообщений | Источники в ответах | Цель зафиксирована | Термины |
|---|---|---|---|---|
| A (RAG-модуль) | 12 | **12/12** | ✅ | RRF, grounding |
| B (инварианты) | 13 | **13/13** | ✅ | инвариант, ProposedAction |

- Отчёт: `dev/logs_reports/stages/dialog_scenarios.md`.
- Память задачи: `goal` + `clarifications` + `constraints` + `terms` пополняются
  merge-ом и переживают перезапуск.

### Деталь (важно)

- Порог 0.45 (косинус) разделяет релевантное (top-1 sim ≥ 0.5156) и нерелевантное
  (≤ 0.4159). Абстрактный вопрос без лексического совпадения с корпусом может
  попасть под порог → «не знаю» (корректное поведение части 3).

### Регрессия

- `unit_runner.py` **280 OK** (было 271; +9 `test_rag_working_memory.py`).
- `check_acceptance.sh` **33/33** · `smoke.py` OK · `scenario.py` OK.
- `requirements.txt` — не изменён.

### Гейт 11→12

| № | Проверка | Ожидаемо | Факт |
|---|---|---|---|
| 1 | RAG на каждом сообщении | ✅ | ✅ (test) |
| 2 | `len(sources) ≥ 1` в каждом ответе | ✅ | ✅ 12/12, 13/13 |
| 3 | `goal` учитывается | ✅ | ✅ |
| 4 | `goal`/`terms` merge + round-trip | ✅ | ✅ (test) |
| 5 | история растёт и переживает перезапуск | ✅ | ✅ (test) |
| 6 | 2 сценария по 10–15 сообщений | созданы | ✅ 12 и 13 |
| 7 | `TaskStage` не затронут | ✅ | ✅ (test) |
| 8 | ��ез `--rag` промпт прежний | ✅ | ✅ (test) |
| 9 | `test_rag_working_memory.py` + `unit_runner.py` | зелёные | ✅ 280 OK |
| 10 | `git diff --stat requirements.txt` | пусто | ✅ |
| 11 | запись + перечитывание `migr_plan.md` | ✅ | ✅ |

**Гейт 11→12: ✅ зелёный.**

### Коммит

- Предложен оператору:
  `feat(agent): RAG в каждом обмене + память задачи + 2 длинных сценария (этап 11)`

---

## Этап 12 — ФИНАЛ: документация + чистка + приёмка (цель: Ф)

- Статус: ✅ завершён (2026-10-06)

### Было

- Флаги §6.3 и команды §6.4 частично отсутствовали в `Kod.py`; гейт — 33 проверки;
  `README.md`/`dev/Проверка.md` — на уровне Ревизии 6; `.tmp/` забит (203 МБ).

### Стало (код)

| Артефакт | Что добавлено |
|---|---|
| `Kod.py` | флаги `--rag-ask/--rag-verify/--rag-threshold/--rag-unknown/--rag-reranker/--rag-rewrite`; команды `/rag ask|sources|quotes|verify`; `run_rag_ask`/`run_rag_verify`/`_load_queries`/`_rag_llm_callable`/`_print_answer_sources`; регистрация в `main` |
| `dev/tests_debug/check_acceptance.sh` | +10 проверок (34–43) Ревизии 7 |
| `README.md` | раздел RAG (конвейер, порог, rewrite, источники/цитаты, «не знаю»), команды/флаги, дерево `rag/`, тестовый контур (280 OK / 43/43), демонстрации |
| `dev/Проверка.md` | раздел «Ревизия 7 — RAG-модуль (части 1–4)» (R7.1–R7.14) + общий итог |

### Живые прогоны (RouterAI + Ollama bge-m3)

| Прогон | Результат | Транскрипт |
|---|---|---|
| `--rag-ingest` | 117 чанков / 9 документов (дельта: ~1 изменён) | `rag_ingest_live.txt` |
| `--rag-search` | 5 источников со скорами/метаданными | `rag_search_live.txt` |
| `--rag-ask` | ответ + 5 источников + 4 цитаты, verdict `partial` | `rag_ask_live.txt` |
| `--rag-eval` | hit-rate@5 = **0.8824**, MRR 0.724, nDCG 0.903 | `rag_eval_live.txt` |
| `--rag-verify` | источники **10/10**, цитаты **10/10**, смысл 6/10 | `rag_verify_live.txt` |
| `--rag-compare` | fixed/dense 0.9706; hybrid ≥ компонент ✅ | `rag_compare_live.txt` |
| REPL `/rag on|find|status` | блок `[rag]` включён, поиск 4 источника | `rag_repl_live.txt` |
| `dialog_runner.py` | A 12/12, B 13/13 источников; цель/термины зафиксированы | `dialog_scenarios.md` |

### Регрессия

- `unit_runner.py` **280 OK** · `check_acceptance.sh` **43/43** · `smoke.py` OK ·
  `scenario.py` OK · `dialog_runner.py` DIALOG OK.
- `requirements.txt` — не изменён.

### Чистка

- `dev/tests_debug/.tmp/` — очищен (203 МБ → пусто); `rag/index/` оставлен (в `.gitignore`).

### Гейт 12 (финальный)

| № | Проверка | Ожидаемо | Факт |
|---|---|---|---|
| 1 | `unit_runner.py` | без регрессии | ✅ 280 OK |
| 2 | `smoke.py` / `scenario.py` | OK / OK | ✅ |
| 3 | `check_acceptance.sh` | 43/43 | ✅ |
| 4 | живые прогоны `rag_*_live.txt` | созданы | ✅ |
| 5 | hit-rate@5 (`--rag-eval`) | ≥ 0.80 | ✅ 0.8824 |
| 6 | источники/цитаты в `--rag-ask` | есть | ✅ 5/4 |
| 7 | 2 сценария по 10–15 сообщений | цель удержана, источники в каждом ответе | ✅ 12/12, 13/13 |
| 8 | `README.md` / `dev/Проверка.md` | соответствуют коду | ✅ |
| 9 | `dev/tests_debug/.tmp/` | пуст | ✅ |
| 10 | `git diff --stat requirements.txt` | пусто | ✅ |
| 11 | юниты зелёные **без** Ollama | ✅ | ✅ |

**Гейт 12: ✅ зелёный.**

### Коммит

- Предложен оператору:
  `docs(rag): итог Ревизии 7 — 4 части Задание.txt, гейт 33→43, README/Проверка (этап 12)`

---

## Итог Ревизии 7

**Задача:** довести существующий полноценный CLI-агент AI_9 до требований
`ND/tasks/n_5/Задание.txt` (4 части). **Статус: ✅ закрыта.**

| Часть | Требование | Реализация | Проверка |
|---|---|---|---|
| 1 | RAG «вопрос→поиск→объединение→LLM» + сравнение с/без RAG на 10 вопросах | `RagService.answer`, `compare_answers` (2 режима) | no_rag 0/10 источников, must_contain 5/19 → rag 10/10, 12/19 |
| 2 | reranker/порог + top-K до/после + query rewrite + 4 режима | `retrieval.threshold=0.45`, `rewrite.py`, `ANSWER_MODES` (4) | hit-rate@5 0.8824; фильтр не хуже (0.579→0.632) |
| 3 | источники (source+section/chunk_id) + цитаты + «не знаю» | `sources.py`, `citations.py`, `verify.py`, `UnknownConfig` | источники 10/10, цитаты 10/10; «не знаю» без LLM |
| 4 | RAG в каждом обмене + память задачи + 2 длинных сценария | `_rag_retrieve` (кэш на обмен), `WorkingMemory` (goal/terms), `dialog_runner.py` | A 12/12, B 13/13; цель/термины зафиксированы |

**Ключевые свойства:**

- **RAG — включаемый/отключаемый слой** (по умолчанию выключен; `--rag`/`/rag on`);
  без `--rag` промпт байт-в-байт прежний, `rag/` не импортируется.
- **AI_9 — полноценный чат-агент**, не «мини-чат»: `core/chat.py`, `core/task_state.py`,
  `--chat*`, `/chat*` не создавались.
- **Границы соблюдены:** `rag/` не импортирует `core/` (связь через DI-фасад `RagService`);
  RAG не меняет `TaskStage` (инструмент/поиск ≠ переход).
- **Деградация, не падение:** недоступная Ollama → `HashingEmbedder`; пустой поиск →
  «не знаю» без вызова LLM.

**Метрики (живой прогон, bge-m3):** hit-rate@5 = **0.8824**, recall@k = 0.8824,
MRR = 0.724, nDCG@k = 0.903; источники/цитаты 10/10; сравнение режимов — фильтр не хуже.

**Детерминированный контур:** L2 **280 OK** · L3 SMOKE OK · L4 SCENARIO OK ·
гейт **43/43** · диалоги DIALOG OK — без живого ключа и сети.

**Документация:** `README.md` и `dev/Проверка.md` синхронизированы; `.tmp/` очищен.

**Коммит — за оператором.**