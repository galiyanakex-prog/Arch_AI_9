# migr_plan_1.md — Этап 1. Ollama + embedding-модель: проверка (О1)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (Ревизия 7, §4 «Этап 1»).
> Контур: **О (оснащение)**. Метка цели: **О1**. Зависимости: **этап 0** (закрыт).
> Порядок выполнения: **пошагово с оператором** — агент даёт команду, оператор
> подтверждает, агент выполняет и фиксирует вывод.
> **Коммиты — только за оператором** (текст предложен в ШАГЕ 1.5).

## Цель этапа

**Подтвердить**, что локальный сервис эмбеддингов (поднят в Ревизии 6) доступен и
воспроизводим: бинарь `ollama`, прослушивание **только** `127.0.0.1:11434`, модель
`bge-m3` (dim 1024), справка `ND/models/bge-m3_params.md`. **Новой установки нет** —
этап проверочный; при необходимости запуск/`pull` выполняет **оператор**.

## Предусловия (проверено 2026-10-05)

- `systemctl is-active ollama` → **active**; `is-enabled` → disabled (поднимается
  вручную/через `Restart`, автозапуск при загрузке — отдельное решение оператора).
- `ss -ltnp | grep 11434` → слушает **127.0.0.1:11434** (не `0.0.0.0`).
- `curl http://127.0.0.1:11434/api/version` → `{"version":"0.35.1"}`.
- `ollama list` → `bge-m3:latest` (1.2 ГБ).
- `ND/models/bge-m3_params.md` — создан в Ревизии 6.
- `.env.example` — содержит `OLLAMA_EMBED_URL`, `OLLAMA_EMBED_MODEL`.
- `rag/config.json → embedding` = `{provider: "ollama", model: "bge-m3", dim: 1024,
  url: "http://127.0.0.1:11434"}`.

## Границы этапа

- **Не** пишем код RAG (этапы 3–6 — проверка, 7–12 — работа).
- **Не** трогаем `Kod.py`, `core/`, `storage/`, `memory/`, `integrations/`.
- **Не** добавляем pip-зависимостей (Ollama — внешний сервис, не библиотека Python).
- **Не** открываем порт наружу: `OLLAMA_HOST` = `127.0.0.1:11434` (решение №5).

---

## Шаги

### ШАГ 1.1 — Проверка сервиса (агент)

```bash
systemctl is-active ollama          # ожидаем: active
systemctl is-enabled ollama         # ожидаем: disabled (или enabled — не критично)
ss -ltnp 2>/dev/null | grep 11434   # ожидаем: LISTEN ... 127.0.0.1:11434
```

**Если inactive** — команды выполняет **оператор** (мы вне песочницы):

```bash
sudo systemctl enable --now ollama  # цель: поднять локальный сервис эмбеддингов
```

Убедиться, что `OLLAMA_HOST` = `127.0.0.1:11434` (не `0.0.0.0`).

### ШАГ 1.2 — Проверка модели (агент)

```bash
ollama list | grep -E "bge-m3|nomic-embed-text"
```

**Если модели нет** — команда оператора:

```bash
ollama pull bge-m3                  # ~1.2 ГБ, dim 1024, RU+EN
```

Фолбэк для слабого железа: `ollama pull nomic-embed-text` (274 МБ, dim 768). При выборе
фолбэка правятся **только** `rag/config.json → embedding.{model,dim}`; код не трогается.

### ШАГ 1.3 — Живой probe `/api/embed` (агент)

```bash
curl -s --max-time 5 http://127.0.0.1:11434/api/version
.venv/bin/python - <<'EOF'
import json, urllib.request
req = urllib.request.Request(
    "http://127.0.0.1:11434/api/embed",
    data=json.dumps({"model": "bge-m3", "input": ["тест", "второй текст"]}).encode(),
    headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=60) as resp:
    data = json.load(resp)
vecs = data["embeddings"]
print("векторов:", len(vecs), "| dim =", len(vecs[0]),
      "| первые 3:", [round(x, 4) for x in vecs[0][:3]])
assert len(vecs) == 2 and len(vecs[0]) == 1024, f"ожидали 2×1024, получили {len(vecs)}×{len(vecs[0])}"
print("OK: /api/embed вернул 2 вектора длиной 1024")
EOF
```

Транскрипт сохранить в `dev/logs_reports/stages/rag_ollama_probe.txt` (перезапись
версии Ревизии 6 допустима — фиксируем текущее состояние).

### ШАГ 1.4 — Справка и `.env.example` (проверка наличия)

```bash
grep -c "Эндпоинты API\|Параметры\|Отличия от чат-моделей" ND/models/bge-m3_params.md
grep -E "OLLAMA_EMBED_URL|OLLAMA_EMBED_MODEL" .env.example
```

Ожидаемо: справка содержит все три раздела; `.env.example` — обе переменные.
При отсутствии — создать (образец — в `dev/old_vers/7/` и §4 мастер-плана).

### ШАГ 1.5 — Запись в журнал + перечитывание плана

Внести запись «Этап 1» в `dev/migr_log.md` по шаблону §7.3.

**Предлагаемый текст коммита** (выполняет **только** оператор):

```
chore(rag): проверка локального сервиса эмбеддингов Ollama (этап 1, Ревизия 7)

Причина: этап 4 (OllamaEmbedder) требует живого эндпоинта 127.0.0.1:11434 с моделью
dim 1024. Сервис поднят в Ревизии 6 — Ревизия 7 подтверждает доступность и фиксирует
транскрипт probe; новых установок и pip-зависимостей нет.
```

---

## Выход этапа

- подтверждено: сервис active, слушает `127.0.0.1:11434`, модель `bge-m3` (dim 1024);
- `dev/logs_reports/stages/rag_ollama_probe.txt` — транскрипт probe;
- `ND/models/bge-m3_params.md`, `.env.example` — проверены;
- запись «Этап 1» в `dev/migr_log.md`;
- `requirements.txt`, `Kod.py`, `core/`, `storage/` — **не изменены**.

## Гейт 1→2 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `curl -s http://127.0.0.1:11434/api/version` | JSON с `version` |
| 2 | `ss -ltnp \| grep 11434` | слушает **127.0.0.1**, не `0.0.0.0` |
| 3 | `systemctl is-active ollama` | `active` |
| 4 | `ollama list \| grep bge-m3` | модель присутствует |
| 5 | probe `/api/embed` (heredoc) | 2 вектора длиной **1024** |
| 6 | `ND/models/bge-m3_params.md` | разделы «Эндпоинты API», «Параметры», «Отличия от чат-моделей» |
| 7 | `.env.example` | содержит `OLLAMA_EMBED_URL`, `OLLAMA_EMBED_MODEL` |
| 8 | `unit_runner.py` / `smoke.py` / `scenario.py` / `check_acceptance.sh` | без регрессии (244 OK / SMOKE OK / SCENARIO OK / 33 из 33) |
| 9 | `git diff --stat requirements.txt` | пусто |
| 10 | запись «Этап 1» + перечитывание `migr_plan.md` | ✅ |

Красный хотя бы один из 1–9 → карточка в `dev/logs_reports/errors/error_<ts>.md`,
этап 1 остаётся открытым.

## Откат

Правок кода нет; откат = вернуть `dev/logs_reports/stages/rag_ollama_probe.txt` из
бэкапа при необходимости. Запись в журнале помечается ❌ с причиной.

## Что передаём дальше

- **Этапу 4 (R2):** живой эндпоинт `127.0.0.1:11434/api/embed`, модель `bge-m3`
  dim 1024 — `OllamaEmbedder` ходит именно сюда; фолбэк `HashingEmbedder` (dim 256).
- **Этапу 2 (О2):** сервис для сборки корпуса не нужен, но порядок 1→2→3→4 сохраняется.
