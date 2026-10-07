# migr_plan_3.md — Этап 3. Второй/третий серверы на VPS (И3)

> Рабочий план-алгоритм **одного этапа** на основе `dev/migr_plan.md` (Ревизия 5).
> Контур: **И (инфраструктура VPS)**. Метка цели: **И3** (несколько MCP-серверов).
> Коммиты — только за оператором.

## Цель этапа
На VPS поднимаются `scheduler :8010` и `pipeline :8020` — реальные HTTP-MCP-серверы,
управляемые тем же `deploy_services.sh`. Это материальная база для «несколько
MCP-серверов» (`Задание_d20.txt`) и для мультисерверного флоу (этап 8).

## Предусловия (выполнено)
- Этап 1 ✅: `time :8000` под `systemctl --user`, публичный доступ.
- Этап 2 ✅: `dev/vps/` (mcp_vps.sh, deploy_services.sh, services.list, evidence/).
- Серверы `scheduler_server.py`/`pipeline_server.py` уже в репозитории
  (`integrations/mcp/`), порты 8010/8020, `allowed_hosts` с точным `IP:port`.

## Границы этапа
Не трогаем код серверов (только юниты + деплой). Не чиним D1 (этап 5). Не строим
мультисерверный сценарий (этап 8) — только поднимаем серверы и доказываем
`initialize`+`tools/list` снаружи.

---

## Шаги

### ШАГ 3.1 — юниты `mcp-scheduler-server.service`, `mcp-pipeline-server.service`
`dev/vps/units/`, по образцу `mcp-time-server.service` (общий venv, `Restart=always`,
`WantedBy=default.target`, env `SCHEDULER_PORT`/`PIPELINE_PORT`).

### ШАГ 3.2 — `services.list` → три сервера
`mcp-time-server:8000`, `mcp-scheduler-server:8010`, `mcp-pipeline-server:8020`.

### ШАГ 3.3 — деплой
```bash
scp dev/vps/units/*.service dev/vps/services.list mcp-vps:/home/t/doc/AI_9/dev/vps/...
ssh mcp-vps 'cd /home/t/doc/AI_9 && bash dev/vps/deploy_services.sh'
```
> ⚠ Найден и исправлен баг `deploy_services.sh`: `while read` терял последнюю
> строку без `\n` → добавлено `|| [ -n "$name" ]`.

### ШАГ 3.4 — `.env`: публичные адреса scheduler/pipeline
```bash
printf 'SCHEDULER_MCP_URL=http://91.188.212.77:8010/mcp\nPIPELINE_MCP_URL=http://91.188.212.77:8020/mcp\n' >> .env
```
> Дефолты `config.py` — `127.0.0.1` (для клиента **на** VPS). С локальной машины
> нужен публичный адрес, иначе `connection refused` маскируется под
> `Cancelled via cancel scope`.

### ШАГ 3.5 — живой probe 8010/8020
```bash
./dev/vps/mcp_vps.sh probe 8010
./dev/vps/mcp_vps.sh probe 8020
```
**Ожидаемо:** session-id + тулы (7 у scheduler, 4 у pipeline).

### ШАГ 3.6 — регрессия + запись в журнал
L2/L3/L4/гейт; запись «Этап 3» в `dev/migr_log.md`.

---

## Гейт 3→4
| # | Проверка | Ожидаемо |
|---|---|---|
| 1 | `mcp_vps.sh status` | три сервиса `active`, порты 8000/8010/8020 |
| 2 | `probe 8010` | session-id + 7 тулов планировщика |
| 3 | `probe 8020` | session-id + 4 тула пайплайна |
| 4 | `Kod.py --mcp-probe` (все живы) | все READY, 15 тулов, exit 0 |
| 5 | регрессия L2/L3/L4/гейт | 122 OK · SMOKE OK · SCENARIO OK · 21/21 |
| 6 | код продукта не изменён | `git diff` пуст по `Kod.py`, `core/`, `integrations/` |

## Риски этапа
| Риск | Проявление | Действие |
|---|---|---|
| `while read` теряет последнюю строку | pipeline не деплоится | `|| [ -n "$name" ]` (исправлено) |
| `127.0.0.1` в дефолтах | `Cancelled via cancel scope` | публичный адрес в `.env` |
| Порт закрыт панелью | `timeout` | шаг 0.5 мастер-плана |

## Перечитывание
После гейта — перечитать `dev/migr_plan.md` (§4 «Этап 4», §6) и создать
`dev/migr_plan_4.md`.
