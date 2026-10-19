# Сценарий ручной демонстрации «Часть 1 — локальные LLM: выбор модели, `/model`, субагенты»

> Назначение: показать куратору **часть 1** `ND/tasks/n_6/Задание.txt` в живом
> терминале: локальные модели (LM Studio) видны, переключаются; агент работает на
> боевой локальной модели; субагент — дочерний процесс на той же локальной LLM.
> Время: 5–7 минут. Файл — артефакт процесса, живёт только в `dev/`.

## Реквизиты

- Терминал в корне проекта, venv активирует обёртка `./run.sh` сама.
- **LM Studio поднят** и слушает `127.0.0.1:1234` (см. раздел README «Как поднять
  LM Studio»): `lms server start` → `lms server status` → «running on port 1234».
- Боевая модель — `Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K`.
- Демо-пользователь — свежий (`demo`), чтобы показать интервью и создание дерева с нуля.

---

## Шаг 1. Список моделей (без токенов LLM)

```bash
./run.sh --model-list
```

**Увидите:** реестр моделей и метку текущей (`*`).

```
[Модели] Всего: 6; текущая: cloud:stepfun/step-3.5-flash
  * cloud:stepfun/step-3.5-flash  (cloud)
    lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K  (local)
    lmstudio:qwen/qwen2.5-coder-14b  (local)
    lmstudio:codellama-7b-python  (local)
    ollama:bge-m3  (local [embedding])
    mock  (local)
```

> Реестр — `models.json`. Секретов в нём нет (ключ — только в окружении).

---

## Шаг 2. Переключение модели в REPL

```bash
./run.sh --user demo
```

В REPL:

```
/model list
/model status
/model use lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K
/model status
Скажи одним словом: готово
/model use cloud:stepfun/step-3.5-flash
/model status
```

**Увидите:** после каждого `/model use` меняется баннер `[Сессия] модель: …`; ответ
подписан `[service/model] Агент: …`; локальная модель идёт с пометкой `(локально, Q6_K,
ctx 8192, профиль rag-strict)`.

```
[Модель] Переключено: lmstudio/Qwen2.5-Coder-3B-…-Q6_K
[Сессия] модель: lmstudio/Qwen2.5-Coder-3B-…-Q6_K (локально, Q6_K, ctx 8192, профиль rag-strict)
[lmstudio/Qwen2.5-Coder-3B-…-Q6_K] Агент: готово
```

> `/model list|status` токенов LLM не тратят (только HTTP-probe сервиса).
> Переключение не трогает `TaskStage`/память.

---

## Шаг 3. Запрет облака и один запрос на боевой модели (one-shot)

```bash
./run.sh --oneshot "Ответь одним словом: столица Франции?" \
  --model lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K \
  --local-only --fresh
```

**Увидите:** ответ локальной модели с подписью (примерно 2–3 секунды на простой вопрос):

```
[Сессия] модель: lmstudio/Qwen2.5-Coder-3B-…-Q6_K (локально, Q6_K, ctx 8192, профиль rag-strict)
[lmstudio/Qwen2.5-Coder-3B-…-Q6_K] Агент: Париж
```

> `--local-only` запрещает облачные модели в сессии (страховка «работаем строго локально»).

---

## Шаг 4. Субагент на локальной LLM

```bash
./run.sh --subagent-run "Ответь одним словом: готово" --subagent-service lmstudio
```

**Увидите:** субагент = **дочерний процесс** `Kod.py --oneshot`, лог с подписью модели:

```
[Субагент] id=Ответь_одним_словом_готово_… сервис=lmstudio модель=lmstudio:Qwen2.5-Coder-3B-…-Q6_K pid=…
[Субагент] статус=ok (6.22 с), лог: …/dev/logs_reports/stages/subagent_…md
[lmstudio/Qwen2.5-Coder-3B-…-Q6_K] Агент: готово
```

> Субагент пишет только в `users/sub_*/` и `stages/`; `TaskStage` основной задачи не трогает.

---

## Шаг 5. Видимость модели (где ещё видно подпись)

- `Den_log.md` — каждая запись ответа несёт `model=…`;
- `tokens.csv` — колонка `model`;
- фасад/шлюз — поле `model` в JSON-ответе (см. `scen_access.md`).

```bash
tail -3 tokens.csv
```

---

## Ожидаемый итог

- Список моделей печатается; текущая помечена `*`.
- `/model use` переключает cloud ↔ local; баннер и префикс реплики меняются.
- Один запрос на боевой локальной модели отвечает и подписан.
- Субагент запускается на локальной LLM, пишет лог, завершается.
- Модель видна в логе и CSV.
