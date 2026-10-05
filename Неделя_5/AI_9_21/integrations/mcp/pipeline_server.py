# -*- coding: utf-8 -*-
"""integrations/mcp/pipeline_server.py — MCP-сервер пайплайна (День 18, задание 2).

Три MCP-инструмента образуют цепочку «получить → обработать → сохранить»:
  search(query)        — получает данные (детерминированный набор фактов);
  summarize(text)      — обрабатывает (сжимает) полученный текст;
  saveToFile(name, content) — сохраняет результат в область пайплайна (через `Store`).

Автовыполнение цепочки и передача данных между шагами — на стороне клиента
(`core/tool_pipeline.py`): результат одного шага становится аргументом следующего.

Образец настройки — `doc/mcp/mcp-time-server/time_server_http.py`.

Запуск:
    python -m integrations.mcp.pipeline_server           # HTTP :8020
    python -m integrations.mcp.pipeline_server --stdio   # stdio (для тестов)

Переменные окружения: `PIPELINE_MEMORY_DIR`, `PIPELINE_USER_ID` (по умолчанию
`pipeline`), `PIPELINE_PORT` (по умолчанию 8020).
"""
from __future__ import annotations

import json
import os

from mcp.server.mcpserver import MCPServer

from storage.store import Store

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MEMORY_DIR = os.getenv("PIPELINE_MEMORY_DIR", os.path.join(_BASE_DIR, "users"))
_DEFAULT_USER = os.getenv("PIPELINE_USER_ID", "pipeline")

server = MCPServer("Pipeline Server")

# Детерминированный «поисковый» корпус (без сети): источник данных для пайплайна.
_KNOWLEDGE = {
    "python": [
        "Python — интерпретируемый язык с динамической типизацией.",
        "Python поддерживает функциональный и объектно-ориентированный стиль.",
        "Экосистема Python включает пакеты PyPI.",
    ],
    "mcp": [
        "MCP — протокол Model Context Protocol для инструментов агентов.",
        "MCP-сервер предоставляет инструменты (tools) со схемами.",
        "MCP поддерживает stdio и Streamable HTTP транспорты.",
    ],
    "default": [
        "Данные найдены: краткая справка по запросу.",
        "Источник данных — детерминированный корпус сервера пайплайна.",
    ],
}


def configure(memory_dir: str | None = None, user_id: str | None = None) -> None:
    """Переопределить хранилище/пользователя (для тестов и DI)."""
    global _MEMORY_DIR, _DEFAULT_USER
    if memory_dir:
        _MEMORY_DIR = memory_dir
    if user_id:
        _DEFAULT_USER = user_id


def _store() -> Store:
    return Store(_MEMORY_DIR)


@server.tool()
def search(query: str) -> str:
    """Получить данные по запросу (шаг 1 пайплайна: получить данные).

    Args:
        query: Поисковый запрос (например, python или mcp).

    Returns:
        Текстовый блок найденных фактов (для передачи в summarize).
    """
    key = (query or "").strip().lower()
    facts = _KNOWLEDGE.get(key, _KNOWLEDGE["default"])
    return "\n".join(facts)


@server.tool()
def summarize(text: str) -> str:
    """Обработать текст (шаг 2 пайплайна: обработать данные).

    Args:
        text: Текст, полученный на предыдущем шаге (результат search).

    Returns:
        Сжатая сводка: число предложений и первые ключевые фразы.
    """
    sentences = [s.strip() for s in (text or "").replace("\n", " ").split(".") if s.strip()]
    head = "; ".join(sentences[:2]) if sentences else (text or "").strip()
    return f"Сводка ({len(sentences)} предложений): {head}"


@server.tool()
def saveToFile(name: str, content: str) -> str:
    """Сохранить результат (шаг 3 пайплайна: сохранить результат).

    Args:
        name: Имя файла результата.
        content: Содержимое (результат summarize).

    Returns:
        JSON с именем файла и числом сохранённых символов.
    """
    store = _store()
    path = os.path.join(store.user_dir(_DEFAULT_USER), "pipeline", f"{name}.txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content or "")
    return json.dumps({"saved": f"{name}.txt", "chars": len(content or "")},
                      ensure_ascii=False)


@server.tool()
def readFile(name: str) -> str:
    """Прочитать ранее сохранённый файл пайплайна (проверка сохранения).

    Args:
        name: Имя файла результата.

    Returns:
        Содержимое файла либо пояснение, что файла нет.
    """
    store = _store()
    path = os.path.join(store.user_dir(_DEFAULT_USER), "pipeline", f"{name}.txt")
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return f"Файл «{name}.txt» не найден."


transport_security = None
try:  # HTTP-режим требует разрешённых хостов (образец time_server_http.py)
    from mcp.server.transport_security import TransportSecuritySettings
    transport_security = TransportSecuritySettings(allowed_hosts=[
        "localhost", "localhost:8020", "127.0.0.1", "127.0.0.1:8020",
        "0.0.0.0", "91.188.212.77", "91.188.212.77:8020",
    ])
except Exception:
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
        uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PIPELINE_PORT", "8020")))
