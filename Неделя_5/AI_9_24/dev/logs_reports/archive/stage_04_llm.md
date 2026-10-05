# stage_04_llm.md — Этап 4. LLM-клиент (core/llm_client.py)

## Было
`core/llm_client.py` существовал (LLMClient ABC + RouterAIClient + MockClient), но:
- тест `test_router_client_needs_key` совершал ЖИВОЙ сетевой вызов (в окружении
  активной сессии CLI был реальный API_KEY) — нарушение §3;
- константы MODEL/URL/цены/окно в клиенте не были заведены явно (часть — только в
  Kod.py/доноре).

## Стало
- Контракт `LLMClient (ABC)` + `RouterAIClient` + `MockClient` (детерминированный,
  отражает слои/сообщения) — соответствует `ПРОМТ_llm.md`.
- Константы в клиенте: URL, MODEL, REQUEST_TIMEOUT, RETRY_DELAYS (п.16).
- Тесты LLM переведены на заглушку `requests` (§7 п.17): живой сети НЕ происходит.
  Проверены: абстрактность ABC; детерминизм MockClient; отражение слоёв; обработка
  сетевой ошибки → None; разбор choices; исчерпание 429 → None.

## Ошибки (зафиксированы в errors/)
1. `error_2026-09-17_live_call_llm.md` — случайный живой вызов (✅ исправлено: запрет
   сети в тестах через заглушку requests, прогоны LLM-тестов выполняются с `env -u API_KEY`).
2. Технические правки раннера/тестов: раннер передаёт tmp_path только если тест его
   принимает; патч только `requests.post` (иначе requests.exceptions становился MagicMock).
   Это правка ТЕСТОВ (§6.1: правки не ослабляют проверку, а усиливают изоляцию).

## Проверка
`env -u API_KEY && $PY dev/tests_debug/unit_runner.py test_llm` → 6 OK, 0 FAIL, exit 0.

## Статус
✅ Этап 4 закрыт. Следующий этап — Этап 5 «Prompt» (core/prompt_builder.py, сверка с
ПРОМТ_prompt.md).