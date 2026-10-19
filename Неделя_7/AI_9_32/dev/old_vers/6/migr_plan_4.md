# migr_plan_4.md — Этап 4. Эмбеддинги (R2)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (Ревизия 6, §4 «Этап 4»).
> Контур: **R (реализация)**. Метка цели: **R2**. Зависимости: **этап 1** (Ollama),
> **этап 3** (чанки). Порядок: **пошагово с оператором**.
> **Коммиты — только за оператором** (текст предложен в ШАГЕ 4.7).

## Цель этапа

Реализовать `rag/embedding.py`: протокол `Embedder` (`embed(texts) -> list[list[float]]`,
`dim`, `model_id`) и реализации — `HashingEmbedder` (дефолт, 0 зависимостей),
`OllamaEmbedder` (живой, localhost), `FakeEmbedder` (тесты),
`SentenceTransformerEmbedder` (заглушка). Плюс кэш эмбеддингов и деградация.

## Предусловия (выполнено)

- Ollama 0.35.1, `bge-m3` dim 1024, `/api/embed` отвечает (этап 1);
- `rag/config.py → EmbeddingConfig` (`provider=ollama`, `model=bge-m3`, `dim=1024`,
  `url=http://127.0.0.1:11434`, `batch_size=32`, `timeout_seconds=30`, `retries=2`,
  `keep_alive=10m`, `fallback_provider=hashing`, `hashing_dim=256`);
- `rag/chunking.py` — чанки с `sha1` (этап 3);
- `rag/embedding.py` — заглушка.

## Границы этапа

- **Не** строим индекс (этап 5), **не** считаем метрики (этап 7).
- **Не** трогаем `Kod.py`, `core/`, `storage/`, `memory/`, `integrations/`.
- **Не** добавляем pip-зависимостей: `SentenceTransformerEmbedder` — заглушка.
- **Не** ходим во внешнюю сеть: только `127.0.0.1:11434`.

---

## Шаги

### ШАГ 4.1 — `RagDependencyError` (агент)

Добавить в `rag/config.py` (рядом с `RagConfigError`) и экспортировать из
`rag/__init__.py`. Нужен для заглушки `SentenceTransformerEmbedder`.

### ШАГ 4.2 — `rag/embedding.py` (агент)

| Класс | Назначение |
|---|---|
| `Embedder` | протокол: `dim`, `model_id`, `embed(texts)` |
| `HashingEmbedder` | char 3–5-граммы → blake2b → dim 256 → L2-норма; детерминирован |
| `OllamaEmbedder` | `POST /api/embed`, батчи 32, таймаут, retry ×2, `keep_alive`; только localhost |
| `FakeEmbedder` | детерминированный по хэшу текста (тесты) |
| `SentenceTransformerEmbedder` | заглушка → `RagDependencyError` |
| `make_embedder(cfg)` | выбор по `cfg.provider` |

### ШАГ 4.3 — Кэш эмбеддингов (агент)

`rag/index/emb_cache.json` по `sha1(text) → vector`; перестроение не переэмбедит
неизменившиеся чанки. Класс `EmbeddingCache` в `rag/embedding.py`.

### ШАГ 4.4 — Деградация (агент)

Ollama недоступен → предупреждение в лог + `HashingEmbedder` (не падение);
состояние в `stats()`.

### ШАГ 4.5 — `test_rag_embedding.py` (агент)

Проверки: детерминизм хэширующего; косинус одинакового ≈ 1, разного < 0.9;
`dim` стабилен; заглушка → `RagDependencyError`; не-localhost URL отвергнут;
`FakeEmbedder` воспроизводим; кэш round-trip.

### ШАГ 4.6 — Живой прогон (агент)

`OllamaEmbedder` на 3 реальных чанках корпуса → вектор `dim` из конфига;
транскрипт в `dev/logs_reports/stages/rag_embed_live.txt`.

### ШАГ 4.7 — Запись в журнал + перечитывание плана

---

## Выход этапа

- `rag/embedding.py` — реализован;
- `rag/config.py` — `RagDependencyError`;
- `dev/tests_debug/unit/test_rag_embedding.py` — создан;
- `dev/logs_reports/stages/rag_embed_live.txt` — транскрипт;
- запись «Этап 4» в `dev/migr_log.md`;
- `requirements.txt`, `Kod.py`, `core/`, `storage/` — **не изменены**.

## Гейт 4→5 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `unit_runner.py test_rag_embedding` | все зелёные **без** Ollama |
| 2 | `HashingEmbedder` детерминирован | повтор == первый |
| 3 | косинус одинакового ≈ 1, разного < 0.9 | да |
| 4 | `SentenceTransformerEmbedder` → `RagDependencyError` | да |
| 5 | не-localhost URL отвергнут | `ValueError` |
| 6 | живой `OllamaEmbedder` на 3 чанках | вектор dim 1024 |
| 7 | L2/L3/L4/гейт | без регрессии |
| 8 | `git diff --stat requirements.txt` | пусто |
| 9 | запись «Этап 4» + перечитывание `migr_plan.md` | ✅ |

## Откат

```bash
git checkout -- rag/embedding.py rag/config.py rag/__init__.py
rm -f dev/tests_debug/unit/test_rag_embedding.py
rm -rf rag/index/
```

## Что передаём дальше

- **Этапу 5 (R3):** `Embedder.embed` — источник векторов для индекса; `sha1` — ключ кэша.
- **Этапу 6 (R4):** `dim` — размерность dense-поиска.
- **Этапу 10 (R8):** `EmbeddingCache` — основа кэша поиска.
