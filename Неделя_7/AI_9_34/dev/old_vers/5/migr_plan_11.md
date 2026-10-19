# migr_plan_11.md — Этап 11. D7: авторизация транспорта

> Рабочий план-алгоритм **одного этапа** на основе `dev/migr_plan.md` (Ревизия 5).
> Контур: **D (правки продукта)**. Метка: **D7**. Коммиты — только за оператором.

## Цель этапа
`MCPServerConfig.headers`/`token_env` → `HttpMCPTransport` шлёт `Authorization`;
серверная часть проверяет токен. **Не блокирует** финал, пока серверы публичные
и без секретов (проверка выключена, если env `MCP_AUTH_TOKEN` не задан).

## Предусловия (выполнено)
- Этап 4 ✅: D7 воспроизведён (транспорт не шлёт заголовки).
- Этапы 5–10 ✅: D1/D2/D5/D3/D4/D6 закрыты; регрессия зелёная.

## Границы этапа
Правки: `integrations/mcp/config.py`, `integrations/mcp/transport.py`,
`integrations/mcp/auth.py` (новое), `time_server.py`/`scheduler_server.py`/
`pipeline_server.py`. Секрет — только в env, не в коде/конфиге.

---

## Шаги

### ШАГ 11.1 — конфиг
`MCPServerConfig.headers: dict` + `token_env: str | None`; `_parse_server` читает их.

### ШАГ 11.2 — клиентский транспорт
`HttpMCPTransport(headers, token_env)`; `_auth_headers()` = статические заголовки +
`Authorization: Bearer <env>`; передача через `httpx2.AsyncClient(headers=...)`
в `streamable_http_client(http_client=...)`; `close()` закрывает http_client.
`make_transport` пробрасывает поля.

### ШАГ 11.3 — серверная проверка
`integrations/mcp/auth.py::auth_middleware(app, token_env="MCP_AUTH_TOKEN")`:
если env задан — требовать `Authorization: Bearer <token>`, иначе 401; если не
задан — проверка выключена. Подключено в трёх серверах.

### ШАГ 11.4 — тесты + живой прогон
`dev/tests_debug/unit/test_d7_auth.py` (6 функций); живой `run_live_d7.sh`:
публичный сервер → подключение; сервер с токеном → без токена 401, с токеном READY;
проверка 35 в гейте.

---

## Гейт 11→12 (живой)
| # | Проверка | Ожидаемо |
|---|---|---|
| 1 | unit `test_d7_auth` | 6 OK |
| 2 | живой: публичный сервер | подключён (1 тул) |
| 3 | живой: сервер с токеном, клиент без токена | отклонён (401) |
| 4 | живой: сервер с токеном, клиент с токеном | подключён (1 тул) |
| 5 | регрессия L2/L3/L4/гейт | 148 OK · SMOKE OK · SCENARIO OK · 25/25 |

## Перечитывание
После гейта — перечитать `dev/migr_plan.md` (§4 «Этап 12», §6) и создать
`dev/migr_plan_12.md`.
