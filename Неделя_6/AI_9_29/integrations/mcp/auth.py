"""integrations/mcp/auth.py — серверная проверка токена (D7, Ревизия 5).

ASGI-middleware: если задан env `MCP_AUTH_TOKEN`, все запросы обязаны нести
`Authorization: Bearer <token>`; иначе — 401. Если переменная НЕ задана, проверка
выключена (серверы публичные — текущее поведение сохраняется).

Секрет живёт только в env (не в коде/конфиге). Клиентская сторона — D7 в
`integrations/mcp/transport.py` (`token_env` → `Authorization`).
"""

from __future__ import annotations

import os


def auth_middleware(app, token_env: str = "MCP_AUTH_TOKEN"):
    """Обернуть ASGI-app проверкой Bearer-токена из env (если задан)."""
    expected = os.getenv(token_env)

    async def wrapped(scope, receive, send):
        if expected and scope.get("type") == "http":
            headers = dict(scope.get("headers") or [])
            raw = headers.get(b"authorization", b"").decode("latin-1")
            if raw != f"Bearer {expected}":
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"text/plain; charset=utf-8")]})
                await send({"type": "http.response.body",
                            "body": b"401 Unauthorized: \xd0\xbd\xd0\xb5\xd0\xb2\xd0\xb5\xd1\x80\xd0\xbd\xd1\x8b\xd0\xb9 \xd1\x82\xd0\xbe\xd0\xba\xd0\xb5\xd0\xbd"})
                return
        await app(scope, receive, send)

    return wrapped
