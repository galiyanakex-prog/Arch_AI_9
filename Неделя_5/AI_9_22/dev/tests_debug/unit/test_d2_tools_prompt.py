# -*- coding: utf-8 -*-
"""Юнит-тест D2 (Ревизия 5): каталог инструментов доезжает до промта.

Проверяет детерминированно (без сети):
  * блок [tools] присутствует при deliver, содержащем `tools`;
  * блока нет при deliver без `tools`;
  * `render_tool_protocol(tools)` перечисляет квалифицированные имена и
    обязательные аргументы; пустой каталог → базовый протокол.

Формат — модульные функции `test_*` (конвенция dev/tests_debug/unit_runner.py).
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def _tools():
    from core.tools import ToolDescriptor
    return [
        ToolDescriptor(name="mcp.time.get_time", description="Текущее время",
                       input_schema={"type": "object", "properties": {}, "required": []},
                       source="mcp", provider="time", original_name="get_time"),
        ToolDescriptor(name="mcp.pipeline.search", description="Получить данные",
                       input_schema={"type": "object",
                                     "properties": {"query": {"type": "string"}},
                                     "required": ["query"]},
                       source="mcp", provider="pipeline", original_name="search"),
    ]


def test_tools_block_present_when_delivered():
    from core.prompt_builder import PromptBuilder
    from core.agent import PromptContext
    pb = PromptBuilder("ROLE")
    ctx = PromptContext("найди данные", {}, tools=_tools())
    msgs = pb.build(ctx, {"tools"})
    assert any("[tools]" in m["content"] for m in msgs), "блок [tools] должен быть в промте"


def test_tools_block_absent_without_deliver():
    from core.prompt_builder import PromptBuilder
    from core.agent import PromptContext
    pb = PromptBuilder("ROLE")
    ctx = PromptContext("найди данные", {}, tools=_tools())
    msgs = pb.build(ctx, {"profile"})
    assert not any("[tools]" in m["content"] for m in msgs), "без deliver tools блока быть не должно"


def test_render_tool_protocol_lists_names_and_required():
    from core.llm_client import render_tool_protocol, TOOL_PROTOCOL_PROMPT
    proto = render_tool_protocol(_tools())
    assert "mcp.time.get_time" in proto
    assert "mcp.pipeline.search" in proto
    assert "обязательные аргументы: query" in proto
    assert render_tool_protocol([]) == TOOL_PROTOCOL_PROMPT
