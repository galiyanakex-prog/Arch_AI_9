# Живой прогон M9 (Ревизия 2) — «найди город Москва»

Дата: 2026-09-25. Цель этапа M9: доказать полное требование куратора на **живых**
LLM + MCP (реальный сервер `https://weatherapi.projecteol.ru/mcp/`).

## Живой `--mcp-probe` (реальное соединение + реальный список)


[MCP] Подключение к серверам: weather, demo
[MCP] «weather»: подключён (READY)
[MCP] Соединение установлено (READY). Список доступных инструментов:

  mcp.weather.search_locations            (query: string required, limit 1..8)
  mcp.weather.get_forecast_metadata       (без аргументов)
  mcp.weather.get_weather_forecast        (latitude/longitude required; hours, start, …)

[MCP] Всего инструментов: 3
[MCP] Соединение закрыто (DISCONNECTED).   exit=0


## Живой REPL tool-use (LLM сам вызывает инструмент)

Команда:


printf 'Иван\nкраткий\nнет\nтест\nнайди город Москва\n/exit\n' \
  | python Kod.py --user m9u --mcp


Ответ агента:

> **Нашёл город Москва (Россия) с координатами 55.75204, 37.61781.**

Лог:


[02:53:00] [Инструменты] mcp.weather.search_locations: succeeded


## Живой ручной вызов `/mcp call`


/mcp call mcp.weather.search_locations {"query":"Москва"}
→ результат: {"query":"Москва","results":[{"name":"Moscow","country":"RU",
   "latitude":55.75204,"longitude":37.61781,"timezone":"Europe/Moscow"}, …]}


## Аудит вызова (`tool_audit.jsonl`)


{"execution_id": "exec-0001", "tool": "mcp.weather.search_locations",
 "status": "succeeded", "phase": "invoked",
 "arguments_hash": "9d47a52fdfe6b749",
 "call_id": "chatcmpl-tool-b97...", "duration_ms": 424,
 "error": "", "at": "2026-09-25 02:53:00"}


## Инварианты соблюдены

- LLM действительно предложил вызов инструмента (`tool_calls` в нативном формате;
  `call_id` = `chatcmpl-tool-…` подтверждает нативный OpenAI-путь).
- `TaskStage` при вызове не менялся (инструмент ≠ переход); запись в `transition_log`
  отсутствует.
- Сырой ответ сервера в память не писался — только нормализованная запись
  `external_actions` (working) и аудит с `arguments_hash`.

## Повторный живой прогон M12 (финал, 2026-09-25 05:32)

Повторная проверка после этапов M10–M12 (тесты/документация/актуализация arch) —
на том же реальном сервере и живом LLM:

- `--mcp-probe` → READY, 3 тула (`search_locations`, `get_forecast_metadata`,
  `get_weather_forecast`), DISCONNECTED, exit 0;
- REPL `--mcp` → «найди город Москва» → ответ:
  «Найден город Москва (Россия): Координаты: 55.75204° с.ш., 37.61781° в.д.;
  Часовой пояс: Europe/Moscow»;
- аудит: `{"tool": "mcp.weather.search_locations", "status": "succeeded",
  "arguments_hash": "9d47a52fdfe6b749", "call_id": "chatcmpl-tool-84fce84144d8f170",
  "duration_ms": 336, "at": "2026-09-25 05:32:12"}`;
- каталог персистится (`catalog.json`, version 1, 3 тула).

Итог: требование куратора (Ревизия 2) подтверждено на живом контуре повторно.

