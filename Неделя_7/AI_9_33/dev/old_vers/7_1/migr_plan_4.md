# migr_plan_4.md — Этап 4. Эмбеддинги (R2)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (Ревизия 7, §4 «Этап 4»).
> Контур: **R (RAG-ядро)**. Метка цели: **R2**. Зависимости: **этап 3**, **этап 1** (Ollama).
> Порядок: **пошагово с оператором**. **Коммиты — только за оператором** (ШАГ 4.6).

## Цель этапа

**Проверить/адаптировать** `rag/embedding.py`: протокол `Embedder`
(`embed(texts) -> list[list[float]]`, `dim`, `model_id`) и реализации (`HashingEmbedder`,
`OllamaEmbedder`, `FakeEmbedder`, заглушка `SentenceTransformerEmbedder`), кэш и деградацию.

> **Фундамент есть (Ревизия 6):** `rag/embedding.py` реализован; `test_rag_embedding.py` (8)
> зелёные. **Ничего с нуля.**

## Предусловия

- Ollama active, `bge-m3` (dim 1024) — этап 1 закрыт.
- `rag/config.json → embedding` = `{provider: "ollama", model: "bge-m3", dim: 1024,
  url: "http://127.0.0.1:11434"}`.
- `rag/chunking.py` даёт чанки с `sha1` — этап 3 закрыт.

## Границы этапа

- **Не** трогаем `index/retrieval/rerank` (этапы 5–6).
- **Не** устанавливаем `sentence-transformers` (тяжёлая зависимость; заглушка остаётся).
- **Не** открываем сеть наружу: только `127.0.0.1:11434`.
- **Не** меняем `requirements.txt`.

---

## Шаги

### ШАГ 4.1 — Аудит протокола и реализаций (агент)

```bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
grep -nE "class |def (embed|dim|model_id)" rag/embedding.py | head -40
```

Сверить: `Embedder` (протокол), `HashingEmbedder` (char 3–5-граммы → blake2b → dim=256
→ L2-норма), `OllamaEmbedder` (`POST /api/embed`, `urllib`, таймаут, повтор ×2, батчи 32,
`keep_alive`), `FakeEmbedder`, `SentenceTransformerEmbedder` (заглушка →
`RagDependencyError`).

### ШАГ 4.2 — Юниты без Ollama (агент)

```bash
API_KEY=test-key .venv/bin/python dev/tests_debug/unit_runner.py 2>&1 | grep -iE "rag_embedding|Итого"
```

Ожидаемо: `test_rag_embedding` (8) зелёный. Проверки: детерминизм хэширующего (повтор ==
первый), косинус одинакового текста ≈ 1, разного < 0.9, `dim` стабилен, заглушка даёт
`RagDependencyError`, не-localhost URL отвергнут, `FakeEmbedder` воспроизводим.

### ШАГ 4.3 — Проверка валидации localhost (агент)

```bash
.venv/bin/python - <<'EOF'
from rag.embedding import OllamaEmbedder
try:
    OllamaEmbedder(model="bge-m3", dim=1024, url="http://0.0.0.0:11434")
    print("ОШИБКА: не-localhost не отвергнут")
except ValueError as e:
    print("OK: не-localhost отвергнут:", e)
EOF
```

### ШАГ 4.4 — Живая ветка: `OllamaEmbedder` на реальных чанках (агент)

```bash
.venv/bin/python - <<'EOF'
from pathlib import Path
from rag.chunking import chunk_document
from rag.embedding import OllamaEmbedder
txt = Path("README.md").read_text(encoding="utf-8")
chunks = [c.text if hasattr(c,'text') else c["text"] for c in chunk_document("README.md", txt, strategy="structural")][:3]
emb = OllamaEmbedder(model="bge-m3", dim=1024, url="http://127.0.0.1:11434")
vecs = emb.embed(chunks)
print("векторов:", len(vecs), "| dim:", len(vecs[0]))
assert len(vecs) == 3 and len(vecs[0]) == 1024, "ожидали 3×1024"
print("OK: OllamaEmbedder вернул 3×1024")
EOF
```

Транскрипт → `dev/logs_reports/stages/rag_embed_live.txt`.

### ШАГ 4.5 — Проверка деградации и кэша (агент)

```bash
.venv/bin/python - <<'EOF'
from rag.embedding import OllamaEmbedder, HashingEmbedder
# недоступный порт → деградация (зависит от реализации: warn + фолбэк)
emb = OllamaEmbedder(model="bge-m3", dim=1024, url="http://127.0.0.1:11435")
try:
    v = emb.embed(["тест"])
    print("деградация → dim:", len(v[0]))
except Exception as e:
    print("исключение (допустимо, если реализация так задумана):", type(e).__name__)
h = HashingEmbedder(dim=256)
a, b = h.embed(["одинаковый текст"])[0], h.embed(["одинаковый текст"])[0]
assert a == b, "хэширующий не детерминирован"
print("OK: HashingEmbedder детерминирован, dim=256")
EOF
```

### ШАГ 4.6 — Запись в журнал + коммит (оператор)

Запись «Этап 4» в `dev/migr_log.md`. **Предлагаемый коммит:**

```
fix(rag): проверка/адаптация embedding.py (этап 4, Ревизия 7)

Причина: этап 5 (индекс) опирается на контракт Embedder и кэш emb_cache.json.
Фундамент Ревизии 6 подтверждён: юниты без Ollama зелёные; живая ветка OllamaEmbedder
возвращает вектор dim=1024; не-localhost отвергается; деградация работает.
```

---

## Выход этапа

- подтверждён контракт `Embedder`; реализации работают; localhost-only валидация;
- живой транскрипт `stages/rag_embed_live.txt` (3×1024);
- `test_rag_embedding.py` — зелёный; запись «Этап 4» в журнале.

## Гейт 4→5 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `test_rag_embedding.py` | 8 OK (без Ollama) |
| 2 | детерминизм `HashingEmbedder` | повтор == первый |
| 3 | косинус одинакового/разного | ≈1 / <0.9 |
| 4 | не-localhost URL | `ValueError` |
| 5 | живая ветка `OllamaEmbedder` | 3 вектора × **1024** |
| 6 | деградация при недоступном сервисе | warn + фолбэк (или документированное исключение) |
| 7 | `unit_runner.py` | без регрессии |
| 8 | `git diff --stat requirements.txt` | пусто |
| 9 | запись «Этап 4» + перечитывание `migr_plan.md` | ✅ |

## Откат

`git checkout -- rag/embedding.py dev/tests_debug/unit/test_rag_embedding.py`. Запись ❌.

## Что передаём дальше

- **Этапу 5 (R3):** векторы `dim` из конфига + `model_id` — метаданные индекса.
- **Этапу 6 (R4):** dense-режим опирается на `vectors.bin`.
