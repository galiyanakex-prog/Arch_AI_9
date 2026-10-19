# migr_review_4.md — Этап 4. Обновление «Карты артефактов» (R4)

> Рабочий план **одного этапа** на основе `dev/migr_review.md` (**редакция v1.2**, §4 «Этап 4»).
> Контур: **R2 (артефакты и разделы)**. Метка цели: **R4**. Зависит: **1, 2, 3**.
> Порядок выполнения: **пошагово с оператором**.
> **Коммиты — только за оператором**.

## Цель этапа

Привести раздел «Карта артефактов» (стр. 1741) в соответствие с фактической структурой
и с деревьями, обновлёнными на этапах 1–3.

## Расхождения (уточнены после чтения текущего состояния README)

**Важно:** «Карта артефактов» уже **частично** обновлена под Ревизию 8 — в ней есть
`serve.py`, `gateway/*`, `models.json`, `core/model_registry.py`, `core/subagents.py`,
`core/resources.py`. Поэтому объём этапа меньше, чем предполагалось в мастер-плане.

| Позиция | Статус | Действие |
|---|---|---|
| `serve.py`, `gateway/*`, `models.json`, `core/model_registry.py`, `core/subagents.py`, `core/resources.py` | ✅ уже есть | не трогать |
| `integrations/mcp/*` — перечень не содержит `auth.py`, `time_server.py` | ❌ неполно | дополнить перечень |
| `gateway/*` — перечень не содержит `sync_questions.py`, `questions.json`, `gateway.json` | ❌ неполно | дополнить перечень |
| `dev/vps/*` — перечень не содержит `units/` (5 systemd-юнитов), `evidence/` | ❌ неполно | дополнить перечень |
| `ND/` | ❌ отсутствует | добавить (см. также этап 3) |
| `agents.md` | ❌ отсутствует | добавить (см. также этап 3) |
| `dev/review/*` (мастер-план ревью + рабочие планы) | ❌ отсутствует | добавить |
| «Служебные артефакты»: `dev/tests_debug/*` — «L2 (+9 новых модулей R8), L3, L4 (+6 сценариев), гейт 58/58» | ⚠️ требует сверки | сверить счётчики на этапе 6, здесь — только пометить «сверить» |

## Фактические данные (из этапа 0)

```
integrations/mcp/ (11): __init__, auth, client, config, demo_server, gateway,
  pipeline_server, provider, scheduler_server, time_server, transport
gateway/ (6 py + 2 json + 4 html): __init__, app, config, questions,
  sync_questions, users + gateway.json, questions.json + templates/
dev/vps/: deploy_services.sh, mcp_vps.sh, services.list, ssh_config.snippet,
  sshd_gateway.snippet, README_vps.md, README_gateway.md,
  units/ (5), evidence/ (5 + .gitkeep)
dev/review/: migr_review.md, migr_review_0.md … migr_review_9.md
ND/: models/ (7), other/ (3), tasks/ (7)
agents.md (20 строк)
```

---

## Шаги

### ШАГ 4.1 — Дополнить перечень `integrations/mcp/*`

**Текущая строка:**

```
- `integrations/mcp/*` — MCP-слой: config, transport (stdio + HTTP + fake), client, gateway,
  provider, demo_server, scheduler_server, pipeline_server.
```

**Правка:**

```
- `integrations/mcp/*` — MCP-слой: config, transport (stdio + HTTP + fake), client, gateway,
  provider, demo_server, scheduler_server, pipeline_server, time_server, auth.
```

### ШАГ 4.2 — Дополнить перечень `gateway/*`

**Текущая строка:**

```
- `gateway/*` — веб-шлюз на VPS: `app.py` (чат, прокси), `users.py` (регистрация),
  `questions.py` (интервью), `config.py`, `templates/`.
```

**Правка:**

```
- `gateway/*` — веб-шлюз на VPS: `app.py` (чат, прокси), `users.py` (регистрация),
  `questions.py` + `questions.json` (интервью, единый источник истины),
  `sync_questions.py` (обновление снапшота вопросов), `config.py` + `gateway.json`
  (лимиты, адрес фасада), `templates/` (login, register, interview, chat).
```

### ШАГ 4.3 — Дополнить перечень `dev/vps/*`

**Текущая строка:**

```
- `dev/vps/*` — инфраструктура доступа: скрипты деплоя, `ssh_config.snippet`,
  `README_gateway.md`.
```

**Правка:**

```
- `dev/vps/*` — инфраструктура доступа: скрипты деплоя (`deploy_services.sh`,
  `mcp_vps.sh`), `services.list`, `ssh_config.snippet`, `sshd_gateway.snippet`,
  `units/` (5 systemd-юнитов: шлюз, туннель, 3 MCP-сервера), `evidence/`
  (артефакты проверки MCP на VPS), `README_vps.md`, `README_gateway.md`.
```

### ШАГ 4.4 — Добавить `ND/` в «Рабочие артефакты»

**Правка:** перед строкой `run.sh` и `run.desktop` добавить:

```
- `ND/models/*_params.md` — справки по моделям: окно контекста, параметры, доступные
  кванты, требования по RAM (боевая — `Qwen2.5-Coder-3B-…-abliterated_params.md`).
```

### ШАГ 4.5 — Добавить `agents.md` и `dev/review/*` в «Служебные артефакты»

**Текущий блок:**

```
- `dev/Проверка.md` — чек-лист приёмки: 48 критериев Ревизии 8.
- `dev/migr_plan.md` и `migr_plan_*.md` — план-эталон и рабочие планы миграции.
- `dev/migr_log.md` — журнал миграции и итоги ревизий.
- `dev/tests_debug/*` — L2 (+9 новых модулей R8), L3, L4 (+6 сценариев), гейт 58/58.
- `dev/logs_reports/stages/*` — транскрипты живых прогонов.
```

**Правка:**

```
- `dev/Проверка.md` — чек-лист приёмки: 48 критериев Ревизии 8.
- `dev/migr_plan.md` и `migr_plan_*.md` — план-эталон и рабочие планы миграции.
- `dev/migr_log.md` — журнал миграции и итоги ревизий (+ журнал ревью документации).
- `dev/review/migr_review.md` и `migr_review_*.md` — мастер-план и рабочие планы
  ревью документации (приведение README к реальной картине проекта).
- `dev/tests_debug/*` — L2 (42 модуля, +9 новых R8), L3, L4 (9 сценариев),
  гейт `check_acceptance.sh` (число проверок — см. этап 6).
- `dev/logs_reports/stages/*` — транскрипты живых прогонов (56 файлов).
- `agents.md` — краткая памятка агенту (вспомогательный документ).
- `ND/tasks/n_1 … n_7` — задания куратора по неделям (источник требований).
- `ND/other/tunel_plan.md` — наработки по туннелю (учтены в `dev/vps/`).
```

> **Примечание:** число проверок гейта здесь намеренно не зафиксировано числом —
> в README заявлено 58, в скрипте насчитано 59. Сверка — этап 6 (R6).

### ШАГ 4.6 — Проверка правок

```bash
# Все упомянутые в карте артефактов пути существуют
for f in integrations/mcp/time_server.py integrations/mcp/auth.py \
         gateway/sync_questions.py gateway/questions.json gateway/gateway.json \
         dev/vps/units dev/vps/evidence dev/review/migr_review.md \
         ND/models agents.md; do
  if [ -e "$f" ]; then echo "OK: $f"; else echo "MISSING: $f"; fi
done
# Устаревших ссылок нет
grep -n 'migr_2_plan\|README_3\|README_4\|scen_model_switch' README.md
```

**Ожидаемо:** все OK; grep не находит устаревших ссылок (если нашёл — этап 2/7,
зафиксировать и передать).

### ШАГ 4.7 — Перечитывание `migr_review.md`

Перечитать `dev/review/migr_review.md` целиком.

**Предлагаемый текст коммита** (выполняет **только оператор**):

```
docs(readme): обновить «Карту артефактов» — дополнить mcp/ (time_server, auth),
gateway/ (sync_questions, questions.json), dev/vps/ (units, evidence),
добавить ND/, agents.md, dev/review/
```

---

## Выход этапа

- `README.md` — раздел «Карта артефактов» обновлён;
- `dev/migr_log.md` — запись этапа 4;
- `dev/review/migr_review.md` — перечитан.

## Гейт 4→5 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `integrations/mcp/*` — 11 модулей в перечне | ✅ |
| 2 | `gateway/*` — все 6 py + 2 json + templates | ✅ |
| 3 | `dev/vps/*` — units/ и evidence/ упомянуты | ✅ |
| 4 | `ND/` в карте артефактов | ✅ |
| 5 | `agents.md` в служебных артефактах | ✅ |
| 6 | `dev/review/*` в служебных артефактах | ✅ |
| 7 | Все упомянутые пути существуют | ✅ |
| 8 | Устаревших ссылок нет | ✅ |
| 9 | Запись в migr_log.md | ✅ |
| 10 | Перечитывание migr_review.md | ✅ |

## Откат

`git checkout HEAD -- README.md` — выполняет оператор.

## Что передаём дальше

- **Этапу 6 (R6):** счётчик гейта подтверждён (58) — сверять только остальное.
- **Этапу 8 (R8):** карта артефактов как источник для проверки перекрёстной
  согласованности.