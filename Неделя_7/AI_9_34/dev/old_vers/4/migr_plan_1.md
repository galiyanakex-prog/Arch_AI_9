# migr_plan_1.md — рабочий план этапа M1 «Конфиг сервера задания `time`»

> Рабочий план-алгоритм **одного этапа** миграции `den_17` (Ревизия 3, `dev/migr_plan.md`).
> Разворачивает этап **M1**. **Конец этапа — гейт в M2** (`migr_plan_2.md`).

---
## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **M1** — Конфиг сервера задания `time` (http, env `MCP_SERVER_URL`) |
| Рабочий план | `dev/migr_plan_1.md` |
| Зависит от | M0 |
| Открывает | `dev/migr_plan_2.md` (M2 — реальное discovery к серверу задания) |
| Тип изменений | Код продукта: `integrations/mcp/config.py` (точечно) |
| Живой ключ | **Не нужен** (смоук — импорт/выбор транспорта; живой прогон — M2) |
| Точка отката | Зелёный гейт M0→M1 |

**Цель.** Добавить сервер задания `time` в `DEFAULT_SERVERS` (http, endpoint из env
`MCP_SERVER_URL`, enabled=True), сохранив `weather` и `demo`. Инфраструктура Ревизии 2
(транспорт/gateway/provider/registry) **не переписывается** — она уже умеет http.

---

## 1. Шаги этапа

### Шаг 1.1 — Сервер задания в конфиге (`integrations/mcp/config.py`)
- Ввести `TIME_MCP_URL = os.getenv("MCP_SERVER_URL", "http://91.188.212.77:8000/mcp")`.
- В `DEFAULT_SERVERS` добавить сервер `time`:
  `transport="http"`, `endpoint=TIME_MCP_URL`, `enabled=True`, `trust_level="low"`.
- Сохранить `weather` (http, env `MCP_WEATHER_URL`, enabled=True) и `demo` (stdio,
  enabled=False) — **без изменений**.
- `_parse_server`: убедиться, что `endpoint` при `transport="http"` уже поддержан
  (Ревизия 2) — правок не требуется, только проверка.

### Шаг 1.2 — Примитив-смоук этапа
- `load_servers_config(None)` содержит `time` с endpoint из env/дефолта;
- `make_transport(time_cfg)` → `HttpMCPTransport`;
- `MCPGateway._make_client(time_cfg)` выбирает http-ветку.

### Шаг 1.3 — Проверка нерегрессии
- `py_compile` (L1);
- существующий тест состава дефолта (`test_default_servers_and_store_roundtrip` и
  подобные) — **при необходимости** привести в соответствие с новым сервером `time`
  (тесты **не расширяем**, только синхронизируем существующие ожидания);
- L2/L3/L4/гейт — без регрессии.

---

## 2. Выход этапа

- Сервер `time` в `DEFAULT_SERVERS`; env `MCP_SERVER_URL` читается; `weather`/`demo`
  сохранены.
- Смоук: импорт/выбор транспорта — зелёные; SDK — только в `integrations/mcp/`.
- Запись M1 в `migr_log.md`.

## 3. Гейт M1→M2

- [ ] сервер `time` в `DEFAULT_SERVERS` (`transport="http"`, endpoint из `MCP_SERVER_URL`);
- [ ] `weather` и `demo` сохранены без изменений;
- [ ] выбор транспорта по `MCPServerConfig.transport` работает (http/stdio);
- [ ] grep: `mcp` SDK — только в `integrations/mcp/`; `core/memory/storage` — чисто;
- [ ] L1 зелёный; L2/L3/L4/гейт — без регрессии.

**Зелёный** → запись M1 ✅ → перечитать `migr_plan.md` → `migr_plan_2.md`.
**Красный** → карточка ошибки, этап открыт.

## 4. Запись в `migr_log.md`
По форме §6.4 `migr_plan.md` (Статус/Было/Стало/Проверка/Артефакты/Риски/Перечитывание/Гейт).

## 5. Следующий шаг
Перечитать `dev/migr_plan.md` → M2 (`dev/migr_plan_2.md`): реальное discovery к серверу
задания (`--mcp-probe`, `/mcp refresh`, `/mcp status`, деградация).
