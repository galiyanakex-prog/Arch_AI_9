# Транскрипт живого прогона — этап 3 (L2): `/model` + отображение модели

Дата: 2026-10-11. Среда: LM Studio `127.0.0.1:1234` (боевая модель LOADED),
Ollama `127.0.0.1:11434` (bge-m3). Пользователь прогона: `switchtest` (временный).

## Сценарий

Одна сессия `Kod.py --user switchtest`: старт на облаке → `/model` → `/model list`
→ `/model use lmstudio:…Q6_K` → ответ → `/model use cloud:…` → ответ → `/exit`.

## Вывод (фрагмент)

```
[Сессия] модель: cloud/stepfun/step-3.5-flash (облако, ctx 262144, профиль default)

Вы [Основная_задача]: /model
[Модель] cloud/stepfun/step-3.5-flash
  сервис: cloud | облачная | роль: chat
  профиль: default | параметры: {}

Вы [Основная_задача]: /model list
[Модели] Всего: 4; текущая: cloud:stepfun/step-3.5-flash
  * cloud:stepfun/step-3.5-flash  (cloud)
    lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K  (local)
    ollama:bge-m3  (local [embedding])
    mock  (local)

Вы [Основная_задача]: /model use lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K
[Модель] Переключено: lmstudio/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K
[Сессия] модель: lmstudio/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K (локально, Q6_K, ctx 8192, профиль rag-strict)

Вы [Основная_задача]: Скажи: ок
[lmstudio/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K] Агент: Конец работы.

Вы [Основная_задача]: /model use cloud:stepfun/step-3.5-flash
[Модель] Переключено: cloud/stepfun/step-3.5-flash
[Сессия] модель: cloud/stepfun/step-3.5-flash (облако, ctx 262144, профиль default)

Вы [Основная_задача]: Скажи: ок
[cloud/stepfun/step-3.5-flash] Агент: ок (3)

Вы [Основная_задача]: /exit
[Выход] Состояние сохранено. До встречи!
```

## Видимость модели (проверено)

- **Баннер:** `[Сессия] модель: …` при старте и после каждого `/model use`.
- **Префикс реплики:** `[service/model] Агент: …` у каждого ответа.
- **`Den_log.md`:** каждая запись ответа несёт `model=…`:
  ```
  model=lmstudio/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K
  model=cloud/stepfun/step-3.5-flash
  ```
- **`tokens.csv`:** новая колонка `model`:
  ```
  exchange,timestamp,prompt_tokens,cost_rubles,cost_total_rubles,model
  1,2026-10-11 19:16:51,171,0.001881,0.001881,lmstudio/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K
  2,2026-10-11 19:16:56,182,0.002002,0.004004,cloud/stepfun/step-3.5-flash
  ```

## Замечания

- Локальная модель ответила «Конец работы.» на «Скажи: ок» — поведение 3B-модели
  (не ошибка контура); главное — ответ пришёл от локального сервиса и подписан.
- `/model list` и `/model status` токенов LLM не тратят (только HTTP-probe).
- Переключение не тронуло `TaskStage`/память/`deliver` (проверено юнит-тестом).
