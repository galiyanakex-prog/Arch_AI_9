# gateway_access.md — живой прогон шлюза (этап 10, S2)

> Транскрипт живого прогона шлюза `gateway/` на хосте против фасада `serve.py`
> (режим `--mock`, loopback, без интернета). Скрипт: `dev/tests_debug/.tmp/gateway_live_run.sh`.
> Дата: 2026-10-13. Цель — доказать контракты шлюза до выкатки на VPS.

## Схема прогона

```
curl → шлюз (127.0.0.1:8080) → фасад (127.0.0.1:8090, --mock) → агент
```

На VPS вместо loopback-фасада будет адрес `http://127.0.0.1:8090` через SSH
reverse tunnel (см. `tunnel_setup.md`).

## Результаты

| № | Проверка | Команда | Результат |
|---|---|---|---|
| 1 | Регистрация | `POST /register` | `HTTP 302` (редирект на интервью) |
| 2 | Интервью | `POST /interview` | `HTTP 302` (редирект на чат) |
| 3 | Список моделей с хоста | `GET /api/models` | JSON: `current`, `models[]` (cloud + lmstudio) |
| 4 | Чат: вопрос | `POST /api/ask` | `HTTP 200`, ответ + `model` |
| 5 | Лимит 6/мин | 7× `POST /api/ask` | 1–6 → `200`, 7-й → `429` |
| 6 | Длинный запрос | `POST /api/ask` (8001 симв.) | `HTTP 413` (отказ до фасада) |
| 7 | Переключение модели | `POST /api/model` | `HTTP 200`, `switched_to` = lmstudio/3B |
| 8 | История на VPS | `GET /api/history` | JSON: реплики user + assistant |
| 9 | Недоступный фасад | `POST /api/ask` после `kill` фасада | `HTTP 503` «Сервис временно недоступен» |

## Ключевые строки вывода

```
== 1. Регистрация ==
register HTTP 302
== 2. Интервью ==
interview HTTP 302
== 3. Список моделей (с хоста через туннель) ==
{"current":"cloud:stepfun/step-3.5-flash","models":[{"id":"cloud:stepfun/step-3.5-flash",...
== 4. Чат: вопрос ==
{"answer":"[Mock] вижу 6 сообщений: system:Ты полезный ассистент...
== 5. Лимит: 7 запросов подряд (отдельный пользователь) ==
  запрос 1 → HTTP 200
  ...
  запрос 6 → HTTP 200
  запрос 7 → HTTP 429
== 6. Слишком длинный запрос ==
long HTTP 413
== 7. Переключение модели ==
{"model":"lmstudio/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K",...
== 8. История на VPS ==
{"history":[{"role":"user","text":"привет, кто ты?"},{"role":"assistant","model":"mock/Mock",...
== 9. Недоступный фасад (убиваем фасад, свежий пользователь) ==
no-facade HTTP 503
== готово ==
```

## Выводы

- Все контракты шлюза подтверждены на хосте: регистрация/вход/интервью/чат/лимиты/
  переключение модели/история/деградация при недоступном фасаде.
- Лимит частоты срабатывает ровно на 7-м запросе (6 проходят) — проверено руками.
- Длинный запрос отклоняется **до** обращения к фасаду (`413`).
- Недоступный фасад → `503` с понятным текстом, без зависания.
- Шлюз не импортирует ядро агента (`Kod.py`/`rag/`) — только HTTP к фасаду.

## Что осталось за оператором (на VPS)

Выкатка `gateway/` на VPS, установка `flask` + `requests` в отдельный venv
`/home/t/doc/.venv`, юнит `ai9-gateway`, юнит туннеля на хосте, проверка
`sshd`/фаервола — см. `dev/vps/README_gateway.md`.

## Дополнение v1.2 (2026-10-14) — вопросы интервью и автосекрет

Доработки внутри этапа 10 (решения №26, №27). Проверено:

| № | Проверка | Команда | Результат |
|---|---|---|---|
| 10 | Канон вопросов с хоста | `GET 127.0.0.1:8091/interview/questions` (фасад `--mock`) | JSON: `version` + 3 вопроса (`style`/`constraints`/`context`) |
| 11 | Отпечаток совпал | шлюз `GET /interview` | форма показана (`200`) |
| 12 | Отпечаток разошёлся | шлюз `GET /interview` (хост «обновил» вопросы) | `409` + «Вопросы интервью устарели — обратитесь к администратору» |
| 13 | Автосекрет | `session_secret` без env `GATEWAY_SECRET` | секрет сгенерирован в `gateway/.secret` (в `.gitignore`) |

```
== 10. Канон вопросов интервью (фасад) ==
{"questions":[{"key":"style","question":"Какой стиль ответов предпочитаете? ..."},
 {"key":"constraints",...},{"key":"context",...}],
 "version":"d447fbc523907dc55b89e5976633d6aa8b2e85da4fd53280096b774fd9813088"}
```

- Отпечаток канона: `d447fbc523907dc55b89e5976633d6aa8b2e85da4fd53280096b774fd9813088`.
- Обновление снапшота на VPS — `gateway/sync_questions.py` (см. `README_gateway.md`).
- Тесты: `test_gateway.py` + `test_facade.py` — **31 passed** (в т.ч. сверка вопросов
  и автосекрет).

## Живой прогон на VPS (2026-10-14) — гейт 10→11

> Выкатка выполнена по `dev/vps/README_gateway.md`. Сквозной прогон — через
> **публичный адрес** `http://91.188.212.77:8080` (не loopback). Скрипты:
> `dev/tests_debug/.tmp/gateway_live_e2e.sh`, `gateway_live_model.sh`,
> `gateway_live_persist.sh`, `gateway_live_profile.sh`, `gateway_live_persist_hist.sh`.

Схема: `curl → шлюз VPS :8080 → (SSH reverse tunnel) → фасад хоста :8090 → агент`.

| № | Проверка | Команда | Результат |
|---|---|---|---|
| 1 | Вход/чат с внешнего устройства | `GET http://91.188.212.77:8080/` | `HTTP 302` (редирект на `/login`) |
| 2 | Регистрация | `POST /register` | `HTTP 302` |
| 3 | Интервью: форма (сверка вопросов) | `GET /interview` | `HTTP 200`, форма показана (вопросы свежие) |
| 4 | Интервью: отправка | `POST /interview` | `HTTP 302` |
| 5 | Профиль в `users/<логин>/` | `ls users/live3_*` | `profile.json` (name/style/constraints/context), `model_state.json` |
| 6 | Список моделей | `GET /api/models` | JSON: `current`, `models[]` (cloud + lmstudio + ollama) |
| 7 | Вопрос агенту (облако) | `POST /api/ask` | `HTTP 200` (4.45 c), ответ + `model` |
| 8 | Переключение модели из веба | `POST /api/model` (боевая 3B) | `HTTP 200`, `switched_to` = lmstudio/3B |
| 9 | Вопрос к локальной 3B | `POST /api/ask` | `HTTP 200` (38.9 c), ответ + `model` = lmstudio/3B |
| 10 | Постоянство выбора модели | 2× `POST /api/ask` | оба ответа `model` = lmstudio/3B |
| 11 | Лимит 6/мин | 7× `POST /api/ask` | 1–5 → `200`, 6–7 → `429` |
| 12 | Длинный запрос | `POST /api/ask` (8001 симв.) | `HTTP 413` |
| 13 | История на VPS | `GET /api/history` | JSON: реплики user + assistant |
| 14 | История переживает рестарт | `systemctl --user restart ai9-gateway` → `GET /api/history` | история сохранена (SQLite) |
| 15 | Лог без текста ответа | `journalctl -u ai9-gateway` | `[Шлюз] ask login=… chars=… model=…` (текста ответа нет) |
| 16 | Отпечаток вопросов | хост `GET /interview/questions` vs `gateway/questions.json` | совпадают (`d447fbc5…`) |
| 17 | MCP сохранён | `./dev/vps/mcp_vps.sh status` | `mcp-time/scheduler/pipeline` — `active`, порты `:8000/:8010/:8020` |
| 18 | `--mcp-probe` | `python Kod.py --mcp-probe` | exit 0, 4 инструмента |
| 19 | Офлайн-регрессия | `unit_runner.py` + `pytest -q` | **408 OK / 0 FAIL**; **409 passed** |
| 20 | `requirements.txt` | `git diff --stat requirements.txt` | пусто |

Ключевые строки вывода:

```
== 0. Шлюз отвечает ==
GET / → HTTP 302
== 1. Регистрация ==
POST /register → HTTP 302
== 2. Интервью: форма (сверка вопросов) ==
GET /interview → HTTP 200
  ✓ форма показана (вопросы свежие)
== 5. Вопрос агенту ==
POST /api/ask → HTTP 200 (4.454768s)
{"answer":"Я — Живой, полезный ассистент ...","model":"cloud/stepfun/step-3.5-flash",...}
== 6. Переключение модели из веба ==
POST /api/model → HTTP 200
{"model":"lmstudio/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K",...}
== 8. Лимит 6/мин (7 запросов) ==
  запрос 1 → HTTP 200 ... запрос 5 → HTTP 200
  запрос 6 → HTTP 429
  запрос 7 → HTTP 429
== 9. Длинный запрос (>8000) ==
POST /api/ask (8001) → HTTP 413
```

Отпечаток вопросов (хост = шлюз):
`d447fbc523907dc55b89e5976633d6aa8b2e85da4fd53280096b774fd9813088`.

### Нюансы, найденные при выкатке (внесены в `README_gateway.md`)

1. **На VPS нет `rsync`** — копирование выполнено через `tar` по SSH (те же исключения).
2. **`ControlMaster auto` конфликтует с туннелем** — в `~/.ssh/config` для `mcp-vps`
   включён общий мультиплексированный канал; туннель подключался к нему, forward
   регистрировался на master, а процесс `ssh` сразу завершался → systemd зацикливал
   рестарт. Исправлено добавлением `-o ControlMaster=no -o ControlPath=none` в
   `ai9-tunnel.service` (туннелю нужна собственная сессия).

### Вывод

Гейт 10→11 пройден: внешний вход/чат, интервью → профиль, переключение модели из веба,
лимиты, синхронность вопросов, `--mcp-probe`, транскрипты, офлайн-регрессия,
`requirements.txt` без изменений, запись + перечитывание — всё зелёное.
