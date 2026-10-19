# migr_plan_2.md — Этап 2. Корпус, 10 контрольных вопросов, golden-запросы (О2)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (Ревизия 7, §4 «Этап 2»).
> Контур: **О (оснащение)**. Метка цели: **О2**. Зависимости: **этапы 0–1**.
> Порядок: **пошагово с оператором**. **Коммиты — только за оператором** (ШАГ 2.5).

## Цель этапа

**Проверить** требование «корпус 20–30 страниц» и **дополнить** измерительный материал:
добавить **10 контрольных вопросов** (часть 1 `Задание.txt`) к существующему golden-набору.

## Предусловия (Ревизия 6, проверено)

- `rag/datasets/corpus.list` — **9 файлов, 29.1 стр.** (в диапазоне 20–30);
- `rag/datasets/queries.jsonl` — **24 golden-запроса**, формат
  `{"id","query","relevant","must_contain"}`;
- чёрный список в `rag/corpus.py` (`.env`, `.ssh/`, `users/`, `.venv/`, `__pycache__/`,
  `rag/index/`, `*.db`) реализован.

## Границы этапа

- **Не** режем и не переписываем исходные документы корпуса.
- **Не** трогаем `rag/*.py` (только `datasets/`).
- **Не** удаляем существующие 24 golden-запроса — только добавляем.
- **Не** добавляем pip-зависимостей.

---

## Шаги

### ШАГ 2.1 — Проверка `corpus.list` (агент)

```bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
.venv/bin/python - <<'EOF'
from pathlib import Path
lines = [l.strip() for l in Path("rag/datasets/corpus.list").read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
miss = [p for p in lines if not Path(p).exists()]
chars = sum(len(Path(p).read_text(encoding="utf-8", errors="ignore")) for p in lines if Path(p).exists())
print("файлов:", len(lines), "| отсутствуют:", miss)
print("символов:", chars, "| ~страниц (chars/1800):", round(chars/1800, 1))
assert not miss, f"битые пути: {miss}"
assert 20 <= chars/1800 <= 30, "объём вне диапазона 20–30 стр."
print("OK: корпус в диапазоне 20–30 стр.")
EOF
```

### ШАГ 2.2 — Дополнение `queries.jsonl` 10 контрольными вопросами (агент)

Добавить 10 строк (формат части 1 — с полями `expect` и `relevant`):

```jsonl
{"id":"c01","query":"Как в проекте считается бюджет токенов для блоков промпта?","expect":"описание расчёта бюджета и порядка усечения блоков (RAG усекается первым)","relevant":["core/prompt_builder.py"],"must_contain":["бюджет","rag"]}
{"id":"c02","query":"Какие слои памяти есть у агента AI_9?","expect":"перечисление слоёв памяти (краткосрочная, рабочая, долгосрочная, профиль)","relevant":["memory/manager.py","README.md"],"must_contain":["память"]}
{"id":"c03","query":"Что такое ProposedAction и зачем нужен InvariantChecker?","expect":"описание предложенного действия и проверки инвариантов","relevant":["core/invariants.py"],"must_contain":["инвариант"]}
{"id":"c04","query":"Какие стадии жизненного цикла задачи (TaskStage) определены?","expect":"список стадий и допустимых переходов","relevant":["core/state_machine.py"],"must_contain":["TaskStage"]}
{"id":"c05","query":"Как устроен профиль-роутер и выбор профиля?","expect":"описание логики маршрутизации по профилям","relevant":["core/profile_router.py"],"must_contain":["профил"]}
{"id":"c06","query":"Как работает ретривер: режимы bm25, dense, hybrid?","expect":"описание трёх режимов и взвешенного RRF","relevant":["rag/retrieval.py"],"must_contain":["hybrid"]}
{"id":"c07","query":"Что делает реранкер LexicalReranker и почему вес 0.05?","expect":"мягкое смешивание с малым весом, чтобы не ухудшить hit-rate","relevant":["rag/rerank.py"],"must_contain":["rerank"]}
{"id":"c08","query":"Какие две стратегии чанкинга поддерживаются и чем различаются?","expect":"fixed и structural, различия по границам и метаданным","relevant":["rag/chunking.py"],"must_contain":["структур","fixed"]}
{"id":"c09","query":"Как устроено хранилище storage/store и где лежат данные пользователя?","expect":"описание storage/store.py и путей users/","relevant":["storage/store.py"],"must_contain":["storage"]}
{"id":"c10","query":"Что такое grounding и режим strict при работе RAG?","expect":"описание режимов off/warn/strict и авто-перегенерации","relevant":["rag/grounding.py"],"must_contain":["grounding"]}
```

> ⚠️ **Оператор:** пути `relevant` — предположительные; перед записью подтвердите, что
> указанные файлы действительно покрывают тему (иначе поправим на реальные сегменты
> корпуса). Вопросы — русские, формулировки **морфологически далеки** от текста.

Проверка:

```bash
.venv/bin/python - <<'EOF'
import json
from pathlib import Path
rows = [json.loads(l) for l in Path("rag/datasets/queries.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
ids = [r["id"] for r in rows]
assert len(ids) == len(set(ids)), "дубли id"
ctrl = [r for r in rows if "expect" in r]
print("всего запросов:", len(rows), "| контрольных (с expect):", len(ctrl))
assert len(ctrl) >= 10, "нужно ≥ 10 контрольных"
print("OK: queries.jsonl валиден")
EOF
```

### ШАГ 2.3 — Проверка чёрного списка `corpus.py` (агент)

```bash
grep -nE "\.env|\.ssh|users|\.venv|__pycache__|rag/index|\.db" rag/corpus.py | head
```

Ожидаемо: перечисленные шаблоны присутствуют в исключениях. При отсутствии —
дополнить и зафиксировать в журнале (правка `rag/corpus.py` — единственное
допустимое изменение кода на этом этапе, только если тест красный).

### ШАГ 2.4 — Запись в журнал + перечитывание плана

Внести запись «Этап 2» в `dev/migr_log.md` по шаблону §7.3: было (9 файлов/24 golden)
→ стало (9 файлов/24+10) → артефакты → гейт.

### ШАГ 2.5 — Предложение коммита (выполняет **только** оператор)

```
data(rag): 10 контрольных вопросов части 1 + проверка корпуса (этап 2, Ревизия 7)

Причина: часть 1 Задание.txt требует мини-набор из 10 контрольных вопросов (что
ожидаем в ответе + какие источники). Корпус Ревизии 6 (9 файлов, 29.1 стр.) уже в
диапазоне 20–30 — дополняем только измерительный материал (queries.jsonl).
```

---

## Выход этапа

- `rag/datasets/queries.jsonl` — **10 контрольных** (с `expect`/`relevant`) + 24 golden;
- подтверждено: `corpus.list` резолвится, объём 20–30 стр.;
- подтверждено: чёрный список `corpus.py` работает;
- запись «Этап 2» в `dev/migr_log.md`.

## Гейт 2→3 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `corpus.list` резолвится | 0 битых путей |
| 2 | объём корпуса | 20–30 стр. (число в журнале) |
| 3 | `queries.jsonl` — валидный JSONL | без ошибок парсинга |
| 4 | контрольных вопросов (с `expect`) | **≥ 10** |
| 5 | golden-запросов сохранено | **≥ 24** |
| 6 | каждый `relevant` встречается в корпусе | ✅ |
| 7 | чёрный список `corpus.py` | покрывает `.env/.ssh/users/.venv/__pycache__/rag-index/*.db` |
| 8 | `unit_runner.py`/`smoke.py`/`scenario.py`/`check_acceptance.sh` | без регрессии |
| 9 | `git diff --stat requirements.txt` | пусто |
| 10 | запись «Этап 2» + перечитывание `migr_plan.md` | ✅ |

## Откат

`git checkout -- rag/datasets/queries.jsonl` (или восстановление из бэкапа);
правка `corpus.py` — `git checkout -- rag/corpus.py`. Запись помечается ❌.

## Что передаём дальше

- **Этапу 7 (R5):** 10 контрольных вопросов — вход для `rag.compare` (два режима).
- **Этапу 9 (R7):** `expect`/`relevant` — эталон для `verify.py` (источники/цитаты).
- **Этапу 8 (R6):** тот же набор — для сравнения 4 режимов.
