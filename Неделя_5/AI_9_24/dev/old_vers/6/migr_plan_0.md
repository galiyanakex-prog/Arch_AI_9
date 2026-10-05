# migr_plan_0.md — Этап 0. Доступ и привилегии (И1 + И2а)

> Рабочий план-алгоритм **одного этапа** на основе `dev/migr_plan.md` (Ревизия 5).
> Контур: **И (инфраструктура VPS)**. Метки цели: **И1** (SSH-доступ),
> **И2а** (привилегии без пароля + открытые порты).
> Порядок выполнения: **пошагово с оператором** — агент даёт команду, оператор
> выполняет и отчитывается, затем следующая команда.

## Цель этапа
Агент управляет VPS `91.188.212.77` (`t`) по ключу **без пароля**, выполняет
ограниченный набор root-операций через узкий sudoers-белый список, публичные
порты MCP открыты. Это фундамент: без него все дальнейшие гейты были бы
«мёртвыми» проверками.

## Предусловия (уже выполнено)
- Ключи созданы: `AI_9/.ssh/id_ed25519_AI_9_vps{,.pub}` (в `.gitignore`).
- `~/.ssh/authorized_keys` на VPS исправлен (был каталогом), права `700/600`.
- `ssh -i .ssh/id_ed25519_AI_9_vps t@91.188.212.77` → **работает** (проверено).
- Порт 22 открыт; `sudo` требует пароль; `docker` нет; `mcp-time-server` — `inactive`.

## Границы этапа
Не запускаем и не правим серверные сервисы (это этап 1), не создаём скрипты
(этап 2), не трогаем код `den_20`. Root-операции выполняет **оператор**; агент
не вводит и не хранит пароль sudo.

---

## Шаги

### ШАГ 0.1 — SSH-алиас `mcp-vps` (локальная машина)
Файл `~/.ssh/config` вне репозитория; добавляем блок, чтобы не помнить путь к ключу.
```bash
cat >> ~/.ssh/config <<'EOF'

Host mcp-vps
    HostName 91.188.212.77
    User t
    IdentityFile ~/.ssh/id_ed25519_AI_9_vps
    IdentitiesOnly yes
    ServerAliveInterval 60
    ServerAliveCountMax 3
    ExitOnForwardFailure yes
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 10m
EOF
chmod 600 ~/.ssh/config
```
> ⚠️ `IdentityFile` — абсолютный путь. Ключ лежит в репозитории
> (`AI_9/.ssh/…`); для `ssh` это допустимо, но **копию** ключа лучше держать в
> `~/.ssh/` (решение оператора; если перенесём — правим путь в блоке).

**Проверка:** `ssh -o BatchMode=yes mcp-vps 'whoami; hostname'` → `t`, без пароля.

### ШАГ 0.2 — Linger для пользователя `t` (VPS)
Без него `systemctl --user` живёт только время SSH-сессии → сервисы будут умирать.
```bash
loginctl enable-linger t || sudo loginctl enable-linger t
loginctl show-user t --property=Linger
ls -d /run/user/$(id -u)
```
**Ожидаемо:** `Linger=yes`, каталог `/run/user/1001` существует.

### ШАГ 0.3 — Узкий sudoers-белый список (VPS, только через `visudo`)
Даёт агенту `sudo -n` **только** для перечисленного; пароль не нужен и не светится.
```bash
sudo visudo -f /etc/sudoers.d/mcp-ops
```
Содержимое файла:
```sudoers
# AI_9: узкие root-права для управления MCP-серверами на учебном VPS
t ALL=(root) NOPASSWD: /usr/bin/loginctl enable-linger t
t ALL=(root) NOPASSWD: /usr/bin/loginctl show-user t
t ALL=(root) NOPASSWD: /usr/sbin/ufw allow 8000/tcp
t ALL=(root) NOPASSWD: /usr/sbin/ufw allow 8010/tcp
t ALL=(root) NOPASSWD: /usr/sbin/ufw allow 8020/tcp
t ALL=(root) NOPASSWD: /usr/sbin/ufw status verbose
t ALL=(root) NOPASSWD: /usr/sbin/ufw show added
```
Затем:
```bash
sudo -n ufw status verbose
sudo -n -l
```
**Ожидаемо:** `visudo` принимает синтаксис; `sudo -n ufw status verbose` проходит
**без запроса пароля**; `sudo -n -l` показывает ровно эти команды.

### ШАГ 0.4 — Открыть публичные порты MCP (VPS)
```bash
sudo -n ufw allow 8000/tcp
sudo -n ufw allow 8010/tcp
sudo -n ufw allow 8020/tcp
sudo -n ufw status verbose
```
**Ожидаемо:** три правила `ALLOW IN … 8000/8010/8020/tcp`.
> Если `ufw` выключен (`Status: inactive`) — правила не нужны, но фиксируем это в
> журнале: тогда барьер только в панели провайдера.

### ШАГ 0.5 — Security group провайдера (веб-консоль, только оператор)
В панели хостинга открыть **TCP 8000, 8010, 8020** (входящие, source `0.0.0.0/0`).
Это единственный шаг, недоступный из SSH.

### ШАГ 0.6 — Проверка снаружи (локальная машина)
```bash
for p in 8000 8010 8020; do
  timeout 6 bash -c "cat < /dev/null > /dev/tcp/91.188.212.77/$p" 2>/dev/null \
    && echo "$p ОТКРЫТ" || echo "$p закрыт/фильтруется"
done
```
**Ожидаемо на выходе этапа:** `8000` может быть ещё закрыт (сервер не запущен — это
этап 1), но **фильтрации по firewall быть не должно**: `connection refused`, а не
таймаут. 8010/8020 — аналогично (серверов ещё нет).

### ШАГ 0.7 — Журнал
Запись «Этап 0» в `dev/migr_log.md` по шаблону §6.3 мастер-плана (было/стало/
живой прогон/гейт). Коммитов на этом этапе нет (локальные файлы проекта — на
усмотрение оператора, VPS как git-репозиторий не менялся).

---

## Выход этапа
- `ssh mcp-vps` — без пароля;
- `Linger=yes`, `/run/user/1001` есть;
- `sudo -n ufw status verbose` — без пароля, белый список работает;
- порты 8000/8010/8020 разрешены в ufw и в панели провайдера.

## Гейт 0→1 (все пункты зелёные)
1. `ssh -o BatchMode=yes mcp-vps 'whoami'` → `t`, exit 0.
2. `ssh mcp-vps 'loginctl show-user t --property=Linger'` → `Linger=yes`.
3. `ssh mcp-vps 'sudo -n ufw status verbose'` → exit 0 (без пароля) + правила видны.
4. `ssh mcp-vps 'sudo -n -l'` → список совпадает с белым списком (шире — красный).
5. Локальный TCP-тест 8000/8010/8020 → **refused**, а не timeout (значит файрвол
   не мешает; «сервер не запущен» — норма до этапа 1).

## Откат
- `~/.ssh/config`: удалить добавленный блок (или закомментировать).
- sudoers: `sudo rm /etc/sudoers.d/mcp-ops` (файл отдельный — основной конфиг не тронут).
- ufw: `sudo ufw delete allow 8000/tcp` (и 8010, 8020).
- linger: `loginctl disable-linger t`.
- Панель провайдера: закрыть правила.
