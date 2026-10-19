# stage_03_memory.md — Этап 3. Память (memory/*)

## Было
Файлы `memory/*` существовали (созданы в предыдущей сессии), но не были сверены с
обновлённым метапромтом (добавлены PolicyEngine, сигнатуры 4 слоёв, инварианты).

## Стало
Сверено с `ПРОМТ_memory.md` (актуализирован на Этапе 0). Покрытие:
- `MemoryContext`, `MemoryItem` (source/scope/owner/visibility/source_message_id/role),
  `MemoryLayer` (ABC: read/write/as_prompt_block), `PolicyEngine` (задел п.18);
- 4 слоя — `short_term` (append-only, parent_id, окно SHORT_TERM_WINDOW=10),
  `working` (пересчитываемое состояние: description/refs/lifecycle_summary/
  decisions/constraints/facts/open_questions/current_state), `long_term`
  (profile_ref как ССЫЛКА + tasks/decisions/knowledge), `profile`
  (style/constraints/context, запись MERGE);
- `MemoryManager` (remember с логом «куда легло», recall/build_blocks — дозированная
  доставка, report) + `LAYER_ORDER` + `default_layers`.

Инварианты подтверждены тестами: 4 класса с разными layer_name; remember маршрутизирует
в свой файл; build_blocks не подмешивает невыбранный слой; сообщения неизменяемы с
parent_id; профиль в SQLite; report содержит все слои.

## Проверка
`$PY dev/tests_debug/unit_runner.py test_memory` → 6 OK, 0 FAIL, exit 0.

## Статус
✅ Этап 3 закрыт. Следующий этап — Этап 4 «LLM-клиент» (core/llm_client.py, сверка с
ПРОМТ_llm.md).