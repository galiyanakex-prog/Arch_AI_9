# stage_F_state.md — Этап F: Task State Machine (отчёт по форме «было → стало → проверка → статус»)

> Артефакт процесса миграции `den_13` на `ND/arch/arch_den_13.md`.
> Заполняется по ходу выполнения рабочих планов `dev/migr_plan_0.md` … `dev/migr_plan_8.md`.
> Основной журнал результатов — `dev/migr_log.md`; здесь — свод «было/стало» по Этапу F.

---

## 1. Было (базовая линия, зафиксирована 2026-09-20, подшаг 0.1)

Проект `den_13` — копия `den_12` (персонализация + модель памяти) без переименований.

| Компонент | Состояние «до» |
|---|---|
| `core/state_machine.py` | **задел**: `class TaskState(Enum)` — 4 стадии (planning/execution/validation/done); `ALLOWED_TRANSITIONS` (4 ключа, без paused/failed); `next_state(current, target) -> bool`. **Нет** dataclass, паузы, resume, персистентности, цикла исполнения |
| `storage/store.py` | фасад иерархии `users/<id>/…`: profile(s), long_term, working, sessions_resume, session, list_tasks. **Не знает** `task_state.json` |
| `memory/working.py` | `as_prompt_block()` даёт строку `Стадия задачи: {current_state}` (зеркало из `working_memory.json`); `write()` умеет ветку `current_state` |
| `core/agent.py` | `identify / interview_questions / initialize_user / load_state / switch_profile / build_context / respond / remember_message / switch_task / save_state` + `active_profile / auto_route / router`. **Нет** жизненного цикла задачи |
| `Kod.py` | REPL: `/memory /profile(6 подкоманд) /tasks /task /deliver /compare /summary /state /tokens /cost /help /exit`; `show_state()` печатает 4 стадии задела; 11 флагов |
| `dev/tests_debug/` | L2 `unit_runner.py` — 40 тестов в 7 модулях (вкл. `test_state.py` — 4 теста задела); L3 `smoke.py`; L4 `scenario.py` — 6 сценариев; гейт `check_acceptance.sh` — 9 проверок |

**Прогон базовой линии (подшаг 0.1), 2026-09-20:**

| Проверка | Команда | Результат |
|---|---|---|
| L2 unit | `env -u API_KEY $PY dev/tests_debug/unit_runner.py` | **40 OK, 0 FAIL**, EXIT 0 |
| L4 scenario | `env API_KEY=test-key $PY dev/tests_debug/scenario.py` | **6 сценариев OK**, EXIT 0 |
| Гейт | `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` | **9 из 9 зелёные (FAIL=0)**, EXIT 0 |

---

## 2. Регресс-лист: 22 прежних критерия приёмки (не ломать)

Источник: `den_12/dev/Проверка.md` (в `den_13/dev/` файл **отсутствует** — см. §4, расхождение R1).

| № | Критерий | Чем проверяется | Влияние Этапа F |
|---|---|---|---|
| 1 | Комплектность и сборка | `py_compile Kod.py core/*.py memory/*.py storage/*.py`; README, run.sh (+x), run.desktop | гейт [1] — следить на каждом этапе |
| 2 | 4 типа памяти — разные классы/файлы | `test_memory.py::test_four_layers_present` | нет |
| 3 | Иерархия хранилища по канону | `test_storage.py` (7 тестов) | **дополняется** `task_state.json` (Этап 2) — только добавление методов |
| 4 | Явная маршрутизация «что куда» | `test_memory.py::test_remember_routes_explicitly` | нет |
| 5 | Дозированная доставка | `test_prompt.py::test_dosed_delivery_cut_layer`; `/deliver` | нет |
| 6 | Идентификация на старте | smoke (`--user` / ввод до загрузки) | нет |
| 7 | Интервью-инициализация | `test_agent.py::test_interview_initialization`; `scenario_interview` | нет |
| 8 | Понятие таски + переход | `test_agent.py::test_switch_task`; `/tasks`, `/task` | **дополняется**: `switch_task()` + `load_task_state()` (Этап 4.5) |
| 9 | Промт явными блоками | `test_prompt.py::test_blocks_order` | `BLOCK_ORDER` не меняется; состояние — внутри блока `working` |
| 10 | LLM за интерфейсом (ABC + RouterAI + Mock) | `test_llm.py` (6) | нет (MockClient используется как executor) |
| 11 | Задел state machine | `test_state.py` (4) | **меняется**: миграция имён `TaskState`→`TaskStage`, `next_state`→`transition` (Этап 6.1); между Этапами 1 и 6 — статус ⚠ |
| 12 | Resume | `test_agent.py::test_resume_known_user`; `scenario_resume` | нет (resume сессии ≠ resume автомата — разные сущности) |
| 13 | Неизменяемые сообщения с `parent_id` | `test_memory.py::test_short_term_append_and_parent` | нет |
| 14 | Демонстрации задания | `/compare`; `scenario.py` | **дополняется** `scenario_pause_resume` (Этап 6.3) |
| 15 | Текстовое описание модели памяти | README «Модель памяти» | **дополняется** раздел «Состояние задачи» (Этап 7.1) |
| 16 | Уроки дня 10 перенесены | `Kod.py`: errors="replace", readline, CSV; retry 429; BASE_DIR | нет |
| 17 | Тесты без живого ключа | `API_KEY=test-key`, `MockClient` | **усиливается**: автомат тестируется на заглушках |
| 18 | Фильтр инвариантов НЕ реализуем | задел `PolicyEngine` в `memory/base.py` | нет |
| 19 | `Проверка.md` только в `dev/` | `ls ./Проверка.md` → нет файла | нет (гейт [9]) |
| 20 | Несколько профилей на пользователя | `test_person.py::test_multi_profile_roundtrip`; `/profile list\|show\|use\|new` | нет |
| 21 | Миграция и обратная совместимость | `test_migration_old_schema`, `test_backward_compatibility` | нет |
| 22 | Роутер и авто-выбор профиля | `test_person.py::test_router_*`, `test_agent_*`, `test_two_profiles_different_answers`; `scenario_personalization` | нет |

**Новые критерии Этапа F** (`arch_den_13.md` §4.3): 23 — формализованное состояние
(этап/шаг/ожидаемое действие); 24 — пауза на любом этапе + продолжение без повторных
объяснений; 25 — персистентность и жизненный цикл (save/load, перезапуск, шаги не
повторяются, переходы по `ALLOWED_TRANSITIONS`).

---

## 3. Карта точек вставки (подшаг 0.3)

### 3.1 `core/state_machine.py` (Этап 1) — полная переработка файла (28 строк сейчас)
| Что | Где | Действие |
|---|---|---|
| `class TaskState(Enum)` (4 стадии) | строки 11–15 | **заменить** на `class TaskStage(str, Enum)` — 6 этапов (+PAUSED, +FAILED) |
| `ALLOWED_TRANSITIONS` | строки 19–24 | **переписать** на ключи `TaskStage`, добавить paused/failed-ветки по §2.3 |
| `next_state()` | строки 27–29 | **сохранить как обёртку** над `transition()` (совместимость до Этапа 6.1) |
| `@dataclass TaskState` | — | **добавить** (9 полей канона задания) |
| `transition(state, target) -> bool` | — | **добавить** (единственная точка смены этапа + лог «[Автомат]») |
| `pause_task` / `resume_task` | — | **добавить** (идемпотентные, по канону задания) |
| `save_state` / `load_state` | — | **добавить** (JSON, enum → `.value`, битый файл → None) |
| `run_task(state, executor, validator)` | — | **добавить** (один проход автомата, §2.4) |
| импорты | строка 8 (`from enum import Enum`) | **дополнить**: `dataclasses`, `json`, `typing.Any`, `os` |

⚠ Конфликт имён: `TaskState` сейчас — Enum, по канону задания — dataclass. Enum
переименовывается в `TaskStage` (как в задании); `Kod.py` строка 60
(`from core.state_machine import TaskState, ALLOWED_TRANSITIONS`) и `show_state()`
(строки ~370) требуют правки на Этапе 5.3.

### 3.2 `storage/store.py` (Этап 2) — только добавление
| Что | Где | Действие |
|---|---|---|
| docstring-дерево | строки 4–16 | **дополнить** строкой `task_state.json` в блоке `tasks/<task_name>/` |
| новая секция | после «--- Рабочая память ---» (`write_working`, ~строка 175) | **добавить** секцию «--- Состояние задачи (state machine) ---»: `task_state_path()`, `read_task_state()`, `write_task_state()` |
| существующие методы | — | **не трогать** (регресс-запрет, 7 тестов storage) |

Образец стиля: `working_path/read_working/write_working` (путь → read с дефолтом →
write через `ensure_task` + `write_json`).

### 3.3 `memory/working.py` (Этап 3) — только `as_prompt_block()`
| Что | Где | Действие |
|---|---|---|
| `as_prompt_block()` | последние ~18 строк файла | **дополнить**: чтение `store.read_task_state(ctx.user_id, ctx.task)` → строки «Этап: … (шаг N/M): …», «Ожидаемое действие: …», «Пауза (вернуться к: …)», «Ошибка: …» |
| строка `Стадия задачи: {current_state}` | конец `as_prompt_block()` | **сохранить** (обратная совместимость, критерий 9/15) |
| `read()` / `write()` | начало класса | **не менять** (контракт `MemoryLayer`); ветка `current_state` в `write()` уже есть — зеркало пишется из `Agent._persist_task_state()` (решение подшага 3.2) |

### 3.4 `core/agent.py` (Этап 4)
| Что | Где | Действие |
|---|---|---|
| импорты | строки 22–27 | **дополнить**: `from core.state_machine import TaskStage, TaskState, run_task, pause_task, resume_task, transition` |
| `__init__` | после `self.initialized = False` (~строка 70) | **добавить** `self.task_state: TaskState \| None = None` |
| `load_state(user_id)` | ~строки 130–140 | **дополнить** вызовом `self.load_task_state()` в конце |
| новая секция «Жизненный цикл задачи» | после `switch_profile` / перед `build_context` | **добавить**: `load_task_state()`, `start_task()`, `_persist_task_state()`, `step_task()`, `run_to_end()`, `pause()`, `resume()`, `retry_task()` + класс `LLMExecutor` |
| `switch_task()` | `self.task = new_task` (~строка 215) | **дополнить** вызовом `self.load_task_state()` после смены задачи |
| `save_state()` | конец файла (~строки 225–236) | **дополнить** сейвом `task_state.json` |
| `respond()` | ~строки 155–180 | **не менять** (блок working уже несёт этап/шаг после Этапа 3) |

### 3.5 `Kod.py` (Этап 5)
| Что | Где | Действие |
|---|---|---|
| импорт | строка 60: `from core.state_machine import TaskState, ALLOWED_TRANSITIONS` | **заменить** на `TaskStage, TaskState, ALLOWED_TRANSITIONS` |
| `show_state()` | раздел 12 (~строки 368–374) | **переписать**: снимок `agent.task_state` + карта переходов по `TaskStage`; нужна передача `agent` в функцию |
| if-цепочка команд | после `/task` (~строка 430) и до `/deliver` | **добавить** обработчики `/plan`, `/step`, `/run`, `/pause`, `/resume`; ветку `retry` — в обработчик `/task` |
| `print_help()` | раздел 10 (~строки 175–195) | **дополнить** 6 новыми командами |
| стартовая печать «Команды: …» | ~строка 400 | **дополнить** новыми командами |
| `--fresh` | `main()`, ~строка 385 | **дополнить**: не восстанавливать `task_state.json` |
| `/exit`, `EOFError`, `KeyboardInterrupt` | `agent.save_state()` | **не менять** (сейв `task_state.json` — внутри `save_state()`, Этап 4.5) |

---

## 4. Расхождения плана и фактического состояния (найдено в подшаге 0.2/0.3)

| № | Расхождение | Влияние | Решение |
|---|---|---|---|
| R1 | В `den_13/dev/` **отсутствуют** `Проверка.md`, `FINAL_REV.md`, `meta_promt/`, `logs_reports/`, `tests_debug/scenario/`, `tests_debug/fixtures/` — хотя `README.md` (строки 321, 354, 388, 408) на них ссылается, а `arch_den_13.md` §3.1 описывает как часть итогового дерева. Донор: `den_12/dev/` (там `Проверка.md` — 22 критерия, `meta_promt/` — 10 файлов, `logs_reports/` — run_log + final_report) | Этап 7: подшаги 7.2/7.3 — не «правка», а **создание** файлов (копия из `den_12` + адаптация под Д13); гейт [9] «в корне дня нет Проверка.md» остаётся зелёным | `migr_plan_7.md` скорректирован: донор `den_12/dev/Проверка.md` (22 строки) → добавить строки 23–25; `FINAL_REV.md`/`ПРОМТ_fsm.md` — создать |
| R2 | `dev/logs_reports/` не существует → некуда писать `stage_F_state.md`, `run_log.md`, `errors/` | Этап 0.2 | каталоги созданы при выполнении подшага 0.2 (`stages/`, `errors/`) |
| R3 | `Kod.py` импортирует `TaskState` как Enum; после Этапа 1 `TaskState` — dataclass | Этапы 1 и 5 | на Этапе 1 `next_state()` сохраняется обёрткой, но **импорт `TaskState` в `Kod.py` сломает `show_state()`** (итерация по dataclass). Решение: на Этапе 1 добавить алиас `TaskStateEnum = TaskStage` **не требуется** — вместо этого правка импорта и `show_state()` переносится в Этап 1 (подшаг 1.1, минимально: `from core.state_machine import TaskStage, ALLOWED_TRANSITIONS` + `show_state()` по `TaskStage`), чтобы `py_compile`/гейт [1] и smoke не падали между этапами |
| R4 | `dev/tests_debug/.tmp/` содержит ~150 каталогов от предыдущих прогонов (не очищается) | не блокирует | очистка не требуется (`.tmp/` в .gitignore); при желании — убрать перед Этапом 8 |

---

## 5. Стало (заполняется по ходу Этапов 1–8)

| Компонент | Было | Стало | Проверка | Статус |
|---|---|---|---|---|
| `core/state_machine.py` | задел: Enum 4 стадии + `next_state()` | | | ⏳ Этап 1 |
| `storage/store.py` | не знает `task_state.json` | | | ⏳ Этап 2 |
| `memory/working.py` | строка «Стадия задачи» | | | ⏳ Этап 3 |
| `core/agent.py` | нет жизненного цикла | | | ⏳ Этап 4 |
| `Kod.py` | 12 команд, `/state` — 4 стадии | | | ⏳ Этап 5 |
| `dev/tests_debug/` | L2 40 / L4 6 / гейт 9 | | | ⏳ Этап 6 |
| Документация | README без раздела «Состояние задачи» | | | ⏳ Этап 7 |
| Приёмка | 22 критерия | | | ⏳ Этап 8 |
