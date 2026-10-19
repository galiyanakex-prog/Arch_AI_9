# stage_05_prompt.md — Этап 5. PromptBuilder (core/prompt_builder.py)

## Было
`core/prompt_builder.py` существовал: роль + слои + summary + short_term + query, с
бюджетом. Были мелкие излишки (неиспользуемые `add()`, `profile_ctx`) и не было
явной привязки `BLOCK_ORDER`/«резерва» в комментарии.

## Стало
Сверено с `ПРОМТ_prompt.md`:
- `BLOCK_ORDER` = роль → profile → long_term → working → summary → short_term → current;
- `PromptBuilder.build(ctx, deliver, budget)` собирает блоки в каноническом порядке;
- дозированная доставка: набор слоёв — параметр, невыбранный слой не попадает;
- бюджет: обязательные блоки (роль, текущий запрос) не урезаются, необязательные
  опускаются по порядку при превышении;
- убран мёртвый код (`add`, `profile_ctx`) без изменения контракта.

## Проверка
`$PY dev/tests_debug/unit_runner.py test_prompt` → 4 OK, 0 FAIL, exit 0.

## Статус
✅ Этап 5 закрыт. Следующий этап — Этап 6 «Агент» (core/agent.py, сверка с
ПРОМТ_agent.md).