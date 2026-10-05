# README_vps.md — операторский контур отладки MCP на VPS (Этап 2, И4)

> Мост «оператор ↔ VPS». Продуктом не импортируется, в acceptance-гейт не входит.
> Всё, что здесь описано, живёт в `dev/vps/` и работает с машины оператора.

## Что где лежит

| Файл | Назначение |
|---|---|
| `mcp_vps.sh` | единая точка отладки: `status/probe/tools/call/log/deploy/tunnel` |
| `deploy_services.sh` | идемпотентный деплой user-юнитов (запускается **на VPS**, без sudo) |
| `services.list` | список юнитов `имя:порт` для деплоя |
| `units/*.service` | источники пользовательских systemd-юнитов |
| `ssh_config.snippet` | готовый блок алиаса `mcp-vps` для `~/.ssh/config` |
| `evidence/` | расшифровки живых прогонов (`probe_*`, `call_*`) |

## Быстрый старт

```bash
# 1. состояние сервисов и портов на VPS
./dev/vps/mcp_vps.sh status

# 2. handshake + список инструментов (расшифровка в evidence/)
./dev/vps/mcp_vps.sh probe 8000

# 3. вызов инструмента
./dev/vps/mcp_vps.sh call 8000 get_time '{"timezone_name":"Europe/Moscow"}'

# 4. журнал сервиса
./dev/vps/mcp_vps.sh log mcp-time-server

# 5. деплой после правки юнитов (git pull + deploy на VPS)
./dev/vps/mcp_vps.sh deploy
```

## Матрица отказов (что означает ответ)

| Симптом | Причина | Что делать |
|---|---|---|
| `connection refused` | порт закрыт / сервис не запущен | `mcp_vps.sh status`; `systemctl --user restart <unit>` |
| `421 Misdirected Request` | `Host` нет в `allowed_hosts` сервера | добавить точный `IP:port` в `allowed_hosts` (не `"*"`) |
| `timeout` (нет ответа) | фильтрует панель провайдера / `ufw` | открыть порт в панели; `sudo -n ufw status verbose` |
| `Missing session ID` | пропущен `initialize` | сначала `initialize`, затем запросы с `mcp-session-id` |
| `Session not found` | чужой/протухший session-id | заново `initialize` (сессия живёт в рамках процесса) |
| `Parse error` | битый JSON в `-d` | проверить кавычки; использовать `mcp_vps.sh` |

## Порядок Streamable HTTP (почему не одним `curl`)

1. `POST initialize` → сервер отвечает `200` и заголовком `mcp-session-id`;
2. `POST notifications/initialized` с этим id;
3. `POST tools/list` (и `tools/call`) с тем же id.

`mcp_vps.sh probe/call` делают все три шага сами — вручную собирать не нужно.

## Безопасность

- Пароль sudo в скрипты/историю **не попадает** — только NOPASSWD-белый список.
- Секреты/endpoint'ы — из `.env` (в git не коммитятся).
- `allowed_hosts` — точный набор `host:port`; `"*"` запрещён.
