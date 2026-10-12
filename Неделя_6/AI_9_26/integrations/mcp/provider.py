"""integrations/mcp/provider.py — провайдер MCP-тулов (День 16).

Тонкий адаптер над MCPGateway: нормализация уже в gateway; провайдер только
предъявляет тулы реестру через контракт ToolProvider (синхронный — реестр
синхронный; async шлюза скрыт за asyncio.run).
"""

from __future__ import annotations

import asyncio

from core.tools import ToolDescriptor, ToolProvider
from integrations.mcp.gateway import MCPGateway, MCPGatewaySync


class MCPToolProvider(ToolProvider):
    """Источник инструментов «mcp» поверх шлюза."""

    def __init__(self, gateway: MCPGateway | MCPGatewaySync) -> None:
        self._gateway = gateway

    def provider_id(self) -> str:
        return "mcp"

    def discover(self) -> list[ToolDescriptor]:
        if isinstance(self._gateway, MCPGatewaySync):
            return self._gateway.discover()
        return asyncio.run(self._gateway.discover())
