# migr_plan_1.md — рабочий план этапа M1 «HTTP-транспорт + конфиг реального сервера»

> Рабочий план-алгоритм **одного этапа** миграции `den_16` (Ревизия 2, `dev/migr_plan.md`).
> Разворачивает этап **M1**. **Конец этапа — гейт в M2** (`migr_plan_2.md`).

---
## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **M1** — HTTP-транспорт + конфиг реального сервера |
| Рабочий план | `dev/migr_plan_1.md` |
| Зависит от | M0 |
| Открывает | `dev/migr_plan_2.md` (M2 — реальное discovery) |
| Тип изменений | Код продукта: `integrations/mcp/{transport,config,client,gateway}.py` |
| Живой ключ | **Не нужен** (смоук — импорт/выбор транспорта; живой прогон — M2) |
| Точка отката | Зелёный гейт M0→M1 |

**Цель.** Добавить `HttpMCPTransport` (Streamable HTTP, SDK 2.2.0), выбор транспорта по
конфигу и реальный сервер по умолчанию; устранить квирк чтения схемы тула (`input_schema`).

---

## 1. Шаги этапа

### Шаг 1.1 — `HttpMCPTransport` (`integrations/mcp/transport.py`)
- Добавить класс `HttpMCPTransport(MCPTransport)`:
  - ленивый импорт внутри `initialize()`: `from mcp import ClientSession` +
    `import mcp.client.streamable_http as sm` (SDK 2.2.0 — функция
    `streamable_http_client`, **не** `streamablehttp_client`);
  - хранит `endpoint` (str), `timeout_seconds`; при старте:
    `self._streams = sm.streamable_http_client(self._endpoint)`;
    `read, write = await self._streams.__aenter__()`; `ClientSession(read, write)`;
    `await session.initialize()`;
  - `list_tools()` — как в stdio, но с **фиксом схемы** (см. 1.2);
  - `close()` — `__aexit__` по session и streams (по образцу stdio); ошибки →
    `MCPConnectionError(server_id, …)`.
- Сохранить общий помощник извлечения схемы (см. 1.2), чтобы stdio/http/fake не
  расходились.

### Шаг 1.2 — Фикс чтения схемы тула (`input_schema`)
SDK 2.2.0 отдаёт `Tool.input_schema` (snake_case), а не `inputSchema`. Ввести единый
хелпер, например:
```python
def _tool_schema(t) -> dict:
    schema = getattr(t, "input_schema", None)
    if schema is None:
        schema = getattr(t, "inputSchema", None)
    if schema is None and isinstance(t, dict):
        schema = t.get("input_schema") or t.get("inputSchema")
    return schema or {"type": "object"}
```
Применить в `StdioMCPTransport.list_tools` и `HttpMCPTransport.list_tools` (fake-транспорт
работает с dict — остаётся совместим).

### Шаг 1.3 — Конфиг реального сервера (`integrations/mcp/config.py`)
- `DEFAULT_SERVERS`: сервер `weather` — `transport="http"`,
  `endpoint=os.getenv("MCP_WEATHER_URL", "https://weatherapi.projecteol.ru/mcp/")`,
  `enabled=True`, `trust_level="low"`; **демо-сервер `demo` (stdio) сохранить** (для
  детерминированных тестов) — но по умолчанию активен реальный `weather`
  (демо — при явном выборе/в тестах).
- `_parse_server`: поддержать `endpoint` при `transport="http"`; при `stdio` — `command`.

### Шаг 1.4 — Выбор транспорта (`gateway.py` + `client.py`)
- `MCPGateway._make_client(server)`: ветка по `server.transport`:
  `"http"` + `endpoint` → `HttpMCPTransport(server.server_id, server.endpoint, timeout)`;
  иначе (`"stdio"`) → `StdioMCPTransport(...)`.
- `MCPClient.__init__`: дефолтный транспорт — тоже по `config.transport`.
- Сохранить инжекцию транспорта (тесты) без изменений.

### Шаг 1.5 — Примитив-смоук этапа
- Импорт `HttpMCPTransport`; выбор транспорта по `transport="http"`/`"stdio"`;
- фикс схемы: объект-имитация Tool с `input_schema` → `_tool_schema` возвращает словарь.

---

## 2. Выход этапа

- `HttpMCPTransport` в `transport.py`; фикс `input_schema`; реальный сервер в конфиге;
  выбор транспорта по конфигу.
- Смоук: импорт/выбор/фикс схемы — зелёные; SDK — только в `integrations/mcp/`.
- Запись M1 в `migr_log.md`.

## 3. Гейт M1→M2

- [ ] `HttpMCPTransport` импортируется; функция SDK 2.2.0 вызывается корректно;
- [ ] выбор транспорта по `MCPServerConfig.transport` работает (http/stdio);
- [ ] схема тула читается из `input_schema` (и совместимо с dict/`inputSchema`);
- [ ] реальный сервер в `DEFAULT_SERVERS` (`weather`, env `MCP_WEATHER_URL`);
- [ ] grep: `mcp` SDK — только в `integrations/mcp/`; `core/memory/storage` — чисто;
- [ ] L1 зелёный; L2 **112 OK**; L3/L4/гейт — без регрессии.

**Зелёный** → запись M1 ✅ → перечитать `migr_plan.md` → `migr_plan_2.md`.
**Красный** → карточка ошибки, этап открыт.

## 4. Запись в `migr_log.md`
По форме §6.4 `migr_plan.md` (Статус/Было/Стало/Проверка/Артефакты/Риски/Перечитывание/Гейт).

## 5. Следующий шаг
Перечитать `dev/migr_plan.md` → M2 (`dev/migr_plan_2.md`): реальное discovery к
`weatherapi` (`--mcp-probe`, `/mcp refresh`, `/mcp status`, деградация).