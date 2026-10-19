"""integrations/mcp/demo_server.py — минимальный локальный MCP-сервер (День 16).

Локальный вариант из задания: «поднимите MCP-сервер, если используете локальный
вариант». stdio-транспорт, 3 тула (канон погодного примера лекции):
- get_time      — текущее время (без аргументов);
- echo          — повтор текста (text: required);
- weather_stub  — погода-заглушка (location: required, units: Celsius|Kelvin).

Запуск: python -m integrations.mcp.demo_server

Примечание: mcp 2.2.0 — FastMCP переименован в MCPServer
(mcp.server.mcpserver); API v1 (mcp<2) не используется.
"""

from __future__ import annotations

from datetime import datetime

from mcp.server.mcpserver import MCPServer

server = MCPServer(name="demo", version="1.0.0")


@server.tool()
def get_time() -> str:
    """Возвращает текущее время сервера в формате ГГГГ-ММ-ДД ЧЧ:ММ:СС."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@server.tool()
def echo(text: str) -> str:
    """Возвращает переданный текст без изменений (проверка связи)."""
    return text


@server.tool()
def weather_stub(location: str, units: str = "Celsius") -> str:
    """Возвращает заглушку прогноза погоды для location (units: Celsius|Kelvin)."""
    if units not in ("Celsius", "Kelvin"):
        return f"Ошибка: units должен быть Celsius или Kelvin (получено: {units})"
    return f"Погода в {location}: +21 {units}, ясно (заглушка)"


if __name__ == "__main__":
    server.run(transport="stdio")