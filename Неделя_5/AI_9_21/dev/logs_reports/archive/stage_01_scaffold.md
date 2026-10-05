# stage_01_scaffold.md — Этап 1. Скаффолд

## Было
Каталоги `core/`, `memory/`, `storage/`, `dev/{meta_promt,tests_debug/unit,
tests_debug/smoke,tests_debug/scenario,logs_reports/{stages,errors}}` отсутствовали
частично; финальные артефакты (`README.md`, `run.sh`, `run.desktop`,
`Проверка.md`, `final_report.md`) и каталог `fixtures/` отсутствовали.

## Стало
Полный каркас дерева по arch_den_11.md §2.1 + §3.1:
- рабочие пакеты: `core/`, `memory/`, `storage/`; точка входа `Kod.py`;
- служебные: `dev/{meta_promt,tests_debug/{unit,smoke,scenario,fixtures},
  logs_reports/{stages,errors}}`;
- финальные артефакты-заглушки (непустыми станут на Этапе 10): `README.md`,
  `run.sh`, `run.desktop`, `dev/Проверка.md`,
  `dev/logs_reports/final_report.md`.

Примечание: рабочий код уже был на диске (создан в предыдущей сессии) — расхождение
зафиксировано в `errors/error_2026-09-17_scaffold_order.md` (⚠️ обход); код не
переписывается, сверяется на Этапах 2–8 по контрактам метапромтов.

## Проверка
`find .` (исключая users/, __pycache__) → все каркасные пути присутствуют; exit 0.

## Статус
✅ Этап 1 закрыт. Следующий этап — Этап 2 «Хранилище» (storage/*, сверка с
ПРОМТ_storage.md).