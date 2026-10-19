# migr_review_0.md — Этап 0. Снимок состояния: фактические счетчики, деревья, размеры (R0)

> Рабочий план **одного этапа** на основе `dev/migr_review.md` (**редакция v1.2**, §4 «Этап 0»).
> Контур: **R0 (подготовка)**. Метка цели: **R0**. Зависимости: **нет** (первый этап).
> Порядок выполнения: **пошагово с оператором** — агент даёт команду, оператор подтверждает,
> агент выполняет и фиксирует вывод; затем следующий шаг.
> **Коммиты — только за оператором** (текст предложен в ШАГЕ 0.7).

## Цель этапа

Зафиксировать **объективную точку отсчёта** — фактические счётчики, деревья, размеры —
независимую от документов. Сформировать список расхождений (README vs диск).
**Ничего не правим** — только снимаем снимок.

## Предусловия

- `dev/review/migr_review.md` — мастер-план ревью (редакция v1.2, этапы 0–9).
- `dev/old_vers/8/migr_review.md` — бэкап предыдущей редакции (172 строки).
- `dev/migr_log.md` — журнал прогресса Ревизии 8 (874 строки).
- `README.md` — 1948 строк, ~5675 токенов, 15 разделов.

## Границы этапа

- **Не** трогаем `README.md` — правок на этом этапе нет.
- **Не** трогаем `dev/Проверка.md` — только чтение.
- **Не** запускаем тесты, прогоны, LLM-запросы.
- **Не** создаём новых файлов (кроме записи в `migr_log.md`).
- **`git` — только оператор**; агент git-команд не выполняет.

---

## Шаги

### ШАГ 0.1 — Git-снимок

```bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
git status --short
git log --oneline -6
git diff --stat
```

**Записать в `migr_log.md`:** что в HEAD, что не закоммичено, последние коммиты.
**Ожидаемо:** HEAD = `dc48bb2` (этап 12); не закоммиченных правок README нет.

### ШАГ 0.2 — Хронология ключевых файлов

```bash
stat -c '%y %n' README.md dev/migr_log.md dev/Проверка.md dev/review/migr_review.md
stat -c '%y %n' Kod.py serve.py core/agent.py core/model_registry.py
```

**Записать в `migr_log.md`:** mtime ключевых файлов.
**Ожидаемо:** `migr_review.md` — сегодня; `README.md` — ранее (этап 12).

### ШАГ 0.3 — Подсчёт модулей

```bash
echo "core:"; ls core/*.py | wc -l
echo "rag:"; ls rag/*.py | wc -l
echo "mcp:"; ls integrations/mcp/*.py | wc -l
echo "gateway:"; ls gateway/*.py | wc -l
echo "unit:"; ls dev/tests_debug/unit/test_*.py | wc -l
echo "scenario:"; ls dev/tests_debug/scenario/*.md | wc -l
echo "stages:"; ls dev/logs_reports/stages | wc -l
echo "fixtures:"; ls -A dev/tests_debug/fixtures 2>/dev/null | wc -l
```

**Записать в `migr_log.md`:** точные числа.
**Ожидаемо:** core=16, rag=19, mcp=11, gateway=6, unit=42, scenario=9, stages=56, fixtures=0.

### ШАГ 0.4 — Размеры и временные файлы

```bash
du -sh dev/tests_debug/.tmp
du -sh rag/index/
wc -l -c README.md dev/migr_log.md dev/Проверка.md dev/review/migr_review.md
```

**Записать в `migr_log.md`:** размеры.
**Ожидаемо:** .tmp=636 КБ (не пусто), rag/index/ есть, README=1948 строк.

### ШАГ 0.5 — Проверка существования файлов из README

```bash
# Файлы, заявленные в README, но отсутствующие на диске
for f in serve.py gateway/app.py gateway/questions.py gateway/sync_questions.py \
         gateway/templates/chat.html gateway/templates/interview.html \
         gateway/templates/login.html gateway/templates/register.html \
         models.json core/model_registry.py core/subagents.py core/resources.py \
         integrations/mcp/time_server.py integrations/mcp/auth.py \
         dev/tests_debug/scenario/scen_multiserver_flow.md \
         dev/tests_debug/scenario/scen_model_switch.md \
         dev/migr_2_plan.md dev/migr_2_plan_0.md; do
  if [ -f "$f" ]; then echo "E: $f"; else echo "M: $f"; fi
done
```

**Записать в `migr_log.md`:** список «E» (есть) и «M» (отсутствует).
**Ожидаемо:** `scen_model_switch.md`, `migr_2_plan.md` — M; всё остальное — E.

### ШАГ 0.6 — Проверка отсутствия файлов в README

```bash
# Файлы на диске, не упомянутые в README
for f in agents.md ND/models/bge-m3_params.md ND/models/DeepSee-V4-Pro-0813.md \
         ND/models/GPT-5-Nano.md ND/models/Llama-3-8B-Lunaris.md \
         ND/models/Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated_params.md \
         ND/models/Step-3.5-Flash-Params.md ND/other/1.txt ND/other/2.txt \
         ND/other/tunel_plan.md ND/tasks/n_1 ND/tasks/n_2 ND/tasks/n_3 \
         ND/tasks/n_4 ND/tasks/n_5 ND/tasks/n_6 ND/tasks/n_7 \
         dev/tests_debug/unit/test_facade.py dev/tests_debug/unit/test_gateway.py \
         dev/tests_debug/unit/test_llm_local.py dev/tests_debug/unit/test_llm_optimize.py \
         dev/tests_debug/unit/test_llm_resources.py dev/tests_debug/unit/test_model_switch.py \
         dev/tests_debug/unit/test_rag_gen_compare.py dev/tests_debug/unit/test_rag_local_gen.py \
         dev/tests_debug/unit/test_subagents.py \
         dev/vps/units/ai9-gateway.service dev/vps/units/ai9-tunnel.service \
         dev/vps/units/mcp-pipeline-server.service dev/vps/units/mcp-scheduler-server.service \
         dev/vps/units/mcp-time-server.service \
         dev/vps/evidence/call_8000_get_time_20260930T200921Z.txt \
         dev/vps/evidence/probe_8000_20260930T200910Z.txt; do
  if grep -q "$f" README.md 2>/dev/null; then echo "Y: $f"; else echo "N: $f"; fi
done
```

**Записать в `migr_log.md`:** список «Y» (упомянут) и «N» (не упомянут).
**Ожидаемо:** `agents.md`, `ND/*`, 9 новых unit-тестов, 5 systemd-юнитов — N.

### ШАГ 0.7 — Формирование сводной таблицы расхождений

На основе ШАГОВ 0.5–0.6 составить таблицу:

| Категория | Файл/раздел | Статус | Действие |
|---|---|---|---|
| Отсутствуют в README, но есть на диске | `serve.py` | E | добавить в дерево модулей |
| Отсутствуют в README, но есть на диске | `gateway/` | E | добавить в дерево модулей |
| Отсутствуют в README, но есть на диске | `models.json` | E | добавить в дерево модулей |
| Отсутствуют в README, но есть на диске | `core/model_registry.py` | E | добавить в дерево модулей |
| Отсутствуют в README, но есть на диске | `core/subagents.py` | E | добавить в дерево модулей |
| Отсутствуют в README, но есть на диске | `core/resources.py` | E | добавить в дерево модулей |
| Отсутствуют в README, но есть на диске | `integrations/mcp/time_server.py` | E | добавить в дерево модулей |
| Отсутствуют в README, но есть на диске | `integrations/mcp/auth.py` | E | добавить в дерево модулей |
| Отсутствуют в README, но есть на диске | `agents.md` | E | добавить в служебные артефакты |
| Отсутствуют в README, но есть на диске | `ND/` (13 файлов) | E | добавить в дерево модулей + карту артефактов |
| Заявлены в README, но отсутствуют на диске | `scen_model_switch.md` | M | удалить из дерева dev/ |
| Заявлены в README, но отсутствуют на диске | `migr_2_plan.md` | M | удалить из дерева dev/ |
| Заявлены в README, но отсутствуют на диске | `migr_2_plan_0…9.md` | M | удалить из дерева dev/ |
| Не упомянуты в README, но есть на диске | 9 новых unit-тестов R8 | N | добавить в дерево dev/ |
| Не упомянуты в README, но есть на диске | `scen_multiserver_flow.md` | N | добавить в дерево dev/ |
| Не упомянуты в README, но есть на диске | `vps/units/` (5 юнитов) | N | добавить в дерево dev/ |
| Не упомянуты в README, но есть на диске | `vps/evidence/` | N | добавить в дерево dev/ |

**Записать в `migr_log.md`:** полную таблицу.

### ШАГ 0.8 — Запись в `migr_log.md` + перечитывание `migr_review.md`

**Записать в `migr_log.md`:** запись этапа 0 по шаблону §7.3 `migr_review.md`.
**Перечитать** `dev/review/migr_review.md` целиком.

**Предлагаемый текст коммита** (выполняет **только** оператор):

```
docs(rev): этап 0 ревью — снимок состояния (R0)

Фактические счётчики: core=16, rag=19, mcp=11, gateway=6, unit=42,
scenario=9, stages=56, fixtures=0, .tmp=636КБ.
Выявлено 18 расхождений README vs диск (14 отсутствуют в README, 2 устаревших,
2 не упомянуты). Мастер-план migr_review.md v1.0 создан.
```

---

## Выход этапа

- `dev/migr_log.md` — запись «Ревью Этап 0» (снимок состояния + таблица расхождений);
- `dev/review/migr_review.md` — перечитан;
- `README.md` — **не изменён**.

## Гейт 0→1 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `git status --short` | пусто или только не-README |
| 2 | `git log --oneline -6` | HEAD = dc48bb2 (этап 12) |
| 3 | `stat` ключевых файлов | mtime зафиксированы |
| 4 | Подсчёт модулей | core=16, rag=19, mcp=11, gateway=6, unit=42, scenario=9, stages=56, fixtures=0 |
| 5 | Размеры | .tmp=636КБ, README=1948 строк |
| 6 | Проверка существования | 2 M, остальное E |
| 7 | Проверка отсутствия | 14+ N |
| 8 | Сводная таблица | 18 расхождений |
| 9 | Запись в migr_log.md | ✅ |
| 10 | Перечитывание migr_review.md | ✅ |

Красный хотя бы один из 1–10 → карточка в `dev/logs_reports/errors/error_<ts>.md`,
этап 0 остаётся открытым.

## Откат

Правок кода и документации нет; откат не нужен.

## Что передаём дальше

- **Этапу 1 (R1):** таблица расхождений — вход для обновления «Дерева модулей».
- **Этапу 2 (R2):** таблица расхождений — вход для обновления «Дерева `dev/`».
- **Этапу 3 (R3):** таблица расхождений — вход для добавления отсутствующих разделов.