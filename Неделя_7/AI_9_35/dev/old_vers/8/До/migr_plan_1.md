# migr_plan_1.md — Этап 1. Локальные сервисы: LM Studio + боевая модель (О1)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (**Ревизия 8, v1.1**, §4 «Этап 1»).
> Контур: **О (оснащение)**. Метка цели: **О1**. Зависимости: **этап 0** (закрыт).
> Порядок выполнения: **пошагово с оператором** — агент даёт команду, оператор
> подтверждает, агент выполняет и фиксирует вывод.
> **Коммиты — только за оператором** (текст предложен в ШАГЕ 1.7).

## Цель этапа

Подтвердить, что **боевая локальная чат-модель** доступна по HTTP и CLI и отвечает.
Закрывает **часть 1** `Задание.txt`: «модель запускается локально», «к ней можно
обратиться через CLI или HTTP API», «минимум 3 запроса разной сложности».

**Боевая модель (решение №20):** `Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-GGUF`, файл
`~/.lmstudio/models/mradermacher/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-GGUF/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated.Q6_K.gguf`.
**Скачивать ничего не нужно** — модель уже на диске (2,5 ГБ, единственный тег).

## Предусловия (проверено 2026-10-11)

- Боевой GGUF на диске (2,5 ГБ); других тегов у Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated нет.
- LM Studio CLI: `/home/u/.lmstudio/bin/lms`; HTTP-сервер `127.0.0.1:1234` **не отвечал**.
- Ollama `127.0.0.1:11434` **не отвечала** (эмбеддинг-сервис RAG, `bge-m3`).
- Железо: RAM 15 ГБ, **дискретного GPU нет** → CPU-inference.

## Границы этапа

- **Не** пишем код агента (это этапы 2–4); этап — **проверочный**.
- **Не** трогаем `Kod.py`, `core/`, `storage/`, `memory/`, `integrations/`, `rag/`.
- **Не** добавляем pip-зависимостей (LM Studio/Ollama — внешние сервисы).
- **`ollama pull` не выполняем** — можно вытеснить `bge-m3` и сломать RAG-индекс.
- **Установка/запуск сервисов — за оператором** (мы вне песочницы).

---

## Шаги

### ШАГ 1.1 — Подъём LM Studio (выполняет ОПЕРАТОР)

Агент объясняет цель и последствия; команды запускает оператор:

```bash
~/.lmstudio/bin/lms status          # убедиться, что сервер не поднят (иначе: lms server stop)
~/.lmstudio/bin/lms server start    # поднять HTTP-сервер на 127.0.0.1:1234
~/.lmstudio/bin/lms ls              # убедиться, что боевая модель видна
~/.lmstudio/bin/lms load mradermacher/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-GGUF:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated.Q6_K.gguf --gpu 0 --context-length 8192
~/.lmstudio/bin/lms ps              # подтвердить загрузку и фактическое потребление RAM
```

> `--gpu 0` — потому что дискретного GPU нет (см. §0.4); `--context-length 8192` —
> стартовое окно, уточняется на этапе 7. **Без отвечающего сервера и загруженной модели
> гейт 1 не закрывается** (решение №21).

> **TODO(документация, этап 12) — алгоритм подъёма LM Studio → в `README.md`.**
> По факту этапа 10 (2026-10-14) оператор поднимал LM Studio неполно (`lms ls` / `lms load` /
> `lms chat`), но **не** `lms server start` → порт `1234` не слушался → агент отдавал
> «Сервис временно недоступен» (фасад `502`). Правильный алгоритм с пояснениями
> («что это → зачем → ожидаемый результат») нужно внести в `README.md` на этапе 12
> (ШАГ 12.4): **`lms server start` — главный шаг**; `lms load` — необязательно;
> `lms chat` — агенту не нужен; проверка `lms server status` / `lms ps` /
> `curl :1234/v1/models`; LM Studio может «засыпать» → тот же симптом.

### ШАГ 1.2 — Живая проверка HTTP (агент)

```bash
curl -s --max-time 5 http://127.0.0.1:1234/v1/models | head -c 400
```

Ожидаемо: в списке есть `Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated`. Затем — **3 запроса разной сложности**
через `POST /v1/chat/completions`:

- **Л1** «Скажи: ок» (smoke);
- **Л2** «Перечисли 3 модуля проекта по списку файлов» (следование инструкции);
- **Л3** «По этому фрагменту кода объясни, что делает функция, и назови риск» (рассуждение).

```bash
.venv/bin/python - <<'EOF'
import json, time, urllib.request
URL = "http://127.0.0.1:1234/v1/chat/completions"
MODEL = "mradermacher/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-GGUF:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated.Q6_K.gguf"
prompts = [
    ("Л1", "Скажи: ок"),
    ("Л2", "Перечисли 3 модуля проекта по списку файлов: core/agent.py, rag/service.py, memory/manager.py"),
    ("Л3", "Объясни, что делает функция, и назови риск: def f(xs): return sum(xs)/len(xs)"),
]
for tag, text in prompts:
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": text}],
                       "temperature": 0.2, "max_tokens": 256}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.load(r)
    dt = time.time() - t0
    ans = data["choices"][0]["message"]["content"]
    print(f"[{tag}] {dt:.1f}s | {len(ans)} симв. | {ans[:120]!r}")
    assert ans.strip(), f"{tag}: пустой ответ"
print("OK: 3 запроса разной сложности отвечены")
EOF
```

### ШАГ 1.3 — CLI-проверка LM Studio (агент)

```bash
~/.lmstudio/bin/lms --help | head -30
# 1 запрос через CLI (точная подкоманда — по факту вывода --help, напр. lms run)
```

### ШАГ 1.4 — Ollama как альтернативный провайдер (не обязателен)

```bash
curl -s --max-time 3 http://127.0.0.1:11434/api/version || echo "Ollama-чат: НЕДОСТУПЕН"
```

- Если Ollama отвечает и на ней есть **чат-модель** — те же 3 запроса через `POST /api/chat`
  и 1 через `ollama run`; она регистрируется в `models.json` (этап 2) как второй локальный путь.
- Если Ollama занята эмбеддингом или недоступна — **явная строка «Ollama-чат недоступен»**
  в транскрипте. **Часть 1 от этого не страдает** (боевой путь — LM Studio).
- **`ollama pull` не выполняем.**

### ШАГ 1.5 — Транскрипт живого прогона

Сохранить в `dev/logs_reports/stages/local_llm_probe.md`: запрос, ответ, латентность,
число токенов, версия сервиса, тег/квант модели.

### ШАГ 1.6 — Справка о модели + `.env.example`

- `ND/models/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated_params.md` — окно контекста, параметры, доступные
  теги квантования (из каталога `~/.lmstudio/models`), требования по RAM; отдельно —
  фактическое потребление по `lms ps`. Если Ollama-чат использовалась — вторая справка.
- `.env.example` (без секретов):
  ```
  LMSTUDIO_URL=http://127.0.0.1:1234
  LMSTUDIO_MODEL=mradermacher/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-GGUF:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated.Q6_K.gguf
  OLLAMA_CHAT_URL=http://127.0.0.1:11434
  AI9_MODEL=cloud
  ```

### ШАГ 1.7 — Запись в журнал + перечитывание плана

Внести запись «Этап 1» в `dev/migr_log.md` по шаблону §7.3.

**Предлагаемый текст коммита** (выполняет **только** оператор):

```
feat(local-llm): LM Studio + боевая Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K (этап 1, Ревизия 8)

Причина: часть 1 Задание.txt требует запущенной локальной LLM, доступной по CLI/HTTP,
с ≥ 3 запросами разной сложности. Боевая модель уже на диске; этап поднимает сервер
LM Studio, фиксирует живые ответы и справку о модели. Ollama остаётся эмбеддинг-сервисом
RAG (pull не выполняется).
```

---

## Выход этапа

- подтверждено: LM Studio `127.0.0.1:1234` отвечает, боевая модель в `/v1/models`;
- 3 запроса разной сложности через HTTP + 1 через CLI — с латентностями;
- `dev/logs_reports/stages/local_llm_probe.md` — транскрипт;
- `ND/models/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated_params.md` — справка;
- `.env.example` — переменные LM Studio/Ollama (без секретов);
- статус Ollama-чата зафиксирован (живой путь или явное «недоступно»);
- запись «Этап 1» в `dev/migr_log.md`;
- `requirements.txt`, `Kod.py`, `core/`, `storage/` — **не изменены**.

## Гейт 1→2 (живой, все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `GET /v1/models` | содержит `Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated` |
| 2 | `POST /v1/chat/completions` × 3 | непустой ответ на все 3 запроса разной сложности |
| 3 | CLI-запрос через `lms` | выполнен |
| 4 | транскрипт с латентностями | `stages/local_llm_probe.md` |
| 5 | справка `ND/models/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated_params.md` | создана |
| 6 | статус Ollama-чата | живой путь **или** явное «недоступно» |
| 7 | `unit_runner.py` / `smoke.py` / `scenario.py` / `check_acceptance.sh` | без регрессии (290 OK / SMOKE OK / SCENARIO OK / 39 из 43) |
| 8 | `git diff --stat requirements.txt` | пусто |
| 9 | запись «Этап 1» + перечитывание `migr_plan.md` | ✅ |

Красный хотя бы один из 1–3 → карточка в `dev/logs_reports/errors/error_<ts>.md`,
этап 1 остаётся открытым (**блокер**: без LM Studio живые этапы не начинаются).

## Откат

Правок кода нет; откат = остановить сервер (`lms server stop`) и вернуть транскрипт/справку
из бэкапа при необходимости. Запись в журнале помечается ❌ с причиной.

## Что передаём дальше

- **Этапу 2 (L1):** живой эндпоинт `127.0.0.1:1234/v1/chat/completions` и полный id модели —
  `OpenAICompatClient` ходит именно сюда; `models.json` получает боевой id.
- **Этапу 5 (G1):** Ollama `bge-m3` (эмбеддинги) — retrieval локального RAG.
- **Этапу 7 (P1):** `--context-length 8192` — стартовое окно для профилей параметров.