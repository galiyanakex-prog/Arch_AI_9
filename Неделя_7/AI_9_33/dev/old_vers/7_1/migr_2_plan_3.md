# migr_2_plan_3.md — Этап 3. Живой прогон: `dialog_runner.py` → `goal`/`terms` (Ж1)

> Рабочий план **одного этапа** на основе `dev/migr_2_plan.md` (Ревизия 7.1, §4 «Этап 3»).
> Контур: **Ж (живой прогон)**. Метка цели: **Ж1**. Зависимости: **этап 0**.
> Порядок: **пошагово с оператором**. **Коммиты — только за оператором** (ШАГ 3.5).

## Цель этапа

**Решение оператора №17, Вариант (A).** Прогнать `dialog_runner.py` (живой LLM, ключ в
`.env`) и **подтвердить**, что в `working_memory.json` появились
`goal`/`terms`/`clarifications`/`constraints` — закрывает «НЕ ПРОВЕРЕНО» (Ш9).

> **Факт (Ш9):** код поддерживает поля (`memory/working.py`, `core/agent.py._update_task_memory`),
> сценарии A/B содержат триггер-фразы, но в единственном `working_memory.json` (w17) этих
> полей нет (файл старого прогона).

## Предусловия

- `memory/working.py` — поля `goal`/`clarifications`/`constraints`/`terms` (этап 11 Ревизии 7).
- `core/agent.py` — `_update_task_memory` (триггер-фразы), `_enrich_query`.
- `dev/tests_debug/scenario/scen_dialog_A.md` (12) и `scen_dialog_B.md` (13).
- `dev/tests_debug/dialog_runner.py` — прогон сценариев.
- Ключ LLM в `.env`; согласие оператора дано.

## Границы этапа

- **Не** меняем код — только прогон и фиксация.
- **Не** трогаем git и VPS.
- **Не** меняем `requirements.txt`.

---

## Шаги

### ШАГ 3.1 — Красная проверка (агент)

bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
grep -rE "\"goal\"|\"terms\"|\"clarifications\"" users/*/tasks/*/working_memory.json; echo "exit=$?"


Ожидаемо: пусто (exit 1) → полей на практике нет.

### ШАГ 3.2 — Живой прогон сценариев (агент)

bash
.venv/bin/python dev/tests_debug/dialog_runner.py 2>&1 | tee dev/logs_reports/stages/dialog_scenarios.md | tail -20


Ожидаемо: сценарии A (12) и B (13) прогнаны; источники в каждом ответе; цель/термины
зафиксированы; exit 0.

### ШАГ 3.3 — Зелёная проверка (агент)

bash
grep -rE "\"goal\"|\"terms\"|\"clarifications\"|\"constraints\"" users/*/tasks/*/working_memory.json


Ожидаемо: поля присутствуют; зафиксировать значения (цель диалога, термины RRF/grounding,
ограничения).

### ШАГ 3.4 — Перечитывание мастер-плана (агент)

Перечитать `dev/migr_2_plan.md` перед этапом 4.

### ШАГ 3.5 — Запись в журнал + коммит (оператор)

Запись «Ревизия 7.1 — Этап 3» в `dev/migr_log.md`: «НЕ ПРОВЕРЕНО» → **ПОДТВЕРЖДЕНО**
(путь к `working_memory.json` + поля). **Предлагаемый коммит:**


test(rag): живой прогон dialog_runner — goal/terms в working_memory.json (Ревизия 7.1, этап 3)

Причина: решение оператора №17 (Вариант A) — подтвердить поля памяти задачи на практике.


---

## Выход этапа

- `dev/logs_reports/stages/dialog_scenarios.md` — обновлён (живой прогон);
- `users/<user>/tasks/*/working_memory.json` — содержит `goal`/`terms`/`clarifications`;
- запись «Этап 3» в `dev/migr_log.md` («НЕ ПРОВЕРЕНО» → ПОДТВЕРЖДЕНО).

## Гейт 3→4 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | живой прогон `dialog_runner.py` | exit 0 |
| 2 | сценарии A/B | 12 и 13 сообщений |
| 3 | `goal` в `working_memory.json` | присутствует |
| 4 | `terms` в `working_memory.json` | присутствует |
| 5 | транскрипт `dialog_scenarios.md` | создан/обновлён |
| 6 | `unit_runner.py` | без регрессии |
| 7 | `git diff --stat requirements.txt` | пусто |
| 8 | запись «Этап 3» + перечитывание `migr_2_plan.md` | ✅ |

## Откат

Этап не меняет продукт; при красном гейте — запись помечается ⚠️, «НЕ ПРОВЕРЕНО»
сохраняется, повтор прогона.

## Что передаём дальше

- **Этапу 7 (Д3):** подтверждение полей → пометка в `migr_log.md` (пункт 17 закрыт).
