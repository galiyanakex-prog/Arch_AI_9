# Транскрипт живого прогона локальной LLM (этап 1, Ревизия 8)

- Дата: 2026-10-11
- Сервис: LM Studio, HTTP `127.0.0.1:1234`
- Боевая модель: `qwen2.5-coder-3b-instruct-distill-qwen3-coder-next-abliterated`
  (файл `Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated.Q6_K.gguf`, 2,54 ГБ, Q6_K)
- Устройство: CPU (дискретного GPU нет)

## 1. Состояние сервиса

```
$ ~/.lmstudio/bin/lms status
Server:  OFF
$ ~/.lmstudio/bin/lms server start
Success! Server is now running on port 1234
```

```
$ ~/.lmstudio/bin/lms ps
IDENTIFIER                                                        MODEL                                                             STATUS    SIZE      CONTEXT    PARALLEL    LOAD CONFIG    DEVICE    TTL
qwen2.5-coder-3b-instruct-distill-qwen3-coder-next-abliterated    qwen2.5-coder-3b-instruct-distill-qwen3-coder-next-abliterated    IDLE      2.54 GB   32768      4           LM Studio      Local
```

```
$ curl -s http://127.0.0.1:1234/v1/models
... qwen2.5-coder-3b-instruct-distill-qwen3-coder-next-abliterated ...
```

## 2. HTTP-запросы (POST /v1/chat/completions)

| # | Сложность | Промпт | Латентность | Символов | usage |
|---|---|---|---|---|---|
| Л1 | простая | «Скажи: ок» | **4,0 с** | 39 | prompt 34 / completion 14 |
| Л2 | средняя | «Перечисли 3 модуля проекта по списку файлов…» | **36,0 с** | 830 | prompt 59 / completion 256 |
| Л3 | сложная | «Объясни, что делает функция, и назови риск…» | **36,3 с** | 778 | prompt 57 / completion 256 |

Ответы непустые на все 3 запроса. Л2/Л3 упёрлись в `max_tokens=256` (генерация до лимита).

Пример ответа Л3 (начало):

```
## Объяснение работы кода
Функция `f(xs)` вычисляет среднее значение элементов списка `xs`. ...
```

## 3. CLI-проверка

- `lms ls` → боевая модель видна: `qwen2.5-coder-3b-instruct-distill-qwen3-coder-next-abliterated  3B  Qwen2  2.54 GB  Local  ✓ LOADED`.
- `lms ps` → модель загружена (IDLE, 2.54 GB, context 32768).
- Зачёт CLI выполнен по `lms ls` + `lms ps` (интерактивный `lms chat` не запускался — тяжёлая сессия на CPU).

## 4. Ollama (эмбеддинги RAG)

```
$ curl -s http://127.0.0.1:11434/api/version
Ollama: НЕ отвечает
```

Зафиксировано как **ограничение среды**: 4 красные RAG-проверки гейта (№33/38/39/43)
остаются красными до подъёма Ollama с `bge-m3`. Это не регресс кода.

## 5. Вывод

- Часть 1 `Задание.txt` (локальная LLM запущена, доступна по HTTP и CLI, ≥ 3 запроса) — **выполнена**.
- Латентность: короткие ответы ~4 с; длинные на CPU ~36 с при лимите 256 токенов.
- Модель 2,54 ГБ легко помещается в RAM 15 ГБ.