# migr_plan_3.md — Этап 3. Текст и чанкинг: две стратегии (R1)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (Ревизия 6, §4 «Этап 3»).
> Контур: **R (реализация)**. Метка цели: **R1**. Зависимости: **этап 0** (контракты),
> **этап 2** (корпус). Порядок: **пошагово с оператором**.
> **Коммиты — только за оператором** (текст предложен в ШАГЕ 3.7).

## Цель этапа

Реализовать `rag/text.py` (нормализация/токенизация/стемминг) и `rag/chunking.py`
(**две стратегии** чанкинга — требование `Задание_d21.txt`) с полными метаданными.
Первый юнит-модуль RAG: `test_rag_text.py`, `test_rag_chunking.py`.

## Предусловия (выполнено)

- `rag/types.py` — `Chunk` заморожен (этап 0);
- `rag/config.py` — `ChunkingConfig` (`size_tokens=400`, `overlap_ratio=0.15`,
  `fixed_size_tokens=300`, `fixed_overlap_tokens=60`, `parent_max_tokens=1200`,
  `keep_code_whole=True`);
- `rag/datasets/corpus.list` — 9 файлов (этап 2);
- `rag/text.py`, `rag/chunking.py` — заглушки с `NotImplementedError`.

## Границы этапа

- **Не** считаем эмбеддинги (этап 4), **не** строим индекс (этап 5).
- **Не** трогаем `Kod.py`, `core/`, `storage/`, `memory/`, `integrations/`.
- **Не** добавляем pip-зависимостей (только stdlib).
- **Не** реализуем S3 `semantic` (задел, не в гейте).

---

## Шаги

### ШАГ 3.1 — `rag/text.py` (агент)

Публичный API (контракт этапа 0 сохраняется):

| Функция | Назначение |
|---|---|
| `normalize(text)` | NFKC + casefold + снятие пунктуации (для BM25) |
| `tokenize(text)` | список токенов (слова + числа) |
| `stem(word)` | лёгкий рус. стеммер (оконечные правила) |
| `split_sentences(text)` | сплит по `.` `!` `?` `…` с учётом сокращений |
| `est_tokens(text)` | эвристика `len(text)//4` (явно помечена как приближение) |
| `normalize_code(text)` | для кода: регистр сохраняется, `snake_case` дробится |
| `STOPWORDS` | стоп-слова RU+EN из `rag/stopwords_ru_en.txt` |

### ШАГ 3.2 — `rag/stopwords_ru_en.txt` (агент)

Список стоп-слов (RU + EN), по одному на строку, `#` — комментарий.

### ШАГ 3.3 — `rag/chunking.py` (агент)

| Код | Имя | Правила |
|---|---|---|
| **S1** | `fixed` | окно `size=300` токенов, `overlap=60`; граница — по концу предложения; хвост < 40 токенов → к предыдущему |
| **S2** | `structural` | границы по md-заголовкам и блокам кода/таблиц; секция > 400 → допил по предложениям с `overlap=15%`; код/таблицы **не режутся**; parent-child (родитель ≤ 1200) |
| S3 | `semantic` | задел (не в гейте) |

Контракт `doc` — dict: `{doc_id, source, title, text}`. Возврат — `list[Chunk]`.

### ШАГ 3.4 — `test_rag_text.py` (агент)

Проверки: `normalize` снимает регистр/пунктуацию; `tokenize` даёт слова; `stem`
сводит формы; `split_sentences` не рвёт сокращения; `est_tokens` ≈ len/4;
`normalize_code` сохраняет регистр и дробит `snake_case`.

### ШАГ 3.5 — `test_rag_chunking.py` (агент)

Проверки: обе стратегии дают чанки на реальном файле корпуса; метаданные заполнены
у 100%; длина в целевом диапазоне; overlap 10–20%; код-блок не разрезан; `section`
корректен для вложенных заголовков; пустой/битый файл не роняет; CRLF и BOM пережиты;
**S1 и S2 дают разное число чанков**.

### ШАГ 3.6 — Прогон тестов и гейт (агент)

`unit_runner.py test_rag_text`, `unit_runner.py test_rag_chunking`, затем полный
контур (регрессия).

### ШАГ 3.7 — Запись в журнал + перечитывание плана

---

## Выход этапа

- `rag/text.py`, `rag/chunking.py` — реализованы;
- `rag/stopwords_ru_en.txt` — создан;
- `dev/tests_debug/unit/test_rag_text.py`, `test_rag_chunking.py` — созданы;
- запись «Этап 3» в `dev/migr_log.md`;
- `requirements.txt`, `Kod.py`, `core/`, `storage/` — **не изменены**.

## Гейт 3→4 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `unit_runner.py test_rag_text` | все зелёные |
| 2 | `unit_runner.py test_rag_chunking` | все зелёные |
| 3 | обе стратегии дают чанки на корпусе | да |
| 4 | метаданные заполнены у 100% чанков | да |
| 5 | S1 и S2 дают **разное** число чанков | да |
| 6 | ни один код-блок не разрезан | да |
| 7 | L2/L3/L4/гейт | без регрессии (148+ OK / SMOKE OK / SCENARIO OK / 25 из 25) |
| 8 | `git diff --stat requirements.txt` | пусто |
| 9 | запись «Этап 3» + перечитывание `migr_plan.md` | ✅ |

## Откат

```bash
git checkout -- rag/text.py rag/chunking.py
rm -f rag/stopwords_ru_en.txt
rm -f dev/tests_debug/unit/test_rag_text.py dev/tests_debug/unit/test_rag_chunking.py
```

## Что передаём дальше

- **Этапу 4 (R2):** `Chunk.text` — вход для эмбеддера; `Chunk.sha1` — ключ кэша.
- **Этапу 5 (R3):** `chunk_document` — источник чанков для индекса.
- **Этапу 7 (R5):** обе стратегии — предмет сравнения на `queries.jsonl`.
