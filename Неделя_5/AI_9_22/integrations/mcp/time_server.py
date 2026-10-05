"""MCP-сервер времени (порт 8000) — перенесён в репозиторий AI_9.

Раньше жил отдельно: /home/t/doc/mcp/mcp-time-server/time_server_http.py
на собственном venv. Теперь — часть дерева AI_9, запускается из общего venv
/home/t/doc/mcp/ai9 (Этап 1 плана dev/migr_log.md).

Запуск:
    python -m integrations.mcp.time_server            # HTTP :8000
    python -m integrations.mcp.time_server --stdio    # stdio (для отладки)

Переменные окружения:
    TIME_PORT — порт HTTP (по умолчанию 8000).

Инструмент: get_time(timezone_name) — текущее время в IANA-зоне (ISO 8601).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mcp.server.mcpserver import MCPServer

server = MCPServer(name="time", version="1.0.0")


@server.tool()
def get_time(timezone_name: str = "UTC") -> str:
    """Текущее время в указанном часовом поясе (IANA) в формате ISO 8601.

    Args:
        timezone_name: IANA-имя зоны: Europe/Moscow, Asia/Tokyo, UTC и т.п.

    Returns:
        ISO 8601 время в указанной зоне либо текст ошибки для неизвестной зоны.
    """
    try:
        tz = timezone.utc if timezone_name.upper() == "UTC" else ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return (
            f"Ошибка: неизвестный часовой пояс '{timezone_name}'. "
            "Используйте формат IANA, например Europe/Moscow или Asia/Tokyo."
        )
    return datetime.now(tz).isoformat()


transport_security = None
try:  # HTTP-режим требует разрешённых хостов (образец scheduler_server.py)
    from mcp.server.transport_security import TransportSecuritySettings
    transport_security = TransportSecuritySettings(allowed_hosts=[
        "localhost", "localhost:8000", "127.0.0.1", "127.0.0.1:8000",
        "0.0.0.0", "91.188.212.77", "91.188.212.77:8000",
    ])
except Exception:  # необязательная зависимость HTTP-режима
    transport_security = None


app = server.streamable_http_app(transport_security=transport_security) \
    if transport_security is not None else server.streamable_http_app()

# D7 (Ревизия 5): если задан env MCP_AUTH_TOKEN — требовать Bearer-токен.
from integrations.mcp.auth import auth_middleware
app = auth_middleware(app)


if __name__ == "__main__":

    import sys
    if "--stdio" in sys.argv:
        server.run(transport="stdio")
    else:
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("TIME_PORT", "8000")))
