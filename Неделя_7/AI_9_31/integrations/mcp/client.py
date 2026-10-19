"""integrations/mcp/client.py — MCP-клиент (День 16).

Единственное место импорта `mcp` SDK (вместе с demo_server.py): модель MCP не
протекает в core. Любой сбой → MCPConnectionError (не None, не молчание).
"""

from __future__ import annotations

from integrations.mcp.config import MCPServerConfig
from integrations.mcp.transport import MCPConnectionError, MCPTransport


class MCPClient:
    """Клиент одного MCP-сервера: handshake + discovery.

    Транспорт инжектится (для тестов — FakeMCPTransport; по умолчанию —
    StdioMCPTransport по command из конфига).
    """

    def __init__(self, config: MCPServerConfig, transport: MCPTransport | None = None):
        self.config = config
        self.server_id = config.server_id
        if transport is None:
            from integrations.mcp.transport import make_transport
            transport = make_transport(config)
        self._transport = transport
        self.init_info: dict = {}

    async def initialize(self) -> dict:
        """Handshake: protocol version + capabilities → готовность."""
        try:
            self.init_info = await self._transport.initialize()
        except MCPConnectionError:
            raise
        except Exception as exc:
            raise MCPConnectionError(self.server_id, f"initialize: {exc}") from exc
        return self.init_info

    async def list_tools(self) -> list[dict]:
        """Сырые описания тулов → нормализация {name, description, inputSchema}."""
        try:
            raw = await self._transport.list_tools()
        except MCPConnectionError:
            raise
        except Exception as exc:
            raise MCPConnectionError(self.server_id, f"list_tools: {exc}") from exc
        normalized: list[dict] = []
        for item in raw:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue  # битое описание пропускаем (не падаем)
            normalized.append({
                "name": item["name"],
                "description": item.get("description") or "",
                "inputSchema": item.get("inputSchema") or {"type": "object"},
            })
        return normalized

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Вызов инструмента → нормализованный {isError, text, raw}."""
        try:
            result = await self._transport.call_tool(name, arguments or {})
        except MCPConnectionError:
            raise
        except Exception as exc:
            raise MCPConnectionError(self.server_id, f"call_tool «{name}»: {exc}") from exc
        return result

    async def close(self) -> None:
        await self._transport.close()
