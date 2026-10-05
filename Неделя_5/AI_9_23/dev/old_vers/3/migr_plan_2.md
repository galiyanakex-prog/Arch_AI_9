# migr_plan_2.md — рабочий план этапа M2 «Реальное discovery к weatherapi»

> Рабочий план-алгоритм этапа **M2** миграции `den_16` (Ревизия 2). **Конец — гейт в M3**.

---
## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **M2** — Реальное discovery к `weatherapi` |
| Зависит от | M1 |
| Открывает | `migr_plan_3.md` (M3 — `tools/call`) |
| Тип изменений | Преимущественно прогон/проверка; возможны мелкие правки вывода/конфига |
| Живой прогон | **Да** (сеть к MCP; LLM-ключ не нужен) |
| Точка отката | Гейт M1→M2 |

**Цель.** Доказать **настоящее** подключение к реальному MCP-серверу и получение
**настоящего** списка инструментов; зафиксировать факты.

---

## 1. Шаги этапа

### Шаг 2.1 — Живой `--mcp-probe`
```bash
PY="../../.venv/bin/python"
timeout 60 $PY Kod.py --mcp-probe ; echo "exit=$?"
```
**Ожидаемо:** `[MCP] Соединение установлено (READY)`; три инструмента
`mcp.weather.search_locations` / `mcp.weather.get_forecast_metadata` /
`mcp.weather.get_weather_forecast` с описаниями и input-схемами; `Всего инструментов: 3`;
`DISCONNECTED`; `exit=0`.

### Шаг 2.2 — REPL-флоу
`$PY Kod.py --user w16 --mcp` →
`/mcp connect` → `/mcp status` (READY) → `/mcp refresh` (3 тула, `catalog.json`) →
`/mcp tools` (список) → `/mcp servers` → `/mcp disconnect` → `/exit`.
**Ожидаемо:** каталог = 3 реальных тула; `catalog.json` записан (`users/w16/…`).

### Шаг 2.3 — Проверка деградации
`MCP_WEATHER_URL="https://invalid.invalid/mcp/" $PY Kod.py --mcp-probe` → понятная
ошибка, `exit=1`; REPL (`--mcp`) при недоступном сервере — `FAILED`, память/профили/автомат
живы.

### Шаг 2.4 — Зафиксировать факты
Реальный список/схемы (см. §0.4 `migr_plan.md`) → в `migr_log.md` M2; при расхождении со
схемой — актуализировать ожидания (не код).

---

## 2. Выход этапа
- Подтверждённое живое соединение и реальный список 3 тулов (транскрипты в
  `dev/logs_reports/stages/`).
- Каталог `catalog.json` с реальными тулами.
- Запись M2 в `migr_log.md`.

## 3. Гейт M2→M3
- [ ] живой `--mcp-probe` → `READY`, 3 реальных тула, `DISCONNECTED`, exit 0;
- [ ] `/mcp refresh` → `catalog.json` с реальными тулами; `/mcp status` = READY;
- [ ] неверный URL → ошибка/деградация, не падение;
- [ ] L1/L2 без регрессии.

**Зелёный** → запись ✅ → перечитать `migr_plan.md` → `migr_plan_3.md`.

## 4. Запись в `migr_log.md`
По форме §6.4 (в «Проверка» — реальные команды, их вывод, exit-коды).

## 5. Следующий шаг
Перечитать `dev/migr_plan.md` → M3 (`migr_plan_3.md`): `tools/call`.