# -*- coding: utf-8 -*-
"""Юнит-тест D5 (Ревизия 5): таймауты транспорта (`asyncio.wait_for`).

Проверяет детерминированно (без сети): зависшая операция обрывается по
`timeout_seconds` и превращается в `MCPConnectionError("таймаут …")`, а не
вешает event loop. Формат — модульные функции `test_*`.
"""
import asyncio
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


class _HangingSession:
    """Сессия-заглушка: любой вызов висит дольше таймаута."""

    async def list_tools(self):
        await asyncio.sleep(5)
        return None

    async def call_tool(self, name, arguments):
        await asyncio.sleep(5)
        return None


class _FastSession:
    async def list_tools(self):
        class R:
            tools = []
        return R()


def _http_transport(timeout):
    from integrations.mcp.transport import HttpMCPTransport
    return HttpMCPTransport("hang", "http://127.0.0.1:9/mcp", timeout_seconds=timeout)


def test_list_tools_times_out():
    from integrations.mcp.transport import MCPConnectionError
    t = _http_transport(0.05)
    t._session = _HangingSession()
    try:
        asyncio.run(t.list_tools())
        assert False, "ожидался MCPConnectionError по таймауту"
    except MCPConnectionError as exc:
        assert "таймаут" in exc.reason, exc.reason


def test_call_tool_times_out():
    from integrations.mcp.transport import MCPConnectionError
    t = _http_transport(0.05)
    t._session = _HangingSession()
    try:
        asyncio.run(t.call_tool("x", {}))
        assert False, "ожидался MCPConnectionError по таймауту"
    except MCPConnectionError as exc:
        assert "таймаут" in exc.reason, exc.reason


def test_fast_operation_passes():
    t = _http_transport(1.0)
    t._session = _FastSession()
    assert asyncio.run(t.list_tools()) == []