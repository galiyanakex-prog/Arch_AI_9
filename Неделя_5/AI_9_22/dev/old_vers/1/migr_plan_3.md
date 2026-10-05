# migr_plan_3.md — рабочий план этапа M3 «MCP-слой: config / transport / client»

> **Роль документа.** Рабочий план-алгоритм **одного этапа** миграции проекта `den_16`
> на целевую архитектуру `Nedela_4/den_16/arch_den_16.md`. Разворачивает этап **M3** из
> `migr_plan.md` §4. Закрывает фундамент MCP-интеграции (`arch_den_16.md` §2.4, часть 1).
> **Конец этого этапа — автоматический гейт в этап M4** (`migr_plan_4.md`).
> Источники: `migr_plan.md` (эталон), `arch_den_16.md` §2.4,
> `Рекомендации_MCP_d16.txt` (MCPServerConfig; транспорт не попадает в бизнес-логику;
> SDK — внутри интеграционного адаптера), `Суть_N4.md` §3.3 (изоляция прав через
> тулинг).

---

## 0. Паспорт этапа

| Поле | Значение |
|---|---|
| Этап | **M3** — MCP-слой: config / transport / client |
| Рабочий план | `dev/migr_plan_3.md` (этот файл) |
| Зависит от | **M1** (SDK установлен, контракты) |
| Открывает | `dev/migr_plan_4.md` (M4 — gateway / provider / demo_server) |
| Закрывает | `arch_den_16.md` §2.4 (config.py, transport.py, client.py) |
| Основные артефакты | `integrations/__init__.py`, `integrations/mcp/{__init__,config,transport,client}.py` |
| Живой ключ | **Не нужен** (FakeMCPTransport; stdio-подпроцесс — только M4) |
| Меняет поведение | **Нет** (новый слой, никем не импортируется до M6) |

**Цель этапа.** Создать фундамент MCP-интеграции: конфиг серверов (`MCPServerConfig`
+ загрузка `servers.json` с дефолтами), транспорт (`MCPTransport` ABC +
`StdioMCPTransport` на `mcp` SDK + `FakeMCPTransport` для тестов) и клиент
(`MCPClient` — единственное место импорта SDK; handshake `initialize` + `list_tools`;
любой сбой → `MCPConnectionError`, не молчание).

---

## 1. Вход и предусловия

- `mcp` SDK в venv (M1); контракты `core/tools.py` (M1).
- M1, M2 зелёные (L2 91/0).

**Предусловия:** `mcp` SDK импортируется **только** в `integrations/mcp/client.py`
(и `demo_server.py` на M4); `core/`/`memory/`/`storage/`/`Kod.py` слой не импортируют;
транспорт — async (нативный для SDK); клиент не знает о стадиях/профилях/памяти.

---

## 2. Шаги этапа (исполняемый алгоритм)

### Шаг 3.1 — Каркас слоя `integrations/`
1. `integrations/__init__.py` (пустой), `integrations/mcp/__init__.py` (пустой).
2. **Ожидаемый результат:** пакет импортируется.

### Шаг 3.2 — `config.py`: MCPServerConfig + загрузка
1. `@dataclass(frozen=True) MCPServerConfig`: `server_id: str`,
   `transport: str = "stdio"`, `command: tuple[str, ...] | None = None`,
   `endpoint: str | None = None` (задел HTTP), `enabled: bool = True`,
   `trust_level: str = "low"`, `allowed_tools: frozenset[str] = frozenset()`
   (пусто = все), `denied_tools: frozenset[str] = frozenset()`,
   `timeout_seconds: float = 30.0`, `max_result_bytes: int = 65536`.
2. `DEFAULT_SERVERS` — конфиг демо-сервера по умолчанию: `server_id="demo"`,
   `transport="stdio"`, `command=("python", "-m",
   "integrations.mcp.demo_server")`, `enabled=True` (единственный в den_16).
3. `load_servers_config(path) -> list[MCPServerConfig]`: чтение JSON
   (`{"servers": [...]}`); отсутствующий/битый файл → `[DEFAULT_SERVERS]`
   (приложение не падает — наследие устойчивости `Store`); неизвестные ключи
   игнорируются; `command` — list → tuple.
4. **Ожидаемый результат:** конфиг по arch §2.4; дефолт живёт без файла.

### Шаг 3.3 — `transport.py`: ABC + stdio + fake
1. `class MCPTransport(ABC)`: `async initialize()`, `async list_tools() ->
   list[dict]` (сырые `{name, description, inputSchema}`), `async call_tool(name,
   arguments)` (задел дня 17+ — `NotImplementedError` или заглушка), `async close()`.
2. `class StdioMCPTransport(MCPTransport)`: обёртка над `mcp` SDK — stdio-клиент
   (подпроцесс по `command` из конфига), `timeout_seconds` на вызовы; ошибки SDK →
   `MCPConnectionError`. Реализация — по фактическому API установленной версии SDK
   (`mcp.client.stdio` / `ClientSession`); при расхождении версий — зафиксировать
   фактический API в `migr_log.md`.
3. `class FakeMCPTransport(MCPTransport)`: детерминированная заглушка —
   конструктор принимает список сырых тулов, флаги `fail_initialize`,
   `fail_list_tools`, `timeout`, `is_error_tool`; метод `set_tools(...)` — смена
   каталога (для теста обновлений); `initialize`/`list_tools`/`close` — без сети и
   без подпроцесса.
4. `class MCPConnectionError(Exception)`: `server_id`, `reason`.
5. **Ожидаемый результат:** три транспорта + исключение; fake полностью
   детерминирован.

### Шаг 3.4 — `client.py`: MCPClient (единственный импорт SDK)
1. `class MCPClient`: конструктор `(config: MCPServerConfig, transport:
   MCPTransport | None = None)` — транспорт инжектится (для тестов — fake; по
   умолчанию — `StdioMCPTransport`).
2. `async initialize()`: handshake — `transport.initialize()` → готовность;
   протокол/capabilities фиксируются в состоянии клиента (для `/mcp status`).
3. `async list_tools() -> list[dict]`: `transport.list_tools()` → нормализация
   сырых описаний: `{name, description, inputSchema}` (дефолты: `description=""`,
   `inputSchema={"type": "object"}`); фильтр прав **не здесь** (это gateway, M4).
4. Любой сбой (исключение транспорта/таймаут/битый формат) → `MCPConnectionError`
   (не `None`, не молчание).
5. **Ожидаемый результат:** клиент по arch §2.4; SDK-импорт только здесь.

### Шаг 3.5 — Примитив-смоук этапа (инлайн, `.tmp/`)
```bash
python - <<'EOF'
# 1. load_servers_config(несуществующий путь) → [DEFAULT_SERVERS] (demo/stdio)
# 2. load_servers_config(битый JSON) → [DEFAULT_SERVERS], не падает
# 3. FakeMCPTransport: initialize → ok; list_tools → список сырых тулов
# 4. FakeMCPTransport(fail_list_tools=True) → MCPConnectionError
# 5. FakeMCPTransport(timeout=True) → MCPConnectionError (не зависание)
# 6. MCPClient(config, transport=fake): initialize + list_tools → нормализованные
#    {name, description, inputSchema} с дефолтами
# 7. import integrations.mcp.client — успешен (SDK импортируется)
EOF
```
**Ожидаемый результат:** все блоки OK, EXIT 0.

### Шаг 3.6 — Проверка непротекания SDK
1. `grep -rn "import mcp\|from mcp" core/ memory/ storage/ Kod.py integrations/` →
   **только** `integrations/mcp/client.py` (на этом этапе; `demo_server.py` — M4).
2. `grep -rn "state_machine\|profile\|memory" integrations/mcp/*.py` → пусто
   (слой не знает о внутренностях агента).
3. **Ожидаемый результат:** границы чистые.

### Шаг 3.7 — Регрессия
1. L1 → ok (включая новые модули); L2 → **91 OK, 0 FAIL**; L3/L4/гейт — без
   изменений (13+2⚠).
**Ожидаемый результат:** полная нерегрессия.

---

## 3. Выход этапа

- `integrations/mcp/{config,transport,client}.py` (+ `__init__`).
- Примитив-смоук этапа.
- Запись этапа **M3** в `dev/migr_log.md` (включая фактический API SDK, если
  отличается от плана).

---

## 4. Автоматический гейт M3→M4

Гейт считается **зелёным**, если одновременно:
- [ ] `MCPServerConfig` — поля по arch §2.4; `load_servers_config`: отсутствующий/
      битый файл → `[DEFAULT_SERVERS]`, не падает;
- [ ] `MCPTransport` ABC + `StdioMCPTransport` (SDK) + `FakeMCPTransport`
      (программируемые отказы/таймаут/смена каталога) + `MCPConnectionError`;
- [ ] `MCPClient`: initialize + list_tools → нормализованные `{name, description,
      inputSchema}`; сбой → `MCPConnectionError` (не `None`);
- [ ] SDK импортируется только в `integrations/mcp/client.py` (grep);
- [ ] слой не знает о стадиях/профилях/памяти (grep);
- [ ] L1 зелёный; L2 **91 OK, 0 FAIL**; L3/L4/гейт — без изменений.

**Зелёный** → запись M3 в `migr_log.md` (✅) → **перечитать `migr_plan.md`** →
создать `migr_plan_4.md`.
**Красный** → карточка ошибки, этап M3 открыт.

---

## 5. Запись в `migr_log.md` (форма §6.4)

```text
## Этап M3 — MCP-слой: config / transport / client
- Статус: ✅ завершён | ⚠️ обход | ❌ открыт
- Было: integrations/ не существовал; SDK установлен, но не использовался
- Стало: <config (MCPServerConfig + дефолт demo); transport (ABC + stdio + fake);
  client (initialize/list_tools, MCPConnectionError)>
- Проверка: <примитив-смоук (7 блоков); grep-непротекание; L1/L2/L3/L4/гейт>
- Артефакты: integrations/mcp/{__init__,config,transport,client}.py
- Спорное/риски: <фактический API SDK vs план; версия SDK>
- Перечитывание migr_plan.md перед следующим этапом: ✅ выполнено (дата/время)
- Гейт M3→M4: ✅ пройден | ❌ не пройден
```

---

## 6. Следующий шаг

Перечитать актуальный `dev/migr_plan.md`, затем приступить к **M4** по
`dev/migr_plan_4.md` (MCP-слой, часть 2: `gateway.py` — MCPConnectionState +
MCPGateway + синхронный фасад; `provider.py` — MCPToolProvider; `demo_server.py` —
локальный stdio-сервер с 3 тулами; интеграционный прогон stdio → demo_server).
