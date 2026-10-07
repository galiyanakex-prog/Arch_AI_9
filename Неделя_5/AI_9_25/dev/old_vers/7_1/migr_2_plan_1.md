# migr_2_plan_1.md — Этап 1. Код: секция `rewrite` + `RewriteConfig` (К1)

> Рабочий план **одного этапа** на основе `dev/migr_2_plan.md` (Ревизия 7.1, §4 «Этап 1»).
> Контур: **К (код)**. Метка цели: **К1**. Зависимости: **этап 0**.
> Порядок: **пошагово с оператором**. **Коммиты — только за оператором** (ШАГ 1.6).

## Цель этапа

**Решение оператора №4, Вариант (B).** Добавить секцию `rewrite` в `rag/config.json` и
класс `RewriteConfig` в `rag/config.py` (единообразие с `unknown`/`retrieval`); rewrite
настраивается из конфига, а не только флагом `--rag-rewrite`.

> **Факт (Ш11):** секции `rewrite` в `rag/config.json` **нет**; класса `RewriteConfig` в
> `rag/config.py` **нет**; rewrite управляется флагом `--rag-rewrite` (`Kod.py:143`, `672–676`).

## Предусловия

- `rag/rewrite.py` — функция `rewrite(query, history, llm, mode)` (этап 8 Ревизии 7).
- `rag/config.py` — `RagConfig` + секции `retrieval`/`unknown` (образец для `rewrite`).
- `Kod.py` — флаг `--rag-rewrite {off,llm,heuristic}`.

## Границы этапа

- **Не** меняем логику `rewrite.py` (только конфигурируемость).
- **Не** делаем rewrite включённым по умолчанию (`enabled=false`).
- **Не** меняем `requirements.txt`.

---

## Шаги

### ШАГ 1.1 — Красная проверка (агент)

```bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
grep -n "rewrite" rag/config.json; echo "exit=$?"
grep -n "class RewriteConfig" rag/config.py; echo "exit=$?"
```

Ожидаемо: оба `grep` — пусто (exit 1) → расхождение воспроизведено.

### ШАГ 1.2 — Класс `RewriteConfig` в `rag/config.py` (агент)

Добавить по образцу `UnknownConfig`:

```python
@dataclass
class RewriteConfig:
    enabled: bool = False
    mode: str = "heuristic"   # heuristic | llm
```

- поле `rewrite: RewriteConfig` в `RagConfig`;
- слияние из JSON (`rag/config.json → "rewrite"`) и env (`AI9_RAG_REWRITE_MODE`);
- валидация `mode ∈ {heuristic, llm}` (иначе `RagConfigError`).

### ШАГ 1.3 — Секция `rewrite` в `rag/config.json` (агент)

```json
"rewrite": {
  "enabled": false,
  "mode": "heuristic"
}
```

### ШАГ 1.4 — Приоритет флага над конфигом в `Kod.py` (агент)

```bash
grep -n "rag_rewrite" Kod.py
```

- при `--rag-rewrite` — значение флага имеет приоритет (прежнее поведение не ломается);
- при отсутствии флага — значение из `rag/config.json → rewrite.mode`.

### ШАГ 1.5 — Тест `test_rag_rewrite_config.py` (агент)

Создать `dev/tests_debug/unit/test_rag_rewrite_config.py`:
- `RagConfig.load("rag/config.json")` даёт `rewrite.mode == "heuristic"`;
- env `AI9_RAG_REWRITE_MODE=llm` переопределяет;
- дефолт `heuristic`; `enabled=false` не включает rewrite;
- невалидный `mode` → `RagConfigError`.

```bash
env -u API_KEY .venv/bin/python dev/tests_debug/unit_runner.py 2>&1 | grep -iE "rewrite_config|Итого"
```

### ШАГ 1.6 — Запись в журнал + коммит (оператор)

Запись «Ревизия 7.1 — Этап 1» в `dev/migr_log.md`. **Предлагаемый коммит:**

```
feat(rag): секция rewrite + RewriteConfig в конфиге (Ревизия 7.1, этап 1)

Причина: решение оператора №4 (Вариант B) — rewrite настраивается из конфига,
единообразно с unknown/retrieval; флаг --rag-rewrite сохраняет приоритет.
```

---

## Выход этапа

- `rag/config.py` — класс `RewriteConfig` + поле в `RagConfig`;
- `rag/config.json` — секция `rewrite`;
- `Kod.py` — приоритет флага над конфигом;
- `dev/tests_debug/unit/test_rag_rewrite_config.py` — зелёный;
- запись «Этап 1» в `dev/migr_log.md`.

## Гейт 1→2 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `grep -n "rewrite" rag/config.json` | секция есть |
| 2 | `RewriteConfig` импортируется | ✅ |
| 3 | `rewrite.mode` из конфига | `heuristic` |
| 4 | env `AI9_RAG_REWRITE_MODE` | переопределяет |
| 5 | `--rag-rewrite` приоритет | прежнее поведение |
| 6 | `test_rag_rewrite_config.py` + `unit_runner.py` | зелёные, без регрессии |
| 7 | `git diff --stat requirements.txt` | пусто |
| 8 | запись «Этап 1» + перечитывание `migr_2_plan.md` | ✅ |

## Откат

`git checkout -- rag/config.py rag/config.json Kod.py dev/tests_debug/unit/test_rag_rewrite_config.py`;
запись ❌.

## Что передаём дальше

- **Этапу 5 (Д1):** README может упомянуть секцию `rewrite` в конфиге.
- **Этапу 2 (К2):** независимая правка кода (метрика стабильности).
