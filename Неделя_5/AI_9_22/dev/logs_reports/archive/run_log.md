# run_log.md — сводный журнал прогонов проекта

> Сводный журнал создания проекта. Команда → результат → exit-код.
> Последний выполненный этап определяется по этому файлу и `stages/` (не по памяти).

## Переменные проекта (§2.1 START-PROMT.md)

| Переменная | Значение (вычислено на хосте) |
|---|---|
| `AI9_ROOT` | /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9 |
| `KOD` | /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9/Nedela_3/den_12 |
| `DEV` | $KOD/dev |
| `MP` | $DEV/meta_promt |
| `LOGS` | $DEV/logs_reports |
| `TST` | $DEV/tests_debug |
| `VENV_ACT` | $AI9_ROOT/.venv/bin/activate |
| `PY` | $AI9_ROOT/.venv/bin/python |
| `META` | $AI9_ROOT/МЕТА-ПРОМТ_den_N.md |
| `DONOR` | $AI9_ROOT/Nedela_2/den_10/den_10_Kod.py |
| `MODEL` | stepfun/step-3.5-flash |

Хост-порядок (запрещён хардкод): пути выше выведены в этой сессии через `git rev-parse --show-toplevel`,
на другом хосте вычисляются заново по §2.1. Литералы в этой таблице — фиксация для аудита текущей сессии.

## Этап 0. Окружение — статус ✅

- `$PY --version` → Python 3.13.5 (exit 0).
- `$VENV_ACT` → существует (exit 0).
- Зависимости: `requests` 2.34.2 ✅, `dotenv` ✅, `pytest` ❌ отсутствует.
  - Решение (§6.1): юнит-уровень L2 выполняется `$PY $TST/unit_runner.py` (допустимая альтернатива),
    `pytest` не устанавливаем — venv недели не должен зависеть от лишних пакетов.
- Справочные файлы — все на месте: Step-3.5-Flash_params.md, МЕТА-ПРОМТ_den_N.md, DONOR,
  Суть_N3.md, Задание_Д12.txt, arch_den_11.md, arch_den_11_plan_2.md.

### Флаги koda для субагентов (§5 START-PROMT)

`koda run` — такого сабкоманды нет. Неинтерактивный запуск: `koda --prompt "..."` либо
`koda -p "..."` (вход задачи) + `-y/--yolo` (авто-одобрение). Рабочая форма:

```bash
cd "$KOD"
koda --yolo -p "$MP/ПРОМТ_<часть>.md"
```

`<флаг входа файла>` = `-p/--prompt`; `<флаг авто-одобрения>` = `-y/--yolo`.
ЗАФИКСИРОВАНО и используется неизменно далее.

## Журнал этапов

| Этап | Задача | Команда/проверка | exit | Статус |
|---|---|---|---|---|
| 0 | Окружение + метапромты | `$PY --version`, deps, `koda --help`; 8 метапромтов в $MP | 0 | ✅ |
| 1 | Скаффолд | `find .` — каркас дерева полный; созданы README/.sh/.desktop/Проверка/final_report/fixtures | 0 | ✅ |
| 2 | Хранилище | `$PY $TST/unit_runner.py test_storage` — сверка с ПРОМТ_storage.md | 0 | ✅ |
| 3 | Память | `$PY $TST/unit_runner.py test_memory` — сверка с ПРОМТ_memory.md | 0 | ✅ |
| 4 | LLM-клиент | `env -u API_KEY $PY $TST/unit_runner.py test_llm` — заглушка requests, без сети | 0 | ✅ |
| 5 | PromptBuilder | `$PY $TST/unit_runner.py test_prompt` — сверка с ПРОМТ_prompt.md | 0 | ✅ |
| 6 | Агент | `$PY $TST/unit_runner.py test_agent` — сверка с ПРОМТ_agent.md | 0 | ✅ |
| 7 | State machine | `$PY $TST/unit_runner.py test_state` — сверка с ПРОМТ_state.md | 0 | ✅ |
| 8 | CLI | L1 `py_compile` всей сборки; сверка с ПРОМТ_cli.md | 0 | ✅ |
| 9 | Отладка | L1–L4: unit_runner/smoke/scenario все exit 0 | 0 | ✅ |
| 10 | Финал | README/run.sh/run.desktop/Проверка.md/final_report; `API_KEY=test-key bash $TST/check_acceptance.sh` → 9/9 | 0 | ✅ |
| 11 | Живой смоук | требует явного согласия пользователя на живые вызовы (§3) | — | ⏸ отложен |
| E | Персонализация (ПРОМТ_person.md, фазы A–D) | L1 OK; L2 `unit_runner.py` → 40 OK / 0 FAIL (вкл. test_person 9); L3 smoke OK; L4 scenario → 6/6 (вкл. scenario_personalization); гейт `check_acceptance.sh` → 9 из 9 | 0 | ✅ |

## Инцидент безопасности 2026-09-18

При `bash -x check_acceptance.sh` строка `echo (API_KEY=$API_KEY)` вывела реальный
ключ в локальный stdout. Ключ из вывода чекера убран; в сеть/коммиты не попадал.
Подробности — final_report.md §5. Рекомендация: ротация ключа при подозрении.