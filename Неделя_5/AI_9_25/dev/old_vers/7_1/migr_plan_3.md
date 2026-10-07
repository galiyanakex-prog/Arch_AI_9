# migr_plan_3.md — Этап 3. Текст и чанкинг: две стратегии (R1)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (Ревизия 7, §4 «Этап 3»).
> Контур: **R (RAG-ядро)**. Метка цели: **R1**. Зависимости: **этап 2**.
> Порядок: **пошагово с оператором**. **Коммиты — только за оператором** (ШАГ 3.6).

## Цель этапа

**Проверить/адаптировать** существующие `rag/text.py` и `rag/chunking.py`: подтвердить,
что они дают **две стратегии** чанкинга (требование `Задание.txt`) с полными метаданными;
при расхождениях — дополнить, не ломая API.

> **Фундамент есть (Ревизия 6):** `rag/text.py` + `rag/chunking.py` реализованы;
> тесты `test_rag_text.py` (7) и `test_rag_chunking.py` (8) зелёные. **Ничего с нуля.**

## Предусловия

- `rag/text.py`, `rag/chunking.py`, `rag/stopwords_ru_en.txt` — на месте.
- `dev/tests_debug/unit/test_rag_text.py`, `test_rag_chunking.py` — зелёные (репер Ревизии 6).
- `rag/datasets/corpus.list` — резолвится (этап 2).

## Границы этапа

- **Не** трогаем `retrieval/rerank/index/embedding` (этапы 4–6).
- **Не** добавляем новых стратегий в гейт (S3 `semantic` — задел, не обязателен).
- **Не** меняем сигнатуры публичных функций без необходимости; при правке — обновить тесты.
- **Не** добавляем pip-зависимостей.

---

## Шаги

### ШАГ 3.1 — Аудит `text.py` (агент)

```bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
sed -n '1,60p' rag/text.py
grep -nE "def (normalize|tokenize|split_sentences|stem|estimate_tokens)" rag/text.py
```

Сверить с §4: NFKC + casefold + снятие пунктуации; сплит по предложениям
(`. ! ? …`, сокращения); эвристика токенов `len(text)/4`; лёгкий рус. стеммер + стоп-слова
из `stopwords_ru_en.txt`; отдельная нормализация для кода (идентификаторы регистрозависимо,
`snake_case` дробится). Зафиксировать расхождения в журнале.

### ШАГ 3.2 — Аудит `chunking.py`: две стратегии (агент)

```bash
grep -nE "def |fixed|structural|overlap|size|parent" rag/chunking.py | head -40
```

Сверить с таблицей стратегий:

| Код | Имя | Правила (ожидаемо) |
|---|---|---|
| **S1** | `fixed` | окно `size=300` токенов, `overlap=60` (20%); граница по концу предложения; хвост < 40 токенов → к предыдущему |
| **S2** | `structural` | границы по `#`…`######` и код/таблицы; секция > `size=400` → допил по предложениям, `overlap=15%`; код/таблицы **не режутся**; `parent-child` |
| S3 | `semantic` | задел (не в гейте) |

### ШАГ 3.3 — Проверка метаданных чанка (агент)

```bash
.venv/bin/python - <<'EOF'
from rag.chunking import chunk_document
from pathlib import Path
txt = Path("README.md").read_text(encoding="utf-8")
chunks = chunk_document("README.md", txt, strategy="structural")
need = {"chunk_id","doc_id","source","title","section","lines","content_type","tokens","sha1","strategy","parent_id"}
miss = [c for c in chunks if not need <= set(c.__dict__ if hasattr(c,'__dict__') else c)]
print("чанков:", len(chunks), "| без полных метаданных:", len(miss))
print("пример:", chunks[0])
assert not miss, "у чанка не хватает метаданных"
print("OK: метаданные заполнены")
EOF
```

Ожидаемо: `chunk_id` (`<doc_id>#<n>`), `doc_id` (sha1 пути), `source`, `title`, `section`
(`A > B > C`), `lines`, `content_type` (`text|code|table`), `tokens`, `sha1`, `strategy`,
`parent_id`.

### ШАГ 3.4 — Прогон двух стратегий на корпусе (агент)

```bash
.venv/bin/python - <<'EOF'
from pathlib import Path
from rag.chunking import chunk_document
lines = [l.strip() for l in Path("rag/datasets/corpus.list").read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
n_fixed = n_struct = 0
for p in lines:
    t = Path(p).read_text(encoding="utf-8", errors="ignore")
    n_fixed  += len(chunk_document(p, t, strategy="fixed"))
    n_struct += len(chunk_document(p, t, strategy="structural"))
print("fixed:", n_fixed, "| structural:", n_struct)
assert n_fixed != n_struct, "стратегии дают одинаковое число чанков — фиктивны"
print("OK: стратегии различаются")
EOF
```

### ШАГ 3.5 — Тесты контура (агент)

```bash
API_KEY=test-key .venv/bin/python dev/tests_debug/unit_runner.py 2>&1 | grep -iE "rag_text|rag_chunking|Итого"
```

Ожидаемо: `test_rag_text` (7) и `test_rag_chunking` (8) зелёные; итог без регрессии.

### ШАГ 3.6 — Запись в журнал + коммит (оператор)

Внести запись «Этап 3» в `dev/migr_log.md`. **Предлагаемый коммит:**

```
fix(rag): проверка/адаптация text.py + chunking.py (этап 3, Ревизия 7)

Причина: Задание.txt требует ≥ 2 стратегии чанкинга с полными метаданными.
Фундамент Ревизии 6 подтверждён (fixed/structural различаются, метаданные полные);
правки — только при выявленном расхождении.
```

---

## Выход этапа

- подтверждено: `text.py` даёт нормализацию/токенизацию/стемминг; `chunking.py` — **две**
  стратегии с полными метаданными; S1 ≠ S2 по числу чанков;
- тесты `test_rag_text.py`, `test_rag_chunking.py` — зелёные;
- запись «Этап 3» в `dev/migr_log.md`.

## Гейт 3→4 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | обе стратегии дают чанки на корпусе | n > 0 |
| 2 | метаданные у 100% чанков | нет пропусков |
| 3 | S1 ≠ S2 (число чанков) | различаются |
| 4 | `section` корректен для вложенных заголовков | тест зелёный |
| 5 | код/таблица не разрезаны | тест зелёный |
| 6 | `test_rag_text.py` / `test_rag_chunking.py` | 7 / 8 OK |
| 7 | `unit_runner.py` | без регрессии |
| 8 | `git diff --stat requirements.txt` | пусто |
| 9 | запись «Этап 3» + перечитывание `migr_plan.md` | ✅ |

## Откат

`git checkout -- rag/text.py rag/chunking.py dev/tests_debug/unit/test_rag_*.py`.
Запись помечается ❌ с причиной.

## Что передаём дальше

- **Этапу 4 (R2):** чанки с метаданными — вход для эмбеддингов.
- **Этапу 5 (R3):** `sha1` текста — ключ кэша эмбеддингов.
- **Этапу 8 (R6):** `section`/`title` — сигналы реранкера.
