# migr_plan_5.md — рабочий план этапа M5 «Хранение: servers.json + catalog.json»

> **Роль документа.** Рабочий план-алгоритм **одного этапа** миграции проекта `den_16`
> на целевую архитектуру `Nedela_4/den_16/arch_den_16.md`. Разворачивает этап **M5** из
> `migr_plan.md` §4. Закрывает персистентность MCP-конфига и каталога через фасад
> `Store` (`arch_den_16.md` §2.5).
> **Конец этого этапа — автоматический гейт в этап M6** (`migr_plan_6.md`).
> Источники: `migr_plan.md` (эталон), `arch_den_16.md` §2.5,
> `Рекомендации_MCP_d16.txt` (Store — единственный владелец файлов; gateway JSON
> напрямую не пишет; каталог серверов — user-scope, аудит — task-scope).

> **Синхронизировано с фактом реализации: 2026-09-24.** Правки внесены строго по
> `README.md` (факт реализации) и `dev/migr_log.md` (история процесса) — оба
> равноправные источники истины. `dev/migr_log.md` не изменялся; исходная версия —
> в `dev/old_vers/`.

---
## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **M5** — Хранение: servers.json + catalog.json |
| Рабочий план | `dev/migr_plan_5.md` (этот файл) |
| Зависит от | **M1** (контракты), **M4** (gateway/provider/demo) |
| Открывает | `dev/migr_plan_6.md` (M6 — CLI: DI + /mcp + --mcp-probe) |
| Закрывает | `arch_den_16.md` §2.5 (методы фасада Store + иерархия integrations/mcp/) |
| Основные артефакты | `storage/store.py` (расширение) |
| Живой ключ | **Не нужен** |
| Меняет поведение | **Нет** (новые методы фасада; существующие не тронуты) |

**Цель этапа.** Конфиг серверов и снимок каталога переживают перезапуск:
`users/<id>/integrations/mcp/servers.json` (user/application scope) и
`catalog.json` (снимок `ToolCatalogSnapshot`); битые/отсутствующие файлы → дефолты,
приложение не падает; gateway JSON напрямую не пишет — только через `Store`.

---

## 1. Вход и предусловия

- `storage/store.py` текущий (фасад дней 11–15: `safe_name`, `ensure_*`,
  `read/write_json`, `task_state_path`, `invariants_path` и т.д.).
- `core/tools.py` (ToolCatalogSnapshot), `integrations/mcp/config.py`
  (MCPServerConfig, load_servers_config) после M3–M4.
- M1–M4 зелёные (L2 91/0).

**Предусловия:** фасад только расширяется (новые методы); существующие методы и
`db.py` не трогаются; `users/` проекта тестами не трогается (`.tmp/`).

---

## 2. Шаги этапа (исполняемый алгоритм)

### Шаг 5.1 — Методы конфига серверов
1. `Store.mcp_servers_path(user_id) -> Path`:
   `users/<user_id>/integrations/mcp/servers.json` (каталог создаётся при записи).
2. `Store.read_mcp_servers(user_id) -> list[MCPServerConfig] | None`: файл есть →
   `load_servers_config(path)` (M3); отсутствует/битый → `None` (дефолтизация — у
   вызывающего: `load_servers_config` → `[DEFAULT_SERVERS]`; приложение не падает).
3. `Store.write_mcp_servers(user_id, servers)`: сериализация конфигов
   (`{"servers": [...]}`; tuple → list); атомарная запись (как у существующих
   `write_json`).
4. **Ожидаемый результат:** конфиг живёт в иерархии; дефолт без файла.

### Шаг 5.2 — Методы каталога
1. `Store.tool_catalog_path(user_id) -> Path`:
   `users/<user_id>/integrations/mcp/catalog.json`.
2. `Store.save_tool_catalog(user_id, data: dict)`: сериализация **готового** dict
   каталога `{"schema_version": 1, "version": <int>, "tools": [ {name,
   description, input_schema, source, provider, original_name, risk_level,
   allowed_stages, requires_confirmation, enabled}, ... ], "created_at": <ISO>}`.
3. `Store.read_tool_catalog(user_id) -> dict | None`: файл есть → готовый dict
   каталога (восстановление frozen dataclass и `allowed_stages` list → frozenset —
   у вызывающего); отсутствует/битый → `None` (дефолтизация — у вызывающего:
   **пустой каталог** `{"schema_version": 1, "version": 0, "tools": [],
   "created_at": null}`; миграция: нет файла → пустой каталог).
4. **Ожидаемый результат:** round-trip snapshot равен; битый файл → пустой каталог.

### Шаг 5.3 — Аудит (реализован)
1. `Store.append_tool_audit(user_id, task_id, record)` и
   `Store.load_tool_audit(user_id, task_id) -> list[dict]` — путь
   `users/<id>/tasks/<task>/tool_audit.jsonl`; реализация — append-only (битые
   строки пропускаются); рабочий вызов — день 17+.
2. **Ожидаемый результат:** аудит работает; `transition_log` не тронут (успешный
   вызов инструмента не создаёт запись о переходе).

### Шаг 5.4 — Смоук этапа (инлайн, `.tmp/`)
```bash
python - <<'EOF'
# 1. Store(tmp_dir): write_mcp_servers → read_mcp_servers → конфиги равны
# 2. read_mcp_servers(без файла) → None; битый JSON → None (дефолт у вызывающего)
# 3. save_tool_catalog(user_id, dict) → read_tool_catalog → dict равен
#    (version, tools, created_at; allowed_stages — list)
# 4. read_tool_catalog(без файла) → None (дефолт — пустой каталог version=0)
# 5. read_tool_catalog(битый JSON) → None, не падает
# 6. иерархия: users/<id>/integrations/mcp/{servers,catalog}.json существуют
EOF
```
**Ожидаемый результат:** все блоки OK, EXIT 0; временные файлы — только в
`dev/tests_debug/.tmp/m5_<ts>/`.

### Шаг 5.5 — Проверка границ
1. `grep -n "json.dump\|open(" integrations/mcp/gateway.py integrations/mcp/provider.py`
   → пусто (gateway/provider JSON напрямую не пишут).
2. `grep -n "transition_log" storage/store.py` → без изменений (аудит — отдельный
   файл, задел).
3. **Ожидаемый результат:** Store — единственный владелец файлов.

### Шаг 5.6 — Регрессия
1. L1 → ok; L2 → **91 OK, 0 FAIL** (`test_storage.py` зелёный — существующие
   методы не сломаны); L3/L4/гейт — без изменений (13+2⚠).
**Ожидаемый результат:** полная нерегрессия.

---

## 3. Выход этапа

- `storage/store.py` — новые методы (servers + catalog + audit).
- Смоук этапа.
- Запись этапа **M5** в `dev/migr_log.md`.

---

## 4. Автоматический гейт M5→M6

Гейт считается **зелёным**, если одновременно:
- [ ] `mcp_servers_path`/`read_mcp_servers`/`write_mcp_servers` работают;
      отсутствующий/битый файл → `None` (дефолт `[DEFAULT_SERVERS]` у вызывающего);
- [ ] `tool_catalog_path`/`read_tool_catalog`/`save_tool_catalog` работают;
      round-trip равен; отсутствующий/битый файл → `None` (дефолт пустого каталога
      schema_version=1, version=0 — у вызывающего);
- [ ] `append_tool_audit`/`load_tool_audit` реализованы (append-only);
      `transition_log` не тронут;
- [ ] gateway/provider не пишут JSON мимо Store (grep);
- [ ] иерархия `users/<id>/integrations/mcp/` соответствует arch §2.5;
- [ ] L1 зелёный; L2 **91 OK, 0 FAIL**; L3/L4/гейт — без изменений;
- [ ] `db.py` и прочие контракты не тронуты.

**Зелёный** → запись M5 в `migr_log.md` (✅) → **перечитать `migr_plan.md`** →
создать `migr_plan_6.md`.
**Красный** → карточка ошибки, этап M5 открыт.

---

## 5. Запись в `migr_log.md` (форма §6.4)

```text
## Этап M5 — Хранение: servers.json + catalog.json
- Статус: ✅ завершён | ⚠️ обход | ❌ открыт
- Было: Store без MCP-методов; конфиг и каталог не переживали перезапуск
- Стало: <mcp_servers_path/read/write (None → дефолт у вызывающего);
  tool_catalog_path/read/save (round-trip, дефолты); append/load_tool_audit
  (реализованы)>
- Проверка: <смоук (6 блоков); grep-границы; L1/L2/L3/L4/гейт>
- Артефакты: storage/store.py
- Спорное/риски: <если есть>
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (дата/время)
- Гейт M5→M6: ✅ пройден | ❌ не пройден
```

---

## 6. Следующий шаг

Перечитать актуальный `dev/migr_plan.md`, затем приступить к **M6** по
`dev/migr_plan_6.md` (CLI: DI с `mcp_enabled`; семейство `/mcp` — 6 форм; флаги
`--mcp`/`--mcp-probe`; REPL-смоук канона задания).
