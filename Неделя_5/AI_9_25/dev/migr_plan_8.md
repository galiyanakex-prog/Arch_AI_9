# migr_plan_8.md — Этап 8. Интеграция RAG в AI_9 (R6)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (Ревизия 6, §4 «Этап 8»).
> Контур: **R (реализация)**. Метка цели: **R6**. Зависимости: **этапы 4–7** (эмбеддер,
> индекс, ретривер, метрики). Порядок: **пошагово с оператором**.
> **Коммиты — только за оператором** (текст предложен в ШАГЕ 8.7).

## Цель этапа

Модуль `rag/` начинает работать **внутри агента**, не меняя его контрактов:
блок `[rag]` в промте (после `[tools]`), флаги `--rag*`, команды `/rag …`,
DI-сборка `RagService` в `Kod.py`. **Без `--rag` поведение и промпт — байт-в-байт
прежние** (главная регрессионная проверка).

## Предусловия (выполнено)

- `rag/embedding.py`, `rag/index.py`, `rag/retrieval.py`, `rag/eval.py`,
  `rag/compare.py` — реализованы (этапы 4–7);
- `storage/store.py` — `rag_root/rag_index_dir/read_rag_config/write_rag_config` (этап 5);
- `rag/config.py` — `load_config`, `RagConfig.load` (env `AI9_RAG_*`);
- `rag/__init__.py` — экспортирует `RagService` (контракт, заглушка).

## Уточнение к мастер-плану

Мастер-план §4 упоминает `core/context.py` — **такого файла нет**. Контекст промта —
класс `PromptContext` в `core/agent.py`. Блок `[rag]` добавляется через атрибут
`rag_block` (по образцу `tools_block`, День 16), а не через `add_block`.

## Границы этапа

- **Не** реализуем grounding (этап 9) и кэш/multi-query (этап 10): `RagService.ground`
  остаётся понятной заглушкой; `--rag-multi-query` принимается, но пока no-op с
  предупреждением.
- **Не** меняем `TaskStage`, `transition_log`, `invariants`, `profile`.
- **Не** добавляем pip-зависимостей (`requirements.txt` неизменен).
- `rag/` **не** импортирует `core/`; `core/` **не** импортирует `rag/` (связь — DI в
  `Kod.py` + готовый текст блока).

---

## Шаги

### ШАГ 8.1 — `core/prompt_builder.py` (агент)

- `BLOCK_ORDER`: вставить `"rag"` **после** `"tools"`, **до** `"long_term"`.
- `DELIVERABLE`: добавить `"rag"` (иначе `deliver & DELIVERABLE` вырежет блок).
- `render_rag(hits, budget, estimator)` — нумерованные источники
  `[doc_id#chunk_id]` + фрагменты + инструкция «опирайся на источники, ставь ссылки,
  чего нет — не выдумывай»; усечение по бюджету токенов.
- В `PromptBuilder.build`: блок `[rag]` из `getattr(ctx, "rag_block", "")`,
  **обязательность = False** (усекается при нехватке бюджета; `role`/`current` —
  всегда; `invariants`/`profile` стоят раньше и не вытесняются). При пустом
  `rag_block` блок НЕ добавляется → промпт идентичен прежнему.

### ШАГ 8.2 — `rag/service.py` (агент) — фасад §6.1

- `RagService(cfg, log=None)` — ленивая загрузка: индекс, эмбеддер, ретривер.
- `ingest(paths=None)` → `IngestReport` (discover → index.ingest → save).
- `search(query, k=None, mode=None, filters=None)` → `list[Hit]`.
- `context_block(query, k=None, budget=None, hits=None)` → готовый текст блока
  (форматирование живёт в `rag/`, чтобы `rag/` не импортировал `core/`; `hits`
  передаются извне — один поиск на запрос).
- `stats()` → dict (n_docs, n_chunks, model_id, dim, размер, состояние Ollama).
- `compare(...)`, `evaluate(...)` — тонкие обёртки над `rag.compare`/`rag.eval`.
- `ground(...)` — заглушка «этап 9» (NotImplementedError с ясным текстом).

### ШАГ 8.3 — `core/agent.py` (агент)

- `PromptContext.__init__`: `rag_block: str = ""`.
- `Agent.__init__`: `self.rag_service = None`, `self.rag_enabled = False`,
  `self.rag_block_enabled = True`, `self.rag_top_k = None`, `self.rag_mode = None`,
  `self.last_rag_hits = []` (по образцу MCP-слоя — опциональные DI-зависимости).
- `build_context`: если `rag_enabled and rag_service` → один `search`, сохранить
  `last_rag_hits`, строка `[RAG]` в лог (запрос/режим/k/chunk_id/скоры/латентность);
  при `rag_block_enabled` — `context_block(hits=…)` → `PromptContext.rag_block`.
  Ошибки RAG **не** роняют ответ (деградация: блок отсутствует, агент отвечает).

### ШАГ 8.4 — `Kod.py`: флаги + DI (агент)

- Флаги (блок `parser.add_argument`): `--rag`, `--rag-ingest PATH…`,
  `--rag-search "…"`, `--rag-mode`, `--rag-strategy`, `--rag-top-k`,
  `--rag-config FILE`, `--rag-compare`, `--rag-eval [DATASET]`,
  `--rag-grounding {off,warn,strict}`, `--rag-multi-query`, `--no-rag-block`.
- `_build_rag_config(args)` — `RagConfig.load(--rag-config)` + переопределения
  флагами (mode/strategy/top_k/grounding/multi_query).
- `build_agent(..., rag_enabled=False, rag_config=None)` — по образцу
  `if mcp_enabled:`: создать `RagService`, присвоить `agent.rag_service`,
  `agent.rag_enabled=True`, `agent.deliver.add("rag")`.
- В `main` после `deliver & DELIVERABLE`: `if args.rag: agent.deliver.add("rag")`
  (как `tools`, D2); `agent.rag_block_enabled = not args.no_rag_block`;
  печать `[Режим] RAG …`.

### ШАГ 8.5 — `Kod.py`: one-shot + `/rag` (агент)

- One-shot (в `main` до REPL, по образцу `--mcp-probe`): `--rag-ingest`,
  `--rag-search`, `--rag-compare`, `--rag-eval` → собрать `RagService`, выполнить,
  выйти (коды возврата 0/1).
- `handle_rag_command(agent, user_input)` — `on|off|ingest|find|stats|eval`
  (`check` — заглушка «этап 9»). `find/stats/eval` токенов LLM **не** тратят.
- В REPL-цикле: ветка `if command == "/rag":`. В `print_help` — строки `/rag …`.

### ШАГ 8.6 — `test_rag_integration.py` (агент)

- **Главная регрессия:** `PromptContext` без `rag_block` (или `rag_block=""`) →
  собранный промпт **байт-в-байт** равен промпту без знания о RAG.
- С `rag_block` и `"rag" in deliver` → блок `[rag]` присутствует, стоит **после**
  `[tools]` и **до** `[long_term]`.
- `render_rag`: нумерация, ссылки `[doc_id#chunk_id]`, усечение по бюджету.
- `BLOCK_ORDER.index("rag") == index("tools")+1`; `"rag" in DELIVERABLE`.
- `RagService` на пустом/отсутствующем индексе: `search` → `[]`, `context_block` →
  `""`, `stats` не падает (агент отвечает без блока).
- Инвариант: RAG не меняет `TaskStage`/`transition_log` (проверка на Agent-заглушке).

### ШАГ 8.7 — Запись в журнал + перечитывание плана

---

## Выход этапа

- `core/prompt_builder.py`, `core/agent.py`, `Kod.py`, `rag/service.py` — изменены;
- `dev/tests_debug/unit/test_rag_integration.py` — создан;
- запись «Этап 8» в `dev/migr_log.md`;
- `requirements.txt`, `rag/index*`, датасеты — **не изменены**.

## Гейт 8→9 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `unit_runner.py test_rag_integration` | все зелёные |
| 2 | **без `--rag` промпт байт-в-байт прежний** | да (юнит №1) |
| 3 | с `--rag` блок `[rag]` присутствует, после `[tools]`, в бюджете | да |
| 4 | при пустом индексе блока нет, но агент отвечает | да |
| 5 | RAG не меняет `TaskStage`/`transition_log` | да |
| 6 | `python Kod.py --rag --mock` поднимается и печатает `[RAG]` | да |
| 7 | `python Kod.py --rag-search "…" --mock` печатает top-k и выходит 0 | да |
| 8 | L2/L3/L4/гейт (25) | без регрессии |
| 9 | `git diff --stat requirements.txt` | пусто |
| 10 | `rag/` не импортирует `core/`; `core/` не импортирует `rag/` | да |
| 11 | запись «Этап 8» + перечитывание `migr_plan.md` | ✅ |

## Откат

```bash
git checkout -- core/prompt_builder.py core/agent.py Kod.py rag/service.py
rm -f dev/tests_debug/unit/test_rag_integration.py
```

## Что передаём дальше

- **Этапу 9 (R7):** `agent.last_rag_hits` + `RagService.ground` → `/rag check`,
  авто-перегенерация.
- **Этапу 10 (R8):** `RagService.search` → кэш + multi-query.
- **Этапу 11 (Ф):** флаги/команды → README/arch + гейт 25→33.
