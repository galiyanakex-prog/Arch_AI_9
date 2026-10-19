# migr_review_2.md — Этап 2. Обновление «Дерева `dev/`» (R2)

> Рабочий план **одного этапа** на основе `dev/migr_review.md` (**редакция v1.2**, §4 «Этап 2»).
> Контур: **R1 (деревья)**. Метка цели: **R2**. Зависит: **0**.
> Порядок выполнения: **пошагово с оператором**.
> **Коммиты — только за оператором**.

## Цель этапа

Привести раздел «Дерево `dev/`» (стр. 1653) в соответствие с фактической структурой
`dev/tests_debug/`, `dev/logs_reports/`, `dev/vps/`.

## Расхождения (из этапа 0)

| Файл/каталог | Статус | Действие |
|---|---|---|
| `migr_2_plan.md` | ❌ заявлен, не существует | удалить из дерева |
| `migr_2_plan_0.md … migr_2_plan_9.md` | ❌ заявлены, не существуют | удалить из дерева |
| `scen_model_switch.md` | ❌ заявлен, не существует | удалить из дерева |
| `scen_multiserver_flow.md` | ✅ существует, не упомянут | добавить в дерево |
| 9 новых unit-тестов R8 | ✅ существуют, не упомянуты | добавить в дерево |
| `vps/units/` (5 systemd-юнитов) | ✅ существует, не упомянут | добавить в дерево |
| `vps/evidence/` (5 файлов + .gitkeep) | ✅ существует, не упомянут | добавить в дерево |
| `fixtures/` (пустой) | ✅ существует, не упомянут | добавить с пометкой |

## Фактические данные (из этапа 0)

```
dev/tests_debug/unit/ (42 модуля):
  test_agent.py, test_d1_probe.py, test_d2_tools_prompt.py, test_d4_routing.py,
  test_d5_timeout.py, test_d6_fixes.py, test_d7_auth.py, test_facade.py,
  test_fsm.py, test_gateway.py, test_invariants.py, test_llm.py,
  test_llm_local.py, test_llm_optimize.py, test_llm_resources.py, test_mcp.py,
  test_memory.py, test_model_switch.py, test_person.py, test_prompt.py,
  test_rag_cache.py, test_rag_chunking.py, test_rag_embedding.py, test_rag_eval.py,
  test_rag_gen_compare.py, test_rag_grounding.py, test_rag_index.py,
  test_rag_integration.py, test_rag_local_gen.py, test_rag_rerank.py,
  test_rag_retrieval.py, test_rag_rewrite_config.py, test_rag_service.py,
  test_rag_text.py, test_rag_verify.py, test_rag_verify_stability.py,
  test_rag_working_memory.py, test_state.py, test_storage.py, test_subagents.py,
  test_time_server.py, test_transitions.py

dev/tests_debug/scenario/ (9 файлов):
  scen_1.md, scen_access.md, scen_dialog_A.md, scen_dialog_B.md,
  scen_local_llm.md, scen_multiserver_flow.md, scen_optimize.md,
  scen_rag.md, scen_rag_local.md

dev/vps/units/ (5 файлов):
  ai9-gateway.service, ai9-tunnel.service, mcp-pipeline-server.service,
  mcp-scheduler-server.service, mcp-time-server.service

dev/vps/evidence/ (5 файлов + .gitkeep):
  call_8000_get_time_20260930T200921Z.txt,
  call_8000_get_time_20260930T223208Z.txt,
  probe_8000_20260930T200910Z.txt, probe_8010_20260930T220655Z.txt,
  probe_8020_20260930T220655Z.txt

dev/logs_reports/stages/ — 56 файлов
dev/tests_debug/fixtures/ — пусто
```

---

## Шаги

### ШАГ 2.1 — Удалить устаревшие планы Ревизии 7.1

**Текущий блок (стр. 1660–1661):**

```
├── migr_2_plan.md                # мастер-план Ревизии 7.1 (актуализация)
├── migr_2_plan_0.md … migr_2_plan_9.md  # рабочие планы Ревизии 7.1
```

**Правка:** удалить обе строки (файлы не существуют на диске).

### ШАГ 2.2 — Удалить несуществующий сценарий

**Текущий блок (стр. 1686):**

```
│   │   └── scen_model_switch.md  # переключение моделей (Ревизия 8)
```

**Правка:** удалить строку (файл не существует на диске).

### ШАГ 2.3 — Добавить отсутствующий сценарий

**Правка:** в блок `scenario/` добавить:

```
│   │   ├── scen_multiserver_flow.md  # мультисерверный поток (Ревизия 7)
```

### ШАГ 2.4 — Обновить блок `unit/`

**Текущий блок (стр. 1673–1676):**

```
│   ├── unit/
│   │   ├── … прежние модули (MCP/RAG off)
│   │   ├── test_mcp.py           # контракты + реестр + gateway + call_tool + policy + tool-use
│   │   └── test_rag_*.py         # integration / grounding / cache / rerank / verify / working_memory
```

**Правка:** заменить на конкретику (42 модуля, с явным перечислением новых R8):

```
│   ├── unit/                     # 42 модуля test_*.py (канонический раннер — unit_runner.py)
│   │   ├── … прежние модули (MCP/RAG off)
│   │   ├── test_mcp.py           # контракты + реестр + gateway + call_tool + policy + tool-use
│   │   ├── test_rag_*.py         # integration / grounding / cache / rerank / verify / working_memory
│   │   └── Ревизия 8 (9 модулей):
│   │       ├── test_llm_local.py         # локальные клиенты + ModelRegistry
│   │       ├── test_model_switch.py      # /model, отображение, регрессия
│   │       ├── test_subagents.py         # запуск/таймаут/безопасность
│   │       ├── test_rag_local_gen.py     # локальная генерация в RAG
│   │       ├── test_rag_gen_compare.py   # сравнение генераторов
│   │       ├── test_llm_optimize.py      # профили, шаблон, метрики
│   │       ├── test_llm_resources.py     # замеры ресурсов
│   │       ├── test_facade.py            # фасад: маршруты, очередь, подпись
│   │       └── test_gateway.py           # вход, регистрация, лимиты, прокси
```

### ШАГ 2.5 — Обновить строку `vps/`

**Текущий блок (стр. 1691):**

```
└── vps/                          # инфраструктурный контур VPS (units/, evidence/, скрипты)
```

**Правка:** раскрыть содержимое:

```
└── vps/                          # инфраструктурный контур VPS
    ├── deploy_services.sh        # выкатка сервисов
    ├── mcp_vps.sh                # управление MCP на VPS
    ├── services.list             # список сервисов
    ├── ssh_config.snippet        # конфиг SSH-туннеля (хост)
    ├── sshd_gateway.snippet      # справка по GatewayPorts (VPS)
    ├── README_vps.md             # инструкция по VPS
    ├── README_gateway.md         # инструкция по шлюзу
    ├── units/                    # 5 systemd-юнитов:
    │   ├── ai9-gateway.service           # шлюз на VPS (:8080)
    │   ├── ai9-tunnel.service            # SSH reverse tunnel (хост)
    │   ├── mcp-time-server.service       # MCP :8000
    │   ├── mcp-scheduler-server.service  # MCP :8010
    │   └── mcp-pipeline-server.service   # MCP :8020
    └── evidence/                 # артефакты проверки MCP на VPS (5 probe/call)
```

### ШАГ 2.6 — Добавить `fixtures/`

**Правка:** в блок `tests_debug/` добавить:

```
│   ├── fixtures/                 # фикстуры (пусто — заполняется по мере надобности)
```

### ШАГ 2.7 — Обновить счётчик сценариев ручной демонстрации

**Правка:** в описании `scenario/` указать фактическое число — **9 сценариев**
(было заявлено 7, из них 1 не существует → реально 9).

### ШАГ 2.8 — Проверка правок

```bash
# Проверить, что все файлы из нового дерева dev/ существуют
for f in dev/tests_debug/scenario/scen_multiserver_flow.md \
         dev/tests_debug/unit/test_llm_local.py dev/tests_debug/unit/test_model_switch.py \
         dev/tests_debug/unit/test_subagents.py dev/tests_debug/unit/test_rag_local_gen.py \
         dev/tests_debug/unit/test_rag_gen_compare.py dev/tests_debug/unit/test_llm_optimize.py \
         dev/tests_debug/unit/test_llm_resources.py dev/tests_debug/unit/test_facade.py \
         dev/tests_debug/unit/test_gateway.py \
         dev/vps/units/ai9-gateway.service dev/vps/units/ai9-tunnel.service \
         dev/vps/units/mcp-time-server.service dev/vps/units/mcp-scheduler-server.service \
         dev/vps/units/mcp-pipeline-server.service; do
  if [ -f "$f" ]; then echo "OK: $f"; else echo "MISSING: $f"; fi
done
# Проверить, что удалённые файлы действительно отсутствуют
for f in dev/migr_2_plan.md dev/tests_debug/scenario/scen_model_switch.md; do
  if [ -f "$f" ]; then echo "STILL EXISTS: $f"; else echo "OK (absent): $f"; fi
done
```

**Записать в `migr_log.md`:** результат проверки.

### ШАГ 2.9 — Перечитывание `migr_review.md`

Перечитать `dev/review/migr_review.md` целиком.

**Предлагаемый текст коммита** (выполняет **только** оператор):

```
docs(readme): обновить «Дерево dev/» — удалить несуществующие migr_2_plan* и
scen_model_switch.md, добавить 9 unit-тестов R8, scen_multiserver_flow.md,
vps/units/ (5 юнитов), vps/evidence/, fixtures/
```

---

## Выход этапа

- `README.md` — раздел «Дерево `dev/`» обновлён;
- `dev/migr_log.md` — запись этапа 2;
- `dev/review/migr_review.md` — перечитан.

## Гейт 2→3 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `migr_2_plan*` удалены из дерева | ✅ |
| 2 | `scen_model_switch.md` удалён из дерева | ✅ |
| 3 | `scen_multiserver_flow.md` добавлен | ✅ |
| 4 | 9 unit-тестов R8 добавлены | ✅ |
| 5 | `vps/units/` (5 юнитов) раскрыт | ✅ |
| 6 | `vps/evidence/` раскрыт | ✅ |
| 7 | `fixtures/` добавлен | ✅ |
| 8 | Все файлы из нового дерева существуют | ✅ |
| 9 | Удалённые файлы действительно отсутствуют | ✅ |
| 10 | Запись в migr_log.md | ✅ |
| 11 | Перечитывание migr_review.md | ✅ |

## Откат

`git checkout HEAD -- README.md` — выполняет оператор.

## Что передаём дальше

- **Этапу 3 (R3):** обновлённое дерево `dev/` — контекст для добавления отсутствующих разделов.
- **Этапу 4 (R4):** список файлов `vps/units/` и `vps/evidence/` — для карты артефактов.
