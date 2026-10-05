# stage_09_debug.md — Этап 9. Отладка (L1–L4 зелёные)

## Цикл отладки §6.1 — все уровни пройдены по порядку

| Уровень | Команда | exit | Итерации/правки |
|---|---|---|---|
| L1 | `$PY -m py_compile Kod.py core/*.py memory/*.py storage/*.py` | 0 | без правок (Этап 8) |
| L2 | `$PY $TST/unit_runner.py` | 0 | 31/31 OK; правки раннера/тестов-lm: передача tmp_path по сигнатуре; патч только requests.post (изоляция сети, Этап 4) |
| L3 | `API_KEY=test-key $PY $TST/smoke.py` | 0 | 1 правка: изоляция --memory-dir в /tmp (идемпотентность) |
| L4 | `API_KEY=test-key $PY $TST/scenario.py` | 0 | 1 правка: проверка влияния через memory_blocks (MockClient обрезает 80 симв.) |

Стоп-условия не достигнуты (итераций ≤ 5 на модуль; одинаковых трейсбеков подряд нет).

## Ошибки зафиксированы в errors/
- error_2026-09-17_scaffold_order.md (⚠️ обход — порядок создания кода).
- error_2026-09-17_live_call_llm.md (✅ исправлено — запрет сети в тестах LLM).

## Статус
✅ Этап 9 закрыт: L1–L4 exit 0. Следующий этап — Этап 10 «Финал»
(README.md, run.sh/.desktop, Проверка.md, check_acceptance.sh,
final_report.md).