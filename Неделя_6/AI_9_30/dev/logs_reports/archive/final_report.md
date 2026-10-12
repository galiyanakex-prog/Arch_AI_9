# final_report.md — День 11 «Модель памяти агента»: финальный отчёт

Дата: 2026-09-18. Статус: ✅ финал закрыт (Этап 11 — живой смоук — ⏸ отложен,
финал не блокирует).

## 1. Что построено

Переход от «одного снимка состояния» (день 10) к явной модели памяти:
4 слоя (short_term / working / long_term / profile), физически раздельное
хранение, явная маршрутизация записи через `MemoryManager.remember(layer, ...)`
с логом «куда легло», дозированная доставка в промт (`deliver: set`),
задел task state machine (`core/state_machine.py`).

Иерархия хранения (канон куратора):

```
users/<user_id>/
├── profile.json                 # зеркало профиля (авторитет — SQLite profiles)
├── long_term_memory.json        # profile_ref + задачи + решения + знания
└── tasks/<task_name>/
    ├── working_memory.json      # пересчитываемое состояние задачи
    ├── sessions_resume.md
    └── sessions/<session_id>/session.json   # неизменяемые сообщения, parent_id
```

## 2. Архитектура

| Модуль | Файлы | Назначение |
|---|---|---|
| CLI/DI | `Kod.py` | REPL, флаги, токен-учёт/CSV, уроки дня 10 |
| Ядро | `core/agent.py`, `core/prompt_builder.py`, `core/llm_client.py`, `core/state_machine.py` | агентный цикл, блоки промта, LLM-интерфейс (RouterAI + Mock), FSM задач |
| Память | `memory/{base,short_term,working,long_term,profile,manager}.py` | слои + менеджер + PolicyEngine-задел |
| Хранилище | `storage/store.py`, `storage/db.py` | фасад иерархии, ProfileRepository (SQLite) |

## 3. Таблица приёмки (§7 п.1–19)

| № | Критерий | Статус | Артефакт/проверка |
|---|---|---|---|
| 1 | Комплектность, сборка | ✅ | check_acceptance.sh [1–4]; L1 exit 0 |
| 2 | 3+ типа памяти, разные классы/файлы | ✅ | test_memory.py::test_four_layers_present |
| 3 | Иерархия по канону | ✅ | test_storage.py (7 тестов) |
| 4 | Явная маршрутизация + лог | ✅ | test_remember_routes_explicitly; `[Память] … ← …` |
| 5 | Дозированная доставка | ✅ | test_dosed_delivery_cut_layer; /deliver |
| 6 | Идентификация на старте | ✅ | smoke.py CLI (--user / ввод) |
| 7 | Интервью нового ID | ✅ | test_interview_initialization; scenario_interview |
| 8 | Таски + переход | ✅ | test_switch_task; /tasks /task |
| 9 | Промт явными блоками | ✅ | test_blocks_order |
| 10 | LLM за интерфейсом | ✅ | test_llm.py (6 тестов, без сети) |
| 11 | Задел state machine | ✅ | test_state.py (4 теста) |
| 12 | Resume | ✅ | test_resume_known_user; scenario_resume |
| 13 | Сообщения неизменяемы, parent_id; рабочая ≠ лог | ✅ | test_short_term_append_and_parent |
| 14 | Демонстрации задания | ✅ | /compare; scenario.py 5/5; smoke.py exit 0 |
| 15 | Текстовое описание модели памяти | ✅ | README.md «Модель памяти» |
| 16 | Уроки дня 10 перенесены | ✅ | readline, errors=replace, BASE_DIR, retry 429, CSV токенов |
| 17 | Тесты без живого ключа | ✅ | L2/L3/L4 на test-key/MockClient |
| 18 | Фильтр инвариантов — задел | ✅ | PolicyEngine + visibility/scope в memory/base.py |
| 19 | Проверка.md только в dev | ✅ | check_acceptance.sh [9] |

Итог чекера: **9 из 9 зелёные, exit 0** (прогон 2026-09-18, идемпотентен, /tmp).

## 4. Прогоны отладки (Этап 9, §6.1)

| Уровень | Команда | Результат |
|---|---|---|
| L1 | `$PY -m py_compile Kod.py core/*.py memory/*.py storage/*.py` | exit 0 |
| L2 | `$PY $TST/unit_runner.py` | 31/31 OK, exit 0 |
| L3 | `API_KEY=test-key $PY $TST/smoke.py` | exit 0 |
| L4 | `API_KEY=test-key $PY $TST/scenario.py` | 5/5 OK, exit 0 |

Ошибки этапов: `errors/error_2026-09-17_scaffold_order.md` (⚠️ обход),
`errors/error_2026-09-17_live_call_llm.md` (✅ исправлено).

## 5. Инцидент безопасности (зафиксирован)

При трассировке `bash -x check_acceptance.sh` в stdout попал реальный API_KEY
(строка `echo "=== Приёмка дня 11 (API_KEY=$API_KEY) ==="`). Устранено: ключ из
вывода убран; чекер больше не печатает значения переменных окружения. Ключ не
коммитился и не уходил в сеть (вывод локальный). Рекомендация: при подозрении на
компрометацию — ротация ключа routerai.ru.

## 6. Этап 11 — живой смоук

⏸ Отложен: требует явного согласия пользователя на живые LLM-вызовы (§3).
Сценарий готов к запуску: `./run.sh --user <id>` (без --mock), 2–3 обмена,
/memory, /compare, /tokens, /exit. Финал это не блокирует.