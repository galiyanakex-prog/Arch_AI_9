# Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated — справка (этап 1, Ревизия 8)

> Боевая локальная генеративная модель AI_9 (решение оператора №20, изменено 2026-10-11).
> Источник: `~/.lmstudio/models/mradermacher/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-GGUF/`.

## Идентификаторы

- **Боевой id (в `models.json`):** `lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K`
- **Полный id LM Studio (поле `model`):**
  `mradermacher/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-GGUF:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated.Q6_K.gguf`
- **API-id (`GET /v1/models`):** `qwen2.5-coder-3b-instruct-distill-qwen3-coder-next-abliterated`
- **Файл на диске:**
  `~/.lmstudio/models/mradermacher/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-GGUF/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated.Q6_K.gguf`

## Параметры

| Параметр | Значение |
|---|---|
| Архитектура | Qwen2 |
| Параметров | 3B |
| Квантование | **Q6_K** (6 бит) |
| Размер файла | **2,54 ГБ** (2 538 159 872 байт) |
| Доступные теги | **ровно один** — `Q6_K` (других квантов на диске нет) |
| Контекст (загружено) | 32768 (в `lms ps`); боевой профиль — 8192 |
| Параллелизм | 4 |
| Устройство | Local (CPU; дискретного GPU нет) |

## Загрузка

```bash
~/.lmstudio/bin/lms server start
~/.lmstudio/bin/lms load mradermacher/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-GGUF:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated.Q6_K.gguf --gpu 0 --context-length 8192
~/.lmstudio/bin/lms ps
```

## Фактическое потребление (живой прогон 2026-10-11)

- `lms ps` → `IDLE`, **SIZE 2.54 GB**, CONTEXT 32768, PARALLEL 4, DEVICE Local.
- HTTP `POST /v1/chat/completions` (3 запроса разной сложности):
  - Л1 «Скажи: ок» → **4,0 с**, 39 симв.;
  - Л2 (перечислить модули) → **36,0 с**, 830 симв. (упёрлось в `max_tokens=256`);
  - Л3 (объяснить функцию + риск) → **36,3 с**, 778 симв. (упёрлось в `max_tokens=256`).
- Вывод: короткие ответы быстрые (~4 с); длинные на CPU идут ~36 с при лимите 256 токенов.
  Для боевых прогонов — профиль `fast`, ограничение `max_tokens`, таймаут 180 с.

## Требования к RAM

- Файл 2,54 ГБ; при загрузке с контекстом 32768 фактическое потребление — порядка 2,5–4 ГБ.
- RAM хоста 15 ГБ (доступно ~10) → модель **легко помещается** (в отличие от прежней 14B Q4_K_M на 8,4 ГБ).
- GPU: **неприменимо** (`nvidia-smi` отсутствует) → inference по CPU.

## Примечания

- Модель — «abliterated» (сняты отказы); для задач проекта это допустимо.
- Прежняя боевая `Qwen2.5-Coder-14B-Instruct-Q4_K_M` (8,4 ГБ) остаётся на диске как **резерв** для этапа 8.