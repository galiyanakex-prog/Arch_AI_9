# AI_9 — RAG с реранкингом, фильтрацией и переформулированием запроса

> **День 23. Реранкинг и фильтрация.** Агент переработан так, что после поиска
> добавлен **второй этап** — **reranker** или **фильтр релевантности**
> (порог similarity / отдельная модель / heuristic). Настроены **порог отсечения
> нерелевантных результатов** и **топ-K до и после фильтрации**, добавлен
> **query rewrite**, и реализовано **сравнение качества**: без фильтра/rewriting
> против с фильтром.
>
> **Результат дня 23:** улучшенный RAG — фильтрация/реранкинг + query rewrite +
> сравнение режимов. **Формат отчёта — Код.**
>
> Источники постановки: `ND/tasks/n_5/Задание_d23.txt` (неизменяемый первоисточник) и
> `ND/tasks/n_5/Суть_N5.md` (конспект недели RAG: bi-encoder top-20 → cross-encoder
> top-5, overlap-чанкинг, нормализация, три метрики качества).
>
> Наследие проекта: персонализированный CLI stateful-агент (память → профили →
> инварианты → контролируемый жизненный цикл) с MCP как интеграционным источником
> инструментов и RAG-модулем. День 23 доводит RAG-часть до сценария «второй этап
> поиска»: поиск → **реранкинг/фильтрация** → ответ.

---

## Содержание

- [Суть проекта](#суть-проекта)
- [Задание дня 23 — что требуется](#задание-дня-23--что-требуется)
- [Второй этап: реранкинг и фильтрация](#второй-этап-реранкинг-и-фильтрация)
- [Настройки: порог и top-K до/после](#настройки-порог-и-top-k-допосле)
- [Query rewrite](#query-rewrite)
- [Сравнение режимов и качество](#сравнение-режимов-и-качество)
- [Модель памяти](#модель-памяти)
- [Персонализация](#персонализация)
- [Инварианты и ограничения состояния](#инварианты-и-ограничения-состояния)
- [Контролируемые переходы состояний](#контролируемые-переходы-состояний)
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
**подключением к внешнему миру через MCP** (внешний источник инструментов) и —
главное для Дня 23 — **улучшенным RAG-поиском с реранкингом, фильтрацией и
переформулированием запроса**.

RAG (Retrieval-Augmented Generation) — паттерн дополнения ответа LLM **нашими**
знаниями прямо во время инференса. Базовый поиск (bi-encoder) быстрый, но неточный:
топ-20 кандидатов «похожи по вектору», но не все отвечают на вопрос (пример лекции:
запрос про CI/CD для Kotlin Multiplatform — «обзор CI/CD 2023» похож, но
нерелевантен). День 23 добавляет **второй этап** — реранкинг отдельной моделью
(cross-encoder) и/или **фильтр релевантности** по порогу similarity, а также
**query rewrite** перед поиском. Качество измеряется тремя метриками
(релевантность контекста / основанность ответа / корректность ответа).

Центральный конвейер после переработки под День 23:

```
вопрос
  → [query rewrite, опц.] переформулирование запроса
    → retrieval (bi-encoder, быстрый первый этап): top-K_before кандидатов (напр. 20)
      → второй этап: reranker / фильтр релевантности (порог similarity)
        → top-K_after чанков (напр. 5)
          → объединение с вопросом (со ссылками [doc_id#chunk_id])
            → LLM → ответ + grounding
```

Пайплайн строкой (как в постановке дня): **поиск → второй этап (reranker/фильтр) →
top-K_after → запрос к LLM**, плюс **query rewrite** и **сравнение режимов**.

Ключевые границы:

- **Второй этап — не тулз, а часть RAG-конвейера**: реранкинг/фильтрация живут внутри
  `rag/`, LLM их не «вызывает» как инструмент.
- **RAG ≠ переход**: `TaskStage` не меняется ни от поиска, ни от реранкинга, ни от
  фильтрации; RAG-стадий нет.
- **`rag/` и `core/` не импортируют друг друга** — связь только через DI-фасад
  `RagService` и готовый текст блока `[rag]`.
- **RAG выключен по умолчанию**: без флага промпт байт-в-байт прежний, `rag` не
  импортируется. Прежние тесты и критерии приёмки проходят без RAG и без сети.
- **Локальность и приватность**: эмбеддинги считаются локально (Ollama, HTTP на
  `127.0.0.1:11434`); приватные данные не покидают машину.
- **MCP выключен по умолчанию** (`mcp_enabled=False`); без флагов агент работает ровно
  как раньше.

---

## Задание дня 23 — что требуется

> Формулировка первоисточника (`Задание_d23.txt`):
> «Добавьте второй этап после поиска: reranker или фильтр релевантности (порог
> similarity / отдельная модель / heuristic). Настройте: порог отсечения
> нерелевантных результатов; топ-K до и после фильтрации. Сравните: качество без
> фильтра/rewriting; качество с фильтром. Результат: улучшенный RAG: фильтрация/
> реранкинг + query rewrite + сравнение режимов. Формат отчёта: Код.»

### Второй этап после поиска

Реализованы оба механизма, выбираются конфигурацией:

```python
# rag/rerank.py — второй этап после первого (bi-encoder) отбора
def rerank(query: str, hits: list[Hit], mode: str) -> list[Hit]:
    if mode == "cross-encoder":        # отдельная модель: query+doc вместе
        scored = cross_encoder.score(query, hits)     # точно, но медленнее
    elif mode == "heuristic":          # без модели: лексическое пересечение
        scored = lexical_overlap(query, hits)
    elif mode == "threshold":          # только фильтр по similarity
        scored = [h for h in hits if h.score >= threshold]
    else:                              # "off" — baseline (без второго этапа)
        scored = hits
    return dedup_mmr(scored)[:top_k_after]

# rag/retrieval.py — единая точка поиска с настройками до/после
def search(query, top_k_before=20, top_k_after=5, reranker="cross-encoder",
           threshold=0.35, rewrite="off") -> list[Hit]:
    q = rewrite_query(query, rewrite)              # 1) query rewrite (опц.)
    cand = first_stage(q, top_k_before)            # 2) bi-encoder: top-K_before
    return rerank(q, cand, reranker)               # 3) второй этап + фильтр → top-K_after
```

Варианты второго этапа (по заданию):

| Механизм | Как работает | Скорость | Точность |
|---|---|---|---|
| **cross-encoder** (отдельная модель) | query и документ оцениваются вместе | медленно (сек) | высокая |
| **heuristic** | лексическое пересечение/стемы, без модели | быстро (мс) | средняя |
| **порог similarity** | фильтр: оставить только `score ≥ threshold` | мгновенно | отсекает нерелевантное |

### Сравнение качества

Обязательная часть задания — сравнение режимов:

- **baseline** — без фильтра/rewriting (первый этап как есть);
- **rerank** — с реранкингом (cross-encoder или heuristic);
- **filter** — с порогом similarity;
- **rerank + filter** — оба механизма;
- **rewrite + rerank + filter** — полный конвейер.

Отчёт — таблица «режим × метрика» (`/rag compare`, `--rag-compare`) с вердиктом.

---

## Второй этап: реранкинг и фильтрация

### Почему нужен второй этап

Первый этап (bi-encoder) кодирует запрос и документ **отдельно** — быстро
(миллисекунды), но точность средняя. Топ-20 кандидатов могут быть «похожи по вектору»
и при этом не отвечать на вопрос. Второй этап решает это двумя способами:

- **реранкинг** (cross-encoder): query и документ подаются **вместе**, модель даёт
  точную оценку релевантности → из топ-20 получаем точный топ-5;
- **фильтр релевантности**: жёсткий порог similarity отсекает всё ниже `threshold`.

Поток (как в лекции): `Query → Bi-encoder (Top-20) → Cross-encoder (Rerank + Top-5)
→ LLM Answer`.

### Реализация

- **`CrossEncoderReranker`** — интерфейс под cross-encoder (живая модель при
  наличии); детерминированный **офлайн-фолбэк `LexicalReranker`** (лексическое
  пересечение со стемами) — для гейта без сети.
- **Фильтр по порогу** — отсекает `score < threshold` **до** реранкинга (экономия) или
  **после** (пост-фильтр) — настраивается.
- **Дедуп** (≤2 чанка на документ) и **MMR** (λ=0.7) — против повторов и за
  разнообразие, поверх второго этапа.
- **Латентность** реранкинга учитывается отдельно (`/rag stats`: p50/p95 для первого
  и второго этапа).

### Настройка порога

Порог задаётся флагом `--rag-threshold` (или в `rag/config.json`), подбирается
экспериментально под данные: слишком высокий — режем релевантное (падает recall);
слишком низкий — пропускаем «похожий, но нерелевантный» мусор (падает точность).
Значение фиксируется, сравнение порогов — в отчёте
`dev/logs_reports/stages/rag_threshold_compare.md`.

---

## Настройки: порог и top-K до/после

| Параметр | Флаг | По умолчанию | Смысл |
|---|---|---|---|
| **top-K до фильтрации** | `--rag-top-k-before <N>` | `20` | сколько кандидатов берёт первый этап (bi-encoder) |
| **top-K после фильтрации** | `--rag-top-k <N>` / `--rag-top-k-after <N>` | `5` | сколько чанков идёт в промт после второго этапа |
| **порог отсечения** | `--rag-threshold <F>` | `0.35` | минимальный score релевантности (0..1) |
| **реранкер** | `--rag-reranker {off,cross-encoder,heuristic}` | `cross-encoder` | механизм второго этапа |
| **порядок фильтра** | `--rag-filter-order {before,after}` | `before` | порог до или после реранкинга |
| **rewrite** | `--rag-rewrite {off,llm,heuristic}` | `off` | переформулирование запроса |

Логика: **top-K_before (20)** → второй этап (реранкер/фильтр) → **top-K_after (5)** →
блок `[rag]`. Пример «жёсткого» режима: `--rag-top-k-before 30 --rag-threshold 0.5
--rag-top-k 3`.

---

## Query rewrite

Перед поиском запрос можно **переформулировать** (`--rag-rewrite`):

- **`llm`** — переформулирование через LLM (рефразирование/расширение синонимами);
  фолбэк — детерминированная эвристика по стемам (если LLM недоступен);
- **`heuristic`** — детерминированно, без LLM (нормализация + синонимы по стемам);
- **`off`** — запрос уходит как есть (baseline).

Связь с multi-query: переформулирование может давать **несколько вариантов** запроса →
поиск по каждому → **RRF-склейка** кандидатов → второй этап. Результат фиксируется в
блоке `[rag]` (какие формулировки использованы) и в отчёте сравнения.

---

## Сравнение режимов и качество

### Режимы сравнения

`/rag compare <вопрос>` и `--rag-compare` прогоняют один и тот же вопрос по режимам и
печатают таблицу «режим × метрика» + вердикт:

| Режим | Что включено | Что показывает |
|---|---|---|
| `baseline` | первый этап как есть | качество без фильтра/rewriting |
| `filter` | только порог similarity | что даёт отсечение нерелевантного |
| `rerank` | cross-encoder/heuristic | что даёт точный второй этап |
| `rerank+filter` | оба механизма | совместный эффект |
| `rewrite+rerank+filter` | полный конвейер | максимальное качество |

Пример вывода:

```
[RAG] Сравнение режимов для вопроса «как настроить CI/CD для Kotlin Multiplatform?»
  режим                 recall@5   hit@5   mrr     ndcg@5   отсечено
  baseline              0.71       0.75    0.61    0.68     0
  filter (t=0.35)       0.78       0.82    0.66    0.74     7
  rerank (cross-enc)    0.88       0.91    0.79    0.86     0
  rerank+filter         0.92       0.95    0.83    0.90     6
  rewrite+rerank+filter 0.95       0.97    0.86    0.93     5
  вердикт: полный конвейер даёт лучший recall@5/hit@5 при меньшем шуме.
```

### Метрики качества

- **Context relevance** — доля релевантных чанков в результатах поиска;
- **Faithfulness** — основан ли ответ на найденном контексте (а не «из головы»);
- **Answer correctness** — совпадение с эталонным ответом.

Плюс демонстрация эффекта реранкинга: «топ-20 быстро, но неточно» против «топ-5 после
cross-encoder, точно» (кейс CI/CD — похожий, но нерелевантный чанк отсекается).
Реализация: `rag/eval.py` (recall@k / hit_rate@k / mrr / ndcg@k), `rag/compare.py`
(сравнение режимов), `rag/grounding.py` (faithfulness).

---

## Модель памяти

| Тип | Что хранит | Где (файл/хранилище) | Почему так |
|---|---|---|---|
| **Краткосрочная** (`ShortTermMemory`, scope=`session`) | текущий диалог — неизменяемые сообщения с `id`/`parent_id` | `users/<id>/tasks/<task>/sessions/<sid>/session.json` | сообщения — история (append-only); `parent_id` — задел ветвления |
| **Рабочая** (`WorkingMemory`, scope=`task`) | состояние задачи: `description`, `refs`, `lifecycle_summary`, `decisions`, `constraints`, `facts`, `open_questions`, `current_state` | `users/<id>/tasks/<task>/working_memory.json` | **пересчитываемое состояние**, а не лог сообщений |
| **Долговременная** (`LongTermMemory`, scope=`user`) | `profile_ref` (ССЫЛКА), `tasks[]`, `decisions[]`, `knowledge[]` | `users/<id>/long_term_memory.json` | живёт между сессиями; профиль — отдельно, здесь ссылка |
| **Профиль** (`Profile`, scope=`user`) | несколько профилей: `profile_id`, `name`, `domain`, `triggers[]`, `style` + `constraints` + `context`, `skills[]` | JSON в SQLite (`profiles(user_id, profile_id)`), зеркала `users/<id>/profiles/<pid>.json` | отдельная сущность в БД; запись слиянием (MERGE) |

Единая точка входа — `MemoryManager`: `remember()` / `recall()` / `build_blocks()`
(порядок `LAYER_ORDER = profile → long_term → working → short_term`) / `report()`.

### Иерархия хранения

```
users/<user_id>/
├── profile.json                 # зеркало профиля default (авторитет — SQLite profiles)
├── profiles/                    # зеркала всех профилей пользователя
├── long_term_memory.json        # profile_ref + задачи + решения + знания
├── integrations/mcp/            # ветка MCP (servers.json + catalog.json + scheduler/)
└── tasks/<task_name>/
    ├── invariants.json          # ConstraintSet (неизменяемые правила задачи)
    ├── task_state.json          # снимок TaskState (+ transition_log)
    ├── working_memory.json      # пересчитываемое состояние задачи
    ├── sessions_resume.md       # резюме сессий задачи (блок summary)
    ├── tool_audit.jsonl         # история вызовов инструментов (task-scope)
    └── sessions/<session_id>/   # session_id = ГГГГММДД_ЧЧММСС
        └── session.json         # краткосрочная память: сообщения с parent_id
```

Разные сущности — разные файлы. **Очистка истории диалога не сбрасывает состояние, не
удаляет инварианты и не трогает журнал переходов.** Все пути знает только
`storage/store.py`; битый или отсутствующий файл не роняет приложение.

### Сборка промта (явные блоки + дозированная доставка + бюджет)

```
[system: роль] → [system: profile] → [system: invariants] → [system: tools, опц.] →
[system: rag, опц.] → [system: long_term] → [system: working] → [system: summary, опц.] →
[messages: short_term (окно 10)] → [user: текущий запрос] → [резерв под ответ]
```

- `BLOCK_ORDER` = `role, profile, invariants, tools, rag, long_term, working, summary,
  short_term, current`; блок `[rag]` идёт **после `[tools]`, до `[long_term]`**;
- бюджет: необязательный блок пропускается, если `used + tokens > budget`; блок `[rag]`
  усекается **первым**; роль и запрос не урезаются никогда;
- `[rag]` содержит **прошедшие второй этап** чанки (top-K_after) со ссылками
  `[doc_id#chunk_id]` и метаданными (`source`/`section`).

---

## Персонализация

Поверх памяти — **несколько профилей на пользователя** (`profile_id`, `name`, `domain`,
`triggers[]`, `style`, `constraints`, `context`, `skills[]`). Активный профиль привязан
к сессии и входит в каждый промт.

- **хранение**: SQLite + зеркала `users/<id>/profiles/<pid>.json`; **запись слиянием**
  (MERGE);
- **память независима от профилей** — переключение профиля не трогает слои памяти;
- **профиль RAG/MCP менять не может** — только явная механика профилей; `tool_policy`
  в профиле — только сужение прав.

**Профиль-роутер** (`core/profile_router.py`) выбирает профиль по тексту запроса
детерминированно, без LLM: **+2** за триггер (регистронезависимо), **+1** за `domain`;
победитель = максимум (>0); ничья/ноль → `None`. Режим `/profile auto on` запускает
роутер на каждый запрос **до** сборки промта.

---

## Инварианты и ограничения состояния

Слой **неизменяемых правил**: **инвариант — условие, которое должно сохраняться во всех
допустимых состояниях; переход, нарушающий его, должен быть запрещён**. Перед действием
запускается **отдельная Python-проверка** («код запрещает, промт рекомендует»).

| Сущность | Назначение |
|---|---|
| `Invariant` | правило: `id`, `description`, `category`, `severity`, `active` |
| `ConstraintSet` | набор правил — **отдельная сущность** (не память, не профиль, не диалог) |
| `ProposedAction` | действие (`technology`, `adds_dependency`, `changes_database_schema`, `language`; + MCP-поля) |
| `InvariantChecker` (ABC) | `check()` (блокирующие) + `warnings()` (`severity="warning"`) |
| `RuleBasedChecker` | детерминированная реализация без LLM |
| `update_invariant` | изменение правила — только авторизованной операцией (`authorized=True`) |

Хранение — `users/<id>/tasks/<task>/invariants.json`, отдельно от диалога. При нарушении
инструмент **не вызывается**, выдаётся отказ с 4 частями (действие, id правила, причина,
альтернатива). Правило `tool.deny.<qualified>` запрещает конкретный инструмент.

**Переходы и инварианты — разные сущности контроля**: `state_machine` проверяет переходы
(этапы), `InvariantChecker` — действия.

---

## Контролируемые переходы состояний

**Жизненный цикл задачи — строгая машина состояний**: запрет «перепрыгнуть» этап
работает на уровне кода.

### Модель состояний (`TaskStage` — 8)

```python
class TaskStage(Enum):
    NEW = "new"
    PLANNING = "planning"
    PLAN_APPROVED = "plan_approved"
    IMPLEMENTATION = "implementation"
    VALIDATION = "validation"
    DONE = "done"
    PAUSED = "paused"
    FAILED = "failed"
```

### Карта переходов (whitelist)

```python
ALLOWED_TRANSITIONS = {
    NEW:            {PLANNING, PAUSED, FAILED},
    PLANNING:       {PLAN_APPROVED, PAUSED, FAILED},            # НЕТ implementation
    PLAN_APPROVED:  {IMPLEMENTATION, PLANNING, PAUSED, FAILED},
    IMPLEMENTATION: {VALIDATION, PLANNING, PAUSED, FAILED},
    VALIDATION:     {DONE, IMPLEMENTATION, PLANNING, PAUSED, FAILED},
    PAUSED:         set(),        # выход только через resume_task() → previous_stage
    DONE:           set(),        # терминальная
    FAILED:         {PLANNING},   # восстановление — явный /task retry
}
```

Запреты реализуются **отсутствием дуги** (не `if`-ами). **Реранкинг, фильтрация,
rewrite и MCP машину не трогают**: успешный поиск/вызов не создаёт запись перехода.

---

## Модульность и слои

Направление зависимостей однонаправленное: `Kod.py` → `core/` → `memory/` → `storage/`;
`integrations/` и `rag/` — сбоку, подключаются только DI-композицией. `mcp` SDK —
только в `integrations/mcp/`. **`rag/` не импортирует `core/`, а `core/` не импортирует
`rag/`** — связь через DI-фасад `RagService` и готовый текст блока `[rag]`.

- **Хранилище** (`storage/`) — фасад `Store` + ветка `integrations/mcp/`; битый файл →
  схема по умолчанию.
- **Память** (`memory/`) — 4 слоя, MERGE/append только через `MemoryManager`.
- **Ядро** (`core/`) — прежние сущности + инструменты + RAG-мост (`prompt_builder.py`,
  `agent.py`).
- **Интеграции** (`integrations/`) — `mcp/` и `scheduler/`.
- **RAG** (`rag/`) — индексация, **двухэтапный поиск (retrieval → rerank/filter)**,
  **query rewrite**, блок `[rag]`, grounding. Сеть — только `127.0.0.1:11434` (Ollama).
- **CLI** (`Kod.py`) — DI по умолчанию выключенных RAG/MCP; семейства `/rag` и `/mcp`.

---

## Архитектура

### Дерево модулей

```
AI_9/
├── Kod.py                       # точка входа: DI-композиция (+ RagService, mcp_enabled) + REPL
│                                #   (+ /rag…, /mcp…, --rag-compare, --rag-threshold, …)
├── core/                        # ядро агентности
│   ├── agent.py                 # оркестратор: RAG-слой (search → [rag] → ответ) + grounding
│   │                            #   + tool-use цикл
│   ├── llm_client.py            # LLMClient (ABC) + RouterAIClient + MockClient + complete_with_tools
│   ├── prompt_builder.py        # BLOCK_ORDER + DELIVERABLE + budget + блоки [tools], [rag]
│   ├── profile_router.py        # ProfileRouter — детерминированный выбор профиля
│   ├── state_machine.py         # строгая машина состояний (RAG/MCP её не трогают)
│   ├── invariants.py            # Invariant + ConstraintSet + InvariantChecker + ProposedAction
│   ├── tools.py / tool_registry.py / tool_policy.py / tool_executor.py
│   ├── tool_routing.py / tool_pipeline.py
├── integrations/                # слой внешних интеграций (MCP + планировщик)
│   ├── mcp/                     # config / transport / client / gateway / provider / *_server
│   └── scheduler/               # ядро планировщика (stdlib)
├── memory/                      # 4 слоя + MemoryManager
├── rag/                         # ← RAG-модуль — ядро дня 23 (второй этап + rewrite)
│   ├── config.py / config.json  # RagConfig (модель, чанкинг, top_k_before/after, threshold,
│   │                            #   reranker, filter_order, rewrite, grounding)
│   ├── types.py                 # Chunk / DocMeta / Hit / EvalReport / CompareReport / Answer
│   ├── text.py                  # normalize/tokenize/stem + regex чисел/дат/ссылок
│   ├── corpus.py / chunking.py  # сбор корпуса (sha1/mtime); fixed | structural + OVERLAP
│   ├── embedding.py             # OllamaEmbedder (локально) + HashingEmbedder (офлайн-фолбэк)
│   ├── index.py                 # плоский индекс: BM25-постинги + векторы (нормализация 0..1)
│   ├── retrieval.py             # bm25 | dense | hybrid (BM25⊕dense→RRF→MMR); top_k_before
│   ├── rerank.py                # ← ВТОРОЙ ЭТАП: CrossEncoderReranker + LexicalReranker
│   │                            #   + фильтр по порогу similarity; top_k_after
│   ├── rewrite.py               # ← query rewrite: llm | heuristic (+ multi-query)
│   ├── cache.py                 # SearchCache — LRU+TTL, инвалидация по mtime
│   ├── grounding.py             # проверка опоры ответа на источники + вердикт
│   ├── eval.py                  # recall@k / hit_rate@k / mrr / ndcg@k на golden-датасете
│   ├── compare.py               # ← сравнение режимов (baseline/filter/rerank/…)
│   ├── service.py               # RagService — фасад: ingest / search / context_block / answer
│   ├── datasets/                # corpus.list (своя база) + queries.jsonl (контрольные + golden)
│   └── index/                   # рантайм-индекс (в .gitignore)
├── storage/                     # store.py (фасад) + db.py (SQLite профилей)
├── users/                       # рантайм-хранилище
├── run.sh / run.desktop         # запуск
├── README.md                    # единый источник данных о проекте
├── README_3.md                  # эта версия — редакция под День 23 (реранкинг/фильтр/rewrite)
└── dev/                         # служебное пространство
```

### Конвейер (поиск → второй этап → LLM)

```
индексация (офлайн):
  corpus.list → chunking (overlap) → embedding (Ollama) → index (BM25 + vectors, норм. 0..1)

ответ (онлайн):
  вопрос → [rewrite: llm | heuristic, опц.]
    → retrieval: BM25 ⊕ dense → RRF → bi-encoder top-K_before (20)
      → ВТОРОЙ ЭТАП:
          ├─ фильтр релевантности: score ≥ threshold (порог)
          └─ reranker: cross-encoder (или heuristic) → переупорядочивание
        → дедуп (≤2/док) → MMR(λ=0.7) → top-K_after (5)
          → context_block (ссылки [doc_id#chunk_id])
            → объединение с вопросом (build_prompt)
              → LLM → ответ + sources → grounding
```

### Второй этап: реранкер и фильтр

- **Первый этап (bi-encoder)**: query и doc отдельно → быстро (мс) → top-K_before
  кандидатов (напр. 20).
- **Второй этап**:
  - **`cross-encoder`** — query+doc вместе → медленно (сек) → точно;
  - **`heuristic`** — лексическое пересечение/стемы → быстро → детерминированно;
  - **порог similarity** — жёсткий фильтр `score ≥ threshold`;
- **порядок фильтра** (`--rag-filter-order before|after`): порог до реранкинга
  (экономия вычислений) или после (пост-фильтр по уточнённым score);
- **top-K_after** — сколько чанков остаётся после второго этапа (напр. 5);
- **латентность** второго этапа измеряется отдельно (`/rag stats`).

### Порог отсечения

- Порог — минимальный score релевантности (0..1), флаг `--rag-threshold` (по умолчанию
  `0.35`), подбирается экспериментально;
- слишком высокий порог → отсекаем релевантное (падает recall); слишком низкий →
  пропускаем «похожий, но нерелевантный» мусор (падает точность);
- сравнение порогов (`--rag-threshold-sweep`) — таблица «порог × метрики» в отчёте
  `dev/logs_reports/stages/rag_threshold_compare.md`.

### Query rewrite

- `--rag-rewrite {off,llm,heuristic}` — переформулирование запроса перед поиском;
- `llm` — рефразирование/расширение через LLM (фолбэк — детерминированная эвристика);
- `heuristic` — нормализация + синонимы по стемам, без LLM;
- multi-query: несколько вариантов → поиск по каждому → RRF-склейка → второй этап.

### Сравнение режимов

Единая точка сравнения — `rag/compare.py` и `/rag compare <вопрос>`:
`baseline` (без фильтра/rewriting) → `filter` → `rerank` → `rerank+filter` →
`rewrite+rerank+filter`; таблица «режим × метрика» + вердикт.

### Метрики качества

- **Context relevance** — доля релевантных чанков;
- **Faithfulness** — основан ли ответ на контексте;
- **Answer correctness** — совпадение с эталоном;
- реализация: `rag/eval.py`, `rag/grounding.py`, `rag/compare.py`.

### Три кратких описания архитектуры

#### Формула для самой краткой характеристики (1 строка)

> AI_9 — персонализированный CLI stateful-агент (память → профили → инварианты →
> контролируемый жизненный цикл) с улучшенным RAG-поиском: вопрос → query rewrite →
> первый этап (bi-encoder top-20) → **второй этап (реранкер/фильтр по порогу)** →
> top-5 чанков → объединение с вопросом → запрос к LLM → ответ со ссылками, — с
> настраиваемым порогом отсечения, топ-K до/после и сравнением режимов.

#### Краткое и точное описание (одно предложение)

> AI_9 — CLI stateful-агент (RouterAI, step-3.5-flash), в RAG-конвейер которого добавлен
> **второй этап после поиска** — reranker (cross-encoder/heuristic) и/или **фильтр
> релевантности по порогу similarity** — с настраиваемыми **top-K_before** (сколько
> кандидатов берёт bi-encoder, напр. 20) и **top-K_after** (сколько чанков идёт в промт,
> напр. 5), с **query rewrite** (llm/heuristic/multi-query) перед поиском и
> **сравнением режимов** (baseline / filter / rerank / rerank+filter /
> rewrite+rerank+filter) по метрикам релевантности контекста, основанности и
> корректности ответа; локальные эмбеддинги (Ollama), ссылки `[doc_id#chunk_id]`,
> grounding.

#### Полная картина архитектуры с механикой частей

Общая формула: пять основ (память → персонализация → состояние → инварианты →
контролируемый жизненный цикл) + MCP как внешний источник инструментов + **RAG-модуль
с двухэтапным поиском**, доведённый до сценария Дня 23 «реранкинг и фильтрация».

1. **Хранилище (storage/)** — «где всё лежит»: иерархия `users/<id>/…`, ветка MCP,
   индекс RAG (`rag/index/`, `.gitignore`). Битый/отсутствующий файл → схема по
   умолчанию, не падение. Вся запись — через фасад `Store`.

2. **Память (memory/)** — «что агент помнит»: 4 слоя, MERGE/append только через
   MemoryManager, дозированная доставка + токен-бюджет. Результаты поиска в память
   автоматически не пишутся.

3. **Ядро (core/)** — «кто решает»: прежние сущности + инструменты + RAG-мост:
   `prompt_builder.py` (блок `[rag]`), `agent.py` (RAG-слой, `check_grounding`).

4. **Интеграции (integrations/)** — «как достучаться до внешнего мира»: `mcp/` и
   `scheduler/`; SDK — только здесь.

5. **RAG (rag/)** — «что агент знает из документов» — ядро Дня 23: индексация
   (`corpus` → `chunking` с overlap → `embedding` → `index` с нормализацией); поиск
   (`retrieval`: bm25|dense|hybrid → RRF → bi-encoder top-K_before);
   **второй этап** (`rerank`: cross-encoder/heuristic + **фильтр по порогу** →
   top-K_after); **`rewrite`** (llm/heuristic/multi-query); `context_block` → `[rag]`;
   `grounding`; `eval`/`compare`. Сеть — только `127.0.0.1:11434`. Связь с ядром — DI.

6. **Оркестратор и CLI** — «как этим пользуются»: `Agent` отвечает с блоком `[rag]`;
   `build_agent()` при `--rag` собирает `RagService`; команды `/rag …`, флаги `--rag`,
   `--rag-threshold`, `--rag-top-k-before`, `--rag-top-k`, `--rag-reranker`,
   `--rag-filter-order`, `--rag-rewrite`, `--rag-compare`. Жизненный цикл не изменён.

7. **Служебное пространство (dev/)** — «проект про проект»: план-эталон → рабочие планы
   → журнал; тестовый контур L1–L4 + гейт; приёмка; транскрипты живых прогонов.

**Инвариант всей системы**: детерминизм недетерминированной LLM даёт код; RAG/MCP —
адаптеры, которые не имеют права менять внутреннее состояние агента.

---

## Команды REPL

| Команда | Действие |
|---|---|
| `/rag status` | состояние RAG (вкл/выкл, режим, top-K_before/after, порог, реранкер, rewrite, grounding) |
| `/rag on\|off` | включить/выключить RAG в сессии |
| `/rag ingest` | проиндексировать корпус (инкрементально) |
| `/rag find <запрос>` | поиск со скорами **до и после** второго этапа — **почему** выбран чанк |
| `/rag ask <вопрос>` | ответ с RAG (поиск → второй этап → объединение → LLM), со ссылками |
| `/rag compare <вопрос>` | ← **ядро дня 23**: таблица «режим × метрика» (baseline/filter/rerank/…) |
| `/rag threshold <F>` | задать порог отсечения в сессии |
| `/rag topk <before> <after>` | задать top-K до и после фильтрации |
| `/rag rewrite <off\|llm\|heuristic>` | режим переформулирования запроса |
| `/rag rerank <off\|cross-encoder\|heuristic>` | механизм второго этапа |
| `/rag check <ответ>` | проверка опоры ответа на последние источники (без LLM) |
| `/rag stats` | индекс, модель, кэш, латентность p50/p95 (первый и второй этап), Ollama |
| `/rag eval` | метрики на golden-датасете (recall/hit-rate/mrr/ndcg) |
| `/memory` | снимок памяти по слоям |
| `/profile` / `/profile list` / `/profile use <id>` / `/profile route <текст>` / `/profile auto on\|off` | персонализация |
| `/plan` / `/approve` / `/step` / `/run` / `/pause` / `/resume` / `/goto <этап>` / `/transitions` / `/state` | автомат состояний |
| `/invariants` / `/invariant add\|set\|on\|off` / `/check <действие>` | инварианты |
| `/deliver <слои>` / `/compare` / `/summary` | промт и память |
| `/mcp status\|servers\|tools\|refresh\|connect\|call\|disconnect` | MCP-слой (наследие) |
| `/help` / `/exit` | справка / выход |

Без активной задачи `/step`, `/run`, `/pause`, `/resume`, `/approve`, `/goto` печатают
подсказку «сначала `/plan <цель>`». `/rag`-команды без флага `--rag` печатают «RAG
выключен».

---

## Запуск

```bash
# Подготовка RAG (один раз)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull bge-m3                     # или nomic-embed-text (по лекции)
curl -s http://127.0.0.1:11434/api/tags

# Индексация своей базы знаний
./run.sh --rag-ingest                  # corpus.list → chunks (overlap) → embeddings → index

# Второй этап и его настройка — центральный сценарий дня 23
./run.sh --rag --rag-reranker cross-encoder --rag-top-k-before 20 --rag-top-k 5
./run.sh --rag --rag-threshold 0.5 --rag-filter-order before     # фильтр релевантности
./run.sh --rag --rag-rewrite heuristic                           # query rewrite

# Сравнение режимов (без фильтра/rewriting vs с фильтром)
./run.sh --rag-compare                                           # таблица «режим × метрика» + вердикт
./run.sh --rag --rag-threshold-sweep                             # подбор порога

# REPL
./run.sh --rag --user alice            # REPL с RAG (агент сам ищет и реранкирует)

# Метрики и диагностика
./run.sh --rag-eval                    # recall/hit-rate/mrr/ndcg на golden
./run.sh --rag-search "как считается бюджет токенов"   # поиск с указанием top-K_before/after
./run.sh --rag --rag-mode bm25 --rag-top-k-before 30 --rag-threshold 0.5 --rag-top-k 3
./run.sh --rag --rag-grounding strict  # проверка опоры ответа (off|warn|strict)
```

**Флаги RAG:** `--rag`, `--no-rag-block`, `--rag-ingest`, `--rag-path <путь>`,
`--rag-search <запрос>`, `--rag-eval [датасет]`, `--rag-compare`, `--rag-threshold-sweep`,
`--rag-mode {bm25,dense,hybrid}`, `--rag-strategy {fixed,structural}`, `--rag-chunk-size <N>`,
`--rag-overlap <N>`, `--rag-top-k-before <N>`, `--rag-top-k <N>` (он же `--rag-top-k-after`),
`--rag-threshold <F>`, `--rag-reranker {off,cross-encoder,heuristic}`,
`--rag-filter-order {before,after}`, `--rag-rewrite {off,llm,heuristic}`, `--rag-multi-query`,
`--rag-model <имя>`, `--rag-config <файл>`, `--rag-grounding {off,warn,strict}`.

Все пути строятся от `BASE_DIR`; ключ — `API_KEY` из `.env`. При `--mock`, отсутствии
ключа или `API_KEY=test-key` выбирается `MockClient`.

---

## Агентный цикл

```
старт → DI-сборка build_agent(rag_enabled=--rag, mcp_enabled=--mcp) → идентификация user_id
      → активный профиль (--profile) → deliver (--deliver ∩ DELIVERABLE)
обмен (с RAG):
  вопрос → [rewrite: llm|heuristic|off]
        → RagService.search (кэш → BM25⊕dense → RRF → bi-encoder top-K_before)
        → второй этап: фильтр по порогу → reranker (cross-encoder/heuristic)
        → дедуп + MMR → top-K_after
        → context_block [rag] (после [tools], до [long_term])
        → build_prompt(вопрос ⊕ чанки) → llm.complete → ответ со ссылками [doc_id#chunk_id]
        → grounding (strict: провал → одна авто-перегенерация)
автомат: /plan → /approve → /step|/run → validation → done|failed (RAG не меняет переходы)
выход:  save_state() + сейв task_state.json
```

LLM за интерфейсом: `LLMClient (ABC)` → `RouterAIClient` (живой: POST + Bearer, retry на
HTTP 429, таймаут 30 сек, сбой → `None`) и `MockClient`.

---

## Тестирование и приёмка

Всё — **без живого ключа** (`API_KEY=test-key`, `MockClient`, `FakeMCPTransport`),
тестовые данные — только в `dev/tests_debug/.tmp/` (`.gitignore`), рабочие `users/`
не затрагиваются. `pytest` в venv отсутствует — L2 через собственный раннер
`unit_runner.py`.

| Уровень | Команда | Результат |
|---|---|---|
| L1 | `python -m py_compile Kod.py core/*.py memory/*.py storage/*.py rag/*.py` | exit 0 |
| L2 | `env -u API_KEY python dev/tests_debug/unit_runner.py` | все модули OK, 0 FAIL |
| L3 | `API_KEY=test-key python dev/tests_debug/smoke.py` | SMOKE OK, exit 0 |
| L4 | `API_KEY=test-key python dev/tests_debug/scenario.py` | SCENARIO OK, exit 0 |
| Гейт | `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` | все проверки ✅, exit 0 |
| Метрики | `./run.sh --rag-eval` | recall/hit-rate/mrr/ndcg (hit-rate@5 ≥ 0.80) |

**Специфичные для Дня 23 проверки:**

- **второй этап существует**: после поиска вызывается реранкер/фильтр; результат
  отличается от первого этапа при наличии нерелевантных кандидатов;
- **порог отсечения**: при `score < threshold` чанк не попадает в `[rag]`;
- **top-K до/после**: число кандидатов до (top_k_before) и после (top_k_after)
  отличается и настраивается;
- **реранкинг меняет порядок**: нерелевантный «похожий» чанк уходит ниже/отсекается;
- **query rewrite**: переформулировка применяется и попадает в отчёт;
- **сравнение режимов**: baseline / filter / rerank / rerank+filter дают разные метрики;
- **отчёт сравнения** строится (`rag/compare.py`);
- **`TaskStage` не затронут** (RAG ≠ переход); без `--rag` регрессии нет.

---

## Служебное пространство `dev/` (проект про проект)

```
AI_9/dev/
├── migr_plan.md + migr_plan_*.md   # планы миграций (этапы)
├── migr_log.md                     # журнал «было → стало → проверка → статус»
├── Проверка.md                     # чек-лист приёмки + сценарии ручной демонстрации
├── old_vers/                       # история ревизий
├── meta_promt/                     # метапромты пользователя
├── tests_debug/
│   ├── check_acceptance.sh         # гейт приёмки
│   ├── unit_runner.py              # L2-раннер (без pytest)
│   ├── smoke.py                    # L3-смоук
│   ├── scenario.py                 # L4-сценарии (+ RAG-сценарии)
│   ├── unit/                       # модульные тесты (в т.ч. test_rag_*)
│   ├── scenario/                   # scen_*.md (ручные сценарии)
│   └── .tmp/                       # единственное место прогонов (.gitignore)
├── logs_reports/                   # stages/ (+ rag_* транскрипты) + errors/ + archive/
└── vps/                            # инфраструктурный контур VPS
```

---

## Карта артефактов

### Рабочие артефакты (продукт)

| Артефакт | Назначение |
|---|---|
| `Kod.py` + `core/` + `memory/` + `storage/` | агент + каталог инструментов + tool-use + RAG |
| `rag/*` | RAG-модуль: config / corpus / chunking (overlap) / embedding / index / retrieval / **rerank (второй этап)** / **rewrite** / cache / grounding / eval / **compare** / service |
| `rag/datasets/corpus.list` | собственная база знаний (документы проекта) |
| `rag/datasets/queries.jsonl` | контрольные вопросы + golden-набор |
| `integrations/mcp/*` + `integrations/scheduler/*` | MCP-слой + планировщик (наследие) |
| `users/<id>/integrations/mcp/*` | конфиг/каталог MCP (через Store) |
| `README.md` / `README_3.md` | единый источник данных о проекте / редакция под День 23 |

### Служебные артефакты (процесс)

| Артефакт | Назначение |
|---|---|
| `dev/Проверка.md` | чек-лист приёмки + сценарии |
| `dev/migr_plan.md` + `migr_plan_*.md` | план-эталон и рабочие планы |
| `dev/migr_log.md` | журнал миграции + итоги |
| `dev/tests_debug/*` | L1–L4 + гейт (+ RAG-проверки) |
| `dev/logs_reports/stages/rag_threshold_compare.md` | сравнение порогов отсечения |
| `dev/logs_reports/stages/rag_*` | транскрипты живых прогонов |

---

## Порядок достижения итогового состояния

Порядок по зависимостям:

1. **Базовый агент** — память, профили, инварианты, машина состояний, LLM-клиент.
2. **MCP-слой** — контракты инструментов → реестр → `integrations/mcp/` → policy/executor
   → LLM tool-use → CLI (наследие).
3. **RAG-индексация** — `config` → `corpus` → `chunking` (**overlap**) → `embedding`
   (Ollama) → `index` (нормализация 0..1).
4. **RAG-поиск (первый этап)** — `retrieval` (bm25|dense|hybrid → RRF) → top-K_before.
5. **RAG-второй этап** — `rerank` (cross-encoder/heuristic) + **фильтр по порогу** →
   top-K_after; **`rewrite`** (llm/heuristic/multi-query); `cache`.
6. **RAG-ответ** — `service` (`search`/`answer`) → `context_block` → блок `[rag]` в
   `prompt_builder.py` → `agent.py` (grounding).
7. **Сравнение и метрики** — `eval`/`compare` (режимы baseline/filter/rerank/…).
8. **CLI** — `Kod.py` (DI `RagService`, флаги `--rag-threshold`, `--rag-top-k-before`,
   `--rag-top-k`, `--rag-reranker`, `--rag-rewrite`, `--rag-compare`; команды `/rag …`).
9. **Финал** — прогон L1→L4 + гейт, метрики, живой прогон (Ollama + LLM), запись итога
   в `dev/migr_log.md`, предложение коммита (коммит — только по явной команде).

---

## Риски и откат

- **Регрессия базового агента** — RAG выключен по умолчанию (`--rag`): без флага
  поведение прежнее, `rag` не импортируется. Откат — не включать флаг.
- **Зависимость от Ollama** — при недоступности `127.0.0.1:11434` деградация на
  `HashingEmbedder`; юниты и гейт от Ollama не зависят. Откат — не использовать `--rag`.
- **Порог режет релевантное** — слишком высокий `--rag-threshold` падает recall; лечится
  подбором (`--rag-threshold-sweep`) и пост-фильтром.
- **Реранкинг замедляет** — цена точности (мс → сек); включается по необходимости,
  `--rag-reranker heuristic` — компромисс.
- **«Похожий, но нерелевантный» чанк** — ровно то, что лечит второй этап (реранкинг +
  порог).
- **Ответ «из головы»** — симптом неверной настройки RAG; лечится grounding (strict) и
  проверкой доли релевантных чанков.
- **Приватность** — эмбеддинги и второй этап считаются локально.
- **Загрязнение рабочих данных** — тесты пишут только в `dev/tests_debug/.tmp/`.

---

## Известные шероховатости и заделы

- **Формат сдачи Дня 23 — код**; точные имена файлов отчёта в постановке не названы.
- Модель эмбеддингов конфигурируема (`bge-m3` по умолчанию, `nomic-embed-text` по лекции).
- Реранкинг реализован как интерфейс под cross-encoder с детерминированным офлайн-фолбэком
  (`LexicalReranker`) — для гейта без сети; живой cross-encoder подключается при наличии.
- Порог по умолчанию `0.35` — стартовая эвристика; точное значение подбирается под данные.
- Задел: multi-query вживую, гибрид cross-encoder, мультимодальный RAG, автопрогон метрик
  сторонними моделями, кэширование реранк-оценок.
- `transition_log` растёт без ограничения (сжатие — задел).
- Изменения не закоммичены (коммит — только по явной команде пользователя).

---

## Результат

- **Второй этап после поиска реализован**: reranker (cross-encoder / heuristic) и
  **фильтр релевантности** (порог similarity) — выбираются конфигурацией.
- **Настроены порог и top-K**: **порог отсечения** (`--rag-threshold`), **top-K_before**
  (кандидаты первого этапа, напр. 20) и **top-K_after** (чанки в промт, напр. 5);
  порядок фильтра (до/после реранкинга).
- **Query rewrite**: `off | llm | heuristic` (+ multi-query) перед поиском.
- **Сравнение режимов**: `baseline` (без фильтра/rewriting) vs `filter` vs `rerank` vs
  `rerank+filter` vs `rewrite+rerank+filter` — таблица «режим × метрика» + вердикт
  (`rag/compare.py`, `/rag compare`, `--rag-compare`).
- **Качество измеряется** тремя метриками: **context relevance / faithfulness /
  answer correctness** (`rag/eval.py`, `rag/grounding.py`).
- **Техника RAG**: чанкинг с **overlap**, нормализация векторов `0..1`, косинусное
  сходство, bi-encoder top-K_before → cross-encoder top-K_after, дедуп + MMR.
- **Локальность и приватность**: эмбеддинги и второй этап — локально (Ollama,
  `127.0.0.1:11434`).
- **Без регрессии**: RAG выключен по умолчанию; базовый агент, MCP-слой и машина
  состояний не тронуты; «RAG ≠ переход» (`TaskStage` не меняется от поиска/реранкинга).
- **Проверяемость**: L1–L4 и гейт — без живого ключа и сети; живой прогон (Ollama +
  реальный LLM) — отдельно.
