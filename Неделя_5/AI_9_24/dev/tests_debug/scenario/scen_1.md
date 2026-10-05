# Сценарий ручной демонстрации «День 16 — Подключение MCP (Ревизия 2)»

> Назначение: показать куратору выполнение требований `Задание_d16.txt` в живом REPL —
> **настоящее** подключение к **реальному** MCP-серверу, **настоящий** список
> инструментов, **настоящий** вызов инструмента и **полный LLM tool-use**.
> Время: 5–7 минут. Файл — артефакт процесса, живёт только в `dev/`.

## Реквизиты

- Терминал в корне проекта, venv активирует обёртка сама.
- **Живой режим** (нагляднее): реальный MCP-сервер недели
  `https://weatherapi.projecteol.ru/mcp/` (Streamable HTTP) — endpoint по умолчанию
  (переопределяется env `MCP_WEATHER_URL`). Для шага 4 (LLM tool-use) нужен ключ LLM
  в `.env` (`API_KEY`); `/mcp`-команды и `--mcp-probe` токенов LLM не тратят.
- **Запасной режим** (без сети): тестовый контур (`FakeMCPTransport`) —
  `API_KEY=test-key python dev/tests_debug/scenario.py` (сценарии `scenario_mcp_discovery`,
  `scenario_llm_tool_use`, `scenario_tool_denied`).
- Демо-пользователь — свежий (`demo`), чтобы показать интервью и создание дерева с нуля.

---

## Шаг 1. One-shot результат задания: `--mcp-probe` (реальный сервер)

```bash
./run.sh --mcp-probe
```

**Увидите:**

```
[MCP] Подключение к серверам: weather, demo
[MCP] «weather»: подключён (READY)
[MCP] Соединение установлено (READY). Список доступных инструментов:

  mcp.weather.search_locations
    description: Search ProjectEOL's local city index and return coordinates ...
    input_schema: {"type": "object", "properties": {"query": {...}, "limit": {...}}, "required": ["query"], ...}
  mcp.weather.get_forecast_metadata
    ...
  mcp.weather.get_weather_forecast
    ...

[MCP] Всего инструментов: 3
[MCP] Соединение закрыто (DISCONNECTED).
```

> Требования: соединение устанавливается; список инструментов корректно
> возвращается; список выводится кодом. Exit-код — 0.

## Шаг 2. REPL: семейство `/mcp`

```bash
./run.sh --user demo --mcp
```

(если пользователь `demo` новый — пройти интервью: имя, стиль, ограничения, контекст)

```
/mcp status
/mcp servers
/mcp connect
/mcp tools
/mcp refresh
/mcp status
/mcp disconnect
```

**Увидите:**

- `status` до подключения: `weather: disconnected`, каталог v0 (тулов: 0);
- `servers`: `weather: transport=http, enabled=True, trust=low, allowed=все, denied=—`;
- `connect`: «Подключение установлено: READY»;
- `tools` до refresh: «Каталог пуст (выполните: /mcp refresh)» — каталог честен;
- `refresh`: «Каталог обновлён: 3 тулов (версия 1); серверы READY: ['weather'];
  снимок сохранён (catalog.json)»;
- `tools` после refresh: `mcp.weather.search_locations`,
  `mcp.weather.get_forecast_metadata`, `mcp.weather.get_weather_forecast` — имя,
  description, input-схема;
- `status`: `weather: ready`, «Каталог инструментов: версия 1, тулов: 3»;
- `disconnect`: «Соединения закрыты (DISCONNECTED)».

Во втором терминале:

```bash
cat users/demo/integrations/mcp/catalog.json
```

**Увидите:** снимок каталога (schema_version 1, version 1, 3 тула) — каталог
переживает перезапуск (персистентность через `Store`).

## Шаг 3. Настоящий вызов инструмента: `/mcp call`

```
/mcp call mcp.weather.search_locations {"query":"Москва"}
```

**Увидите:** результат с координатами Москвы:

```
[MCP] Вызов mcp.weather.search_locations: succeeded
  результат: {"query": "Москва", "results": [{"name": "Moscow", "country": "RU",
    "latitude": 55.75204, "longitude": 37.61781, "timezone": "Europe/Moscow"}, ...]}
```

## Шаг 4. Полный LLM tool-use: «найди город Москва»

В том же REPL (нужен ключ LLM в `.env`):

```
найди город Москва
```

**Увидите:** агент сам вызывает инструмент и отвечает:

```
Агент: Нашёл город Москва (Россия) с координатами 55.75204, 37.61781.
```

Проверить аудит вызова:

```bash
cat users/demo/tasks/*/tool_audit.jsonl
```

**Увидите:** запись `{"tool": "mcp.weather.search_locations", "status": "succeeded",
"arguments_hash": "...", "call_id": "chatcmpl-tool-...", ...}` — история вызовов
отдельно от `transition_log`.

## Шаг 5. Изоляция прав (allowed/denied_tools)

В `users/demo/integrations/mcp/servers.json` добавить серверу `weather`
`"denied_tools": ["get_weather_forecast"]`, затем в REPL:

```
/mcp connect
/mcp refresh
/mcp tools
```

**Увидите:** 2 тула — `get_weather_forecast` не попал в discovery (изоляция прав
через тулинг). Вернуть конфиг обратно — `/mcp refresh` снова даёт 3 тула
(атомарный swap, version растёт).

## Шаг 6. Недоступный сервер — деградация, не падение

```bash
MCP_WEATHER_URL="https://invalid.invalid/mcp/" ./run.sh --mcp-probe   # exit 1, понятная ошибка
```

В REPL при недоступном сервере: `/mcp connect` → `weather: failed` (overall FAILED),
тулов нет — но REPL жив: `/memory`, `/profile`, `/state` работают (память, профили и
машина состояний не зависят от MCP).

## Шаг 7 (опционально, 60 секунд). Наследие + граница «инструмент ≠ переход»

```
/plan Сделать REST API на Django
/goto implementation
/state
```

**Увидите:** отказ «Нельзя делать реализацию до утверждённого плана…» — машина
состояний дней 11–15 работает как раньше; MCP её не трогает (вызов инструмента
никогда не означает переход `TaskStage`).

---

## Соответствие требованиям `Задание_d16.txt`

| Требование задания | Где показано |
|---|---|
| MCP SDK установлен / сервер доступен | Шаг 1 (реальный HTTP-сервер `weatherapi` отвечает) |
| Соединение устанавливается | Шаг 1 («Соединение установлено (READY)»), Шаг 2 (`/mcp connect`) |
| Список инструментов корректно возвращается | Шаги 1–2 (3 тула: search_locations, get_forecast_metadata, get_weather_forecast) |
| Список выводится кодом | Шаг 1 (`--mcp-probe` печатает имя/description/схему, exit 0), Шаг 2 (`/mcp tools`) |
| **Настоящий вызов инструмента** | Шаг 3 (`/mcp call` → координаты Москвы), Шаг 4 (LLM tool-use) |
| **Полный LLM tool-use** | Шаг 4 («найди город Москва» → вызов → ответ) |
| Изоляция прав через тулинг | Шаг 5 (denied_tools) |
| Недоступный сервер не роняет агента | Шаг 6 (FAILED, REPL жив) |
| Наследие без регрессии | Шаг 7 (переходы/память работают; MCP off по умолчанию) |

**Финальная фраза куратору:** «Агент подключается к **реальному** MCP-серверу по
стандарту: handshake initialize → tools/list → нормализация во внутреннюю модель →
каталог в ToolRegistry с атомарным snapshot; список инструментов выводится кодом
(--mcp-probe и /mcp tools); агент **реально вызывает** инструмент (`tools/call`) и
делает это в **полном LLM tool-use** (LLM сам предлагает вызов, результат возвращается
в модель); MCP — источник инструментов, а не слой контроля: TaskStage, память и
профили MCP не трогает».

---

## Замечания для честности демо

- `--mcp-probe` и `/mcp connect` подключаются к **реальному** серверу
  `https://weatherapi.projecteol.ru/mcp/` (Streamable HTTP) — нужна сеть; ключ LLM
  для MCP-шагов не нужен (`/mcp`-команды токенов не тратят), для шага 4 — нужен.
- Авто-эквивалент демо: `API_KEY=test-key python dev/tests_debug/scenario.py`
  (сценарии `scenario_mcp_discovery`, `scenario_llm_tool_use`, `scenario_tool_denied` —
  всё на `FakeMCPTransport`, без сети) + гейт `check_acceptance.sh` (21/21).
- Без флага `--mcp` агент работает ровно как den_15 (MCP off по умолчанию —
  критерий 48).
- После демо дерево `users/demo/` можно удалить вручную или оставить как артефакт
  показа; на данные `cli_user`/`tester` демо не влияет.