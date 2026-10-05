# migr_plan_0.md — рабочий план этапа M0 (Базовая линия Ревизии 4 и инвентаризация)

> **Роль документа.** Рабочий план-алгоритм **одного этапа** миграции `den_18`
> под требования Дня 18. Подчинён плану-эталону `dev/migr_plan.md` (Ревизия 4,
> §4 «Этап M0»); не расширяет его объём. Один этап = один рабочий план = один
> автоматический гейт. Результат выполнения этапа фиксируется в `dev/migr_log.md`.
> Перед созданием этого файла `migr_plan.md` перечитан (обязательное правило §1.1).

---

## 0. Итог этапа (кратко)

**Цель M0** — зафиксировать фактическое состояние (`den_18` = структурная копия
`den_17`, вся MCP-инфраструктура Ревизий 2–3 готова), перечислить расхождения до
требования дня 18, изучить образец `doc/mcp/mcp-time-server`, подготовить служебные
документы под Ревизию 4 (снимок `old_vers/4/`, очистка `migr_log.md`).

**Продукт M0** — отчёт-сверка в `migr_log.md` + зелёный baseline. Кода продукта
этап **не меняет** (кроме восстановления окружения — см. шаг 7).

---

## 1. Вход и предусловия

- `den_18` уже содержит перенесённую инфраструктуру Ревизий 2–3 (не переписывается).
- План-эталон `dev/migr_plan.md` (Ревизия 4) — источник истины по этапам.
- Первоисточник `Задание_d18.txt` — прочитан целиком (3 задания + Итоговое задание).
- Рабочий каталог: `/home/t/doc/AI_9/Nedela_4/den_18`.

---

## 2. Шаги этапа (алгоритм)

### Шаг 1. Снимок состояния на входе Ревизии 4 → `dev/old_vers/4/`
Скопировать текущие документы миграции и ключевые документы проекта, чтобы история
прошлых ревизий не терялась:
- `migr_plan.md`, `migr_plan_0.md`…`migr_plan_6.md`, `migr_log.md`;
- `Проверка.md`, `Проверка_2.md`;
- `../README.md`, `../arch.md`.

Команда (идемпотентна, копирование только):
```bash
cd /home/t/doc/AI_9/Nedela_4/den_18/dev
mkdir -p old_vers/4
cp migr_plan.md migr_plan_0.md … migr_plan_6.md migr_log.md \
   Проверка.md Проверка_2.md ../README.md ../arch.md old_vers/4/
```

### Шаг 2. Фиксация baseline (L1–L4 + гейт) — как есть, без изменений
Определить интерпретатор и прогнать существующий тестовый контур.

- L1 — компиляция всей сборки:
  ```bash
  PY -m py_compile Kod.py core/*.py memory/*.py storage/*.py integrations/mcp/*.py
  ```
- L2 — юнит-тесты без живого ключа:
  ```bash
  env -u API_KEY PY dev/tests_debug/unit_runner.py
  ```
- L3 — смоук полного цикла:
  ```bash
  API_KEY=test-key PY dev/tests_debug/smoke.py
  ```
- L4 — сценарные тесты задания:
  ```bash
  API_KEY=test-key PY dev/tests_debug/scenario.py
  ```
- Гейт приёмки:
  ```bash
  API_KEY=test-key bash dev/tests_debug/check_acceptance.sh
  ```

Ожидание: L1 EXIT=0; L2 122 OK/0 FAIL; L3 SMOKE OK; L4 SCENARIO OK; гейт 21/21.

### Шаг 3. Сверка дерева с §0.3 плана-эталона (что есть / чего нет)
Зафиксировать расхождения до требования дня 18 (привязать к этапам M1–M6):
- нет планировщика/фоновых задач (M1, M2);
- нет пайплайна `search → summarize → saveToFile` (M3);
- нет MCP-серверов `scheduler`/`pipeline` в `DEFAULT_SERVERS` (M2, M3);
- нет явного механизма выбора нужного инструмента среди серверов и длинного флоу (M4);
- нет режима 24/7 (`--scheduler`) (M5);
- `dev/Проверка.md` — не трёхсценарная (M6).

### Шаг 4. Изучение образца `doc/mcp/mcp-time-server`
Зафиксировать как канон настройки новых серверов:
- `time_server_http.py` — эталон: `mcp.server.mcpserver.MCPServer`, декоратор
  `@mcp.tool()`, `TransportSecuritySettings(allowed_hosts=[...])`,
  `mcp.streamable_http_app(...)`, запуск `uvicorn.run(app, host="0.0.0.0", port=8000)`;
- `time_server_stdio_old.py` — устаревший stdio-вариант (`mcp.run()`); не использовать
  для HTTP-режима.

### Шаг 5. Фиксация точек внедрения (не менять)
Перечислить модули, которые миграция **не трогает**:
`core/state_machine.py` (`TaskStage` 8 стадий), `core/invariants.py`, `memory/*`,
`storage/db.py`, базовые контракты `core/llm_client.py`/`core/prompt_builder.py`,
MCP-инфраструктура Ревизий 2–3 (`integrations/mcp/{config,transport,client,gateway,
provider,demo_server}.py`, `core/{tools,tool_registry,tool_policy,tool_executor}.py`).

### Шаг 6. Подготовка служебки: очистка `dev/migr_log.md` под Ревизию 4
Заменить шапку и записи журнала на шапку Ревизии 4 (история прошлых ревизий — в
`old_vers/`), затем внести запись этапа M0 по шаблону §6.4 плана-эталона.

### Шаг 7. Восстановление рабочего окружения (при необходимости)
Ожидаемый venv недели `AI_9/.venv` отсутствовал (он не под git). Восстановить его и
поставить зависимости проекта, иначе ни тестовый контур, ни MCP-серверы не
запускаются:
```bash
cd /home/t/doc/AI_9
/usr/bin/python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install requests python-dotenv mcp uvicorn
```
Проверка: `./.venv/bin/python -c "import requests, dotenv, mcp, uvicorn"`.

> Секреты только из `.env` (`API_KEY`, `MCP_SERVER_URL`, `SCHEDULER_MCP_URL`,
> `PIPELINE_MCP_URL`); `.env` в репозиторий не коммитить.

---

## 3. Выход этапа (артефакты)

- `dev/old_vers/4/` — снимок состояния на входе Ревизии 4.
- `dev/migr_plan_0.md` — этот рабочий план.
- `dev/migr_log.md` — очищен под Ревизию 4 + запись этапа M0.
- `AI_9/.venv` — рабочее окружение (вне git).

---

## 4. Гейт M0→M1 (критерии)

- [x] Baseline зафиксирован: L1 EXIT=0; L2 122 OK/0 FAIL; L3 SMOKE OK; L4 SCENARIO OK;
      гейт 21/21 (FAIL=0).
- [x] Расхождения перечислены и привязаны к M1–M6.
- [x] Эталон сервера `doc/mcp/mcp-time-server/time_server_http.py` изучён.
- [x] Точки внедрения зафиксированы.
- [x] Служебка готова (`old_vers/4/`, `migr_log.md` очищен под Ревизию 4).
- [x] Рабочее окружение восстановлено.

**Переход M0→M1** — только при полном выполнении критериев; затем **обязательное
перечитывание** `dev/migr_plan.md` и создание `dev/migr_plan_1.md`.