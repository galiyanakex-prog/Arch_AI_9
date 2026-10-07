# migr_log.md — журнал миграции `AI_9` (Ревизия 5): инфраструктура VPS (И) + правки D1–D7

> Журнал результатов миграции по рабочим планам `dev/migr_plan_0.md` … `dev/migr_plan_N.md`
> (единая сквозная нумерация; один файл = один этап = один гейт).
> План-эталон: `dev/migr_plan.md` (Ревизия 5; формат записей — §6.3, правила — §1.1, §5).
> Обозначения: ✅ выполнено · ❌ не выполнено (повтор) · ⚠ допустимое временное отклонение ·
> ⛔ блокирующая ошибка (ожидание указаний).
> **Гейт этапа закрыт только зелёным ЖИВЫМ прогоном против VPS** `91.188.212.77`;
> детерминированный контур (unit/L3/L4/гейт) — обязательная регрессия, но сам гейт не закрывает.
> История прошлых ревизий — в `dev/old_vers/` (1 — stdio дня 16, 2 — Ревизия 2 дня 16,
> 3 — снимок на входе Ревизии 3, 4 — снимок на входе Ревизии 4, 5 — снимок на входе Ревизии 5).
>
> **Ревизия 5.** Задача: довести `AI_9` к подтверждённому живыми прогонами выполнению
> `ND/tasks/n_4/Задание_d20.txt` (несколько MCP-серверов, выбор нужного инструмента,
> корректная маршрутизация, длинный флоу, порядок и отсутствие лишних вызовов).
> Два контура в одном конвейере: этапы `0–3` — инфраструктура VPS (И1–И4),
> этапы `4–12` — точечные правки продукта (дефекты D1–D7 из аудита 2026-09-28).
> **Коммиты — только за оператором**; агент готовит правки и предлагает текст сообщения.

---

## Этап 0 — Доступ и привилегии (И1 + И2а)
- Статус: ✅ завершён (2026-09-30)
- Было: SSH на VPS `91.188.212.77` не работал (публичный ключ был положен как
  **каталог** `~/.ssh/authorized_keys`, права `~/.ssh` — `0600`/`0777`); `sudo`
  требовал пароль; `linger` для `t` не включён; `ufw` не настроен; публичные
  порты MCP (8000/8010/8020) не открыты; `mcp-time-server` — `enabled`, `inactive`.
- Стало:
  - SSH: `~/.ssh/authorized_keys` — настоящий файл (90 байт, `600`), прежний
    каталог переименован в `authorized_keys.d.bak`, `~/.ssh` — `700`; локальный
    алиас `mcp-vps` в `~/.ssh/config` (вне репозитория) с `IdentityFile
    ~/.ssh/id_ed25519_AI_9_vps`, `IdentitiesOnly yes`, keepalive, ControlMaster;
  - вход без пароля: `ssh -o BatchMode=yes mcp-vps 'whoami; hostname'` → `t`,
    `vm-4933f0e1-90a0-4f7b-b303-276fa9b244fe`;
  - `loginctl enable-linger t` → `Linger=yes`, `/run/user/1001` существует,
    `systemctl --user status` отвечает (State: running, Failed: 0 units);
  - `/etc/sudoers.d/mcp-ops` создан через `visudo` — узкий NOPASSWD-белый список
    (7 команд: `loginctl enable-linger/show-user`, `ufw allow 8000/8010/8020/tcp`,
    `ufw status verbose`, `ufw show added`); первая попытка дала syntax error
    (в файл попала строка с fence-маркерами), исправлено;
  - рабочее пространство на VPS: код в git-репозитории `/home/t/doc/AI_9`
    (origin `GAL_444`, HEAD `7feacbd`), venv `/home/t/doc/mcp/ai9`
    (Python 3.13.5, pip 25.1.1).
- Живые прогоны:
  - `ssh -o BatchMode=yes mcp-vps 'whoami; hostname; echo EXIT=$?'` → `t`, hostname, `EXIT=0`;
  - `ssh mcp-vps 'loginctl show-user t --property=Linger'` → `Linger=yes`;
  - `ssh mcp-vps 'sudo -n ufw status verbose'` → `Status: inactive` (без пароля);
  - TCP-тест порта 22 снаружи — открыт.
- Регрессия: код продукта на этом этапе не тронут (этап чисто инфраструктурный).
- Артефакты: VPS — `/etc/sudoers.d/mcp-ops`, `~/.ssh/authorized_keys`,
  `~/.doc/mcp/ai9/venv`; локально — `~/.ssh/config` (алиас), `AI_9/.ssh/` (в `.gitignore`).
- ⚠ Отклонение (зафиксировано): `sudo -n -l` показывает **сверх** белого списка
  строку `(ALL : ALL) ALL` — пользователь `t` состоит в группе `sudo` (базовая
  конфигурация Debian). Белый список работает, но **не ограничивает** привилегии:
  полный `sudo` всё равно доступен (с паролем). Для гейта «не шире белого списка»
  это красный пункт; решение оператора — оставить как есть на учебном VPS или
  вывести `t` из группы `sudo` (`gpasswd -d t sudo`) и опираться на NOPASSWD-список.
- ⚠ `ufw` — `inactive`: правила `allow` не применяются к выключенному фаерволу;
  фактический барьер сейчас только панель провайдера. Включать `ufw enable` до
  добавления `allow OpenSSH` запрещено — потеря SSH.
- Коммит: на VPS не создавался (только `git pull`); локально — на усмотрение оператора.
- Перечитывание migr_plan.md: ✅ (2026-09-30)
- Гейт 0→1: ⚠ **условно пройден** — пункты 1–3 зелёные (SSH, Linger, `sudo -n`),
  пункт 4 (`sudo -n -l` не шире белого списка) — красный по причине выше,
  пункт 5 (TCP-тест 8000/8010/8020 → refused) — не выполнен, перенесён в этап 1
  вместе с шагом 0.5 (панель провайдера).

---

## Переход проекта: `Nedela_4/den_20/` → корень `AI_9/` (2026-09-30, вне нумерации этапов)
- Статус: ✅ завершён
- Было: проект лежал в `AI_9/Nedela_4/den_20/`; `run.sh` и `check_acceptance.sh`
  считали venv по `../../.venv`; `run.desktop` указывал на мёртвый
  `Nedela_3/den_12`; история хранилась копиями директорий (`Nedela_*/den_NN/`).
- Стало:
  - содержимое `Nedela_4/den_20/` перенесено в корень `AI_9/` через `git mv`
    (git фиксирует **rename 240 файлов**, `git log --follow` работает);
  - путь к коду **постоянный** — юниты на VPS пишутся один раз
    (`WorkingDirectory=/home/t/doc/AI_9`, `ExecStart=/home/t/doc/mcp/ai9/bin/python …/Kod.py`)
    и не меняются при переходе на следующий день;
  - история куратору вынесена в **отдельный приватный репозиторий `AI_9/archive`**
    (снимки по тегам через `git archive`, однонаправленно: из основного репа,
    правки в архив не переносятся); архивные недели из рабочего дерева удалены;
  - задания и модели переложены в `ND/tasks/n_N/`, `ND/models/`;
  - пути исправлены: `run.sh` → `source .venv/bin/activate`;
    `dev/tests_debug/check_acceptance.sh:9` → `PY="$KOD/.venv/bin/python"`;
    `run.desktop` → `Exec/Path` на корень `AI_9`;
  - `.gitignore` дополнен: `__pycache__/`, `*.pyc` (`.pyc` ранее трекались и
    пачкали `git status` на каждом прогоне).
- Проверка (после переноса, из нового корня):
  - L1 `compileall core integrations memory storage Kod.py` → EXIT=0;
  - `./run.sh --help` → usage, EXIT=0;
  - L2 `unit_runner.py` → **122 OK, 0 FAIL**;
  - L3 `smoke.py` → **SMOKE OK**, EXIT=0;
  - L4 `scenario.py` → **SCENARIO OK**, EXIT=0;
  - гейт `API_KEY=test-key bash dev/tests_debug/check_acceptance.sh` → **21/21, FAIL=0**.
- Инцидент при правке: `check_acceptance.sh` (412 строк) был ошибочно перезаписан
  фрагментом; восстановлен из `HEAD` (`git show HEAD:Nedela_4/den_20/...`) и
  исправлен точечно (`sed`, строка 9). Файл проверен `bash -n` и полным прогоном —
  потерь нет.
- Коммит: `c60fcac «переход на чистую архитектуру (без архивных копий)»` — выполнен оператором.

---

## Этап 1 — `time` под управлением без sudo + публичный доступ (И2б)
- Статус: ✅ завершён (2026-09-30)
- Было: `mcp-time-server` — системный юнит (`/etc/systemd/system`), требовал sudo
  для управления; код сервера жил вне репозитория
  (`/home/t/doc/mcp/mcp-time-server/time_server_http.py`, отдельный venv);
  venv `/home/t/doc/mcp/ai9` пуст (только pip); снаружи `:8000` — connection refused.
- Стало:
  - сервер перенесён в репозиторий: `integrations/mcp/time_server.py`
    (`python -m integrations.mcp.time_server`, env `TIME_PORT`, `allowed_hosts` —
    точный набор `91.188.212.77:8000` + localhost, `"*"` отсутствует);
  - зависимости зафиксированы: `requirements.txt` (mcp==2.2.0, uvicorn, dotenv);
    venv `/home/t/doc/mcp/ai9` укомплектован (тот же venv — для всех серверов);
  - системный юнит отключён (`sudo systemctl disable --now mcp-time-server`);
  - пользовательский юнит `~/.config/systemd/user/mcp-time-server.service`
    (источник — `dev/vps/units/`), `WantedBy=default.target`, `Restart=always`;
  - идемпотентный деплой без sudo: `dev/vps/deploy_services.sh` + `dev/vps/services.list`
    (формат `имя:порт`; экспорт `XDG_RUNTIME_DIR`/`DBUS_SESSION_BUS_ADDRESS` под
    не-интерактивный SSH — риск §8 закрыт);
  - регрессия Host-защиты: `dev/tests_debug/unit/test_time_server.py`
    (unittest.TestCase; на локальном venv без серверных зависимостей — SKIP,
    на VPS-venv — OK; неверный набор allowed_hosts всегда FAIL).
- Живые прогоны (гейт 1→2):
  - `systemctl --user is-active mcp-time-server` → `active`; `is-enabled` → `enabled`;
  - `ss -ltnp` → `LISTEN 0.0.0.0:8000` (python, PID юнита);
  - handshake СНАРУЖИ (с локальной машины, `dev/tests_debug/.tmp/live_handshake.py`):
    `initialize` → HTTP 200 + `mcp-session-id`; `notifications/initialized` → принято;
    `tools/list` → `{"name":"get_time",...}` — EXIT=0;
  - restart-тест: `systemctl --user restart` → `active`, порт слушает (1 сокет).
- Регрессия: L2 `unit_runner.py` → **122 OK, 0 FAIL**; guard-тест отдельно
  (`unittest discover -s dev/tests_debug/unit -p test_time_server.py`) → **OK**;
  L3 `SMOKE OK`; L4 `SCENARIO OK`.
- Артефакты: VPS — `~/.config/systemd/user/mcp-time-server.service`,
  venv `/home/t/doc/mcp/ai9` (mcp 2.2.0 + uvicorn + dotenv);
  репозиторий — `integrations/mcp/time_server.py`, `requirements.txt`,
  `dev/vps/{deploy_services.sh,services.list,units/mcp-time-server.service}`,
  `dev/tests_debug/unit/test_time_server.py`.
- ⚠ Замечание: в `migr_plan.md` шаг 1.1 описывал unit для прежнего
  `time_server_http.py`; фактически сервер перенесён в пакет `AI_9` и запускается
  `-m integrations.mcp.time_server` — путь к коду постоянный (соответствует
  решению о переходе в корень). Прежний каталог `/home/t/doc/mcp/mcp-time-server/`
  на VPS оставлен как есть (не удалён), системный юнит отключён.
- Коммит: `c06dfaf` — выполнен оператором (рабочее дерево чистое, в `origin/main`).
- Перечитывание migr_plan.md: ✅ (2026-09-30)
- Гейт 1→2: ✅

---

## Этап 2 — Скрипты отладки + живая базовая линия D1 (И4)
- Статус: ✅ завершён (2026-09-30)
- Было: D1 наблюдался только против мёртвых URL (не доказательство); ручной набор
  `curl` для handshake; операторского контура `dev/vps/` не было.
- Стало:
  - `dev/vps/mcp_vps.sh` — единая точка отладки (`status/probe/tools/call/log/
    deploy/tunnel`), без `jq` (bash/curl/ssh/python3); расшифровки пишет в
    `dev/vps/evidence/`;
  - `dev/vps/README_vps.md` (матрица отказов: refused/421/timeout/Missing session
    ID/Session not found/Parse error), `dev/vps/ssh_config.snippet`, `evidence/`;
  - `.env` (в `.gitignore`) с `MCP_SERVER_URL=http://91.188.212.77:8000/mcp`.
- Живые прогоны (гейт 2→3):
  - `mcp_vps.sh status` → `mcp-time-server active`, `:8000` слушает;
    `scheduler`/`pipeline` — `inactive` (ещё не подняты, этап 3);
  - `mcp_vps.sh probe 8000` → `mcp-session-id` непустой, `tools/list` → `get_time`
    (расшифровка `evidence/probe_8000_20260930T200910Z.txt`);
  - **D1 живьём (красное):** `Kod.py --mcp-probe` →
    `time` READY, `weather` READY, `scheduler`/`pipeline` FAILED →
    `[MCP] Соединение не установлено (overall: degraded)` → **EXIT=1**,
    хотя сервер задания жив и `get_time` доступен. Причина: `run_mcp_probe`
    требует `overall == "ready"`, а `DEFAULT_SERVERS` держит `weather/scheduler/
    pipeline` с `enabled=True` на недоступных адресах. Правка — этап 5;
  - `mcp_vps.sh call 8000 get_time {"timezone_name":"Europe/Moscow"}` →
    `2026-09-30T23:09:21.839043+03:00` (расшифровка `evidence/call_8000_get_time_*`).
- Регрессия: L2 **122 OK, 0 FAIL**; L3 **SMOKE OK**; L4 **SCENARIO OK**;
  гейт **21/21, FAIL=0**. Код продукта не изменён (`git status` по `Kod.py`,
  `core/`, `integrations/` пуст).
- Артефакты: `dev/vps/{mcp_vps.sh,README_vps.md,ssh_config.snippet,evidence/}`,
  `dev/migr_plan_2.md`; локально `.env` (не в git).
- ⚠ Замечание: `weather` неожиданно оказался READY (внешний сервер жив) — это не
  мешает D1 (overall всё равно `degraded` из-за scheduler/pipeline). Если в
  будущем `weather` отвалится, D1 воспроизводится тем же прогоном.
- Коммит: предложен `dev/vps: операторский контур отладки + живое воспроизведение D1 (этап 2, И4)` — за оператором.
- Перечитывание migr_plan.md: ✅ (2026-09-30)
- Гейт 2→3: ✅

---

## Этап 3 — Второй/третий серверы на VPS (И3)
- Статус: ✅ завершён (2026-09-30)
- Было: `scheduler`/`pipeline` — `inactive`; юнитов нет; `services.list` — только
  `time`; `--mcp-probe` давал `degraded` (D1) из-за мёртвых scheduler/pipeline.
- Стало:
  - юниты `dev/vps/units/mcp-scheduler-server.service` (:8010),
    `mcp-pipeline-server.service` (:8020) — общий venv `/home/t/doc/mcp/ai9`,
    `WorkingDirectory=/home/t/doc/AI_9`, `Restart=always`;
  - `services.list` — три сервера (`time:8000`, `scheduler:8010`, `pipeline:8020`);
  - **исправлен баг `deploy_services.sh`**: `while read` терял последнюю строку
    без завершающего `\n` (pipeline не деплоился) → добавлено `|| [ -n "$name" ]`
    в оба цикла;
  - `.env` дополнен публичными адресами: `SCHEDULER_MCP_URL`/`PIPELINE_MCP_URL`
    → `http://91.188.212.77:8010|8020/mcp` (дефолты в `config.py` — `127.0.0.1`,
    т.к. рассчитаны на запуск клиента **на** VPS).
- Живые прогоны (гейт 3→4):
  - `mcp_vps.sh status` → все три `active`; `ss -ltnp` → `:8000`, `:8010`, `:8020`
    слушают;
  - `mcp_vps.sh probe 8010` → `mcp-session-id` + 7 тулов планировщика
    (`schedule_reminder`, `schedule_collection`, `record_observation`, `run_due`,
    `get_summary`, `latest_summary`, `list_jobs`);
  - `mcp_vps.sh probe 8020` → 4 тула пайплайна (`search`, `summarize`,
    `saveToFile`, `readFile`);
  - `Kod.py --mcp-probe` (все 4 HTTP-сервера живы) → **все READY**, 15 тулов,
    **EXIT=0** (D1 на этом прогоне не воспроизводится — все серверы доступны;
    красный сценарий D1 сохранён в записи этапа 2).
- Диагностика (важно для будущих этапов): `Cancelled via cancel scope` в
  `MCPGatewaySync` при подключении scheduler/pipeline — **не баг кода**, а
  маскировка `connection refused` (дефолт `127.0.0.1`). По одному и в комбинации
  VPS-серверов — все READY; сбой был только из-за неверного endpoint в `.env`.
- Регрессия: L2 **122 OK, 0 FAIL**; L3 **SMOKE OK**; L4 **SCENARIO OK**;
  гейт **21/21, FAIL=0**. Код продукта не изменён.
- Артефакты: `dev/vps/units/mcp-{scheduler,pipeline}-server.service`,
  `dev/vps/services.list`, `dev/vps/deploy_services.sh` (фикс),
  `dev/vps/evidence/probe_8010_*.txt`, `probe_8020_*.txt`.
- Коммит: предложен `dev/vps: scheduler+pipeline на VPS, фикс deploy_services (этап 3, И3)` — за оператором.
- Перечитывание migr_plan.md: ✅ (2026-09-30)
- Гейт 3→4: ✅

---

## Этап 4 — Базовая линия Ревизии 5 (M0)
- Статус: ✅ завершён (2026-09-30)
- Было: точка отсчёта перед правками D1–D6 не зафиксирована.
- Стало (счётчики, «как есть»):
  - L1 `py_compile` (Kod.py, core, memory, storage, integrations/mcp,
    integrations/scheduler) → **OK**;
  - L2 `unit_runner.py` → **122 OK, 0 FAIL**;
  - L3 `smoke.py` → **SMOKE OK**; L4 `scenario.py` → **SCENARIO OK**;
  - гейт `check_acceptance.sh` → **21/21, FAIL=0**.
- Красные проверки дефектов (воспроизведены):
  - **D1** — `Kod.py --mcp-probe` при недоступном сервере → `overall: degraded`
    → exit 1 (живой прогон этапа 2);
  - **D2** — REPL `--mcp`: `[Режим] Доставка слоёв: ['invariants','long_term',
    'profile','short_term','working']` — **`tools` отсутствует** (затёрт
    `--deliver` в `Kod.py:942`);
  - **D3** — `grep multiserver dev/tests_debug/scenario*` → пусто;
    `dev/tests_debug/.tmp/m4_check.py` отсутствует;
  - **D4** — `/mcp route найди погоду в Москве` → печатает **весь каталог**
    (15 тулов), а не кандидата (подстрочный EN-матчинг, `Kod.py:385`);
  - **D5** — `grep wait_for integrations/mcp/transport.py` → пусто
    (таймаут `timeout_seconds` не применяется);
  - **D6** — `/mcp connect time` → `/mcp status` → поднимает **все 4** сервера
    (`time/weather/scheduler/pipeline`), а не только `time`; `summary=text[:500]`
    (`gateway.py:176`).
- Регрессия: см. счётчики выше (все зелёные). Код продукта не изменён.
- Артефакты: `dev/migr_plan_4.md`; выводы — в этой записи.
- Коммит: не требуется (этап фиксации; правки — этапы 5–10).
- Перечитывание migr_plan.md: ✅ (2026-09-30)
- Гейт 4→5: ✅

---

## Этап 5 — D1: порог probe + `enabled`-политика
- Статус: ✅ завершён (2026-09-30)
- Было (красное, этап 2/4): `run_mcp_probe` требовал `overall == "ready"`; при
  части READY (`degraded`) → `exit 1`; `scheduler`/`pipeline` в `DEFAULT_SERVERS`
  `enabled=True` на недоступных по умолчанию адресах.
- Стало:
  - `Kod.py::run_mcp_probe(only_server=None)` — успех = **≥1 READY-сервер и
    непустой список**; печатает `READY: <список>; overall: <…>`; пустой каталог →
    `exit 1`; добавлен флаг `--mcp-probe-server <id>` (строгая проверка одного);
  - `integrations/mcp/config.py` — `scheduler`/`pipeline` `enabled=False` по
    умолчанию (остаются зарегистрированными), включаются env-флагами
    `SCHEDULER_MCP_ENABLED`/`PIPELINE_MCP_ENABLED` (`_env_flag`);
  - `overall_state()` **не изменён** (семантика состояний — инвариант).
- Живые прогоны (гейт 5→6):
  - без env → `READY: time, weather; overall: ready` → **exit 0**;
  - `--mcp-probe-server time` → `READY: time`, 1 тул → **exit 0**;
  - `SCHEDULER_MCP_ENABLED=1 PIPELINE_MCP_ENABLED=1` → 4 сервера READY, 15 тулов
    → **exit 0**;
  - все адреса мёртвые → `Ни один сервер не подключён` → **exit 1**.
- Регрессия: L2 **125 OK, 0 FAIL** (122 + 3 новых `test_d1_probe.py`);
  L3 **SMOKE OK**; L4 **SCENARIO OK**; гейт **21/21, FAIL=0**.
- Побочные правки (следствие смены формата строки probe):
  `dev/tests_debug/check_acceptance.sh:211` и `dev/tests_debug/smoke.py:237` —
  grep/assert `(READY)` → `(READY` (совместимость с новым выводом).
- Артефакты: `Kod.py`, `integrations/mcp/config.py`,
  `dev/tests_debug/unit/test_d1_probe.py`, `dev/migr_plan_5.md`.
- Коммит: предложен `D1: порог probe (≥1 READY) + enabled-политика серверов (этап 5)` — за оператором.
- Перечитывание migr_plan.md: ✅ (2026-09-30)
- Гейт 5→6: ✅

---

## Этап 6 — D2: каталог реально в промте (`deliver` + протокол)
- Статус: ✅ завершён (2026-09-30)
- Было (красное, этап 4): `Kod.py:961` затирал `agent.deliver` дефолтным
  `--deliver` → `tools` отсутствовал в промте; `TOOL_PROTOCOL_PROMPT` — статичная
  строка без имён инструментов.
- Стало:
  - `Kod.py`: при `--mcp` слой `tools` добавляется в `deliver` после применения
    `--deliver`; добавлен диагностический флаг `--no-tools-block`;
  - `core/llm_client.py`: `render_tool_protocol(tools)` — протокол ОТ КАТАЛОГА
    (квалифицированные имена + обязательные аргументы); пустой каталог → базовый
    `TOOL_PROTOCOL_PROMPT`;
  - `core/agent.py::_respond_with_tools` использует `render_tool_protocol(tools)`.
- Живые прогоны (гейт 6→7):
  - `--mcp` → `[Режим] Доставка слоёв: [..., 'tools', ...]` (tools присутствует);
  - `--mcp --no-tools-block` → `tools` отсутствует (диагностический откат);
  - без `--mcp` → `tools` отсутствует (регрессия = den_15);
  - `render_tool_protocol` → имена `mcp.time.get_time`, `mcp.pipeline.search` +
    «обязательные аргументы: query».
- Регрессия: L2 **128 OK, 0 FAIL** (125 + 3 новых `test_d2_tools_prompt.py`);
  L3 **SMOKE OK**; L4 **SCENARIO OK**; гейт **21/21, FAIL=0**.
- Артефакты: `Kod.py`, `core/llm_client.py`, `core/agent.py`,
  `dev/tests_debug/unit/test_d2_tools_prompt.py`, `dev/migr_plan_6.md`.
- Коммит: предложен `D2: каталог инструментов в промте (deliver + render_tool_protocol) (этап 6)` — за оператором.
- Перечитывание migr_plan.md: ✅ (2026-09-30)
- Гейт 6→7: ✅

---

## Этап 7 — D5: таймауты транспорта (`wait_for`)
- Статус: ✅ завершён (2026-10-01)
- Было (красное, этап 4): `grep wait_for integrations/mcp/transport.py` → пусто;
  `timeout_seconds` не применялся — зависший сервер вешал постоянный event loop
  `MCPGatewaySync`.
- Стало:
  - `_SessionTransport._with_timeout(coro, what)` — обёртка `asyncio.wait_for`
    по `timeout_seconds`; по истечении → `MCPConnectionError("таймаут …")`;
  - применён в `list_tools`, `call_tool` и в `initialize` обоих транспортов
    (stdio: подключение/сессия/initialize; HTTP: подключение/сессия/initialize).
- Живые прогоны (гейт 7→8):
  - `--mcp-probe` (time+weather) → READY, 4 тула, **exit 0** (ложных FAILED нет);
  - `SCHEDULER/PIPELINE_MCP_ENABLED=1` → 4 сервера READY, 15 тулов, **exit 0**;
  - `mcp_vps.sh call 8000 get_time` → `2026-10-01T01:32:08+03:00`.
- Регрессия: L2 **131 OK, 0 FAIL** (128 + 3 новых `test_d5_timeout.py`);
  L3 **SMOKE OK**; L4 **SCENARIO OK**; гейт **21/21, FAIL=0**.
- Артефакты: `integrations/mcp/transport.py`,
  `dev/tests_debug/unit/test_d5_timeout.py`, `dev/migr_plan_7.md`.
- Коммит: предложен `D5: таймауты транспорта (asyncio.wait_for) (этап 7)` — за оператором.
- Перечитывание migr_plan.md: ✅ (2026-10-01)
- Гейт 7→8: ✅

---

## Этап 8 — D3: мультисерверный длинный флоу
- Статус: ✅ завершён (2026-10-01)
- Было (красное, этап 4): в `scenario.py` мультисерверного сценария нет;
  `.tmp/m4_check.py` отсутствует — пункт «Проверьте» подтверждён декларативно.
- Стало:
  - `dev/tests_debug/scenario.py::scenario_multiserver_flow` (L4): 3 сервера
    (`time`/`pipeline`/`scheduler`) на `FakeMCPTransport` + `_Recorder` (порядок
    `(server, tool)`), программируемый `ScriptedClient`;
  - цепочка: `get_time` → `search` → `summarize` → `saveToFile` →
    `schedule_reminder`; проверки порядка, отсутствия лишних, маршрутизации,
    неизменности `TaskStage`, аудита == 5;
  - `dev/tests_debug/.tmp/live_multiserver_flow.py` — **живой** зеркальный прогон
    против VPS (реальные HTTP-транспорты);
  - `dev/tests_debug/scenario/scen_multiserver_flow.md` — описание сценария;
  - `check_acceptance.sh` — проверка 32 (наличие D3-флоу).
- Живые прогоны (гейт 8→9):
  - L4 `scenario.py` → `D3: мультисерверный длинный флоу … OK`, SCENARIO OK;
  - живой (VPS) → enabled `[time, weather, scheduler, pipeline]`, каталог 15 тулов,
    порядок 5 вызовов `[time → pipeline×3 → scheduler]`, все `succeeded`,
    `LIVE D3 OK`; лишних вызовов нет;
  - транскрипт: `dev/logs_reports/stages/stage_08_d3_live_20261001.txt`.
- Регрессия: L2 **131 OK, 0 FAIL**; L3 **SMOKE OK**; L4 **SCENARIO OK**;
  гейт **22/22, FAIL=0**.
- Артефакты: `dev/tests_debug/scenario.py`, `.tmp/live_multiserver_flow.py`,
  `scenario/scen_multiserver_flow.md`, `check_acceptance.sh`, `dev/migr_plan_8.md`.
- Коммит: предложен `D3: мультисерверный длинный флоу (порядок, маршрутизация, аудит) (этап 8)` — за оператором.
- Перечитывание migr_plan.md: ✅ (2026-10-01)
- Гейт 8→9: ✅

---

## Этап 9 — D4: осмысленный выбор инструмента
- Статус: ✅ завершён (2026-10-01)
- Было (красное, этап 4): `/mcp route` — подстрочный EN-матчинг, печатал весь
  каталог (15 тулов) вместо кандидата.
- Стало:
  - `core/tool_routing.py` (новый): `rank_tools(query, tools, top=3)` — чистая
    функция, RU→EN-эвристика (`RU_EN_HINTS` существительные + `RU_ACTION_HINTS`
    глаголы-действия вес 3), стоп-слова, раздельные токены имени/описания
    (имя вес 2 > описание вес 1); без SDK и сети;
  - `Kod.py::/mcp route` — печатает КАНДИДАТА с обоснованием + альтернативы;
    при нуле — «Совпадений нет».
- Живые прогоны (гейт 9→10):
  - unit `test_d4_routing` → 6 OK;
  - живой `/mcp route` (VPS, 15 тулов): «который час» → `time.get_time`;
    «собери данные» → `pipeline.search`; «обработай в сводку» → `pipeline.summarize`;
    «сохрани в файл» → `pipeline.saveToFile`; «напомни о сводке» →
    `scheduler.schedule_reminder`; «погода в Москве» → `weather.*`;
    «непонятно что» → «совпадений нет»;
  - REPL `/mcp route который час` → один кандидат (не весь каталог);
  - транскрипт: `dev/logs_reports/stages/stage_09_d4_route_20261001.txt`.
- Регрессия: L2 **137 OK, 0 FAIL** (131 + 6 новых `test_d4_routing.py`);
  L3 **SMOKE OK**; L4 **SCENARIO OK**; гейт **23/23, FAIL=0**.
- Артефакты: `core/tool_routing.py`, `Kod.py`,
  `dev/tests_debug/unit/test_d4_routing.py`, `.tmp/live_mcp_route.py`,
  `check_acceptance.sh`, `dev/migr_plan_9.md`.
- Коммит: предложен `D4: осмысленный выбор инструмента (rank_tools + /mcp route) (этап 9)` — за оператором.
- Перечитывание migr_plan.md: ✅ (2026-10-01)
- Гейт 9→10: ✅

---

## Этап 10 — D6: пакет мелких исправлений
- Статус: ✅ завершён (2026-10-01)
- Было (красное, этап 4): `/mcp connect <id>` поднимал ВСЕ серверы; `summary=text[:500]`
  терял данные в пайплайне; терминальные стадии не блокировали мутации;
  assistant-сообщение без валидного `tool_calls`.
- Стало:
  - `MCPGateway.start(only_server=None)` + `MCPGatewaySync.start(only_server)`;
    `Kod.py::/mcp connect <id>` поднимает ТОЛЬКО целевой сервер;
  - `ToolExecutionResult.text` (полный) рядом с `summary` (≤500, логи/аудит);
    `gateway.call_tool` заполняет `text`; `tool_executor` пробрасывает;
    `run_pipeline` несёт полный `text` между шагами; `agent` кладёт `text` в tool-сообщение;
  - `core/tools.py`: `TERMINAL_STAGES` + `infer_read_only(name)`; `tool_policy`:
    на done/failed/paused — только read-only (проверка ДО стадийного фильтра);
  - `agent._respond_with_tools`: assistant-сообщение с валидным `tool_calls`
    (id/type/function) + `tool_call_id` в tool-сообщении.
- Живые прогоны (гейт 10→11):
  - unit `test_d6_fixes` → 5 OK;
  - живой `/mcp connect time` → time READY; scheduler/pipeline **disconnected**
    (весь каталог НЕ поднят);
  - регрессия: L2 **142 OK, 0 FAIL**; L3 **SMOKE OK**; L4 **SCENARIO OK**;
    гейт **24/24, FAIL=0**.
- Артефакты: `integrations/mcp/gateway.py`, `Kod.py`, `core/tools.py`,
  `core/tool_executor.py`, `core/tool_pipeline.py`, `core/tool_policy.py`,
  `core/agent.py`, `dev/tests_debug/unit/test_d6_fixes.py`, `check_acceptance.sh`,
  `dev/migr_plan_10.md`.
- Коммит: предложен `D6: пакет мелких исправлений (connect/text/terminal/tool_calls) (этап 10)` — за оператором.
- Перечитывание migr_plan.md: ✅ (2026-10-01)
- Гейт 10→11: ✅

---

## Этап 11 — D7: авторизация транспорта
- Статус: ✅ завершён (2026-10-01)
- Было (красное, этап 4): `HttpMCPTransport` не передавал заголовки авторизации.
- Стало:
  - `MCPServerConfig.headers`/`token_env`; `_parse_server` читает их;
  - `HttpMCPTransport(headers, token_env)` → `_auth_headers()` (статические +
    `Authorization: Bearer <env>`), передача через `httpx2.AsyncClient(headers=…)`
    в `streamable_http_client(http_client=…)`; `close()` закрывает http_client;
  - `integrations/mcp/auth.py::auth_middleware` — серверная проверка Bearer
    (401 без токена); выключена, если env `MCP_AUTH_TOKEN` не задан; подключена
    в time/scheduler/pipeline серверах.
- Живые прогоны (гейт 11→12):
  - unit `test_d7_auth` → 6 OK;
  - живой: публичный сервер → подключён (1 тул); сервер с токеном → без токена
    отклонён (401), с токеном → подключён (1 тул);
  - транскрипт: `dev/logs_reports/stages/stage_11_d7_auth_20261001.txt`;
  - регрессия: L2 **148 OK, 0 FAIL**; L3 **SMOKE OK**; L4 **SCENARIO OK**;
    гейт **25/25, FAIL=0**.
- Артефакты: `integrations/mcp/config.py`, `integrations/mcp/transport.py`,
  `integrations/mcp/auth.py` (новое), `time_server.py`, `scheduler_server.py`,
  `pipeline_server.py`, `dev/tests_debug/unit/test_d7_auth.py`,
  `check_acceptance.sh`, `dev/migr_plan_11.md`.
- Коммит: предложен `D7: авторизация транспорта (Bearer + серверный 401) (этап 11)` — за оператором.
- Перечитывание migr_plan.md: ✅ (2026-10-01)
- Гейт 11→12: ✅

---

## Этап 12 — M7: финал (живой прогон, гейт, синхронизация)
- Статус: ✅ завершён (2026-10-01)
- Живые прогоны D1–D7 (транскрипты в `dev/logs_reports/stages/`):
  - D1 `--mcp-probe` без env → READY time+weather, exit 0; с env → 4 сервера/15 тулов;
  - D2 `--mcp` → deliver содержит `tools`; `--no-tools-block` → нет;
  - D3 мультисерверный флоу → 5 вызовов, порядок верный, все `succeeded`;
  - D4 `/mcp route` → кандидат с обоснованием; мусор → «совпадений нет»;
  - D5 `--mcp-probe` (все серверы) exit 0; `call 8000 get_time` → ISO-время;
  - D6 `/mcp connect time` → только time READY (scheduler/pipeline disconnected);
  - D7 публичный сервер → подключён; с токеном → без токена 401, с токеном READY.
- Итоговый гейт: L1 `py_compile` OK; SDK не протекает в `core` (чисто);
  L2 **148 OK, 0 FAIL**; L3 **SMOKE OK**; L4 **SCENARIO OK**;
  `check_acceptance.sh` **25/25, FAIL=0**.
- Синхронизация документов: `README.md`, `arch.md` (§7.2.2 «Дополнение дня 20
  (Ревизия 5)»), `dev/Проверка.md` (раздел «Ревизия 5 — живые прогоны D1–D7»).
- Артефакты: `dev/migr_plan_12.md`, обновлённые `README.md`/`arch.md`/`dev/Проверка.md`.
- Коммит: предложен `M7: финал Ревизии 5 (живой прогон, гейт, синхронизация) (этап 12)` — за оператором.
- Перечитывание migr_plan.md: ✅ (2026-10-01)
- Гейт (финальный): ✅

---

## Итог Ревизии 5 (день 20, 2026-10-01)

**Инфраструктурный контур VPS (этапы 0–3):**
- доступ/привилегии (SSH-алиас `mcp-vps`, sudoers-белый список — условно);
- `time` под `systemd --user` (:8000);
- скрипты отладки + живая база (`dev/vps/`);
- `scheduler:8010` + `pipeline:8020` (user-юниты `active`+`enabled`).

**Пакет правок дефектов продукта (этапы 4–12, метки D1–D7, M0/M7):**
- **D1** — порог probe (`≥1 READY` + непустой список) + `enabled`-политика серверов;
- **D2** — каталог инструментов в промте (`render_tool_protocol`);
- **D3** — мультисерверный длинный флоу (5 вызовов, порядок, маршрутизация);
- **D4** — осмысленный выбор инструмента (`core/tool_routing.py` + `/mcp route`);
- **D5** — таймауты транспорта (`asyncio.wait_for`);
- **D6** — пакет мелких исправлений (connect по id, полный `text`, терминальные
  стадии read-only, валидный `tool_calls`);
- **D7** — авторизация транспорта (`Authorization: Bearer` + серверный 401).

**Детерминированный контур:** L1 OK · L2 **148 OK** · L3 **SMOKE OK** ·
L4 **SCENARIO OK** · гейт **25/25** · SDK не протекает в `core`.

**Инварианты соблюдены:** `TaskStage` не менялся; MCP off по умолчанию;
`overall_state()` не менялся; временные файлы — только в `dev/tests_debug/.tmp/`;
рабочие `users/` не тронуты; нет захардкоженной последовательности вызовов в продукте.

---

_История Ревизии 4 (этапы M0–M6, 249 строк) — в `dev/old_vers/5/migr_log.md`.

