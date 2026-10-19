# migr_plan_2.md — рабочий план этапа M2 «Реальное discovery к серверу задания»

> Рабочий план-алгоритм этапа **M2** миграции `den_17` (Ревизия 3). **Конец — гейт в M3**.

---
## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **M2** — Реальное discovery к серверу задания `http://91.188.212.77:8000/mcp` |
| Зависит от | M1 |
| Открывает | `migr_plan_3.md` (M3 — реальный вызов `get_time`) |
| Тип изменений | Преимущественно прогон/проверка; возможны мелкие правки вывода/конфига |
| Живой прогон | **Да** (сеть к MCP; LLM-ключ не нужен) |
| Точка отката | Гейт M1→M2 |

**Цель.** Доказать **настоящее** подключение к серверу задания и получение **настоящего**
списка инструментов (`get_time`); зафиксировать факты.

---

## 1. Шаги этапа

### Шаг 2.1 — Живой `--mcp-probe`
```bash
PY="../../.venv/bin/python"
timeout 60 $PY Kod.py --mcp-probe ; echo "exit=$?"
```
**Ожидаемо:** `[MCP] Соединение установлено (READY)`; инструмент
`mcp.time.get_time` с описанием и input-схемой (`timezone_name: string`, default `UTC`);
`DISCONNECTED`; `exit=0`. (Погодный `weather` — тоже READY, если доступен.)

### Шаг 2.2 — REPL-флоу
`$PY Kod.py --user w17 --mcp` →
`/mcp connect` → `/mcp status` (READY) → `/mcp refresh` (тул `get_time`, `catalog.json`) →
`/mcp tools` (список) → `/mcp servers` → `/mcp disconnect` → `/exit`.
**Ожидаемо:** каталог содержит `mcp.time.get_time`; `catalog.json` записан (`users/w17/…`).

### Шаг 2.3 — Проверка деградации
`MCP_SERVER_URL="https://invalid.invalid/mcp/" $PY Kod.py --mcp-probe` → понятная
ошибка для сервера `time`, `exit=1`; REPL (`--mcp`) при недоступном сервере задания —
`FAILED`/`DEGRADED`, память/профили/автомат живы.

### Шаг 2.4 — Зафиксировать факты
Реальный список/схема `get_time` (см. §0.4 `migr_plan.md`) → в `migr_log.md` M2; при
расхождении со схемой — актуализировать ожидания (не код).

---

## 2. Выход этапа
- Подтверждённое живое соединение и реальный список инструментов (транскрипты в
  `dev/logs_reports/stages/`).
- Каталог `catalog.json` с `mcp.time.get_time`.
- Запись M2 в `migr_log.md`.

## 3. Гейт M2→M3
- [ ] живой `--mcp-probe` → `READY`, тул `get_time`, `DISCONNECTED`, exit 0;
- [ ] `/mcp refresh` → `catalog.json` с `mcp.time.get_time`; `/mcp status` = READY;
- [ ] неверный URL → ошибка/деградация, не падение;
- [ ] L1/L2 без регрессии.

**Зелёный** → запись ✅ → перечитать `migr_plan.md` → `migr_plan_3.md`.

## 4. Запись в `migr_log.md`
По форме §6.4 (в «Проверка» — реальные команды, их вывод, exit-коды).

## 5. Следующий шаг
Перечитать `dev/migr_plan.md` → M3 (`migr_plan_3.md`): реальный вызов `get_time`.
