# Транскрипт: фасад агента на хосте (этап 9, S1)

> Живой прогон `serve.py` (Flask, `127.0.0.1:8090`, loopback-only) в режиме `--mock`
> (без сети). Дата: 2026-10-13. Скрипт: `dev/tests_debug/.tmp/facade_live_run.sh`.

## Запуск

```
$ python serve.py --mock --port 8090
[Фасад] слушает http://127.0.0.1:8090 (RAG=выкл, mock=True)
 * Running on http://127.0.0.1:8090
```

## `GET /models` — провайдеры и модели из реестра

```json
{
  "current": "cloud:stepfun/step-3.5-flash",
  "providers": ["cloud", "lmstudio", "mock", "ollama"],
  "models": [
    {"id": "cloud:stepfun/step-3.5-flash", "service": "cloud", "local": false, ...},
    {"id": "lmstudio:Qwen2.5-Coder-3B-...-Q6_K", "service": "lmstudio", "local": true, ...},
    ...
  ]
}
```

## `POST /ask` — ответ с обязательным полем `model`

```json
{
  "answer": "[Mock] вижу 6 сообщений: ...",
  "model": "mock/Mock",
  "sources": [],
  "quotes": [],
  "verdict": "unchecked",
  "usage": {"prompt_tokens": 1, "completion_tokens": 14, "total_tokens": 15, "estimated": true},
  "duration_seconds": 0.001
}
```

## `GET /state?user=facade_live`

```json
{
  "user": "facade_live",
  "model": "mock/Mock",
  "rag_enabled": false,
  "task": "Основная_задача",
  "task_stage": null,
  "busy": false,
  "alive": true
}
```

## Второй `POST /ask` (очередь держит)

Второй запрос сразу после первого → `200`, ответ получен, ошибки нет.

## Учёт (Den_log.md + tokens.csv)

```
[08:57:19] [Фасад] user=facade_live model=mock/Mock tokens=103 duration=0.001s
[08:57:19] [Фасад] user=facade_live model=mock/Mock tokens=131 duration=0.002s
```

```
1,2026-10-13 08:57:19,1,0.000000,0.000000,mock/Mock
2,2026-10-13 08:57:19,1,0.000000,0.000000,mock/Mock
```

## Гейт 9→10

| № | Проверка | Результат |
|---|---|---|
| 1 | `curl POST /ask` | ✅ непустой ответ + поле `model` |
| 2 | тот же прогон без интернета | ✅ (mock, loopback-only) |
| 3 | параллельный запрос | ✅ очередь держит (тест `test_queue_serializes_parallel_requests`) |
| 4 | `Den_log.md` / `tokens.csv` | ✅ user, модель, токены, длительность |
| 5 | после удаления `serve.py` | ✅ агент в терминале не зависит от фасада |
| 6 | `TaskStage` пользователя | ✅ не изменён HTTP-вызовом |
| 7 | `--mcp-probe` + прежняя база | ✅ зелёные |
| 8 | транскрипт | ✅ этот файл |
| 9 | `git diff --stat requirements.txt` | ✅ пусто (flask — не в requirements ядра) |
| 10 | запись «Этап 9» + перечитывание | ✅ |
