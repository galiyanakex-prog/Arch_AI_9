"""integrations/mcp/config.py — конфигурация MCP-серверов (День 16 → День 17).

Загрузка `users/<id>/integrations/mcp/servers.json` с дефолтами: битый или
отсутствующий файл не роняет приложение — возвращается конфиг по умолчанию.
Дефолт Дня 17: сервер задания `time` (инструмент `get_time`), погодный `weather`
и локальный демо-сервер `demo` (для детерминированных тестов).
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

# Реальный MCP-сервер (погода) недели 4; переопределяется env-переменной.
WEATHER_MCP_URL = os.getenv("MCP_WEATHER_URL", "https://weatherapi.projecteol.ru/mcp/")

# Сервер задания Дня 17 (инструмент `get_time`); переопределяется env-переменной.
TIME_MCP_URL = os.getenv("MCP_SERVER_URL", "http://91.188.212.77:8000/mcp")

# Сервер планировщика (День 18, задание 1); переопределяется env-переменной.
SCHEDULER_MCP_URL = os.getenv("SCHEDULER_MCP_URL", "http://127.0.0.1:8010/mcp")

# Сервер пайплайна (День 18, задание 2); переопределяется env-переменной.
PIPELINE_MCP_URL = os.getenv("PIPELINE_MCP_URL", "http://127.0.0.1:8020/mcp")


def _env_flag(name: str, default: bool = False) -> bool:
    """Флаг из env: «1/true/yes/on» → True; «0/false/no/off/пусто» → False."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# D1 (Ревизия 5): scheduler/pipeline по умолчанию ВЫКЛЮЧЕНЫ (enabled=False), но
# остаются зарегистрированными в каталоге конфигов. Включаются env-флагами —
# тогда probe/REPL поднимают их наравне с time/weather. Это убирает ложный
# `degraded` на недоступных по умолчанию адресах, не меняя overall_state().
SCHEDULER_MCP_ENABLED = _env_flag("SCHEDULER_MCP_ENABLED", False)
PIPELINE_MCP_ENABLED = _env_flag("PIPELINE_MCP_ENABLED", False)


@dataclass(frozen=True)
class MCPServerConfig:
    """Конфиг одного MCP-сервера (изоляция прав через тулинг)."""

    server_id: str
    transport: str = "stdio"            # "stdio" | "http" (задел)
    command: tuple[str, ...] | None = None
    endpoint: str | None = None         # задел HTTP-транспорта
    enabled: bool = True
    trust_level: str = "low"
    allowed_tools: frozenset[str] = field(default_factory=frozenset)  # пусто = все
    denied_tools: frozenset[str] = field(default_factory=frozenset)
    timeout_seconds: float = 30.0
    max_result_bytes: int = 65536
    # D7 (Ревизия 5): авторизация HTTP-транспорта. `headers` — статические
    # заголовки; `token_env` — имя env-переменной с токеном (→ Authorization:
    # Bearer <token>). Секрет НЕ хранится в конфиге/коде — только в env.
    headers: dict[str, str] = field(default_factory=dict)
    token_env: str | None = None


# Реальные серверы Дня 17 (Ревизия 3): основной — сервер задания `time`
# (инструмент `get_time`); погодный HTTP-сервер недели сохранён как второй источник;
# локальный демо-сервер (stdio) сохранён для детерминированных тестов.
DEFAULT_SERVERS: tuple[MCPServerConfig, ...] = (
    MCPServerConfig(
        server_id="time",
        transport="http",
        endpoint=TIME_MCP_URL,
        enabled=True,
        trust_level="low",
    ),
    MCPServerConfig(
        server_id="weather",
        transport="http",
        endpoint=WEATHER_MCP_URL,
        enabled=True,
        trust_level="low",
    ),
    MCPServerConfig(
        server_id="scheduler",
        transport="http",
        endpoint=SCHEDULER_MCP_URL,
        enabled=SCHEDULER_MCP_ENABLED,
        trust_level="low",
    ),
    MCPServerConfig(
        server_id="pipeline",
        transport="http",
        endpoint=PIPELINE_MCP_URL,
        enabled=PIPELINE_MCP_ENABLED,
        trust_level="low",
    ),
    MCPServerConfig(
        server_id="demo",
        transport="stdio",
        # sys.executable: интерпретатор текущего процесса (venv недели) —
        # «python» в PATH этой системы отсутствует, демо-сервер не поднимался.
        command=(sys.executable, "-m", "integrations.mcp.demo_server"),
        enabled=False,   # по умолчанию активен реальный сервер; demo — для тестов
        trust_level="low",
    ),
)


def _parse_server(raw: dict) -> MCPServerConfig | None:
    """Словарь → MCPServerConfig; неизвестные ключи игнорируются."""
    if not isinstance(raw, dict) or not isinstance(raw.get("server_id"), str):
        return None
    command = raw.get("command")
    if isinstance(command, list):
        command = tuple(str(c) for c in command)
    elif isinstance(command, str):
        command = (command,)
    else:
        command = None
    allowed = raw.get("allowed_tools") or []
    denied = raw.get("denied_tools") or []
    headers = raw.get("headers") or {}
    if not isinstance(headers, dict):
        headers = {}
    return MCPServerConfig(
        server_id=raw["server_id"],
        transport=str(raw.get("transport", "stdio")),
        command=command,
        endpoint=raw.get("endpoint"),
        enabled=bool(raw.get("enabled", True)),
        trust_level=str(raw.get("trust_level", "low")),
        allowed_tools=frozenset(str(t) for t in allowed),
        denied_tools=frozenset(str(t) for t in denied),
        timeout_seconds=float(raw.get("timeout_seconds", 30.0)),
        max_result_bytes=int(raw.get("max_result_bytes", 65536)),
        headers={str(k): str(v) for k, v in headers.items()},
        token_env=(str(raw["token_env"]) if raw.get("token_env") else None),
    )


def load_servers_config(path: str | None) -> list[MCPServerConfig]:
    """Загрузить конфиг серверов; отсутствующий/битый файл → [DEFAULT_SERVERS]."""
    if not path:
        return list(DEFAULT_SERVERS)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return list(DEFAULT_SERVERS)
    raw_servers = data.get("servers") if isinstance(data, dict) else None
    if not isinstance(raw_servers, list):
        return list(DEFAULT_SERVERS)
    servers = [cfg for cfg in (_parse_server(r) for r in raw_servers) if cfg]
    return servers or list(DEFAULT_SERVERS)
