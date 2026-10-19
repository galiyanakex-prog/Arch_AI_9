# migr_plan_9.md — Этап 9. Часть 3: источники + цитаты + «не знаю» (R7)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (Ревизия 7, §4 «Этап 9»).
> Контур: **R (RAG-ядро)**. Метка цели: **R7**. Зависимости: **этапы 7–8**.
> Порядок: **пошагово с оператором**. **Коммиты — только за оператором** (ШАГ 9.8).

## Цель этапа

**Часть 3 `Задание.txt`:** ответ **обязательно** возвращает текст + **список источников**
(`source` + `section/chunk_id`) + **цитаты**; проверка на 10 вопросах (источники /
цитаты / совпадение смысла); правило **«не знаю»** при релевантности ниже порога.
Создать `rag/sources.py`, `rag/citations.py`, `rag/verify.py`; расширить `grounding.py`
и формат `Answer`.

> **Фундамент есть:** `grounding.py` (`ground`, `extract_citations`, `feedback_prompt`,
> `render_report`, `GroundingReport`) — Ревизия 6. **Новое:** обязательные `sources`/
> `quotes` в `Answer`, модули `sources`/`citations`/`verify`, режим «не знаю».

## Предусловия

- `Answer` (этап 7), порог/фильтр (этап 8), `grounding.py` (Ревизия 6).
- `Hit` содержит `chunk_id`, `doc_id`, `source`, `section`, `text`, `score` (types.py).
- 10 контрольных вопросов с `expect`/`relevant` (этап 2).

## Границы этапа

- **Не** реализуем cross-encoder; grounding — на эвристиках (стемы/сущности/числа).
- **Не** меняем retrieval/index.
- **Не** меняем `requirements.txt`.

---

## Шаги

### ШАГ 9.1 — Расширение `Answer` обязательными полями (агент)

```python
@dataclass(frozen=True)
class Source:
    source: str          # путь
    section: str         # A > B > C
    chunk_id: str        # doc_id#n
    score: float
    def to_dict(self) -> dict: ...

@dataclass(frozen=True)
class Quote:
    chunk_id: str
    text: str            # дословный фрагмент
    source: str
    def to_dict(self) -> dict: ...

@dataclass(frozen=True)
class Answer:
    text: str
    sources: list        # list[Source]
    quotes: list         # list[Quote]
    verdict: str         # ok | partial | hallucination | insufficient
    used_rag: bool = True
    latency_ms: float = 0.0
    def to_dict(self) -> dict: ...
```

Экспортировать `Source`, `Quote`, `Answer` в `rag/__init__.py` (`__all__`).

### ШАГ 9.2 — `rag/sources.py` (агент)

`build_sources(hits) -> list[Source]` — из `Hit` собрать источники: `source`, `section`,
`chunk_id` (`<doc_id>#<chunk_id>`), `score`. Дедуп по `chunk_id`; порядок — по убыванию
`score`.

### ШАГ 9.3 — `rag/citations.py` (агент)

`build_quotes(answer_text, hits, max_quotes=5) -> list[Quote]` — выбрать дословные
фрагменты найденных чанков, наиболее релевантные предложениям ответа (переиспользовать
`grounding._best_chunk`/`_stems`/`_entities`).

### ШАГ 9.4 — `rag/verify.py` (агент)

`verify_answer(answer, hits, queries) -> dict` — на 10 вопросах: есть ли источники,
есть ли цитаты, совпадает ли смысл ответа с цитатами. Отчёт →
`dev/logs_reports/stages/rag_verify_10q.md`.

### ШАГ 9.5 — Режим «не знаю» + строгий grounding (агент)

В `RagService.answer`: если `max(score) < threshold` (или после фильтра пусто) —
**без вызова LLM** вернуть `Answer(text="В источниках этого нет. Уточните вопрос…",
verdict="insufficient", sources=[], quotes=[])`. Режимы `grounding`: `off|warn|strict`
(**strict** по умолчанию при `--rag`): при `verdict=hallucination` — одна авто-перегенерация
с фидбэк-промптом (`grounding_feedback`), затем явная пометка.

### ШАГ 9.6 — Проверка на 10 вопросах (агент)

```bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
.venv/bin/python -m rag.verify --queries rag/datasets/queries.jsonl --k 5 \
  --report dev/logs_reports/stages/rag_verify_10q.md 2>&1 | tail -20
```

Ожидаемо: **источники в 10/10**, **цитаты в 10/10**, смысл совпадает.

### ШАГ 9.7 — Тесты (агент)

Создать `dev/tests_debug/unit/test_rag_verify.py` и дополнить `test_rag_grounding.py`:
- корректный ответ → `ok`;
- выдуманная дата/число → `hallucination`;
- ответ без ссылки → `partial`;
- слабый контекст → `insufficient` + «не знаю»;
- регистр/опечатки не ломают оценку.

```bash
API_KEY=test-key .venv/bin/python dev/tests_debug/unit_runner.py 2>&1 | grep -iE "rag_verify|rag_grounding|Итого"
```

### ШАГ 9.8 — Живой прогон + запись в журнал + коммит (оператор)

Живой прогон `--rag` (реальный LLM) на 3 запросах → в каждом ответе ссылки,
`verdict ≠ hallucination`; транскрипт `stages/rag_grounding_live.md`.
Запись «Этап 9» в `dev/migr_log.md`. **Предлагаемый коммит:**

```
feat(rag): источники + цитаты + режим «не знаю» (этап 9, Ревизия 7)

Причина: часть 3 Задание.txt — ответ обязан нести источники (source + section/chunk_id)
и цитаты; при слабом контексте — «не знаю». Добавлены sources.py/citations.py/verify.py,
обязательные поля Answer; отчёт на 10 вопросах (источники 10/10, цитаты 10/10).
```

---

## Выход этапа

- `rag/types.py` — `Source`, `Quote`, расширенный `Answer`;
- `rag/sources.py`, `rag/citations.py`, `rag/verify.py`;
- `rag/grounding.py` — режим `strict` (авто-перегенерация); `RagService.answer` — «не знаю»;
- `dev/logs_reports/stages/rag_verify_10q.md`, `rag_grounding_live.md`;
- `dev/tests_debug/unit/test_rag_verify.py` + дополнение `test_rag_grounding.py`;
- запись «Этап 9» в `dev/migr_log.md`.

## Гейт 9→10 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | источники в отчёте | **10/10** |
| 2 | цитаты в отчёте | **10/10** |
| 3 | смысл ответа совпадает с цитатами | ✅ |
| 4 | слабый контекст | `insufficient` + «не знаю», без LLM |
| 5 | живой прогон (3 запроса) | ссылки есть, `verdict ≠ hallucination` |
| 6 | `test_rag_verify.py` + `test_rag_grounding.py` | зелёные |
| 7 | `unit_runner.py` | без регрессии |
| 8 | `git diff --stat requirements.txt` | пусто |
| 9 | запись «Этап 9» + перечитывание `migr_plan.md` | ✅ |

## Откат

`git checkout -- rag/types.py rag/sources.py rag/citations.py rag/verify.py rag/grounding.py
rag/service.py rag/__init__.py dev/tests_debug/unit/test_rag_*.py`; отчёты удаляются. Запись ❌.

## Что передаём дальше

- **Этапу 10 (R8):** `Answer` с источниками/цитатами — формат ответа агента.
- **Этапу 11 (R9):** «не знаю» + уточнение в диалоге; источники в каждом ответе.
- **Этапу 12 (Ф):** отчёты `rag_verify_10q.md`, `rag_grounding_live.md` — в DoD.
