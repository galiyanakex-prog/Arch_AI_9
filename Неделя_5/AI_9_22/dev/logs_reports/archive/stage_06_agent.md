# stage_06_agent.md — Этап 6. Агент (core/agent.py)

## Было
`core/agent.py` существовал (Agent + PromptContext), но не был сверен с обновлённым
метапромтом (поля deliver/session_id/message_counter/initialized, механика switch_task).

## Стало
Свёрено с `ПРОМТ_agent.md`. Покрытие:
- PromptContext объявлен в agent.py (владелец); PromptBuilder его потребляет;
- поля агента: user_id, task, deliver (set, default все 4 слоя), session_id,
  message_counter, initialized — есть;
- жизненный цикл: identify (по profile_repo.exists), interview_questions (стиль/
  констрейнты/контекст), initialize_user (профиль + дерево + первая задача),
  load_state (профиль + long-term + список задач), build_context (build_blocks(deliver)
  + short_term окно 10 + summary), respond (remember → build → complete → remember ответ);
- switch_task: отметка перехода в рабочей памяти + новая задача в working и long_term
  со ссылкой на сессию-источник; save_state (lifecycle_summary + sessions_resume.md).

## Проверка
`$PY dev/tests_debug/unit_runner.py test_agent` → 4 OK, 0 FAIL, exit 0:
интервью создаёт дерево; respond маршрутизирует в session.json; load_state
восстанавливает task; switch_task фиксирует переход и ссылку.

## Статус
✅ Этап 6 закрыт. Следующий этап — Этап 7 «State machine» (core/state_machine.py,
сверка с ПРОМТ_state.md).