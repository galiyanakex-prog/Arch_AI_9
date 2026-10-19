# migr_plan_5.md — Этап 5. Индекс и персистентность (R3)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (Ревизия 7, §4 «Этап 5»).
> Контур: **R (RAG-ядро)**. Метка цели: **R3**. Зависимости: **этапы 3–4**.
> Порядок: **пошагово с оператором**. **Коммиты — только за оператором** (ШАГ 5.6).

## Цель этапа

**Проверить/адаптировать** `rag/index.py` + `rag/corpus.py`: артефакты в `rag/index/`
(`postings.json`, `vectors.bin`, `chunks.json`, `meta.json`), инкрементальная индексация,
устойчивость к сбоям/рассинхрону конфига.

> **Фундамент есть (Ревизия 6):** `rag/index.py` + `rag/corpus.py` реализованы;
> `test_rag_index.py` (9) зелёные. `rag/index/` содержит 5 артефактов. **Ничего с нуля.**

## Предусловия

- `rag/embedding.py` — этап 4 закрыт (векторы `dim`, `model_id`).
- `storage/store.py` содержит RAG-корень (проверялось в Ревизии 6).
- `rag/index/` в `.gitignore`.

## Границы этапа

- **Не** трогаем `retrieval/rerank` (этап 6).
- **Не** коммитим `rag/index/` (в `.gitignore`).
- **Не** меняем `requirements.txt`.

---

## Шаги

### ШАГ 5.1 — Аудит артефактов (агент)

```bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
ls -la rag/index/
.venv/bin/python - <<'EOF'
import json
from pathlib import Path
meta = json.loads(Path("rag/index/meta.json").read_text(encoding="utf-8"))
print("meta:", {k: meta.get(k) for k in ("model_id","dim","n_docs","n_chunks","chunker_version","strategy")})
post = json.loads(Path("rag/index/postings.json").read_text(encoding="utf-8"))
print("терминов в postings:", len(post.get("postings", post)))
EOF
```

Ожидаемо: `meta.json` содержит `model_id`, `dim`, `n_docs`, `n_chunks`, `chunker_version`,
`strategy`; `postings.json` — термины; `vectors.bin` — `array('f')` row-major.

### ШАГ 5.2 — Проверка целостности и загрузки (агент)

```bash
.venv/bin/python - <<'EOF'
from rag.index import load_index   # имя может отличаться — уточнить по модулю
try:
    idx = load_index("rag/index")
    print("загружен:", type(idx).__name__)
except Exception as e:
    print("проверить API загрузки:", type(e).__name__, e)
EOF
```

> ⚠️ Уточнить фактическое имя функции загрузки/сохранения по `grep -nE "def " rag/index.py`.

### ШАГ 5.3 — Round-trip BM25 (агент)

```bash
.venv/bin/python - <<'EOF'
from rag.index import BM25Index   # уточнить по модулю
import json
from pathlib import Path
post = json.loads(Path("rag/index/postings.json").read_text(encoding="utf-8"))
print("OK: postings читается; структура верхнего уровня:", list(post)[:5])
EOF
```

Цель — подтвердить, что сохранённая выдача BM25 воспроизводима после повторной загрузки.

### ШАГ 5.4 — Инкрементальная индексация (агент)

```bash
API_KEY=test-key .venv/bin/python dev/tests_debug/unit_runner.py 2>&1 | grep -iE "rag_index|Итого"
```

Ожидаемо: `test_rag_index` (9) зелёный. Проверки: round-trip, инкрементальность
(изменён 1 файл из N → пересчитан только он — по счётчику эмбеддингов), ребилд при смене
`model_id`, пустой индекс не роняет поиск.

### ШАГ 5.5 — Устойчивость записи (агент)

```bash
grep -nE "os\.replace|tmp|NamedTemporary" rag/index.py
```

Ожидаемо: запись через `tmp + os.replace` (атомарность); при расхождении `meta.json` с
`RagConfig` — полный ребилд; битый `postings.json` → ребилд с предупреждением.

### ШАГ 5.6 — Запись в журнал + коммит (оператор)

Запись «Этап 5» в `dev/migr_log.md`. **Предлагаемый коммит:**

```
fix(rag): проверка/адаптация index.py + corpus.py (этап 5, Ревизия 7)

Причина: индекс должен переживать перезапуск и не переэмбеддить не изменившиеся чанки.
Фундамент Ревизии 6 подтверждён: артефакты на месте, round-trip и инкрементальность
зелёные, запись атомарна, ребилд по рассинхрону конфига.
```

---

## Выход этапа

- подтверждено: `rag/index/` (5 артефактов), round-trip BM25, инкрементальность, ребилд;
- `test_rag_index.py` — зелёный; запись «Этап 5» в журнале.

## Гейт 5→6 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | артефакты `rag/index/` | 5 файлов |
| 2 | `meta.json` | `model_id`, `dim`, `n_docs`, `n_chunks` присутствуют |
| 3 | round-trip BM25 | выдача идентична после перезагрузки |
| 4 | инкрементальность | пересчитан только изменённый файл |
| 5 | ребилд при смене `model_id` | ✅ |
| 6 | `test_rag_index.py` | 9 OK |
| 7 | `unit_runner.py` | без регрессии |
| 8 | `git status rag/index/` | пусто (в `.gitignore`) |
| 9 | `git diff --stat requirements.txt` | пусто |
| 10 | запись «Этап 5» + перечитывание `migr_plan.md` | ✅ |

## Откат

`git checkout -- rag/index.py rag/corpus.py dev/tests_debug/unit/test_rag_index.py`;
`rag/index/` пересобирается повторной индексацией. Запись ❌.

## Что передаём дальше

- **Этапу 6 (R4):** индекс (постинги + векторы) — вход для ретривера.
- **Этапу 10 (R8):** `storage/store.py` — RAG-корень для агента.
