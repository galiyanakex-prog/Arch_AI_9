"""integrations/mcp/gateway.py — шлюз MCP (День 16).

Адаптер внешних возможностей, НЕ контролёр: не знает о TaskStage/профилях/
памяти (канон Рекомендации_MCP_d16.txt). Async внутри, синхронный фасад
(`MCPGatewaySync`) наружу — REPL остаётся синхронным.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from enum import Enum

from core.tools import ToolDescriptor, ToolExecutionResult, ToolExecutionState
from integrations.mcp.client import MCPClient
from integrations.mcp.config import MCPServerConfig
from integrations.mcp.transport import (
    MCPConnectionError, MCPTransport, make_transport,
)


class MCPConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    READY = "ready"
    DEGRADED = "degraded"    # часть серверов недоступна
    FAILED = "failed"


class MCPGateway:
    """Шлюз: состояние подключения по серверам + discovery с фильтром прав."""

    def __init__(self, servers: list[MCPServerConfig],
                 transports: dict[str, MCPTransport] | None = None) -> None:
        self._servers = list(servers)
        self._transports = dict(transports or {})
        self._clients: dict[str, MCPClient] = {}
        self._states: dict[str, MCPConnectionState] = {
            s.server_id: MCPConnectionState.DISCONNECTED for s in self._servers
        }

    # -- служебное -----------------------------------------------------------

    def _make_client(self, server: MCPServerConfig) -> MCPClient:
        transport = self._transports.get(server.server_id)
        if transport is None:
            transport = make_transport(server)
        return MCPClient(server, transport=transport)

    def overall_state(self) -> MCPConnectionState:
        states = [s for s in self._states.values() if s is not MCPConnectionState.DISCONNECTED]
        if not states:
            return MCPConnectionState.DISCONNECTED
        if all(s is MCPConnectionState.READY for s in states):
            return MCPConnectionState.READY
        if any(s is MCPConnectionState.READY for s in states):
            return MCPConnectionState.DEGRADED
        return MCPConnectionState.FAILED

    # -- жизненный цикл -------------------------------------------------------

    async def start(self, only_server: str | None = None) -> None:
        """Подключение к включённым серверам (сбой одного — не падение).

        `only_server` (D6): подключить ТОЛЬКО указанный сервер (остальные не
        трогаются) — `/mcp connect <id>` не должен поднимать весь каталог.
        Идемпотентно: уже READY-серверы не пересоздаются (повторный start не
        должен бросать старый HTTP/stdio-генератор в GC — иначе «cancel scope
        in a different task»).
        """
        for server in self._servers:
            if not server.enabled:
                continue
            if only_server is not None and server.server_id != only_server:
                continue
            if (self._states.get(server.server_id) is MCPConnectionState.READY
                    and server.server_id in self._clients):
                continue
            self._states[server.server_id] = MCPConnectionState.CONNECTING
            client = self._make_client(server)
            try:
                await client.initialize()
                self._clients[server.server_id] = client
                self._states[server.server_id] = MCPConnectionState.READY
                print(f"[MCP] «{server.server_id}»: подключён (READY)")
            except MCPConnectionError as exc:
                self._states[server.server_id] = MCPConnectionState.FAILED
                print(f"[MCP] «{server.server_id}»: FAILED — {exc.reason}")

    async def stop(self) -> None:
        """Чистое закрытие всех соединений → DISCONNECTED (у всех серверов)."""
        for server_id, client in list(self._clients.items()):
            try:
                await client.close()
            except Exception:
                pass
            print(f"[MCP] «{server_id}»: отключён")
        self._clients.clear()
        # FAILED-серверы не имеют клиента, но состояние тоже сбрасываем:
        # канон (arch_den_16.md §2.4): stop() → DISCONNECTED.
        for server_id in self._states:
            self._states[server_id] = MCPConnectionState.DISCONNECTED

    def status(self) -> dict:
        """Состояние по серверам (для /mcp status)."""
        return {
            "overall": self.overall_state().value,
            "servers": {
                sid: state.value for sid, state in self._states.items()
            },
        }

    # -- discovery -------------------------------------------------------------

    async def discover(self) -> list[ToolDescriptor]:
        """list_tools у серверов в READY → фильтр прав → ToolDescriptor[]."""
        result: list[ToolDescriptor] = []
        for server in self._servers:
            if not server.enabled:
                continue
            client = self._clients.get(server.server_id)
            if client is None:  # FAILED/DISCONNECTED — тулов нет (каталог честен)
                continue
            try:
                raw_tools = await client.list_tools()
            except MCPConnectionError as exc:
                self._states[server.server_id] = MCPConnectionState.FAILED
                print(f"[MCP] «{server.server_id}»: discovery не удался — {exc.reason}")
                continue
            for item in raw_tools:
                original = item["name"]
                # изоляция прав через тулинг (канон Суть_N4 §3.3)
                if original in server.denied_tools:
                    continue
                if server.allowed_tools and original not in server.allowed_tools:
                    continue
                result.append(ToolDescriptor(
                    name=f"mcp.{server.server_id}.{original}",
                    description=item.get("description", ""),
                    input_schema=item.get("inputSchema") or {"type": "object"},
                    source="mcp",
                    provider=server.server_id,
                    original_name=original,
                ))
        return result

    async def call_tool(self, provider: str, tool_name: str, arguments: dict,
                        execution_id: str = "") -> ToolExecutionResult:
        """Вызов инструмента на сервере `provider` (оригинальное имя тула).

        Сервер не READY → failed-результат (не исключение наружу): шлюз —
        адаптер, ошибку доносит как данные. `TaskStage` не трогается.
        """
        client = self._clients.get(provider)
        qualified = f"mcp.{provider}.{tool_name}"
        if client is None:
            return ToolExecutionResult(
                execution_id=execution_id, tool=qualified,
                status=ToolExecutionState.FAILED.value,
                summary=f"Сервер «{provider}» не в состоянии READY",
                is_error=True,
            )
        try:
            result = await client.call_tool(tool_name, arguments)
        except MCPConnectionError as exc:
            self._states[provider] = MCPConnectionState.FAILED
            return ToolExecutionResult(
                execution_id=execution_id, tool=qualified,
                status=ToolExecutionState.FAILED.value,
                summary=f"Ошибка вызова: {exc.reason}",
                is_error=True,
            )
        is_error = bool(result.get("isError"))
        text = result.get("text", "")
        return ToolExecutionResult(
            execution_id=execution_id, tool=qualified,
            status=(ToolExecutionState.FAILED.value if is_error
                    else ToolExecutionState.SUCCEEDED.value),
            summary=text[:500],
            text=text,
            raw=result.get("raw"),
            is_error=is_error,
        )


class MCPGatewaySync:
    """Тонкий синхронный фасад над async-шлюзом (REPL / --mcp-probe).

    Один постоянный фоновый event loop на всё время жизни фасада. Все операции
    исполняются **в одной долгоживущей задаче** (`_worker`): HTTP/stdio-контексты
    `mcp` SDK держат anyio cancel scope, который обязан войти и выйти в одной и
    той же задаче (иначе «cancel scope in a different task» на close).
    """

    def __init__(self, servers: list[MCPServerConfig],
                 transports: dict[str, MCPTransport] | None = None) -> None:
        self._gateway = MCPGateway(servers, transports)
        self._loop = asyncio.new_event_loop()
        self._queue: asyncio.Queue | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._thread_main, name="mcp-gateway-loop", daemon=True
        )
        self._thread.start()
        self._ready.wait()

    def _thread_main(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._queue = asyncio.Queue()
        self._loop.create_task(self._worker())
        self._loop.call_soon(self._ready.set)
        self._loop.run_forever()

    async def _worker(self) -> None:
        while True:
            coro, future = await self._queue.get()
            if coro is None:
                break
            try:
                result = await coro
            except BaseException as exc:  # пробрасываем в вызывающую нить
                if not future.done():
                    future.set_exception(exc)
            else:
                if not future.done():
                    future.set_result(result)

    def _run(self, coro):
        future = concurrent.futures.Future()
        self._loop.call_soon_threadsafe(self._queue.put_nowait, (coro, future))
        return future.result()

    def start(self, only_server: str | None = None) -> None:
        self._run(self._gateway.start(only_server))

    def stop(self) -> None:
        self._run(self._gateway.stop())

    def status(self) -> dict:
        return self._gateway.status()

    def discover(self) -> list[ToolDescriptor]:
        return self._run(self._gateway.discover())

    def call_tool(self, provider: str, tool_name: str, arguments: dict,
                  execution_id: str = "") -> ToolExecutionResult:
        return self._run(
            self._gateway.call_tool(provider, tool_name, arguments, execution_id))

    @property
    def gateway(self) -> MCPGateway:
        return self._gateway
