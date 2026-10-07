# migr_plan_12.md — Этап 12. Финал: живой прогон, гейт, документация, чистка (Ф)

> Рабочий план **финального этапа** на основе `dev/migr_plan.md` (Ревизия 7, §4 «Этап 12»).
> Контур: **Ф (финал)**. Метка цели: **Ф**. Зависимости: **все этапы 0–11**.
> Порядок: **пошагово с оператором**. **Коммиты — только за оператором** (ШАГ 12.8).

## Цель этапа

Свести Ревизию 7: **живые прогоны** RAG (индексация на `bge-m3`, поиск, ответ с
источниками/цитатами, eval, compare, 2 длинных сценария), расширить гейт приёмки,
**синхронизировать документацию** (`README.md`, `dev/Проверка.md`), почистить временные
файлы и зафиксировать «Итог Ревизии 7».

## Предусловия

- Этапы 0–11 закрыты; `rag/` расширен (`rewrite/sources/citations/verify`); интеграция и
  память задачи работают; 2 сценария прогнаны.
- Ollama active, `bge-m3` (dim 1024) — этап 1.
- `dev/logs_reports/stages/` — каталог транскриптов.

## Границы этапа

- **Не** добавляем новых фич — только прогоны, проверки, документация, чистка.
- **Не** коммитим `rag/index/` (в `.gitignore`).
- **Не** меняем `requirements.txt`.

---

## Шаги

### ШАГ 12.1 — Живая индексация корпуса на `bge-m3` (агент)

```bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
.venv/bin/python Kod.py --rag-ingest 2>&1 | tee dev/logs_reports/stages/rag_ingest_live.txt | tail -20
```

Ожидаемо: `added/updated/removed/chunks` в отчёте; `stats()` — `n_docs`, `n_chunks`,
`model_id`.

### ШАГ 12.2 — Живой поиск и ответ с источниками (агент)

```bash
.venv/bin/python Kod.py --rag-search "как считается бюджет токенов" 2>&1 | tee dev/logs_reports/stages/rag_search_live.txt | tail -20
.venv/bin/python Kod.py --rag-ask "как считается бюджет токенов" 2>&1 | tee dev/logs_reports/stages/rag_ask_live.txt | tail -30
.venv/bin/python Kod.py --rag-eval 2>&1 | tee dev/logs_reports/stages/rag_eval_live.txt | tail -10
.venv/bin/python Kod.py --rag-compare 2>&1 | tee dev/logs_reports/stages/rag_compare_live.txt | tail -20
```

Ожидаемо: поиск отдаёт top-k с метаданными/скорами; ответ несёт **источники + цитаты**;
`--rag-eval` — hit-rate@5 ≥ 0.80; `--rag-compare` — таблица режимов.

### ШАГ 12.3 — REPL-демо и 2 длинных сценария (агент)

```bash
printf '/rag on\n/rag find бюджет токенов\n/rag state\n/exit\n' | .venv/bin/python Kod.py --rag --mock 2>&1 | tee dev/logs_reports/stages/rag_repl_live.txt | tail -30
API_KEY=test-key .venv/bin/python dev/tests_debug/scenario.py 2>&1 | tee dev/logs_reports/stages/dialog_scenarios.md | tail -20
```

Ожидаемо: REPL-демо «вопрос → источники → ответ со ссылками»; 2 сценария по 10–15
сообщений — цель удержана, источники в каждом ответе.

### ШАГ 12.4 — Ручной сценарий `scen_rag.md` (агент)

```bash
ls dev/tests_debug/scenario/scen_rag.md dev/tests_debug/scenario/scen_dialog_A.md dev/tests_debug/scenario/scen_dialog_B.md
```

Ожидаемо: `scen_rag.md` (RAG-демо) + `scen_dialog_A.md`/`scen_dialog_B.md` (часть 4).

### ШАГ 12.5 — Расширение `check_acceptance.sh` (агент)

Добавить проверки (Ревизия 6 — 33; Ревизия 7 добавляет под новые части):

```bash
grep -c "^check\|run_check\|assert" dev/tests_debug/check_acceptance.sh
```

Новые проверки (примерный набор):
1. `import rag`; `rewrite/sources/citations/verify` импортируются;
2. `--rag-ask` возвращает источники **и** цитаты;
3. режим «не знаю» при высоком пороге (без LLM);
4. `--rag-compare` создаёт отчёт с 4 режимами;
5. `--rag-eval` hit-rate@5 ≥ 0.80;
6. `WorkingMemory` round-trip с `goal`/`terms`;
7. 2 длинных сценария существуют и прогнаны;
8. без `--rag` промпт байт-в-байт прежний; RAG не меняет `TaskStage`.

Ожидаемо: гейт **33 → 33+N** зелёный.

### ШАГ 12.6 — Синхронизация документации (агент)

- **`README.md`** ← раздел «RAG-индексация и поиск по документам» + «Диалог и память
  задачи»: назначение, запуск Ollama, команды (`--rag*`, `/rag …`), примеры вывода,
  источники/цитаты, режим «не знаю», включение/отключение RAG.
- **`dev/Проверка.md`** ← чек-лист приёмки: 4 части задания, 10 контрольных вопросов,
  сравнение режимов, проверка источников/цитат, 2 длинных сценария.

```bash
grep -cE "RAG|rag" README.md dev/Проверка.md
```

### ШАГ 12.7 — Чистка временных файлов (агент)

```bash
ls -la dev/tests_debug/.tmp/ 2>/dev/null
rm -rf dev/tests_debug/.tmp/*
ls dev/tests_debug/.tmp/ 2>/dev/null; echo "— .tmp очищен"
```

`rag/index/` **оставляем** (в `.gitignore`); при необходимости пересобрать повторной
индексацией. Рабочие `users/` не трогаем.

### ШАГ 12.8 — «Итог Ревизии 7» + коммит (оператор)

Внести в `dev/migr_log.md` раздел «Итог Ревизии 7»: 4 части закрыты, метрики
(hit-rate@5, faithfulness/grounding), гейт, сценарии, документация. **Предлагаемый коммит:**

```
docs(rag): итог Ревизии 7 — 4 части Задание.txt, гейт 33→N, README/Проверка (этап 12)

Причина: закрыть Ревизию 7. Живые прогоны (ingest/search/ask/eval/compare + 2 длинных
сценария) с транскриптами; гейт расширен; README.md и dev/Проверка.md синхронизированы;
.tmp очищен. RAG — включаемый/отключаемый слой; AI_9 остаётся полноценным агентом.
```

---

## Выход этапа

- транскрипты `dev/logs_reports/stages/rag_*_live.txt`, `dialog_scenarios.md`;
- `check_acceptance.sh` — **33 → 33+N** зелёный;
- `README.md`, `dev/Проверка.md` — синхронизированы;
- `dev/tests_debug/.tmp/` — пуст;
- «Итог Ревизии 7» в `dev/migr_log.md`.

## Гейт (финальный) — все пункты зелёные

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `unit_runner.py` (все модули) | зелёный, без регрессии |
| 2 | `smoke.py` / `scenario.py` | OK / OK (вкл. 2 длинных сценария) |
| 3 | `check_acceptance.sh` | **33+N из 33+N** |
| 4 | живые прогоны `rag_*_live.txt` | созданы |
| 5 | hit-rate@5 (`--rag-eval`) | ≥ 0.80 |
| 6 | источники/цитаты в `--rag-ask` | есть |
| 7 | 2 сценария по 10–15 сообщений | цель удержана, источники в каждом ответе |
| 8 | `README.md` / `dev/Проверка.md` | соответствуют коду |
| 9 | `dev/tests_debug/.tmp/` | пуст |
| 10 | `git diff --stat requirements.txt` | пусто |
| 11 | все юниты зелёные **без** Ollama | ✅ |

## Откат

Финальный этап не создаёт продуктового кода; при красном гейте — вернуть документацию из
`dev/old_vers/7/`, пересобрать `rag/index/`; запись помечается ❌.

## Что передаём дальше

- **DoD Ревизии 7 (§8 мастер-плана):** пункты 1–11 закрыты.
- **Оператору:** предложить коммит (выполняет только оператор); при желании —
  `sudo systemctl enable ollama` для автозапуска (не критично для сессии).
