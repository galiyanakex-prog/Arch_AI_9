# migr_plan_1.md — рабочий план этапа M1 «SDK + контракты инструментов»

> **Роль документа.** Рабочий план-алгоритм **одного этапа** миграции проекта `den_16`
> на целевую архитектуру `Nedela_4/den_16/arch_den_16.md`. Разворачивает этап **M1** из
> `migr_plan.md` §4. Закрывает установку MCP SDK и внутреннюю модель инструментов
> (`arch_den_16.md` §2.2) — **без MCP-слоя и без сети**.
> **Конец этого этапа — автоматический гейт в этап M2** (`migr_plan_2.md`).
> Источники: `migr_plan.md` (эталон), `arch_den_16.md` §2.2, `Задание_d16.txt`
> («Установите MCP SDK / клиент»), `Рекомендации_MCP_d16.txt` (ToolDescriptor —
> внутренняя модель, не MCP).

> **Синхронизировано с фактом реализации: 2026-09-24.** Правки внесены строго по
> `README.md` (факт реализации) и `dev/migr_log.md` (история процесса) — оба
> равноправные источники истины. `dev/migr_log.md` не изменялся; исходная версия —
> в `dev/old_vers/`.

---
## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **M1** — SDK + контракты инструментов |
| Рабочий план | `dev/migr_plan_1.md` (этот файл) |
| Зависит от | **M0** (baseline, служебка готова) |
| Открывает | `dev/migr_plan_2.md` (M2 — Реестр: каталог + атомарный snapshot) |
| Закрывает | `arch_den_16.md` §2.2 (core/tools.py: контракты без MCP SDK) |
| Основные артефакты | venv (+`mcp`), `core/tools.py` (новый) |
| Живой ключ | **Не нужен** (контракты — чистый Python) |
| Меняет поведение | **Нет** (новый модуль, никем не импортируется до M6) |

**Цель этапа.** Установить `mcp` SDK в venv недели (зависимость только для
`integrations/mcp/`) и создать внутреннюю модель инструментов агента — контракты
`ToolDescriptor`/`ToolCallRequest`/`ToolExecutionResult`/`ToolProvider`/
`ToolCatalogSnapshot` — без единого импорта MCP SDK в `core/`.

---

## 1. Вход и предусловия

- M0 зелёный (baseline: L2 91 / L4 9 / гейт 13+2⚠; `import mcp` → ModuleNotFoundError).
- venv недели: `requests`, `python-dotenv` (stdlib: `sqlite3`); `mcp` — отсутствует.
- `core/` — 6 модулей дней 11–15 (контракты не трогать).

**Предусловия:** `mcp` устанавливается **только в venv недели** (не глобально);
`core/tools.py` не импортирует `mcp` и не импортируется существующими модулями
(подключение — M6, DI); `requirements`-файла в проекте нет — версию SDK зафиксировать
в `migr_log.md` (и в README на M8).

---

## 2. Шаги этапа (исполняемый алгоритм)

### Шаг 1.1 — Установить `mcp` SDK
1. `../../.venv/bin/python -m pip install mcp` (Model Context Protocol Python SDK;
   вызов pip-скрипта напрямую ненадёжен из-за shebang копированного venv; при
   конфликте зависимостей — зафиксировать в карточке ошибки).
2. `../../.venv/bin/python -m pip show mcp` → зафиксировать версию;
   `../../.venv/bin/python -c "import mcp; print(mcp.__file__)"`.
3. Проверить, что транзитивные зависимости не сломали `requests`/`dotenv`:
   `python -c "import requests, dotenv"`.
4. **Ожидаемый результат:** SDK установлен; версия зафиксирована; прежние
   зависимости живы.

### Шаг 1.2 — `core/tools.py`: контракты (arch §2.2)
1. `ALL_WORKING_STAGES` — frozenset значений 5 рабочих стадий дня 15
   (`new`, `planning`, `plan_approved`, `implementation`, `validation`) — **строками,
   без импорта `state_machine`** (контракты не зависят от автомата; задел policy
   фильтра по стадиям).
2. `@dataclass(frozen=True) ToolDescriptor`: `name` (квалифицированное:
   `mcp.<server>.<tool>` | `local.<tool>`), `description`, `input_schema: dict`,
   `source: str` (`"local"|"mcp"`), `provider: str`, `original_name: str`;
   дефолты заделов: `risk_level="unknown"`,
   `allowed_stages=ALL_WORKING_STAGES`, `requires_confirmation=False`,
   `enabled=True`.
3. `@dataclass(frozen=True) ToolCallRequest` (задел дня 17+): `name`, `arguments: dict`.
4. `@dataclass(frozen=True) ToolExecutionResult` (задел): `execution_id`, `tool`,
   `status: str`, `summary: str`, `raw: object | None = None` (сырой ответ — только
   текущий execution context, не в память).
5. `class ToolProvider(ABC)`: `provider_id() -> str`, `discover() -> list[ToolDescriptor]`.
6. `@dataclass(frozen=True) ToolCatalogSnapshot`: `version: int`,
   `tools: tuple[ToolDescriptor, ...]`, `created_at: str` (ISO).
7. **Ожидаемый результат:** контракты по arch §2.2 построчно; без импорта `mcp`,
   без сети, без зависимостей от других модулей `core/`.

### Шаг 1.3 — Примитив-смоук этапа (инлайн, `.tmp/`)
```bash
python - <<'EOF'
# 1. import mcp — успешен (SDK установлен)
# 2. from core.tools import (ToolDescriptor, ToolCallRequest,
#    ToolExecutionResult, ToolProvider, ToolCatalogSnapshot, ALL_WORKING_STAGES)
# 3. ToolDescriptor(name="mcp.demo.get_time", ..., source="mcp", provider="demo",
#    original_name="get_time") — frozen, дефолты заделов на месте
# 4. ToolCatalogSnapshot(version=1, tools=(...,), created_at=...) — frozen
# 5. подкласс ToolProvider с discover() — инстанцируется
EOF
```
**Ожидаемый результат:** все блоки OK, EXIT 0; временные файлы (если есть) — только
в `dev/tests_debug/.tmp/m1_<ts>/`.

### Шаг 1.4 — Проверка непротекания SDK
1. `grep -rn "import mcp\|from mcp" core/ memory/ storage/ Kod.py` → **пусто**
   (SDK — только для `integrations/mcp/`, которых ещё нет).
2. `grep -rn "from core.tools\|import core.tools" core/ memory/ storage/ Kod.py`
   → пусто (модуль подключается на M6).
3. **Ожидаемый результат:** оба grep пусты; направление зависимостей чистое.

### Шаг 1.5 — Регрессия
1. L1 `py_compile Kod.py core/*.py memory/*.py storage/*.py` → ok (включая новый
   `core/tools.py`).
2. L2 `unit_runner.py` → **91 OK, 0 FAIL** (новый модуль никого не ломает).
3. L3/L4/гейт → без изменений (13+2⚠).
**Ожидаемый результат:** полная нерегрессия.

---

## 3. Выход этапа

- venv недели с `mcp` SDK (версия зафиксирована).
- `core/tools.py` — контракты внутренней модели инструментов.
- Примитив-смоук этапа (инлайн или `dev/tests_debug/m1_smoke.py` — по решению
  исполнителя; судьба смоуков этапов решается на M8, как в den_15).
- Запись этапа **M1** в `dev/migr_log.md`.

---

## 4. Автоматический гейт M1→M2

Гейт считается **зелёным**, если одновременно:
- [ ] `python -c "import mcp"` успешен; версия зафиксирована в `migr_log.md`;
- [ ] `core/tools.py` импортируется; контракты соответствуют arch §2.2 построчно
      (ToolDescriptor — 10 полей с дефолтами заделов; ToolCatalogSnapshot — frozen);
- [ ] `grep "import mcp" core/ memory/ storage/ Kod.py` → пусто (SDK не протёк);
- [ ] `grep "core.tools" core/ memory/ storage/ Kod.py` → пусто (подключение — M6);
- [ ] L1 зелёный; L2 **91 OK, 0 FAIL**; L3/L4/гейт — без изменений (13+2⚠);
- [ ] прежние зависимости (`requests`, `dotenv`) живы.

**Зелёный** → запись M1 в `migr_log.md` (✅) → **перечитать `migr_plan.md`** →
создать `migr_plan_2.md`.
**Красный** → карточка ошибки `dev/logs_reports/errors/error_<ts>.md`, этап M1 открыт.

---

## 5. Запись в `migr_log.md` (форма §6.4 `migr_plan.md`)

```text
## Этап M1 — SDK + контракты инструментов
- Статус: ✅ завершён | ⚠️ обход | ❌ открыт
- Было: mcp SDK отсутствовал; core/tools.py не существовал
- Стало: <mcp <версия> в venv; контракты ToolDescriptor/ToolCallRequest/
  ToolExecutionResult/ToolProvider/ToolCatalogSnapshot/ALL_WORKING_STAGES>
- Проверка: <import mcp; примитив-смоук; grep-непротекание; L1/L2/L3/L4/гейт>
- Артефакты: venv (+mcp), core/tools.py
- Спорное/риски: <версия SDK; транзитивные зависимости — если есть>
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (дата/время)
- Гейт M1→M2: ✅ пройден | ❌ не пройден
```

---

## 6. Следующий шаг

Перечитать актуальный `dev/migr_plan.md`, затем приступить к **M2** по
`dev/migr_plan_2.md` (`core/tool_registry.py`: ToolRegistry — каталог всех
источников, атомарный snapshot, коллизии имён, недоступные провайдеры).
