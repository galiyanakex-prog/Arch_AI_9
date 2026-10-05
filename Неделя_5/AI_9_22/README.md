# AI_9 — RAG-агент: вопрос → поиск → объединение → ответ

> **День 22. Первый RAG-запрос.** Агент переработан так, что центральная функция —
> `вопрос → поиск релевантных чанков → объединение с вопросом → запрос к LLM`, и она
> работает в **двух режимах**: **без RAG** и **с RAG**. К функции прилагается
> **мини-набор из 10 контрольных вопросов** по собственной базе знаний (для каждого —
> что ожидаем в ответе и какие источники должны быть использованы) и **сравнение
> качества** двух режимов.
>
> **Результат дня 22:** агент с двумя режимами (с RAG / без RAG) + 10 контрольных
> вопросов и сравнение качества. **Формат отчёта — Код.**
>
> Источники постановки: `ND/tasks/n_5/Задание_d22.txt` (неизменяемый первоисточник) и
> `ND/tasks/n_5/Суть_N5.md` (конспект недели RAG: эмбеддинги, чанкинг с перекрытием,
> поиск по косинусному сходству, реранкинг, три метрики качества).
>
> Наследие проекта: персонализированный CLI stateful-агент (память → профили →
> инварианты → контролируемый жизненный цикл), к которому подключён MCP как
> интеграционный источник инструментов, а поверх — RAG-модуль поиска по документам.
> День 22 доводит RAG-часть до законченного сценария «первый RAG-запрос».

---

## Содержание

- [Суть проекта](#суть-проекта)
- [Задание дня 22 — что требуется](#задание-дня-22--что-требуется)
- [10 контрольных вопросов и сравнение качества](#10-контрольных-вопросов-и-сравнение-качества)
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
главное для Дня 22 — **RAG-поиском по собственной базе знаний**.

RAG (Retrieval-Augmented Generation) — паттерн дополнения ответа LLM **нашими**
знаниями прямо во время инференса: текст режется на чанки, векторизуется
embedding-моделью, ищется по косинусному сходству и подмешивается в промт. Качество
поднимают чанкинг с перекрытием (overlap), нормализация векторов и реранкинг
(cross-encoder), а измеряют тремя метриками: **релевантность контекста**,
**основанность ответа (faithfulness)** и **корректность ответа** (`Суть_N5.md`).

Центральная функция агента после переработки под День 22:

```
answer(вопрос, use_rag: bool) -> Ответ
  1. retrieval:  retrieve(вопрос, top_k)            # поиск релевантных чанков
  2. combine:    контекст чанков ⊕ вопрос           # объединение с вопросом
  3. LLM:        llm.complete(объединённый промт)   # запрос к LLM
  4. with_rag:   Ответ + ссылки [doc_id#chunk_id];  without_rag: Ответ как есть
```

Пайплайн строкой (как в постановке дня): **вопрос → поиск релевантных чанков →
объединение с вопросом → запрос к LLM**.

```
вопрос
  → эмбеддинг вопроса (Ollama, локально)
    → поиск по косинусному сходству в базе (bi-encoder: top-20)
      → реранкинг (cross-encoder: top-5)
        → объединение top-5 чанков с вопросом (со ссылками)
          → LLM → ответ
            → [с RAG] ответ со ссылками на источники + проверка опоры (grounding)
            → [без RAG] ответ из общего контекста модели (без источников)
```

Ключевые границы:

- **RAG — контекстооптимизация, а не внешний тулз**: знания приходят в момент
  инференса; при RAG ничего не «дёргается» как MCP-инструмент, знания подгружаются к
  модели. Отличие от MCP — способ хранения знаний (MCP — внешние источники; RAG —
  наши внутренние знания).
- **RAG ≠ переход**: `TaskStage` не меняется от поиска и от использования чанков;
  RAG-стадий нет.
- **`rag/` и `core/` не импортируют друг друга** — связь только через DI-фасад
  `RagService` и готовый текст блока `[rag]`.
- **RAG выключен по умолчанию**: без флага промпт байт-в-байт прежний, `rag` не
  импортируется. Прежние тесты и критерии приёмки проходят без RAG и без сети.
- **Локальность и приватность**: эмбеддинги считаются локально (Ollama, HTTP на
  localhost `127.0.0.1:11434`); приватные данные не покидают машину; при переносе на
  VPS меняется только адрес.
- **MCP выключен по умолчанию** (`mcp_enabled=False`); без флагов агент работает ровно
  как раньше.

---

## Задание дня 22 — что требуется

> Формулировка первоисточника (`Задание_d22.txt`):
> «Реализуйте функцию: вопрос → поиск релевантных чанков → объединение с вопросом →
> запрос к LLM. Сравните: ответ модели без RAG, ответ модели с RAG. Усиление:
> составьте мини-набор из 10 контрольных вопросов по вашей базе; для каждого вопроса
> зафиксируйте: что ожидаете (что должно быть в ответе), какие источники должны быть
> использованы (если применимо). Результат: агент с двумя режимами (с RAG / без RAG)
> + 10 контрольных вопросов и сравнение качества. Формат отчёта: Код.»

### Функция: вопрос → поиск → объединение → LLM

Реализована единая функция ответа в двух режимах (псевдокод):

```python
def answer(question: str, use_rag: bool = True) -> Answer:
    if not use_rag:
        # режим БЕЗ RAG: вопрос уходит в LLM как есть
        llm_reply = llm.complete(build_prompt(question))          # общий контекст модели
        return Answer(text=llm_reply, sources=[], mode="no_rag")

    # режим С RAG: поиск → объединение → LLM
    hits = rag.search(question, mode=..., top_k=...)              # 1) релевантные чанки
    context_block = rag.context_block(hits)                       # со ссылками [doc_id#chunk_id]
    prompt = build_prompt(question, rag_block=context_block)      # 2) объединение с вопросом
    llm_reply = llm.complete(prompt)                              # 3) запрос к LLM
    return Answer(text=llm_reply, sources=hits, mode="with_rag")  # 4) + источники
```

Функция доступна:
- в REPL — как обычный запрос с включённым `--rag` (агент сам вызывает поиск);
- как явная команда сравнения — `/rag compare <вопрос>` (печатает оба ответа);
- как one-shot — `./run.sh --rag-ask "<вопрос>"` (с RAG) и `--rag-ask "<вопрос>" --no-rag`
  (без RAG);
- программно — через DI-фасад `RagService.search` / `context_block` и `LLMClient.complete`.

### Два режима: с RAG / без RAG

| | **Без RAG** (`use_rag=False`) | **С RAG** (`use_rag=True`) |
|---|---|---|
| Что уходит в LLM | только вопрос | вопрос + top-k чанков (со ссылками) |
| Источник ответа | общий контекст модели («среднее по больнице») | собственная база знаний |
| Ссылки на источники | нет | обязательны: `[doc_id#chunk_id]` |
| Риск галлюцинации | высокий (нет опоры) | ниже (ответ опирается на найденное; `grounding`) |
| Типичный провал | уверенно-неправильный ответ | «похожий, но нерелевантный» чанк (лечится реранкингом) |
| Поведение по умолчанию | так работал агент до RAG | включает `--rag` |

Сравнение — обязательная часть задания: `/rag compare <вопрос>` и отчёт
`--rag-compare` показывают для одного и того же вопроса оба ответа бок о бок, а на
контрольном наборе из 10 вопросов — агрегированные метрики качества.

### Мини-набор из 10 контрольных вопросов

Собственная база знаний (корпус `rag/datasets/corpus.list`) — это документация и код
проекта AI_9. Контрольный набор — `rag/datasets/queries.jsonl` (24 проверочных запроса;
ядро — 10 контрольных, см. раздел ниже). Для каждого вопроса зафиксированы **что
ожидаем** и **какие источники** должны быть использованы.

### Сравнение качества

Три метрики (`Суть_N5.md` §3.4.7):

- **Context relevance** — нашли ли правильные чанки (доля релевантных в результатах);
- **Faithfulness** — основан ли ответ на найденном контексте, а не «из головы»;
- **Answer correctness** — совпадение с эталонным ответом.

Плюс демонстрация эффекта реранкинга: «топ-20 быстро, но неточно» против «топ-5 после
cross-encoder, точно» (пример `Суть_N5.md`: запрос про CI/CD — похожий, но нерелевантный
чанк отсекается реранкингом).

---

## 10 контрольных вопросов и сравнение качества

Мини-набор из 10 вопросов по собственной базе (документация/код AI_9). Для каждого
зафиксировано: **что ожидаем в ответе** (режим с RAG должен это дать, режим без RAG —
не может гарантировать) и **какие источники** должны быть использованы.

| № | Контрольный вопрос | Что ожидаем в ответе | Ожидаемые источники |
|---|---|---|---|
| 1 | Сколько стадий у `TaskStage` и как они называются? | Ровно 8: `new`, `planning`, `plan_approved`, `implementation`, `validation`, `done`, `paused`, `failed` | архитектурный раздел README; `core/state_machine.py` |
| 2 | Можно ли перейти `planning → implementation` напрямую? | Нет — дуги нет в `ALLOWED_TRANSITIONS`; нужен `plan_approved` через `/approve` | README (карта переходов); `core/state_machine.py` |
| 3 | Какие четыре слоя памяти и их scope? | Краткосрочная (`session`), рабочая (`task`), долговременная (`user`), профиль (`user`) | README (модель памяти); `memory/*` |
| 4 | Что происходит с инструментом при нарушении инварианта? | Инструмент **не вызывается**; отказ называет (1) действие, (2) id правила, (3) почему обязательно, (4) альтернативу | README (инварианты); `core/invariants.py` |
| 5 | Как профиль-роутер выбирает профиль без LLM? | Детерминированно: +2 за каждый триггер, +1 за `domain`; победитель = максимум (>0), иначе `None` | README (персонализация); `core/profile_router.py` |
| 6 | Какой инструмент даёт сервер задания `time` и его сигнатура? | `get_time(timezone_name: str = "UTC") -> ISO 8601` (IANA-часовой пояс) | README (MCP-слой); `integrations/mcp/config.py` |
| 7 | Где в промте блок `[rag]` и когда он усекается? | После `[tools]`, до `[long_term]`; усекается **первым** при нехватке токен-бюджета | README (сборка промта); `core/prompt_builder.py` |
| 8 | Какие веса RRF у гибридного поиска? | `w_bm25 = 0.1`, `w_dense = 1.0`; порядок BM25⊕dense → RRF → реранк → MMR | README (RAG); `rag/retrieval.py` |
| 9 | В каком режиме grounding запускает авто-перегенерацию? | В `strict` — ровно **одна** авто-перегенерация с фидбэк-промптом; `off`/`warn` — без неё | README (grounding); `rag/service.py`, `core/agent.py` |
| 10 | Меняет ли вызов инструмента `TaskStage`? | Нет — «инструмент ≠ переход»; `transition_log` не получает записей от вызовов | README (переходы); `core/state_machine.py` |

**Ожидаемый эффект сравнения.** Для вопросов 1–10 режим **с RAG** даёт ответ со
ссылкой на конкретный источник и совпадает с эталоном, тогда как режим **без RAG**
отвечает «по общим знаниям модели» — типично неточно (неверное число стадий, неверная
карта переходов, отсутствие ссылок). Это и есть демонстрация качества: релевантность
контекста, основанность ответа и корректность фиксируются на контрольном наборе.

**Автопрогон контрольного набора:** `./run.sh --rag-eval` считает `recall@k`,
`hit_rate@k`, `mrr`, `ndcg@k` по golden-датасету; `./run.sh --rag-compare` даёт таблицу
«стратегия × режим» + вердикт; `/rag compare <вопрос>` показывает боковое сравнение двух
режимов по одному вопросу.

---

## Модель памяти

| Тип | Что хранит | Где (файл/хранилище) | Почему так |
|---|---|---|---|
| **Краткосрочная** (`ShortTermMemory`, scope=`session`) | текущий диалог — неизменяемые сообщения с `id`/`parent_id` | `users/<id>/tasks/<task>/sessions/<sid>/session.json` | сообщения — история (append-only), их нельзя переписывать; `parent_id` — задел ветвления |
| **Рабочая** (`WorkingMemory`, scope=`task`) | состояние задачи: `description`, `refs`, `lifecycle_summary`, `decisions`, `constraints`, `facts`, `open_questions`, `current_state` | `users/<id>/tasks/<task>/working_memory.json` | это **пересчитываемое состояние**, а не лог сообщений: списки дополняются, скаляры перезаписываются |
| **Долговременная** (`LongTermMemory`, scope=`user`) | `profile_ref` (ССЫЛКА), `tasks[]` (со ссылками и `source_session`), `decisions[]`, `knowledge[]` | `users/<id>/long_term_memory.json` | живёт между сессиями и задачами; профиль держится отдельно, здесь — только ссылка |
| **Профиль** (`Profile`, scope=`user`) | **несколько профилей**: `profile_id`, `name`, `domain`, `triggers[]`, `style` + `constraints` + `context`, `skills[]` | JSON в SQLite (`profiles(user_id, profile_id)`), зеркала `users/<id>/profiles/<pid>.json` | профили — отдельная сущность в БД; запись слиянием (MERGE); активный профиль подключён к каждому запросу |

Единая точка входа — `MemoryManager`: `remember()` (запись с логом маршрута),
`recall()` (чтение выбранных слоёв), `build_blocks()` (текстовые блоки в порядке
`LAYER_ORDER = profile → long_term → working → short_term`), `report()` (снимок для `/memory`).

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

Разные сущности — разные файлы: `session.json` (история), `working_memory.json`
(пересчитываемое состояние), `task_state.json` (жизненный цикл + журнал переходов),
`invariants.json` (правила), `integrations/mcp/` (конфиг/каталог инструментов),
`tool_audit.jsonl` (история вызовов). **Очистка истории диалога не сбрасывает
состояние, не удаляет инварианты и не трогает журнал переходов.**

Все пути знает только `storage/store.py`; битый или отсутствующий файл не роняет
приложение (чтение → схема по умолчанию; `read_*` → `None`, дефолтизация у вызывающего).

### Сборка промта (явные блоки + дозированная доставка + бюджет)

```
[system: роль] → [system: profile] → [system: invariants] → [system: tools, опц.] →
[system: rag, опц.] → [system: long_term] → [system: working] → [system: summary, опц.] →
[messages: short_term (окно 10)] → [user: текущий запрос] → [резерв под ответ]
```

- `BLOCK_ORDER` = `role, profile, invariants, tools, rag, long_term, working, summary,
  short_term, current`; блок `[rag]` идёт **после `[tools]`, до `[long_term]`**;
- доставляемое подмножество задаётся `DELIVERABLE`; `role`/`current` — всегда;
- бюджет: необязательный блок пропускается, если `used + tokens > budget`; блок `[rag]`
  усекается **первым**; роль и запрос не урезаются никогда;
- `[rag]` содержит найденные чанки со ссылками `[doc_id#chunk_id]` и метаданными
  (`source`/`section`).

---

## Персонализация

Поверх памяти — **несколько профилей на пользователя** (`profile_id`, `name`, `domain`,
`triggers[]`, `style`, `constraints`, `context`, `skills[]`). Профиль — «призма» под
домен/задачу; активный профиль привязан к сессии и входит в каждый промт.

- `profile_id` — короткое имя (`safe_name`); первый профиль — `default`;
- **профиль = декларативный пайплайн скиллов** (упорядоченные инструкции в промт);
- **хранение**: SQLite + зеркала `users/<id>/profiles/<pid>.json`;
- **запись слиянием** (MERGE) — обновляются только переданные поля, словари мержатся;
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
| `ProposedAction` | действие (`technology`, `adds_dependency`, `changes_database_schema`, `language`; + MCP-поля `action_type`/`tool_name`/`arguments`) |
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

Запреты реализуются **отсутствием дуги** (не `if`-ами): нет дуг
`new → implementation` и `planning → implementation`; путь в `done` — только через
`validation`; из `paused` — только `resume_task()`.

### API контроля

```python
can_transition(from_state, to_state) -> bool     # единственный источник истины — карта
try_transition(state, proposed) -> TaskState      # единственная точка смены этапа
```

Отказ называет правило (`REFUSAL_RULES`, без LLM); каждая попытка пишется в
`transition_log`. **RAG и MCP машину не трогают**: успешный поиск/вызов не создаёт
запись перехода.

---

## Модульность и слои

Направление зависимостей однонаправленное: `Kod.py` → `core/` → `memory/` → `storage/`;
`integrations/` и `rag/` — сбоку, подключаются только DI-композицией. `mcp` SDK —
только в `integrations/mcp/`. **`rag/` не импортирует `core/`, а `core/` не импортирует
`rag/`** — связь через DI-фасад `RagService` и готовый текст блока `[rag]`.

- **Хранилище** (`storage/`) — фасад `Store` + ветка `integrations/mcp/`; устойчивость:
  битый/отсутствующий файл → схема по умолчанию.
- **Память** (`memory/`) — 4 слоя, MERGE/append только через `MemoryManager`.
- **Ядро** (`core/`) — прежние сущности без регрессии + инструменты (`tools.py`,
  `tool_registry.py`, `tool_policy.py`, `tool_executor.py`, `tool_routing.py`,
  `tool_pipeline.py`) + RAG-мост (`prompt_builder.py`, `agent.py`).
- **Интеграции** (`integrations/`) — `mcp/` и `scheduler/`.
- **RAG** (`rag/`) — индексация корпуса, гибридный поиск, блок `[rag]`, grounding.
  Сеть — только `127.0.0.1:11434` (Ollama).
- **CLI** (`Kod.py`) — DI по умолчанию выключенных RAG/MCP; семейства `/rag` и `/mcp`.

---

## Архитектура

### Дерево модулей

```
AI_9/
├── Kod.py                       # точка входа: DI-композиция (+ RagService, mcp_enabled) + REPL
│                                #   (+ /rag…, /mcp…, --rag-ask, --rag-compare, --rag-probe)
├── core/                        # ядро агентности
│   ├── agent.py                 # оркестратор: две ветки ответа (с RAG / без RAG) +
│   │                            #   check_grounding, _grounding_guard + tool-use цикл
│   ├── llm_client.py            # LLMClient (ABC) + RouterAIClient + MockClient + LLMReply +
│   │                            #   complete_with_tools (нативный tool-use + fallback)
│   ├── prompt_builder.py        # BLOCK_ORDER + DELIVERABLE + budget + блоки [tools], [rag]
│   ├── profile_router.py        # ProfileRouter — детерминированный выбор профиля
│   ├── state_machine.py         # строгая машина состояний (RAG/MCP её не трогают)
│   ├── invariants.py            # Invariant + ConstraintSet + InvariantChecker + ProposedAction
│   ├── tools.py / tool_registry.py / tool_policy.py / tool_executor.py
│   ├── tool_routing.py          # rank_tools — детерминированный выбор инструмента
│   └── tool_pipeline.py         # PipelineStep/Pipeline/run_pipeline
├── integrations/                # слой внешних интеграций (MCP + планировщик)
│   ├── mcp/                     # config / transport (stdio+HTTP+fake) / client / gateway /
│   │                            #   provider / demo_server / scheduler_server / pipeline_server
│   └── scheduler/               # ядро планировщика (stdlib)
├── memory/                      # 4 слоя + MemoryManager
├── rag/                         # ← RAG-модуль (индексация + гибридный поиск) — ядро дня 22
│   ├── config.py / config.json  # RagConfig (модель, чанкинг, overlap, режим, top_k, веса, grounding)
│   ├── types.py                 # Chunk / DocMeta / Hit / IngestReport / EvalReport /
│   │                            #   CompareReport / GroundingReport / Answer
│   ├── text.py                  # normalize/tokenize/stem/split_sentences + regex чисел/дат/ссылок
│   ├── corpus.py                # discover/delta — сбор корпуса, deny-список, sha1/mtime
│   ├── chunking.py              # fixed | structural + OVERLAP (chunk_size + overlap)
│   ├── embedding.py             # OllamaEmbedder (локально) + HashingEmbedder (офлайн-фолбэк)
│   ├── index.py                 # плоский индекс: BM25-постинги + векторы (нормализация 0..1)
│   ├── retrieval.py             # bm25 | dense | hybrid (BM25 ⊕ dense → RRF → MMR)
│   ├── rerank.py                # реранкинг: bi-encoder top-20 → cross-encoder top-5
│   ├── cache.py                 # SearchCache — LRU+TTL, инвалидация по mtime
│   ├── grounding.py             # проверка опоры ответа на источники + вердикт
│   ├── eval.py                  # recall@k / hit_rate@k / mrr / ndcg@k на golden-датасете
│   ├── compare.py               # сравнение «с RAG vs без RAG» и стратегий × режимов
│   ├── service.py               # RagService — фасад: ingest / search / context_block /
│   │                            #   answer(use_rag) / compare
│   ├── datasets/                # corpus.list (своя база) + queries.jsonl (10 контрольных + golden)
│   └── index/                   # рантайм-индекс (в .gitignore): chunks/postings/vectors/meta
├── storage/                     # store.py (фасад) + db.py (SQLite профилей)
├── users/                       # рантайм-хранилище
├── run.sh / run.desktop         # запуск
├── README.md                    # единый источник данных о проекте
├── README_2.md                  # эта версия — редакция под День 22 (два режима RAG)
└── dev/                         # служебное пространство
```

### RAG-ядро: конвейер (вопрос → чанки → промт → LLM)

```
индексация (офлайн):
  corpus.list → chunking (overlap) → embedding (Ollama) → index (BM25 + vectors, норм. 0..1)

ответ (онлайн, режим С RAG):
  вопрос → embedding вопроса
    → retrieve: BM25 ⊕ dense → RRF → bi-encoder top-20
      → rerank: cross-encoder → top-5
        → context_block (ссылки [doc_id#chunk_id])
          → объединение с вопросом (build_prompt)
            → LLM → ответ + sources → grounding (ok|partial|hallucination)
```

### Чанкинг с перекрытием (overlap)

- Стратегии: **`fixed`** (окно токенов) и **`structural`** (по заголовкам/блокам —
  «каждый chunk — законченная мысль»);
- **перекрытие обязательно**: соседние чанки пересекаются (пример лекции — окна
  `1–500`, `451–950`, `901–1400`; параметры по умолчанию `chunk_size=500`,
  `overlap=50`); overlap нельзя отключать («всё это должны делать перекрытия»);
- размер чанка и overlap **подбираются экспериментально** под данные; подобранные
  значения фиксируются, сравнение — в отчёте `dev/logs_reports/stages/rag_chunking_compare.md`;
- чанки — 500–1000 токенов (не больше), чтобы не терять контекст и не раздувать промт.

### Эмбеддинги и нормализация

- **Эмбеддинги — строго локально:** только `127.0.0.1:11434` (Ollama) — валидация в
  `RagConfig.validate`; при переносе на VPS меняется только адрес. При недоступности
  Ollama — деградация на `HashingEmbedder` (офлайн-фолбэк).
- Модель по умолчанию — локальная (`bge-m3`, dim 1024); лекция использует
  `nomic-embed-text` (768) — модель **конфигурируема** (`--rag-model`), замена
  бесшовна.
- **Нормализация векторов**: числа приводятся к диапазону `0..1` (деление на максимум
  вектора) перед сравнением — как на лекции.
- Близость — **косинусное сходство** (cosine similarity): `+1` похожи, `−1`
  противоположны, `0` «о разном».

### Поиск: bi-encoder → cross-encoder (реранкинг)

- **Первый этап — bi-encoder** (быстро, миллисекунды, точность средняя): отбор
  **top-20** кандидатов по вектору/BM25⊕dense (RRF).
- **Второй этап — cross-encoder (реранкинг)** (медленно, секунды, точность высокая):
  query и документ оцениваются вместе; из top-20 получается **top-5**.
- Реранкинг лечит главный риск retrieval: «похожий по вектору, но не отвечающий» чанк
  (пример лекции: запрос про CI/CD для Kotlin Multiplatform — «обзор CI/CD 2023»
  похож, но нерелевантен).
- Реализация: `CrossEncoderReranker` (интерфейс под cross-encoder) с детерминированным
  офлайн-фолбэком `LexicalReranker`; гибрид `BM25 ⊕ dense → RRF → реранк → дедуп
  (≤2/док) → MMR(λ=0.7) → top-k`; веса RRF `w_bm25=0.1`, `w_dense=1.0`.

### Объединение с вопросом и запрос к LLM

- **Объединение**: top-5 чанков формируют блок `[rag]` со ссылками
  `[doc_id#chunk_id]`; он вставляется в промт **после `[tools]`, до `[long_term]`**;
- **запрос к LLM**: `llm.complete(prompt)` — единый путь; при включённом RAG — с
  требованием опираться на источники и приводить ссылки;
- **проверка опоры (grounding)**: `off|warn|strict`; `strict` ловит выдуманные
  числа/даты и запускает **одну** авто-перегенерацию с фидбэк-промптом;
- **ответ без RAG**: тот же вопрос без блока `[rag]` — «из общего контекста модели».

### Два режима и точка их сравнения

Единая функция `answer(вопрос, use_rag)` обслуживает оба режима; точка сравнения —
`rag/compare.py` и команда `/rag compare <вопрос>`:

```
/rag compare "сколько стадий у TaskStage?"

БЕЗ RAG: у модели около 5-7 стадий, названия приблизительные, ссылок нет.
С RAG:   ровно 8 стадий (new/planning/plan_approved/implementation/
         validation/done/paused/failed) — источник: core/state_machine.py [#…].
```

### Метрики качества

- **Context relevance** — доля релевантных чанков в результатах поиска;
- **Faithfulness** — основан ли ответ на контексте (нет ссылок / «из головы» → плохо);
- **Answer correctness** — сравнение финального ответа с эталонным;
- реализация: `rag/eval.py` (recall@k / hit_rate@k / mrr / ndcg@k),
  `rag/grounding.py` (faithfulness), `rag/compare.py` (сравнение режимов).
- Если регулярно находятся неверные чанки — ревизия данных/модели (как на лекции).

### Три кратких описания архитектуры

#### Формула для самой краткой характеристики (1 строка)

> AI_9 — персонализированный CLI stateful-агент (память → профили → инварианты →
> контролируемый жизненный цикл) с RAG-поиском по собственной базе знаний, работающий
> в двух режимах: вопрос → поиск релевантных чанков → объединение с вопросом → запрос
> к LLM (с RAG) и тот же вопрос без поиска (без RAG), — а контроль над состоянием
> остаётся за существующими механизмами.

#### Краткое и точное описание (одно предложение)

> AI_9 — CLI stateful-агент (RouterAI, step-3.5-flash), который отвечает на вопрос двумя
> способами: **без RAG** (вопрос уходит в LLM как есть) и **с RAG** (вопрос →
> эмбеддинг локально через Ollama → поиск по косинусному сходству в своей базе: этап
> bi-encoder top-20 → реранкинг cross-encoder top-5 → объединение top-5 чанков со
> ссылками `[doc_id#chunk_id]` с вопросом → запрос к LLM → ответ со ссылками и
> проверкой опоры grounding), с мини-набором из 10 контрольных вопросов (что ожидаем +
> источники) и сравнением качества двух режимов по метрикам релевантности контекста,
> основанности и корректности ответа.

#### Полная картина архитектуры с механикой частей

Общая формула: пять основ (память → персонализация → состояние → инварианты →
контролируемый жизненный цикл) + интеграционный модуль MCP как внешний источник
инструментов + **RAG-модуль как слой доступа к локальным знаниям**, доведённый до
сценария Дня 22 «первый RAG-запрос» в двух режимах.

1. **Хранилище (storage/)** — «где всё лежит»: иерархия `users/<id>/…`, ветка MCP,
   индекс RAG (`rag/index/`, `.gitignore`). Битый/отсутствующий файл → схема по
   умолчанию, не падение. Вся запись — через фасад `Store`.

2. **Память (memory/)** — «что агент помнит»: 4 слоя, MERGE/append только через
   MemoryManager, дозированная доставка + токен-бюджет. Сырые результаты поиска/вызовов
   в память автоматически не пишутся.

3. **Ядро (core/)** — «кто решает»: прежние сущности без регрессии + инструменты
   (`tools.py`, `tool_registry.py`, `tool_policy.py`, `tool_executor.py`,
   `tool_routing.py`, `tool_pipeline.py`) + RAG-мост: `prompt_builder.py` (блок `[rag]`),
   `agent.py` (две ветки ответа, `check_grounding`, `_grounding_guard`).

4. **Интеграции (integrations/)** — «как достучаться до внешнего мира»: `mcp/` (config,
   transport stdio/HTTP/fake, client, gateway, provider, demo_server, scheduler_server,
   pipeline_server) и `scheduler/`; SDK — только здесь.

5. **RAG (rag/)** — «что агент знает из документов» — ядро Дня 22: индексация
   (`corpus` → `chunking` с overlap → `embedding` → `index` с нормализацией) и ответ
   (`retrieval`: bm25|dense|hybrid → RRF; `rerank`: bi-encoder→cross-encoder;
   `context_block` → `[rag]`; `grounding`; `eval`/`compare`). Сеть — только
   `127.0.0.1:11434`. Связь с ядром — только DI (`RagService`).

6. **Оркестратор и CLI** — «как этим пользуются»: `Agent` отвечает в двух режимах;
   `build_agent()` при `--rag` собирает `RagService`; команды `/rag …`, флаги
   `--rag`, `--no-rag`, `--rag-ask`, `--rag-compare`, `--rag-eval`. Жизненный цикл
   (`/plan → /approve → /step|/run → validation → done`) не изменён.

7. **Служебное пространство (dev/)** — «проект про проект»: план-эталон → рабочие планы
   → журнал; тестовый контур L1–L4 + гейт; приёмка; транскрипты живых прогонов.

**Инвариант всей системы**: детерминизм недетерминированной LLM даёт код; RAG/MCP —
адаптеры, которые не имеют права менять внутреннее состояние агента.

---

## Команды REPL

| Команда | Действие |
|---|---|
| `/rag status` | состояние RAG (вкл/выкл, режим, top-k, grounding, индекс, модель) |
| `/rag on\|off` | включить/выключить RAG в сессии (два режима) |
| `/rag ingest` | проиндексировать корпус (инкрементально) |
| `/rag find <запрос>` | поиск со скорами — **почему** выбран чанк |
| `/rag ask <вопрос>` | ответ **с RAG** (вопрос → поиск → объединение → LLM), со ссылками |
| `/rag ask --no-rag <вопрос>` | ответ **без RAG** (вопрос → LLM) |
| `/rag compare <вопрос>` | ← **ядро дня 22**: два ответа бок о бок (с RAG / без RAG) |
| `/rag check <ответ>` | проверка опоры ответа на последние источники (без LLM) |
| `/rag stats` | индекс, модель, размер, RAM, кэш, латентность p50/p95, Ollama |
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

# Два режима — центральный сценарий дня 22
./run.sh --rag-ask "сколько стадий у TaskStage?"                 # ответ С RAG (со ссылками)
./run.sh --rag-ask "сколько стадий у TaskStage?" --no-rag        # ответ БЕЗ RAG
./run.sh --rag-compare                                           # сравнение на контрольном наборе

# REPL
./run.sh --rag --user alice            # REPL с RAG (агент сам ищет чанки)
./run.sh --user alice                  # без RAG (как раньше)

# Метрики и диагностика
./run.sh --rag-eval                    # recall/hit-rate/mrr/ndcg на golden
./run.sh --rag-search "как считается бюджет токенов"   # поиск без LLM, топ-5 со скорами
./run.sh --rag --rag-mode bm25 --rag-top-k 3
./run.sh --rag --rag-grounding strict  # проверка опоры ответа (off|warn|strict)
```

**Флаги RAG:** `--rag`, `--no-rag`, `--rag-ask <вопрос>`, `--rag-compare`, `--no-rag-block`,
`--rag-ingest`, `--rag-path <путь>`, `--rag-search <запрос>`, `--rag-eval [датасет]`,
`--rag-mode {bm25,dense,hybrid}`, `--rag-strategy {fixed,structural}`, `--rag-chunk-size <N>`,
`--rag-overlap <N>`, `--rag-top-k <N>`, `--rag-model <имя>`, `--rag-config <файл>`,
`--rag-grounding {off,warn,strict}`, `--rag-multi-query`.

Все пути строятся от `BASE_DIR`; ключ — `API_KEY` из `.env`. При `--mock`, отсутствии
ключа или `API_KEY=test-key` выбирается `MockClient`.

---

## Агентный цикл

```
старт → DI-сборка build_agent(rag_enabled=--rag, mcp_enabled=--mcp) → идентификация user_id
      → активный профиль (--profile) → deliver (--deliver ∩ DELIVERABLE)
обмен (режим БЕЗ RAG):
  вопрос → remember_message("user") → build_prompt(вопрос) → llm.complete
        → remember_message("assistant") → ответ из общего контекста модели
обмен (режим С RAG):
  вопрос → RagService.search (кэш → BM25⊕dense → RRF → bi-encoder top-20 →
        cross-encoder top-5) → context_block [rag] (после [tools], до [long_term])
        → build_prompt(вопрос ⊕ чанки) → llm.complete → ответ со ссылками [doc_id#chunk_id]
        → grounding (strict: провал → одна авто-перегенерация)
автомат: /plan → /approve → /step|/run → validation → done|failed (RAG не меняет переходы)
выход:  save_state() + сейв task_state.json
```

LLM за интерфейсом: `LLMClient (ABC)` → `RouterAIClient` (живой: POST + Bearer, retry на
HTTP 429 с задержками 2 → 4 → 8 сек, таймаут 30 сек, сбой → `None`) и `MockClient`.

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

**Специфичные для Дня 22 проверки:**

- функция `answer(вопрос, use_rag)` возвращает ответ и (в режиме с RAG) список источников;
- **режим без RAG**: промпт не содержит блока `[rag]`;
- **режим с RAG**: промпт содержит `[rag]` после `[tools]`, до `[long_term]`;
- индекс строится с **overlap** (соседние чанки пересекаются) и переживает save/load;
- поиск отдаёт хит с метаданными; работает реранкинг (top-20 → top-5);
- векторы нормализованы; сравнение — косинусное;
- контрольный набор из 10 вопросов прогоняется; метрики считаются;
- `TaskStage` не затронут (`RAG ≠ переход`).

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
| `rag/*` | RAG-модуль: config / corpus / chunking (overlap) / embedding / index / retrieval / rerank / cache / grounding / eval / compare / service |
| `rag/datasets/corpus.list` | собственная база знаний (документы проекта) |
| `rag/datasets/queries.jsonl` | контрольные вопросы (10 ядровых) + golden-набор |
| `integrations/mcp/*` + `integrations/scheduler/*` | MCP-слой + планировщик (наследие) |
| `users/<id>/integrations/mcp/*` | конфиг/каталог MCP (через Store) |
| `README.md` / `README_2.md` | единый источник данных о проекте / редакция под День 22 |

### Служебные артефакты (процесс)

| Артефакт | Назначение |
|---|---|
| `dev/Проверка.md` | чек-лист приёмки + сценарии |
| `dev/migr_plan.md` + `migr_plan_*.md` | план-эталон и рабочие планы |
| `dev/migr_log.md` | журнал миграции + итоги |
| `dev/tests_debug/*` | L1–L4 + гейт (+ RAG-проверки) |
| `dev/logs_reports/stages/*` | транскрипты живых прогонов (в т.ч. `rag_*`) |

---

## Порядок достижения итогового состояния

Порядок по зависимостям:

1. **Базовый агент** — память, профили, инварианты, машина состояний, LLM-клиент.
2. **MCP-слой** — контракты инструментов → реестр → `integrations/mcp/` → policy/executor
   → LLM tool-use → CLI (наследие).
3. **RAG-индексация** — `config` (валидация) → `corpus` → `chunking` (**overlap**) →
   `embedding` (Ollama) → `index` (нормализация 0..1).
4. **RAG-поиск** — `retrieval` (bm25|dense|hybrid → RRF) → `rerank` (bi-encoder→cross-encoder)
   → `cache` → `grounding` → `eval`/`compare`.
5. **RAG-ответ** — `service` (`answer(use_rag)`) → `context_block` → блок `[rag]` в
   `prompt_builder.py` → `agent.py` (две ветки ответа, grounding).
6. **CLI** — `Kod.py` (DI `RagService`, флаги `--rag*`, команды `/rag …`).
7. **Контрольный набор** — 10 вопросов в `queries.jsonl` (что ожидаем + источники) +
   сравнение качества.
8. **Финал** — прогон L1→L4 + гейт, метрики, живой прогон (Ollama + LLM), запись итога
   в `dev/migr_log.md`, предложение коммита (коммит — только по явной команде).

---

## Риски и откат

- **Регрессия базового агента** — RAG выключен по умолчанию (`--rag`): без флага поведение
  прежнее, `rag` не импортируется. Откат — не включать флаг.
- **Зависимость от Ollama** — при недоступности `127.0.0.1:11434` деградация на
  `HashingEmbedder`; юниты и гейт от Ollama не зависят. Откат — не использовать `--rag`.
- **Рваные чанки** — лечится обязательным **overlap**; параметры подбираются
  экспериментально под данные.
- **«Похожий, но нерелевантный» чанк** — лечится **реранкингом** (bi-encoder → cross-encoder).
- **Ответ «из головы»** — симптом неверной настройки RAG; лечится grounding (strict) и
  проверкой доли релевантных чанков.
- **Приватность** — эмбеддинги считаются локально; приватные данные не покидают машину.
- **Загрязнение рабочих данных** — тесты пишут только в `dev/tests_debug/.tmp/`.

---

## Известные шероховатости и заделы

- **Формат сдачи Дня 22 — код**; точные имена файлов отчёта в постановке не названы.
- Модель эмбеддингов конфигурируема: лекция использует `nomic-embed-text` (768), проект
  по умолчанию — `bge-m3` (1024); переключение бесшовно.
- Реранкинг реализован как интерфейс под cross-encoder с детерминированным офлайн-фолбэком
  (`LexicalReranker`) — для гейта без сети; живой cross-encoder подключается при наличии.
- `floats` нормализуются `0..1` (деление на максимум) перед сравнением — как на лекции.
- Задел: multi-query (`--rag-multi-query`), гибрид с cross-encoder вживую, мультимодальный
  RAG для устаревших форматов, автопрогон метрик сторонними моделями.
- `transition_log` растёт без ограничения (сжатие — задел).
- Изменения не закоммичены (коммит — только по явной команде пользователя).

---

## Результат

- **Функция реализована**: `вопрос → поиск релевантных чанков → объединение с вопросом →
  запрос к LLM` (`RagService.answer(use_rag)` + `LLMClient.complete`).
- **Два режима**: **без RAG** (вопрос → LLM; ответ из общего контекста, без источников) и
  **с RAG** (вопрос → поиск → блок `[rag]` со ссылками `[doc_id#chunk_id]` → LLM → ответ со
  ссылками + grounding).
- **Сравнение качества**: `/rag compare <вопрос>` и `--rag-compare` дают боковое сравнение
  двух ответов; на контрольном наборе — метрики **context relevance / faithfulness /
  answer correctness** (реализация — `rag/eval.py`, `rag/grounding.py`, `rag/compare.py`).
- **Мини-набор из 10 контрольных вопросов** по собственной базе: для каждого зафиксированы
  **что ожидаем** и **ожидаемые источники** (`rag/datasets/queries.jsonl`).
- **Локальность и приватность**: эмбеддинги — локально (Ollama, HTTP на `127.0.0.1:11434`).
- **Техника RAG**: чанкинг с **overlap** (500/50), нормализация векторов `0..1`,
  косинусное сходство, этап bi-encoder top-20 → реранкинг cross-encoder top-5.
- **Без регрессии**: RAG выключен по умолчанию; базовый агент, MCP-слой и машина состояний
  не тронуты; «RAG ≠ переход» (`TaskStage` не меняется от поиска).
- **Проверяемость**: L1–L4 и гейт — без живого ключа и сети; живой прогон (Ollama +
  реальный LLM) — отдельно, в приёмке.
