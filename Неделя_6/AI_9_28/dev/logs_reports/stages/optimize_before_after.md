# Оптимизация генерации RAG: замер «до/после» (этап 7/8, P1/P2)

Профиль: `rag-strict` · строгий шаблон [rag]: да

k = 5 · повторов на вопрос = 2 · вопросов = 2

## Таблица «вопрос × генератор»

| Вопрос | Генератор | must_contain | Источники | Ссылки (валид.) | verdict | Длина | Латентность, мс |
|---|---|---|---|---|---|---|---|
| c01 | lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K | 0/2 | 5 | 0/0 | partial | 39 | 66571.2 |
| c01 | lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K | 0/2 | 5 | 0/0 | partial | 169 | 7495.9 |
| c02 | lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K | 0/2 | 5 | 0/0 | partial | 160 | 71209.4 |
| c02 | lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K | 0/2 | 5 | 0/0 | partial | 160 | 6781.7 |
| c01 | lmstudio:qwen/qwen2.5-coder-14b | 1/2 | 5 | 1/1 | ok | 364 | 194529.3 |
| c01 | lmstudio:qwen/qwen2.5-coder-14b | 1/2 | 5 | 1/1 | ok | 283 | 94958.7 |
| c02 | lmstudio:qwen/qwen2.5-coder-14b | 0/2 | 5 | 0/0 | partial | 39 | 9747.5 |
| c02 | lmstudio:qwen/qwen2.5-coder-14b | 0/2 | 5 | 0/0 | partial | 39 | 8552.5 |
| c01 | lmstudio:codellama-7b-python | 0/2 | 5 | 0/0 | partial | 2333 | 593779.3 |
| c01 | lmstudio:codellama-7b-python | 0/2 | 5 | 0/0 | partial | 2139 | 276129.4 |
| c02 | lmstudio:codellama-7b-python | 0/2 | 5 | 5/5 | hallucination | 1112 | 802710.5 |
| c02 | lmstudio:codellama-7b-python | 2/2 | 5 | 0/4 | partial | 1708 | 320520.1 |

## Сводка по трём осям

| Генератор | Качество: must_contain | Источники | Ссылки валид. | Скорость: медиана, мс | p95, мс | ток/с | Стабильность: ошибки | согласованность |
|---|---|---|---|---|---|---|---|---|
| lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K | 0.0 | 4/4 | 0/0 | 37033.5 | 71209.4 | 0.87 | 0 | 2/2 |
| lmstudio:qwen/qwen2.5-coder-14b | 0.25 | 4/4 | 2/2 | 52353.1 | 194529.3 | 0.59 | 0 | 2/2 |
| lmstudio:codellama-7b-python | 0.25 | 4/4 | 5/9 | 457149.7 | 802710.5 | 0.91 | 0 | 1/2 |

## Вердикт

lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K: must_contain 0.0, источники 4/4, медиана 37033.5 мс / p95 71209.4 мс, ошибок 0, согласованность 2/2 · lmstudio:qwen/qwen2.5-coder-14b: must_contain 0.25, источники 4/4, медиана 52353.1 мс / p95 194529.3 мс, ошибок 0, согласованность 2/2 · lmstudio:codellama-7b-python: must_contain 0.25, источники 4/4, медиана 457149.7 мс / p95 802710.5 мс, ошибок 0, согласованность 1/2

## Разбор расхождений

- **c01** — lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K: ист.=да, must=0; lmstudio:qwen/qwen2.5-coder-14b: ист.=да, must=1; lmstudio:codellama-7b-python: ист.=да, must=0
- **c02** — lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K: ист.=да, must=0; lmstudio:qwen/qwen2.5-coder-14b: ист.=да, must=0; lmstudio:codellama-7b-python: ист.=да, must=2

## Ресурсы по генераторам

| Генератор | RSS пик, МБ | RSS среднее, МБ | CPU среднее, % | Размер модели | RAM до (used/avail) | RAM после (used/avail) |
|---|---|---|---|---|---|---|
| lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K | 3910.0 | 3579.2 | 31.5 | 8.99 GB | 9482/6422 | 9346/6558 |
| lmstudio:qwen/qwen2.5-coder-14b | 9211.8 | 8143.1 | 32.9 | 8.99 GB | 9346/6558 | 11915/3989 |
| lmstudio:codellama-7b-python | 9211.8 | 905.1 | 33.0 | 8.99 GB | 11915/3989 | 12922/2982 |

**GPU:** дискретного GPU нет, inference по CPU, VRAM неприменим.
