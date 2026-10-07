# migr_plan_2.md — Этап 2. Скрипты отладки + живая базовая линия D1 (И4)

> Рабочий план-алгоритм **одного этапа** на основе `dev/migr_plan.md` (Ревизия 5).
> Контур: **И (инфраструктура VPS)**. Метка цели: **И4** (операторский контур
> отладки + воспроизведение D1 **на живом** сервере).
> Порядок: агент готовит файлы и команды, оператор выполняет и отчитывается.
> Коммиты — только за оператором.

## Цель этапа
Появляется повторяемый операторский контур `dev/vps/` (одна команда вместо
ручного набора `curl`), а дефект **D1 воспроизводится живьём**: `Kod.py --mcp-probe`
возвращает `exit 1`, **хотя** сервер `time` отвечает `READY` и отдаёт `get_time`.
До этапа 2 D1 наблюдался только против мёртвых URL — это не доказательство.

## Предусловия (выполнено)
- Этап 0 ✅: SSH `mcp-vps` без пароля, `Linger=yes`, sudoers-белый список.
- Этап 1 ✅: `mcp-time-server` под `systemctl --user`, `active`, `:8000` слушает,
  handshake снаружи даёт `mcp-session-id`, `tools/list` → `get_time`.
- `requirements.txt` зафиксирован; venv `/home/t/doc/mcp/ai9` укомплектован.

## Границы этапа
**Не чиним D1** — только воспроизводим и фиксируем транскриптами (правка на этапе 5).
Не трогаем `Kod.py`, `config.py`, `gateway.py`. Не поднимаем scheduler/pipeline
(этап 3). Временные артефакты — `dev/tests_debug/.tmp/`; расшифровки прогонов —
`dev/vps/evidence/`.

## Что уже есть на входе (артефакты этапа 1)
`dev/vps/deploy_services.sh`, `dev/vps/services.list`, `dev/vps/units/`.
Этап 2 дополняет каталог, не переписывая их.

---

## Шаги

### ШАГ 2.1 — `dev/vps/mcp_vps.sh` (единая точка отладки)
Подкоманды: `status` (юнит+порт), `probe` (raw JSON-RPC handshake + `tools/list`
по указанному порту с сохранением расшифровки), `tools`, `call <port> <tool> <json>`,
`log` (журнал systemd), `deploy` (вызов `deploy_services.sh` по SSH),
`tunnel` (SSH-туннель для отладки без публичного доступа).
Скрипт **локальный** (работает с машины оператора через `ssh mcp-vps` и `curl`),
продуктом не импортируется, в acceptance-гейт не входит.
Зависимости: только `bash`, `curl`, `ssh`, `python3` — **без `jq`**.

**Проверка:** `bash -n dev/vps/mcp_vps.sh` → без ошибок; запуск без аргумента →
краткая справка, exit 1.

### ШАГ 2.2 — `dev/vps/README_vps.md` + `ssh_config.snippet` + `evidence/`
`README_vps.md` — как пользоваться + **матрица отказов**:
`connection refused` (порт закрыт / сервис не запущен) · `421 Misdirected Request`
(`Host` нет в `allowed_hosts`) · `timeout` (фильтрует панель провайдера) ·
`Missing session ID` (пропущен `initialize`) · `Session not found` (чужой/протухший id).
`ssh_config.snippet` — готовый блок алиаса для переноса на другую машину.
`evidence/` — каталог под расшифровки (в git, с `.gitkeep`).

**Проверка:** файлы непустые; `evidence/` существует.

### ШАГ 2.3 — `.env` с живым endpoint (локально, в git не попадает)
```bash
cp .env.example .env
printf 'MCP_SERVER_URL=http://91.188.212.77:8000/mcp\n' >> .env
```
> `.env` в `.gitignore`. `config.py` читает `MCP_SERVER_URL` для сервера `time`
> (дефолт совпадает — проверяем, что конфиг действительно читается).

**Проверка:** `grep MCP_SERVER_URL .env` → строка есть; `git status` по `.env` чист.

### ШАГ 2.4 — `probe` против живого `time` → расшифровка
```bash
./dev/vps/mcp_vps.sh probe 8000
```
Делает `initialize` → `notifications/initialized` → `tools/list`, печатает
`mcp-session-id` и список тулов, пишет полный транскрипт в
`dev/vps/evidence/probe_8000_<UTC>.txt`.

**Ожидаемо:** `time` **READY**, `get_time` в списке, `mcp-session-id` непустой.
Это «зелёный» слой: серверная часть исправна.

### ШАГ 2.5 — **красная** проверка D1 (главный артефакт этапа)
```bash
set -a; . ./.env; set +a
.venv/bin/python Kod.py --mcp-probe; echo "EXIT=$?"
```
**Ожидаемо (красное — это и есть D1):** `time` поднимается, но
`[MCP] Соединение не установлено (overall: degraded)` → **`EXIT=1`**,
хотя `time` READY и `get_time` доступен.
Причина (читать, не править): `Kod.py::run_mcp_probe` требует
`status["overall"] == "ready"`, а `DEFAULT_SERVERS` включает `weather`,
`scheduler`, `pipeline` с `enabled=True` на недоступных адресах →
`overall_state()` = `degraded`.

> Контраст ШАГ 2.4 ↔ ШАГ 2.5 и есть живое доказательство D1: сервер жив,
> а приёмочная команда падает. Правка — этап 5.

### ШАГ 2.6 — живой `tools/call` (мост к этапу 8)
```bash
./dev/vps/mcp_vps.sh call 8000 get_time '{"timezone_name":"Europe/Moscow"}'
```
**Ожидаемо:** ISO 8601 время в `Europe/Moscow`; транскрипт в `evidence/`.

### ШАГ 2.7 — регрессия + запись в журнал
```bash
.venv/bin/python dev/tests_debug/unit_runner.py
API_KEY=test-key .venv/bin/python dev/tests_debug/smoke.py
API_KEY=test-key .venv/bin/python dev/tests_debug/scenario.py
API_KEY=test-key bash dev/tests_debug/check_acceptance.sh
```
**Ожидаемо:** 122 OK / 0 FAIL · SMOKE OK · SCENARIO OK · 21/21 FAIL=0.
Запись «Этап 2» в `dev/migr_log.md` по шаблону §6.3 (с выводом красной проверки).

### ШАГ 2.8 — предложить коммит (выполняет оператор)
Текст: `dev/vps: операторский контур отладки + живое воспроизведение D1 (этап 2, И4)`.

---

## Гейт 2→3
| # | Проверка | Ожидаемо |
|---|---|---|
| 1 | `bash -n dev/vps/mcp_vps.sh` | exit 0 |
| 2 | `mcp_vps.sh probe 8000` | `time` READY, `get_time`, session-id непустой |
| 3 | `Kod.py --mcp-probe` | **exit 1** при `overall: degraded` (D1 живьём) |
| 4 | `mcp_vps.sh call 8000 get_time {...}` | ISO 8601 время |
| 5 | транскрипты в `dev/vps/evidence/` | ≥2 файла, непустые |
| 6 | регрессия L2/L3/L4/гейт | 122 OK · SMOKE OK · SCENARIO OK · 21/21 |
| 7 | код продукта не изменён | `git diff` пуст по `Kod.py`, `core/`, `integrations/` |

Зелёный гейт = живой прогон (пп. 2–4) **плюс** регрессия (п. 6). П. 3 обязан быть
**красным по смыслу** (D1 не починен) — это ожидаемый результат этапа.

## Риски этапа
| Риск | Проявление | Действие |
|---|---|---|
| `weather` оживает и даёт READY | `overall` станет `ready` → probe `exit 0`, D1 «исчезает» | фиксировать вывод целиком; при `ready` воспроизводить D1, выставив `MCP_WEATHER_URL` на недоступный адрес через `.env` (не правкой кода) |
| Скрипт требует `jq` | падение на парсинге | только `bash`/`curl`/`ssh`/`python3` — без `jq` |
| Панель провайдера закроет порт | `timeout` вместо ответа | шаг 0.5 мастер-плана; проверять `ss -ltnp` на VPS |

## Перечитывание
После закрытия гейта — перечитать `dev/migr_plan.md` (§4 «Этап 3», §5, §6) и
создать `dev/migr_plan_3.md`.
