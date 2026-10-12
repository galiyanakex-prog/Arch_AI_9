"""integrations/mcp/transport.py — транспорты MCP (День 16).

ABC + stdio-транспорт (обёртка над `mcp` SDK) + HTTP-транспорт (Streamable HTTP)
+ детерминированная заглушка `FakeMCPTransport` для тестов без сети и подпроцесса.

SDK 2.2.0: stdio — `mcp.client.stdio.stdio_client`; HTTP — 
`mcp.client.streamable_http.streamable_http_client`. Атрибут схемы тула у SDK —
`input_schema` (snake_case); извлечение схемы унифицировано хелпером `_tool_schema`.
"""

from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod


class MCPConnectionError(Exception):
    """Сбой соединения/вызова MCP: не None, не молчание."""

    def __init__(self, server_id: str, reason: str):
        self.server_id = server_id
        self.reason = reason
        super().__init__(f"MCP «{server_id}»: {reason}")


def _tool_schema(tool) -> dict:
    """Схема тула: SDK 2.2.0 отдаёт `input_schema`; dict/тесты — `inputSchema`."""
    schema = getattr(tool, "input_schema", None)
    if schema is None:
        schema = getattr(tool, "inputSchema", None)
    if schema is None and isinstance(tool, dict):
        schema = tool.get("input_schema") or tool.get("inputSchema")
    return schema or {"type": "object"}


def _normalize_tool(tool) -> dict | None:
    """Сырое описание тула SDK/теста → {name, description, inputSchema}."""
    name = getattr(tool, "name", None)
    if name is None and isinstance(tool, dict):
        name = tool.get("name")
    if not isinstance(name, str):
        return None
    if isinstance(tool, dict):
        desc = tool.get("description", "")
    else:
        desc = getattr(tool, "description", "") or ""
    schema = _tool_schema(tool)
    # Оба ключа — совместимость (SDK 2.2.0 snake_case; исторический camelCase).
    return {"name": name, "description": desc or "",
            "inputSchema": schema, "input_schema": schema}


def _content_text(content) -> str:
    """Текстовые части CallToolResult → одна строка (не-текстовые — str())."""
    parts: list[str] = []
    for item in content or []:
        text = getattr(item, "text", None)
        if text is None and isinstance(item, dict):
            text = item.get("text")
        parts.append(text if isinstance(text, str) else str(item))
    return "\n".join(parts)


def _normalize_call_result(result) -> dict:
    """CallToolResult → {isError, text, raw}."""
    is_error = getattr(result, "isError", None)
    if is_error is None and isinstance(result, dict):
        is_error = result.get("isError")
    content = getattr(result, "content", None)
    if content is None and isinstance(result, dict):
        content = result.get("content")
    return {"isError": bool(is_error), "text": _content_text(content), "raw": result}


class MCPTransport(ABC):
    """Транспорт одного MCP-сервера (async — нативно для SDK)."""

    @abstractmethod
    async def initialize(self) -> dict:
        """Handshake: protocol version + capabilities → dict состояния."""

    @abstractmethod
    async def list_tools(self) -> list[dict]:
        """Сырые описания тулов: [{name, description, inputSchema}, ...]."""

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Вызов инструмента → {isError, text, raw}."""
        raise NotImplementedError("call_tool не реализован транспортом")

    @abstractmethod
    async def close(self) -> None:
        """Чистое закрытие соединения."""


class FakeMCPTransport(MCPTransport):
    """Детерминированная заглушка: фиксированный список тулов + программируемые
    отказы/таймаут/смена каталога + программируемые результаты вызова."""

    def __init__(
        self,
        tools: list[dict] | None = None,
        *,
        fail_initialize: bool = False,
        fail_list_tools: bool = False,
        fail_call: bool = False,
        error_call: bool = False,
        timeout: bool = False,
        tool_results: dict | None = None,
        server_id: str = "fake",
    ) -> None:
        self._tools: list[dict] = list(tools or [])
        self._fail_initialize = fail_initialize
        self._fail_list_tools = fail_list_tools
        self._fail_call = fail_call
        self._error_call = error_call
        self._timeout = timeout
        self._tool_results: dict = dict(tool_results or {})
        self._server_id = server_id
        self._initialized = False

    def set_tools(self, tools: list[dict]) -> None:
        """Смена каталога (для теста обновлений)."""
        self._tools = list(tools)

    def set_tool_result(self, name: str, value) -> None:
        """Задать результат вызова тула (для тестов tools/call)."""
        self._tool_results[name] = value

    async def initialize(self) -> dict:
        if self._fail_initialize:
            raise MCPConnectionError(self._server_id, "handshake не удался")
        if self._timeout:
            raise MCPConnectionError(self._server_id, "таймаут handshake")
        self._initialized = True
        return {"protocolVersion": "2025-06-18", "serverInfo": {"name": self._server_id}}

    async def list_tools(self) -> list[dict]:
        if not self._initialized:
            raise MCPConnectionError(self._server_id, "initialize не выполнен")
        if self._fail_list_tools:
            raise MCPConnectionError(self._server_id, "list_tools не удался")
        if self._timeout:
            raise MCPConnectionError(self._server_id, "таймаут list_tools")
        return [dict(t) for t in self._tools]

    async def call_tool(self, name: str, arguments: dict) -> dict:
        if not self._initialized:
            raise MCPConnectionError(self._server_id, "initialize не выполнен")
        if self._fail_call:
            raise MCPConnectionError(self._server_id, f"call_tool «{name}» не удался")
        if name not in self._tool_results:
            raise MCPConnectionError(self._server_id, f"call_tool «{name}»: нет результата")
        value = self._tool_results[name]
        if isinstance(value, dict) and ("text" in value or "isError" in value):
            return {"isError": bool(value.get("isError", self._error_call)),
                    "text": str(value.get("text", "")), "raw": value}
        return {"isError": self._error_call, "text": str(value), "raw": value}

    async def close(self) -> None:
        self._initialized = False


class _SessionTransport(MCPTransport):
    """Общая часть stdio/HTTP: сессия `mcp` SDK + нормализация."""

    def __init__(self, server_id: str, timeout_seconds: float = 30.0) -> None:
        self._server_id = server_id
        self._timeout = timeout_seconds
        self._session = None
        self._streams = None

    async def _with_timeout(self, coro, what: str):
        """D5 (Ревизия 5): ограничить операцию `timeout_seconds`.

        Зависший сервер не должен вешать постоянный event loop `MCPGatewaySync`:
        по истечении лимита → `MCPConnectionError("таймаут …")`, состояние FAILED.
        """
        try:
            return await asyncio.wait_for(coro, timeout=self._timeout)
        except asyncio.TimeoutError as exc:
            raise MCPConnectionError(
                self._server_id, f"таймаут {what} ({self._timeout:g} с)") from exc

    async def list_tools(self) -> list[dict]:
        if self._session is None:
            raise MCPConnectionError(self._server_id, "initialize не выполнен")
        try:
            result = await self._with_timeout(self._session.list_tools(), "list_tools")
        except MCPConnectionError:
            raise
        except Exception as exc:
            raise MCPConnectionError(self._server_id, f"list_tools не удался: {exc}") from exc
        tools = getattr(result, "tools", None)
        if tools is None and isinstance(result, dict):
            tools = result.get("tools")
        raw: list[dict] = []
        for t in tools or []:
            normalized = _normalize_tool(t)
            if normalized is not None:
                raw.append(normalized)
        return raw

    async def call_tool(self, name: str, arguments: dict) -> dict:
        if self._session is None:
            raise MCPConnectionError(self._server_id, "initialize не выполнен")
        try:
            result = await self._with_timeout(
                self._session.call_tool(name, arguments or {}), f"call_tool «{name}»")
        except MCPConnectionError:
            raise
        except Exception as exc:
            raise MCPConnectionError(self._server_id, f"call_tool «{name}» не удался: {exc}") from exc
        return _normalize_call_result(result)

    async def close(self) -> None:
        for obj in (self._session, self._streams):
            if obj is not None:
                try:
                    await obj.__aexit__(None, None, None)
                except BaseException:
                    pass
        self._session = None
        self._streams = None

    @staticmethod
    def _init_info(init) -> dict:
        return {
            "protocolVersion": getattr(init, "protocolVersion", None)
            or (init.get("protocolVersion") if isinstance(init, dict) else None),
            "serverInfo": getattr(init, "serverInfo", None)
            or (init.get("serverInfo") if isinstance(init, dict) else None),
        }


class StdioMCPTransport(_SessionTransport):
    """stdio-транспорт: подпроцесс по `command` из конфига, обёртка над `mcp` SDK.

    Фактический API SDK (mcp 2.2.0) — `mcp.client.stdio.stdio_client` +
    `mcp.ClientSession`; ошибки SDK → MCPConnectionError.
    """

    def __init__(self, server_id: str, command: tuple[str, ...],
                 timeout_seconds: float = 30.0) -> None:
        super().__init__(server_id, timeout_seconds)
        self._command = command

    async def initialize(self) -> dict:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except Exception as exc:  # SDK недоступен
            raise MCPConnectionError(self._server_id, f"SDK недоступен: {exc}") from exc

        params = StdioServerParameters(
            command=self._command[0], args=list(self._command[1:])
        )
        try:
            self._streams = stdio_client(params)
            read, write = await self._with_timeout(
                self._streams.__aenter__(), "stdio-подключение")
            self._session = ClientSession(read, write)
            await self._with_timeout(self._session.__aenter__(), "stdio-сессия")
            init = await self._with_timeout(self._session.initialize(), "initialize")
        except (Exception, asyncio.CancelledError) as exc:
            await self.close()
            raise MCPConnectionError(self._server_id, f"handshake не удался: {exc}") from exc
        return self._init_info(init)


class HttpMCPTransport(_SessionTransport):
    """HTTP-транспорт (Streamable HTTP), обёртка над `mcp` SDK 2.2.0.

    Фактический API SDK — `mcp.client.streamable_http.streamable_http_client`
    (НЕ `streamablehttp_client` из v1) + `mcp.ClientSession`; ошибки → MCPConnectionError.

    D7 (Ревизия 5): при наличии `headers`/`token_env` заголовки авторизации
    передаются через `httpx2.AsyncClient(headers=...)` (SDK 2.2.0 принимает
    готовый http_client). Секрет берётся из env (`token_env`), не из кода.
    """

    def __init__(self, server_id: str, endpoint: str,
                 timeout_seconds: float = 30.0,
                 headers: dict[str, str] | None = None,
                 token_env: str | None = None) -> None:
        super().__init__(server_id, timeout_seconds)
        self._endpoint = endpoint
        self._headers = dict(headers or {})
        self._token_env = token_env
        self._http_client = None

    def _auth_headers(self) -> dict[str, str]:
        """Статические заголовки + Authorization: Bearer из env (если задан)."""
        headers = dict(self._headers)
        if self._token_env:
            token = os.getenv(self._token_env)
            if token:
                headers.setdefault("Authorization", f"Bearer {token}")
        return headers

    async def initialize(self) -> dict:
        try:
            import httpx2
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
        except Exception as exc:  # SDK недоступен
            raise MCPConnectionError(self._server_id, f"SDK недоступен: {exc}") from exc

        try:
            headers = self._auth_headers()
            if headers:
                self._http_client = httpx2.AsyncClient(headers=headers)
            self._streams = streamable_http_client(
                self._endpoint, http_client=self._http_client)
            streams = await self._with_timeout(
                self._streams.__aenter__(), "HTTP-подключение")
            read, write = streams[0], streams[1]
            self._session = ClientSession(read, write)
            await self._with_timeout(self._session.__aenter__(), "HTTP-сессия")
            init = await self._with_timeout(self._session.initialize(), "initialize")
        except (Exception, asyncio.CancelledError) as exc:
            await self.close()
            raise MCPConnectionError(self._server_id, f"handshake не удался: {exc}") from exc
        return self._init_info(init)

    async def close(self) -> None:
        await super().close()
        if self._http_client is not None:
            try:
                await self._http_client.aclose()
            except BaseException:
                pass
            self._http_client = None


def make_transport(server) -> MCPTransport:
    """Фабрика транспорта по конфигу сервера (выбор по полю `transport`).

    `http` + endpoint → HttpMCPTransport; иначе (`stdio`) → StdioMCPTransport.
    """
    transport = getattr(server, "transport", "stdio")
    if transport == "http":
        endpoint = getattr(server, "endpoint", None)
        if not endpoint:
            raise MCPConnectionError(server.server_id, "transport=http без endpoint")
        return HttpMCPTransport(
            server.server_id, endpoint, server.timeout_seconds,
            headers=getattr(server, "headers", None),
            token_env=getattr(server, "token_env", None))
    command = getattr(server, "command", None) or (
        "python", "-m", "integrations.mcp.demo_server")
    return StdioMCPTransport(server.server_id, tuple(command), server.timeout_seconds)