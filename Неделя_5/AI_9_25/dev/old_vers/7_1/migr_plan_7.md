# migr_plan_7.md — Этап 7. Часть 1: функция RAG + два режима + сравнение (R5)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (Ревизия 7, §4 «Этап 7»).
> Контур: **R (RAG-ядро)**. Метка цели: **R5**. Зависимости: **этапы 2, 6**.
> Порядок: **пошагово с оператором**. **Коммиты — только за оператором** (ШАГ 7.7).

## Цель этапа

**Часть 1 `Задание.txt`:** реализовать функцию «вопрос → поиск релевантных чанков →
объединение с вопросом → запрос к LLM» с **двумя режимами** (`use_rag=False/True`) и
**воспроизводимым сравнением** на **10 контрольных вопросах**.

> **Фундамент есть:** `RagService.search/context_block` (Ревизия 6). **Новое:** метод
> `answer(question, use_rag)` + расширение `compare.py` на режимы `no_rag`/`rag`.

## Предусловия

- `rag/service.py` — `search`, `context_block`, `evaluate`, `compare`, `ground` (Ревизия 6).
- `rag/datasets/queries.jsonl` — 10 контрольных + 24 golden (этап 2).
- LLM-клиент доступен (`core/llm_client.py` или через DI; mock-режим — `--mock`).

## Границы этапа

- **Не** реализуем фильтр/rewrite (этап 8) — режимы только `no_rag`/`rag`.
- **Не** реализуем источники/цитаты как обязательный формат (этап 9) — здесь `Answer`
  минимальный (`text` + `hits`), обязательные поля добавит этап 9.
- **Не** меняем `retrieval/rerank/index/embedding`.
- **Не** меняем `requirements.txt`.

---

## Шаги

### ШАГ 7.1 — Проектирование `Answer` (минимум части 1) (агент)

Добавить в `rag/types.py` (этап 9 расширит):

```python
@dataclass(frozen=True)
class Answer:
    text: str                       # ответ LLM
    used_rag: bool                  # режим
    hits: list                      # найденные чанки (для отчёта/источников)
    latency_ms: float = 0.0
    def to_dict(self) -> dict: ...
```

Экспортировать в `rag/__init__.py` (`__all__`).

### ШАГ 7.2 — Метод `RagService.answer` (агент)

```python
def answer(self, question: str, use_rag: bool = True, k: int = None,
           llm=None, mode: str = None) -> Answer:
    if not use_rag:
        text = _llm_complete(question, llm)          # без блока [rag]
        return Answer(text=text, used_rag=False, hits=[])
    hits = self.search(question, k=k, mode=mode)
    block = self.context_block(question, k=k)
    prompt = f"{question}\n\n{block}"
    text = _llm_complete(prompt, llm)
    return Answer(text=text, used_rag=True, hits=hits)
```

`_llm_complete` — тонкая обёртка: если `llm is None` и доступен `core.llm_client` —
использовать его; иначе вернуть детерминированную заглушку (для тестов без сети).
**RAG не импортирует `core/` напрямую** — LLM приходит через параметр/DI.

### ШАГ 7.3 — Расширение `compare.py` на режимы `no_rag`/`rag` (агент)

```bash
grep -nE "def compare|def main|--modes" rag/compare.py
```

Добавить обработку режимов `no_rag` (промпт без блока) и `rag` (с блоком); метрики:
попадание `must_contain`, наличие источников, три метрики качества (context relevance /
faithfulness / answer correctness — по канону `Суть_N5.md`), латентность.

### ШАГ 7.4 — Прогон сравнения двух режимов (агент)

```bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
.venv/bin/python -m rag.compare \
  --queries rag/datasets/queries.jsonl \
  --modes no_rag,rag --k 5 \
  --report dev/logs_reports/stages/rag_modes_compare.md
```

**Обязательный вывод:** таблица «вопрос × (без RAG / с RAG)», **вердикт** (где RAG
улучшил, где нет), **разбор 3 вопросов**, где режимы разошлись.

### ШАГ 7.5 — Тесты `test_rag_service.py` (агент)

Создать `dev/tests_debug/unit/test_rag_service.py`:
- `answer(use_rag=False)` — текст **не** содержит блока `[rag]`;
- `answer(use_rag=True)` — `hits` непусты; промпт содержит источники;
- пустой индекс → `answer(use_rag=True)` не падает (деградация к ответу без блока).

```bash
API_KEY=test-key .venv/bin/python dev/tests_debug/unit_runner.py 2>&1 | grep -iE "rag_service|Итого"
```

### ШАГ 7.6 — Проверка hit-rate@5 режима «с RAG» (агент)

```bash
.venv/bin/python - <<'EOF'
from rag.service import RagService
from rag.config import RagConfig
svc = RagService(RagConfig.load("rag/config.json"))
rep = svc.evaluate(dataset="rag/datasets/queries.jsonl", k=5)
hr = getattr(rep, "hit_rate", None)
print("hit-rate@5:", hr)
assert hr is None or hr >= 0.80, "hit-rate@5 < 0.80"
print("OK: качество retrieval достаточное")
EOF
```

### ШАГ 7.7 — Запись в журнал + коммит (оператор)

Запись «Этап 7» в `dev/migr_log.md` (со ссылкой на отчёт). **Предлагаемый коммит:**

```
feat(rag): функция answer (два режима) + сравнение no_rag/rag (этап 7, Ревизия 7)

Причина: часть 1 Задание.txt — «вопрос → поиск → объединение → LLM» и сравнение
ответов без RAG и с RAG. Добавлены RagService.answer(use_rag) и режимы в compare.py;
отчёт на 10 контрольных вопросах (rag_modes_compare.md), hit-rate@5 ≥ 0.80.
```

---

## Выход этапа

- `rag/types.py` — `Answer`; `rag/service.py` — `answer(use_rag)`;
- `rag/compare.py` — режимы `no_rag`/`rag`;
- `dev/logs_reports/stages/rag_modes_compare.md` — таблица + вердикт + разбор 3 расхождений;
- `dev/tests_debug/unit/test_rag_service.py` — зелёный;
- запись «Этап 7» в `dev/migr_log.md`.

## Гейт 7→8 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `answer(use_rag=False)` | нет блока `[rag]` |
| 2 | `answer(use_rag=True)` | есть `hits`, промпт с источниками |
| 3 | пустой индекс | ответ без RAG, не падение |
| 4 | `rag_modes_compare.md` | создан, есть таблица + вердикт |
| 5 | 10 контрольных вопросов | присутствуют (с `expect`/`relevant`) |
| 6 | hit-rate@5 (режим «с RAG») | **≥ 0.80** |
| 7 | разбор 3 расхождений | есть |
| 8 | `test_rag_service.py` + `unit_runner.py` | зелёные, без регрессии |
| 9 | `git diff --stat requirements.txt` | пусто |
| 10 | запись «Этап 7» + перечитывание `migr_plan.md` | ✅ |

## Откат

`git checkout -- rag/types.py rag/service.py rag/compare.py rag/__init__.py
dev/tests_debug/unit/test_rag_service.py`; отчёт удаляется. Запись ❌.

## Что передаём дальше

- **Этапу 8 (R6):** `answer` — база для режимов `rag_filter`/`rag_filter_rewrite`.
- **Этапу 9 (R7):** `Answer` расширяется обязательными `sources`/`quotes`/`verdict`.
- **Этапу 11 (R9):** `answer` вызывается в каждом обмене агента.
