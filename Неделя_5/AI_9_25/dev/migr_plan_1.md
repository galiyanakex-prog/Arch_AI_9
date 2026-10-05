# migr_plan_1.md — Этап 1. Ollama + embedding-модель (О1)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (Ревизия 6, §4 «Этап 1»).
> Контур: **О (оснащение)**. Метка цели: **О1**. Зависимости: **этап 0** (закрыт).
> Порядок выполнения: **пошагово с оператором** — агент даёт команду/файл, оператор
> подтверждает, агент выполняет и фиксирует вывод; затем следующий шаг.
> **Коммиты — только за оператором** (текст предложен в ШАГЕ 1.9).

## Цель этапа

Поднять **локальный сервис эмбеддингов**, воспроизводимо и проверяемо: бинарь
`ollama`, **user-юнит systemd с автозапуском**, прослушивание **только**
`127.0.0.1:11434`, модель `bge-m3` (dim 1024). Зафиксировать справку о модели в
`ND/models/` по образцу существующих. Никакой логики RAG в коде на этом этапе нет —
только оснащение среды.

## Решение по способу установки (согласовано с оператором 2026-10-04)

Оператор **не хочет** отдельного системного пользователя `ollama` и установку в
`/usr/local` через `sudo`. Выбран **user-space** вариант:

- бинарь и библиотеки — в `~/.local` (без root);
- сервис — **user-юнит** `~/.config/systemd/user/ollama.service`;
- автозапуск — через **`Linger=yes`** (уже включён в системе: `loginctl show-user u`
  → `Linger=yes`), поэтому сервис стартует при загрузке **без логина**;
- модели — в `~/.ollama/models` (по умолчанию для user-режима).

Это даёт автозапуск (требование DoD п.1 «включён») без системного пользователя и без
`sudo`. Отличие от штатного установщика: сервис живёт в вашей сессии, а не в системной.

## Предусловия (проверено 2026-10-04)

- `rag/config.json → embedding` = `{provider: "ollama", model: "bge-m3", dim: 1024,
  url: "http://127.0.0.1:11434"}` (этап 0).
- `rag/config.py` запрещает не-localhost `embedding.url` (`RagConfigError`).
- `curl` есть; `systemctl --user` работает; `Linger=yes`; `~/.config/systemd/user/` есть;
  `~/.local/bin` уже в `PATH`; `zstd` и `tar --zstd` есть; `sudo` требует пароль.
- **`ollama` отсутствует**; порт 11434 не отвечает; юнит не активен (ШАГ 1.1).
- `ollama.com` **недоступен**, GitHub доступен → бинарь берём с GitHub Releases
  (`ollama-linux-amd64.tar.zst`, v0.35.1, ~1.44 ГБ).
- `dev/logs_reports/stages/` существует (образцы транскриптов).

## Границы этапа

- **Не** пишем код RAG (этапы 3–10); **не** собираем корпус (этап 2).
- **Не** трогаем `Kod.py`, `core/`, `storage/`, `memory/`, `integrations/`.
- **Не** добавляем pip-зависимостей: `requirements.txt` остаётся как есть
  (Ollama — внешний сервис, не библиотека Python).
- **Не** открываем порт наружу: `OLLAMA_HOST` = `127.0.0.1:11434`
  (решение пользователя №5 — эмбеддинги строго локально).
- **Не** создаём юнит-модулей `test_rag_*.py` (первый — на этапе 3).

> ⚠️ **Вне песочницы, но без root.** Установка меняет только домашний каталог
> (`~/.local`, `~/.ollama`, `~/.config/systemd/user`) — системные файлы не трогаются,
> `sudo` не нужен. Команды выполняет оператор; агент объясняет каждую, проверяет
> результат и фиксирует транскрипт.

---

## Шаги

### ШАГ 1.1 — Проверка «до» (сервиса нет) ✅ выполнено

```bash
command -v ollama || echo "ollama: НЕТ"
curl -s --max-time 3 http://127.0.0.1:11434/api/version || echo "порт 11434: НЕ отвечает"
systemctl --user is-active ollama 2>/dev/null || echo "user-юнит ollama: не активен"
```

Результат (2026-10-04): `ollama: НЕТ`, порт не отвечает, юнит не активен — красная
проверка этапа; должна позеленеть к ШАГУ 1.4.

### ШАГ 1.2 — Скачивание и распаковка бинаря (оператор)

```bash
cd /tmp
curl -fL --retry 3 -o ollama-linux-amd64.tar.zst \
  https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64.tar.zst
```

~1.44 ГБ. Затем распаковать в `~/.local` (архив содержит `bin/ollama` и `lib/ollama/`):

```bash
mkdir -p ~/.local
tar --zstd -xf /tmp/ollama-linux-amd64.tar.zst -C ~/.local
rm -f /tmp/ollama-linux-amd64.tar.zst
```

Проверка:

```bash
~/.local/bin/ollama --version
```

Ожидаемо: `ollama version is 0.35.1` (или новее). `~/.local/bin` уже в `PATH`, поэтому
далее достаточно `ollama`.

### ШАГ 1.3 — User-юнит с автозапуском (оператор)

Создать `~/.config/systemd/user/ollama.service` (содержимое — в блоке ниже), затем:

```bash
systemctl --user daemon-reload
systemctl --user enable --now ollama
systemctl --user is-active ollama
```

Ожидаемо: `active`. Автозапуск обеспечивает уже включённый `Linger=yes` — сервис
поднимется при загрузке без логина. Проверка linger:

```bash
loginctl show-user "$USER" | grep Linger
```

Ожидаемо: `Linger=yes`.

### ШАГ 1.4 — Живая проверка сервиса (агент)

```bash
curl -s --max-time 5 http://127.0.0.1:11434/api/version
ss -ltnp 2>/dev/null | grep 11434
```

Ожидаемо: JSON `{"version":"0.35.1"}`; порт слушает **127.0.0.1**, не `0.0.0.0`.
Красная проверка ШАГА 1.1 позеленела.

### ШАГ 1.5 — Модель `bge-m3` (оператор)

```bash
ollama pull bge-m3
```

~1.2 ГБ, мультиязычная (RU+EN), dim **1024**, контекст 8192. Модель ляжет в
`~/.ollama/models`.

**Фолбэк для слабого железа:** `ollama pull nomic-embed-text` (274 МБ, dim **768**).
При выборе фолбэка — правятся **только** `rag/config.json → embedding.{model,dim}`
(`nomic-embed-text`, `768`); код не трогается. Выбор фиксируется в журнале.

Проверка:

```bash
ollama list | grep -E "bge-m3|nomic-embed-text"
```

### ШАГ 1.6 — Живой probe `/api/embed` (агент)

```bash
.venv/bin/python - <<'EOF'
import json, urllib.request
req = urllib.request.Request(
    "http://127.0.0.1:11434/api/embed",
    data=json.dumps({"model": "bge-m3", "input": ["тест", "второй текст"]}).encode(),
    headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as resp:
    data = json.load(resp)
vecs = data["embeddings"]
print("векторов:", len(vecs), "| dim =", len(vecs[0]), "| первые 3:", [round(x, 4) for x in vecs[0][:3]])
assert len(vecs) == 2 and len(vecs[0]) == 1024, f"ожидали 2×1024, получили {len(vecs)}×{len(vecs[0])}"
print("OK: /api/embed вернул 2 вектора длиной 1024")
EOF
```

Транскрипт (вывод `curl /api/version` + скрипта) сохранить в
`dev/logs_reports/stages/rag_ollama_probe.txt`.

### ШАГ 1.7 — Справка `ND/models/bge-m3_params.md` (агент)

Создать по образцу `ND/models/Step-3.5-Flash_params.md`. Содержание — в разделе
«Содержимое `ND/models/bge-m3_params.md`» ниже.

### ШАГ 1.8 — `.env.example` (агент)

Добавить (не заменяя существующую строку `API_KEY`):

```dotenv
# RAG: локальный сервис эмбеддингов (Ollama). Секретов нет — только localhost.
OLLAMA_EMBED_URL=http://127.0.0.1:11434
OLLAMA_EMBED_MODEL=bge-m3
```

### ШАГ 1.9 — Запись в журнал + перечитывание плана

Внести запись «Этап 1» в `dev/migr_log.md` по шаблону §7.3 мастер-плана
(было/стало, живой прогон, регрессия, артефакты, коммит, гейт).

---

## Содержимое `~/.config/systemd/user/ollama.service`

```ini
[Unit]
Description=Ollama local embedding service (user)
After=network.target

[Service]
Type=simple
ExecStart=%h/.local/bin/ollama serve
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_MODELS=%h/.ollama/models"
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

> `%h` — домашний каталог пользователя (systemd подставляет сам). `OLLAMA_HOST`
> жёстко фиксирует localhost — наружу сервис не торчит.

---

## Содержимое `ND/models/bge-m3_params.md`

```markdown
# BGE-M3 (bge-m3)

**Разработчик:** BAAI (Beijing Academy of Artificial Intelligence)
**Идентификатор:** `bge-m3`
**Тип:** embedding (не чат-модель — не генерирует текст)
**Способ получения:** `ollama pull bge-m3` (локально, без внешних API)

## Характеристики

| Параметр | Значение |
|---|---|
| Размерность вектора (dim) | **1024** |
| Контекстное окно | 8192 токена |
| Языки | мультиязычная (RU + EN и др.) |
| Размер модели | ~1.2 ГБ |
| Дата релиза | 2024 |

## Эндпоинты API (локальный сервис Ollama)

Базовый адрес: `http://127.0.0.1:11434` (только localhost).

**Версия сервиса:**
```
GET /api/version
→ {"version":"0.x.y"}
```

**Эмбеддинги:**
```
POST /api/embed
Content-Type: application/json

{"model":"bge-m3","input":["текст 1","текст 2"]}
→ {"embeddings":[[...1024...],[...1024...]]}
```

## Параметры запроса

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `model` | string | — | идентификатор модели (`bge-m3`) |
| `input` | string \| array | — | текст или список текстов для эмбеддинга |
| `truncate` | bool | true | обрезать вход до контекста (8192) |
| `keep_alive` | string | "5m" | сколько держать модель в памяти после запроса |

## Отличия от чат-моделей

- **Нет генерации:** возвращает вектор, а не текст.
- **Нет `temperature`/`top_p`/`max_tokens`:** параметры сэмплирования неприменимы.
- **Детерминирована:** один и тот же вход → один и тот же вектор.
- **Назначение:** поиск по смыслу (retrieval), а не диалог.

## Когда применять

- Индексация корпуса и поиск по смыслу в RAG-модуле AI_9.
- Смешанные RU+EN документы (мультиязычность).

## Лимиты и деградация

- Вход длиннее 8192 токенов обрезается (`truncate=true`).
- Сервис недоступен → `rag/embedding.py` переходит на `HashingEmbedder`
  (фолбэк, dim 256) — поиск деградирует, но не падает.
- Внешние API не используются: только `127.0.0.1:11434`.
```

---

## Выход этапа

- `ollama` установлен в `~/.local/bin`, user-юнит `ollama.service` активен,
  слушает `127.0.0.1:11434`, автозапуск через `Linger=yes`;
- модель `bge-m3` подтянута (или `nomic-embed-text` — с правкой конфига);
- `dev/logs_reports/stages/rag_ollama_probe.txt` — транскрипт живого probe;
- `ND/models/bge-m3_params.md` — справка;
- `.env.example` — `OLLAMA_EMBED_URL`, `OLLAMA_EMBED_MODEL`;
- запись «Этап 1» в `dev/migr_log.md`;
- `requirements.txt`, `Kod.py`, `core/`, `storage/` — **не изменены**.

## Гейт 1→2 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `curl -s http://127.0.0.1:11434/api/version` | JSON с `version` |
| 2 | `ss -ltnp \| grep 11434` | слушает **127.0.0.1**, не `0.0.0.0` |
| 3 | `systemctl --user is-active ollama` | `active` |
| 4 | `loginctl show-user "$USER" \| grep Linger` | `Linger=yes` (автозапуск) |
| 5 | `ollama list \| grep bge-m3` | модель присутствует |
| 6 | probe `/api/embed` (heredoc) | 2 вектора длиной **1024** (или 768 для фолбэка) |
| 7 | `ND/models/bge-m3_params.md` | создан, есть разделы «Эндпоинты API», «Параметры», «Отличия от чат-моделей» |
| 8 | `.env.example` | содержит `OLLAMA_EMBED_URL`, `OLLAMA_EMBED_MODEL` |
| 9 | `unit_runner.py` / `smoke.py` / `scenario.py` / `check_acceptance.sh` | без регрессии (148 OK / SMOKE OK / SCENARIO OK / 25 из 25) |
| 10 | `git diff --stat requirements.txt` | пусто |
| 11 | запись «Этап 1» в `migr_log.md` + перечитывание `migr_plan.md` | ✅ |

Красный хотя бы один из 1–10 → карточка в `dev/logs_reports/errors/error_<ts>.md`,
этап 1 остаётся открытым.

## Откат

```bash
systemctl --user disable --now ollama
rm -f ~/.config/systemd/user/ollama.service
systemctl --user daemon-reload
rm -f ~/.local/bin/ollama
rm -rf ~/.local/lib/ollama
rm -rf ~/.ollama            # модели (bge-m3 ~1.2 ГБ)
git checkout -- .env.example
rm -f ND/models/bge-m3_params.md
```

Код продукта не менялся — откат не затрагивает поведение агента; запись в
`migr_log.md` помечается ❌ с причиной.

## Что передаём дальше

- **Этапу 4 (R2):** живой эндпоинт `127.0.0.1:11434/api/embed`, модель `bge-m3`
  dim 1024 — `OllamaEmbedder` будет ходить именно сюда; фолбэк `HashingEmbedder`
  (dim 256) уже заложен в конфиг.
- **Этапу 2 (О2):** сервис не нужен для сборки корпуса, но нужен для этапа 4 —
  порядок 1→2→3→4 сохраняется.
- **Этапу 11 (Ф):** транскрипт `rag_ollama_probe.txt` и справка `bge-m3_params.md`
  входят в DoD Ревизии 6 (пункты 1–2).