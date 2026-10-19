# README_gateway.md — выкатка шлюза AI_9 на VPS (этап 10, S2)

> Операторская инструкция. Всё, что здесь описано, выполняет **оператор** на VPS
> и на хосте. Агент подготовил файлы и команды в формате
> «команда → ожидаемый вывод → чем проверить».
>
> Контур: часть 5 `Задание.txt` — доступ к домашнему агенту через VPS с белым IP.
> Публичный порт — **8080** (решение №22). MCP `:8000/:8010/:8020` **не трогаются**
> (решение №18). Туннель — **SSH reverse** (решение №12); WireGuard не применяется.
>
> **v1.2 (2026-10-14).** Отдельный venv шлюза `/home/t/doc/.venv` (решение №23);
> зависимости `flask` + `requests` (№24); копирование файлов без `git pull`;
> автосекрет `gateway/.secret` (№27); вопросы интервью — единый источник истины (№26).

## Что где лежит

| Файл | Назначение |
|---|---|
| `gateway/app.py` | Flask-шлюз: вход, регистрация, интервью, чат, лимиты, прокси на фасад |
| `gateway/users.py` | Пользователи (пароль — хэшем) + история чата (SQLite) |
| `gateway/config.py` | Загрузка `gateway.json` + секрет сессии (env или автосекрет) |
| `gateway/gateway.json` | Конфиг: адрес фасада, таймаут, порт, лимиты, сессия (секретов нет) |
| `gateway/questions.py` | Чтение/сверка снапшота вопросов интервью |
| `gateway/questions.json` | Снапшот вопросов интервью (генерируется `sync_questions.py`) |
| `gateway/sync_questions.py` | Обновление снапшота вопросов (запускается **на хосте**) |
| `gateway/templates/` | `login.html`, `register.html`, `interview.html`, `chat.html` |
| `dev/vps/units/ai9-gateway.service` | Юнит шлюза (**на VPS**) |
| `dev/vps/units/ai9-tunnel.service` | Юнит туннеля (**на ХОСТЕ**) |
| `dev/vps/sshd_gateway.snippet` | Справка по `sshd` (в текущей схеме правки не нужны) |
| `dev/vps/services.list` | Список юнитов VPS (добавлен `ai9-gateway:8080`) |

## Предусловия

- На хосте работает фасад: `python serve.py` (слушает `127.0.0.1:8090`).
- SSH-алиас `mcp-vps` настроен (см. `dev/vps/ssh_config.snippet`).
- На VPS есть Python 3 (для создания отдельного venv шлюза).

---

## Шаги выкатки

### 1. Создать отдельное окружение шлюза и поставить зависимости

Отдельный venv — прямо под `/home/t/doc/` (решение №23), чтобы не путаться с
MCP-venv `/home/t/doc/mcp/ai9`. **MCP-юниты не трогаем** — они остаются на своём venv.

```bash
# зайти на VPS
ssh mcp-vps

# создать окружение (если ещё нет)
python3 -m venv /home/t/doc/.venv

# активировать
source /home/t/doc/.venv/bin/activate
# проверить, что python теперь из окружения
which python         # → /home/t/doc/.venv/bin/python

# поставить ДВЕ библиотеки: flask — сайт; requests — обращения к фасаду (решение №24)
pip install flask requests

# проверка
python -c "import flask, requests; print(flask.__version__, requests.__version__)"

# выйти из окружения
deactivate
```

Ожидаемо: `Successfully installed flask-3.x requests-2.x ...`; проверка печатает
две версии. Проверка без активации:
`ssh mcp-vps '/home/t/doc/.venv/bin/python -c "import flask, requests; print(flask.__version__, requests.__version__)"'`.

### 2. Скопировать файлы шлюза на VPS (без `git pull`)

Обновлять код на VPS через git пока не будем — копируем только нужное шлюзу.
Команды выполняются **на хосте** (из корня AI_9).

> **На VPS нет `rsync`** (проверено при выкатке 2026-10-14). Копируем через `tar`
> по SSH — тот же результат, те же исключения. Если `rsync` на VPS появится,
> команды ниже можно заменить на `rsync -av --exclude ...`.

```bash
# 1) сам шлюз (без рантайм-мусора: БД, кэш, автосекрет)
tar czf - --exclude='users.db' --exclude='__pycache__' --exclude='.secret' gateway \
  | ssh mcp-vps 'mkdir -p /home/t/doc/AI_9 && tar xzf - -C /home/t/doc/AI_9'

# 2) юнит шлюза + список сервисов + деплой-скрипт + .gitignore
ssh mcp-vps 'mkdir -p /home/t/doc/AI_9/dev/vps/units'
tar czf - dev/vps/units/ai9-gateway.service dev/vps/services.list \
    dev/vps/deploy_services.sh .gitignore \
  | ssh mcp-vps 'tar xzf - -C /home/t/doc/AI_9'
```

Ожидаемо: `tar` молча передаёт файлы. Проверка:
`ssh mcp-vps 'ls /home/t/doc/AI_9/gateway/'` → `app.py config.py gateway.json
questions.json questions.py sync_questions.py templates users.py`.


### 3. Точный текст `.gitignore` на VPS

Файл `.gitignore` общий для хоста и VPS. Вставить как есть в
`/home/t/doc/AI_9/.gitignore` (или скопировать шагом 2.4). Ключевые для шлюза
строки — `gateway/users.db` (БД с пользователями и паролями — коммитить нельзя),
`gateway/__pycache__/` и `gateway/.secret` (автосекрет сессии).

```gitignore
# Скрыть файлы с ключами
.env
ENV

# Python
__pycache__/
*.pyc
.pytest_cache

# Временные файлы
check_models.py
.kodacli
.tmp

# Видео
.mp4
.mov

# SSH
.ssh

# RAG: артефакты индекса (восстанавливаются командой --rag-ingest)
rag/index/
rag/.tmp/

# Шлюз на VPS: база пользователей и история чата (создаётся на месте, не в git)
gateway/users.db
gateway/__pycache__/
# Автосекрет сессии шлюза (решение №27) — генерируется на месте, не в git
gateway/.secret
```

> **Важно про `Den_log.md` / `tokens.csv`.** Это артефакты-доказательства (колонка
> `model` в `tokens.csv`, `model=` в `Den_log.md`) — они **остаются** в git. Тестовый
> шум от живых прогонов откатывается перед коммитом командой
> `git checkout -- Den_log.md tokens.csv` (выполняет оператор). В `.gitignore` их
> добавлять **бесполезно**: правило действует только на неотслеживаемые файлы.

### 4. Задать секрет сессии (или положиться на автосекрет)

Секрет подписывает cookie входа. Порядок (решение №27): env `GATEWAY_SECRET` →
файл `gateway/.secret` → сгенерировать случайный и сохранить в файл.

```bash
# вариант А (рекомендуется): задать секрет в .env
ssh mcp-vps 'grep -q GATEWAY_SECRET /home/t/doc/AI_9/.env || \
  echo "GATEWAY_SECRET=$(openssl rand -hex 32)" >> /home/t/doc/AI_9/.env'
```

Ожидаемо: в `.env` появилась строка `GATEWAY_SECRET=...` (в git не коммитится).
Проверка: `ssh mcp-vps 'grep -c GATEWAY_SECRET /home/t/doc/AI_9/.env'` → `1`.

> Если `GATEWAY_SECRET` не задан, шлюз при первом запуске сам создаст случайный
> секрет в `gateway/.secret` (в `.gitignore`). Предсказуемого dev-секрета в коде нет.

### 5. Развернуть юнит шлюза

```bash
ssh mcp-vps 'cd /home/t/doc/AI_9 && bash dev/vps/deploy_services.sh'
```

Ожидаемо: в статусе `ai9-gateway active :8080`; MCP-юниты по-прежнему `active`.

### 6. Поднять туннель на ХОСТЕ

> ⚠ **Это команды на ДОМАШНЕМ компьютере (хосте), а НЕ на VPS.** Юнит туннеля
> ставится на хост и **не входит** в `dev/vps/services.list` (тот список — для VPS).

Предпосылки (проверить один раз):
- в `~/.ssh/config` есть алиас `mcp-vps` (см. `dev/vps/ssh_config.snippet`);
- ключ `~/.ssh/id_ed25519_AI_9_vps` существует и добавлен на VPS;
- проверка: `ssh mcp-vps 'echo ok'` → `ok`.

```bash
# 1) положить юнит в пользовательские юниты хоста
cp dev/vps/units/ai9-tunnel.service ~/.config/systemd/user/

# 2) перечитать юниты и включить туннель (сейчас и при каждом входе)
systemctl --user daemon-reload
systemctl --user enable --now ai9-tunnel

# 3) чтобы юнит жил даже без активного входа в систему (после перезагрузки хоста)
loginctl enable-linger "$USER"

# 4) проверка статуса
systemctl --user status ai9-tunnel --no-pager
systemctl --user is-active ai9-tunnel      # → active
journalctl --user -u ai9-tunnel -n 20 --no-pager   # последние строки лога
```

Ожидаемо: `active (running)`. Проверка на VPS:
`ssh mcp-vps 'ss -ltnp | grep 8090'` → `127.0.0.1:8090`.

> **⚠ Важно: `ControlMaster=no` в юните туннеля.** В `~/.ssh/config` для `mcp-vps`
> включён `ControlMaster auto` (общий мультиплексированный канал). Если туннель
> подключится к уже существующему master, forward зарегистрируется на нём, а сам
> процесс `ssh` сразу завершится (`status=0`) → systemd зациклит рестарт, порт 8090
> не поднимется. Поэтому в `ai9-tunnel.service` **обязательны** `-o ControlMaster=no`
> и `-o ControlPath=none` — туннелю нужна собственная выделенная сессия. (Проверено
> при выкатке 2026-10-14: без этих опций юнит уходил в бесконечный рестарт.)

> **Зачем `Restart=always`.** Хост сам держит исходящий SSH-канал к VPS. Если канал
> оборвётся (сеть, сон, перезагрузка VPS), systemd поднимет его сам через 5 секунд
> (`RestartSec=5`). Проброс портов на роутере не нужен; WireGuard не применяется.
> Проброшенный порт слушает **только loopback VPS** — фасад из интернета недоступен.

### 7. Проверить сквозной путь

```bash
curl -s http://91.188.212.77:8080/ -o /dev/null -w "gateway HTTP %{http_code}\n"
```

Ожидаемо: `HTTP 302` (редирект на `/login`). Затем в браузере:
`http://91.188.212.77:8080` → регистрация → интервью → чат.

### 8. Сохранность MCP (решение №18)

```bash
./dev/vps/mcp_vps.sh status
```

Ожидаемо: `mcp-time-server`, `mcp-scheduler-server`, `mcp-pipeline-server` — `active`;
порты `:8000/:8010/:8020` слушают. Шлюз их не затронул.

---

## Обновление вопросов интервью (решение №26)

Вопросы интервью — **единый источник истины**: канон в `core/agent.py`
(`INTERVIEW_QUESTIONS`). Шлюз на VPS хранит **снапшот** `gateway/questions.json` с
отпечатком (sha256). При открытии формы шлюз сверяет свой отпечаток с хостовым
(`GET /interview/questions`). Если они разошлись — вместо формы показывается
**«Вопросы интервью устарели — обратитесь к администратору»**.

Если вопросы на хосте изменили — обновить снапшот на VPS (команды **на хосте**):

```bash
# 1) пересобрать снапшот из канона ядра
.venv/bin/python gateway/sync_questions.py

# 2) скопировать снапшот на VPS и перезапустить шлюз
rsync -av gateway/questions.json mcp-vps:/home/t/doc/AI_9/gateway/questions.json
ssh mcp-vps 'systemctl --user restart ai9-gateway'
```

Ожидаемо: `sync_questions.py` печатает отпечаток и три вопроса; после рестарта
форма интервью снова открывается.

---

## Ограничения

- **Rate-limit — in-memory** (решение №25): окно 60 с, счётчик на процесс,
  **сбрасывается при рестарте шлюза**. Значения (6/мин, 8000 символов) — в
  `gateway.json`. Персистентность лимита — предмет этапа 11.
- **Лог не пишет текст ответа**: пишутся логин, длина запроса и
  модель. Ответ и так хранится в истории чата на VPS и в `Den_log.md` фасада.
- **Очередь фасада — 1 запрос**: локальная модель считает одна; второй пользователь
  ждёт (статус «занято»), а не получает ошибку.

## Матрица отказов

| Симптом | Причина | Что делать |
|---|---|---|
| `502/503` в чате | фасад/туннель недоступен | `systemctl --user status ai9-tunnel`; поднять `serve.py` на хосте |
| `connection refused` на `:8080` | юнит шлюза не запущен | `systemctl --user restart ai9-gateway` |
| `429` в чате | лимит 6/мин | подождать минуту (значение — в `gateway.json`) |
| `413` в чате | запрос > 8000 символов | сократить запрос |
| «вопросы интервью устарели» | снапшот на VPS разошёлся с хостом | `gateway/sync_questions.py` + копирование (см. выше) |
| пустой список моделей | фасад не отдаёт `/models` | проверить `curl 127.0.0.1:8090/models` на хосте |

## Безопасность

- Пароли — только хэшами (PBKDF2-HMAC-SHA256, соль на пользователя); открытый текст
  не хранится и не логируется.
- Секрет сессии — из `.env` (`GATEWAY_SECRET`) или автосекрет `gateway/.secret`
  (в `.gitignore`); предсказуемого dev-секрета в коде нет.
- Публичен только `:8080`; фасад (`:8090`) остаётся внутренним (loopback VPS).
- `gateway/users.db` (пользователи + история) и `gateway/.secret` — в `.gitignore`.