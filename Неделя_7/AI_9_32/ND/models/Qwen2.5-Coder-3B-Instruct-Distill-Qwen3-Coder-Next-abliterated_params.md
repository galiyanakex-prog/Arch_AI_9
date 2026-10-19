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

## Итог оптимизации (этап 8, 2026-10-12)

Сравнение трёх генераторов на одном датасете (2 вопроса `c01/c02` × 2 повтора),
профиль `rag-strict`, локальный шаблон [rag] (смягчён — см. ниже). Полный отчёт:
`dev/logs_reports/stages/optimize_before_after.md`.

| Модель | Квант | must_contain | Ссылки валид. | Медиана, мс | ток/с | RSS пик, МБ |
|---|---|---|---|---|---|---|
| **3B (боевая)** | Q6_K | 0.5 | 5/5 | 58 976 | 2.4 | 3 982 |
| 14B | Q4_K_M | 1.0 | 8/8 | 452 852 | 0.51 | 13 545 |
| codellama-7b-python | Q3_K_S | 0.375 | 0/0 | 374 244 | 1.16 | 11 194 |

- **Боевая — эта 3B (Q6_K):** качество не ниже замера «до» (0.5 против 0.5439 —
  регрессии нет), медиана латентности упала в ~4,2×, RSS ~4 ГБ против ~13,5 ГБ у 14B.
- **14B** даёт лучшее качество (must_contain 1.0), но в ~7,7× медленнее и упирается
  в RAM (13,5 из 15 ГБ) → оставлен **резервом**.
- **codellama-7b-python** — худший вариант (не соблюдает формат ссылок `[doc_id#chunk_id]`).
- **Ось «квант»** недоступна: у 3B на диске ровно один тег (Q6_K), докачка — оператор
  (решение №8). Ось «размер» представлена моделями 3B / 7B / 14B.
- **GPU неприменим** (дискретного GPU нет, inference по CPU).

**Находка (влияет на этап 7):** исходный строгий шаблон (жёсткое правило отказа +
few-shot) заставлял 3B **сверхсрабатывать** и отказываться отвечать при наличии ответа
(must_contain падал до 0.0). Правило отказа переформулировано, few-shot убран → 0.5.