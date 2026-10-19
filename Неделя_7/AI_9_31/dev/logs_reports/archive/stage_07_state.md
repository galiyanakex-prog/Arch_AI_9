# stage_07_state.md — Этап 7. State machine (core/state_machine.py)

## Было
`core/state_machine.py` существовал (TaskState + ALLOWED_TRANSITIONS + next_state).

## Стало
Сверено с `ПРОМТ_state.md`:
- `TaskState` — ровно 4 стадии planning/execution/validation/done (канон, §4.8 п.1);
- `ALLOWED_TRANSITIONS` — разрешённые переходы по §3.4;
- `next_state(current, target)` — вспомогательная проверка, логика переходов не ведётся;
- текущая стадия хранится в рабочей памяти (`working_memory.json → current_state`,
  default "planning") — реализовано на слое WorkingMemory (Этап 3).

## Проверка
`$PY dev/tests_debug/unit_runner.py test_state` → 4 OK, 0 FAIL, exit 0.

## Статус
✅ Этап 7 закрыт. Следующий этап — Этап 8 «CLI» (Kod.py, сверка с
ПРОМТ_cli.md).