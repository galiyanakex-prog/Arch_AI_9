# migr_plan_8.md — Этап 8. Часть 2: второй этап (reranker/фильтр) + query rewrite (R6)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (Ревизия 7, §4 «Этап 8»).
> Контур: **R (RAG-ядро)**. Метка цели: **R6**. Зависимости: **этапы 6–7**.
> Порядок: **пошагово с оператором**. **Коммиты — только за оператором** (ШАГ 8.8).

## Цель этапа

**Часть 2 `Задание.txt`:** второй этап после поиска (reranker или фильтр релевантности),
**порог отсечения**, **top-K до и после**, **сравнение** качества без фильтра/rewriting
и с фильтром. Добавить `rag/rewrite.py` (query rewrite) и режимы `rag_filter`,
`rag_filter_rewrite` в `compare.py`.

> **Фундамент есть:** `LexicalReranker` (Ревизия 6). **Новое:** фильтр по порогу,
> `rewrite.py`, `candidate_k`/`final_k`, 4 режима сравнения.

## Предусловия

- `rag/rerank.py` — `LexicalReranker` (вес 0.05) — этап 6 закрыт.
- `RagService.answer` + режимы `no_rag`/`rag` — этап 7 закрыт.
- 10 контрольных вопросов — этап 2 закрыт.

## Границы этапа

- **Не** реализуем cross-encoder (тяжёлые зависимости) — интерфейс `Reranker` оставлен.
- **Не** делаем обязательными источники/цитаты (этап 9).
- **Не** меняем веса RRF/reranker без замера.
- **Не** меняем `requirements.txt`.

---

## Шаги

### ШАГ 8.1 — Фильтр по порогу в ретривере (агент)

Добавить параметр `threshold` (в конфиг `rag/config.json` → `retrieval.threshold`) и
`candidate_k` (до фильтра) / `final_k` (после). Логика: из `candidate_k` кандидатов
(напр. 20) отсеять `score < threshold` → `final_k` (напр. 5). Если после фильтра пусто —
сигнал «не знаю» (готовит часть 3).

```bash
.venv/bin/python - <<'EOF'
from rag.service import RagService
from rag.config import RagConfig
svc = RagService(RagConfig.load("rag/config.json"))
hits = svc.search("несуществующая тема про квантовых китов", k=20, threshold=0.9)
print("после порога 0.9:", len(hits))
assert len(hits) == 0, "высокий порог должен отсечь всё"
print("OK: порог работает")
EOF
```

### ШАГ 8.2 — Модуль `rag/rewrite.py` (агент)

Реализовать `rewrite(query, history=None, llm=None, mode="heuristic") -> str`:
- `heuristic` — снятие «шумовых» фраз, добавление ключевых терминов из истории;
- `llm` — переформулирование через LLM (с учётом истории на этапе 11);
- по умолчанию `heuristic`.

Тест: `rewrite` **не ухудшает** recall@5 на golden (иначе остаётся выключенным).

### ШАГ 8.3 — top-K до/после в отчёте (агент)

В `compare.py` добавить колонки `candidate_k` (до фильтрации) и `final_k` (после);
оба — в конфиге и в отчёте.

### ШАГ 8.4 — Режимы `rag_filter` и `rag_filter_rewrite` (агент)

```bash
grep -nE "def compare|modes|no_rag|rag" rag/compare.py | head
```

Добавить в `compare.py` обработку `rag_filter` (порог + reranker) и `rag_filter_rewrite`
(+ rewrite). Итого 4 режима: `no_rag`, `rag`, `rag_filter`, `rag_filter_rewrite`.

### ШАГ 8.5 — Прогон сравнения 4 режимов (агент)

```bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
.venv/bin/python -m rag.compare \
  --queries rag/datasets/queries.jsonl \
  --modes no_rag,rag,rag_filter,rag_filter_rewrite --k 5 \
  --report dev/logs_reports/stages/rag_modes_compare.md
```

**Обязательный вывод:** 4 режима × 10 вопросов; колонки top-K до/после; **вердикт**
(режим с фильтром **не хуже** без фильтра по hit-rate@5); разбор расхождений.

### ШАГ 8.6 — Тесты `test_rag_rerank.py` (агент)

Создать `dev/tests_debug/unit/test_rag_rerank.py`:
- порог отсекает нерелевантное (hit-rate@5 не падает);
- `top-K_after ≤ top-K_before`;
- `rewrite` не ухудшает recall@5.

```bash
API_KEY=test-key .venv/bin/python dev/tests_debug/unit_runner.py 2>&1 | grep -iE "rag_rerank|rag_retrieval|Итого"
```

### ШАГ 8.7 — Замер порога (агент)

```bash
.venv/bin/python - <<'EOF'
from rag.service import RagService
from rag.config import RagConfig
svc = RagService(RagConfig.load("rag/config.json"))
rep = svc.evaluate(dataset="rag/datasets/queries.jsonl", k=5)
print("hit-rate@5 (с фильтром):", getattr(rep, "hit_rate", rep))
EOF
```

Ожидаемо: с фильтром **не хуже**, чем без (≥ 0.80).

### ШАГ 8.8 — Запись в журнал + коммит (оператор)

Запись «Этап 8» в `dev/migr_log.md`. **Предлагаемый коммит:**

```
feat(rag): фильтр по порогу + query rewrite + 4 режима сравнения (этап 8, Ревизия 7)

Причина: часть 2 Задание.txt — второй этап (reranker/фильтр), порог отсечения,
top-K до/после, сравнение с фильтром и без. Добавлены rewrite.py, режимы
rag_filter/rag_filter_rewrite; отчёт на 10 контрольных вопросах с колонками top-K.
```

---

## Выход этапа

- `rag/config.json` — `retrieval.threshold`, `candidate_k`, `final_k`;
- `rag/rewrite.py` — query rewrite (`llm|heuristic`);
- `rag/compare.py` — 4 режима + колонки top-K до/после;
- `dev/logs_reports/stages/rag_modes_compare.md` — 4 режима, вердикт;
- `dev/tests_debug/unit/test_rag_rerank.py` — зелёный;
- запись «Этап 8» в `dev/migr_log.md`.

## Гейт 8→9 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | порог отсекает нерелевантное | пустая выдача при высоком пороге |
| 2 | `top-K_after ≤ top-K_before` | ✅ |
| 3 | `rewrite` не ухудшает recall@5 | ✅ (иначе выключен) |
| 4 | 4 режима в отчёте | `no_rag`,`rag`,`rag_filter`,`rag_filter_rewrite` |
| 5 | колонки top-K до/после | присутствуют |
| 6 | режим с фильтром | **не хуже** без фильтра (hit-rate@5) |
| 7 | `test_rag_rerank.py` + `unit_runner.py` | зелёные, без регрессии |
| 8 | `git diff --stat requirements.txt` | пусто |
| 9 | запись «Этап 8» + перечитывание `migr_plan.md` | ✅ |

## Откат

`git checkout -- rag/rerank.py rag/rewrite.py rag/compare.py rag/config.json
dev/tests_debug/unit/test_rag_rerank.py`; отчёт удаляется. Запись ❌.

## Что передаём дальше

- **Этапу 9 (R7):** порог → режим «не знаю»; reranker/rewrite → источники/цитаты.
- **Этапу 11 (R9):** `rag_filter_rewrite` с учётом истории диалога.
