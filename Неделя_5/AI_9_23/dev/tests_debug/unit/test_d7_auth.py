# -*- coding: utf-8 -*-
"""Юнит-тест D7 (Ревизия 5): авторизация транспорта.

Проверяет детерминированно (без сети):
  * `HttpMCPTransport._auth_headers` собирает `Authorization: Bearer` из env;
  * `make_transport` пробрасывает `headers`/`token_env` из конфига;
  * серверный `auth_middleware` → 401 без токена, пропускает с верным токеном,
    выключен при отсутствии env.

Формат — модульные функции `test_*`.
"""
import asyncio
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def test_auth_headers_from_env():
    from integrations.mcp.transport import HttpMCPTransport
    os.environ["TEST_MCP_TOKEN"] = "s3cr3t"
    try:
        tr = HttpMCPTransport("time", "http://x/mcp", token_env="TEST_MCP_TOKEN",
                              headers={"X-Trace": "1"})
        h = tr._auth_headers()
        assert h["Authorization"] == "Bearer s3cr3t", h
        assert h["X-Trace"] == "1"
    finally:
        os.environ.pop("TEST_MCP_TOKEN", None)


def test_auth_headers_no_token_env():
    from integrations.mcp.transport import HttpMCPTransport
    tr = HttpMCPTransport("time", "http://x/mcp")
    assert tr._auth_headers() == {}


def test_make_transport_passes_auth():
    from integrations.mcp.config import MCPServerConfig
    from integrations.mcp.transport import HttpMCPTransport, make_transport
    cfg = MCPServerConfig(server_id="time", transport="http",
                          endpoint="http://x/mcp", token_env="T", headers={"A": "b"})
    tr = make_transport(cfg)
    assert isinstance(tr, HttpMCPTransport)
    assert tr._token_env == "T" and tr._headers == {"A": "b"}


def test_config_parses_auth_fields():
    from integrations.mcp.config import _parse_server
    cfg = _parse_server({"server_id": "s", "transport": "http",
                         "endpoint": "http://x", "token_env": "TOK",
                         "headers": {"X": "y"}})
    assert cfg.token_env == "TOK" and cfg.headers == {"X": "y"}


def _inner_app():
    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})
    return inner


def _run_asgi(app, headers):
    """Прогнать ASGI-app одним HTTP-запросом; вернуть status."""
    scope = {"type": "http", "method": "POST", "path": "/mcp",
             "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]}
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    async def inner(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    asyncio.run(app(scope, receive, send))
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


def test_auth_middleware_blocks_without_token():
    from integrations.mcp.auth import auth_middleware
    os.environ["MCP_AUTH_TOKEN"] = "tok"
    try:
        app = auth_middleware(_inner_app())
        assert _run_asgi(app, {}) == 401
        assert _run_asgi(app, {"Authorization": "Bearer wrong"}) == 401
        assert _run_asgi(app, {"Authorization": "Bearer tok"}) == 200
    finally:
        os.environ.pop("MCP_AUTH_TOKEN", None)


def test_auth_middleware_disabled_without_env():
    from integrations.mcp.auth import auth_middleware
    os.environ.pop("MCP_AUTH_TOKEN", None)
    app = auth_middleware(_inner_app())
    assert _run_asgi(app, {}) == 200
