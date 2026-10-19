# migr_plan_6.md — Этап 6. Ретривер (R4)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (Ревизия 7, §4 «Этап 6»).
> Контур: **R (RAG-ядро)**. Метка цели: **R4**. Зависимости: **этап 5**.
> Порядок: **пошагово с оператором**. **Коммиты — только за оператором** (ШАГ 6.6).

## Цель этапа

**Проверить/адаптировать** `rag/retrieval.py` + `rag/rerank.py`: три режима
(`bm25`/`dense`/`hybrid`), взвешенный RRF, `LexicalReranker`, MMR, фильтры, дедуп
≤ 2 чанка/док, объяснимость (`Hit.scores`).

> **Фундамент есть (Ревизия 6):** `rag/retrieval.py` + `rag/rerank.py` реализованы;
> `test_rag_retrieval.py` (7) зелёные. Реальный hit-rate@5 = **0.9167**. **Ничего с нуля.**

## Предусловия

- `rag/index/` — этап 5 закрыт (постинги + векторы + метаданные).
- `rag/stopwords_ru_en.txt` — на месте.
- `rag/cache.py` — LRU 256 + TTL 900 + инвалидация по mtime (проверяется здесь).

## Границы этапа

- **Не** трогаем `service/compare` (этапы 7–8) — только ретривер.
- **Не** меняем веса RRF/reranker без замера (иначе рискуем hit-rate).
- **Не** меняем `requirements.txt`.

---

## Шаги

### ШАГ 6.1 — Аудит режимов и фьюжна (агент)

```bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
grep -nE "def |bm25|dense|hybrid|RRF|rrf|MMR|mmr|weight|k1|b=" rag/retrieval.py | head -50
grep -nE "def |class |weight|mix" rag/rerank.py | head -30
```

Сверить: BM25 (`k1=1.2`, `b=0.75`) → top-50; Dense (косинус блоками 1024) → top-50;
Hybrid — **взвешенный RRF** `Σ w_i/(60 + rank_i)`, `w_bm25=0.1`, `w_dense=1.0` →
top-20 → `LexicalReranker` (мягкое смешивание, вес 0.05) → MMR (`λ=0.7`) → top-k с
дедупом **≤ 2/док**.

### ШАГ 6.2 — Юниты ретривера (агент)

```bash
API_KEY=test-key .venv/bin/python dev/tests_debug/unit_runner.py 2>&1 | grep -iE "rag_retrieval|rag_cache|Итого"
```

Ожидаемо: `test_rag_retrieval` (7) и `test_rag_cache` — зелёные. Проверки: точное
совпадение идентификатора (`build_agent`) в top-3; гибрид не хуже каждой компоненты по
recall@5; MMR уменьшает долю повторов документа; фильтр `content_type="code"` не отдаёт
прозу; пустой запрос → понятная ошибка.

### ШАГ 6.3 — CLI-прогон ретривера (агент)

```bash
.venv/bin/python -m rag.retrieval --query "как считается бюджет токенов" --mode hybrid --k 5 2>&1 | head -30
```

Ожидаемо: top-k с метаданными и скорами (`bm25_rank`, `dense_rank`, `rrf`, `rerank`,
`source_query`). Повторить для `--mode bm25` и `--mode dense`.

### ШАГ 6.4 — Замер hit-rate@5 на golden-датасете (агент)

```bash
.venv/bin/python - <<'EOF'
from rag.service import RagService
from rag.config import RagConfig
svc = RagService(RagConfig.load("rag/config.json"))
rep = svc.evaluate(dataset="rag/datasets/queries.jsonl", k=5)
print("hit-rate@5:", getattr(rep, "hit_rate", rep))
EOF
```

Ожидаемо: **≥ 0.80** (репер Ревизии 6 — 0.9167). Если ниже — разобрать регресс
(веса/стемминг/дедуп) до перехода к этапу 7.

### ШАГ 6.5 — Проверка объяснимости и дедупа (агент)

```bash
.venv/bin/python - <<'EOF'
from rag.service import RagService
from rag.config import RagConfig
svc = RagService(RagConfig.load("rag/config.json"))
hits = svc.search("retrieval hybrid rrf", k=5, mode="hybrid")
from collections import Counter
c = Counter(h.source for h in hits)
print("доков:", len(c), "| максимум на док:", max(c.values()))
print("scores[0]:", hits[0].scores)
assert max(c.values()) <= 2, "дедуп ≤2/док нарушен"
print("OK: дедуп и скоpы в порядке")
EOF
```

### ШАГ 6.6 — Запись в журнал + коммит (оператор)

Запись «Этап 6» в `dev/migr_log.md`. **Предлагаемый коммит:**

```
fix(rag): проверка/адаптация retrieval.py + rerank.py (этап 6, Ревизия 7)

Причина: части 1–2 Задание.txt опираются на три режима поиска и честный фьюжн.
Фундамент Ревизии 6 подтверждён: bm25/dense/hybrid работают, взвешенный RRF,
MMR, дедуп ≤2/док, hit-rate@5 ≥ 0.80; скоры объяснимы.
```

---

## Выход этапа

- подтверждены три режима, взвешенный RRF, reranker, MMR, дедуп, объяснимость;
- hit-rate@5 ≥ 0.80; `test_rag_retrieval.py` зелёный; запись «Этап 6» в журнале.

## Гейт 6→7 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `-m rag.retrieval --mode bm25/dense/hybrid` | все три печатают top-k |
| 2 | `Hit.scores` | содержит `bm25_rank`,`dense_rank`,`rrf`,`rerank` |
| 3 | дедуп | ≤ 2 чанка/док |
| 4 | MMR | снижает долю повторов документа |
| 5 | фильтр `content_type=code` | не отдаёт прозу |
| 6 | hit-rate@5 (golden) | **≥ 0.80** |
| 7 | `test_rag_retrieval.py`/`test_rag_cache.py` | OK |
| 8 | `unit_runner.py` | без регрессии |
| 9 | `git diff --stat requirements.txt` | пусто |
| 10 | запись «Этап 6» + перечитывание `migr_plan.md` | ✅ |

## Откат

`git checkout -- rag/retrieval.py rag/rerank.py rag/cache.py dev/tests_debug/unit/test_rag_*.py`.
Запись ❌.

## Что передаём дальше

- **Этапу 7 (R5):** `search` — ядро функции `answer` (часть 1).
- **Этапу 8 (R6):** порог отсечения и rewrite строятся поверх ранжирования.
- **Этапу 9 (R7):** `Hit.scores` — основа для источников/цитат/grounding.
