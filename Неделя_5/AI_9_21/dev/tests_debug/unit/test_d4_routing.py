# -*- coding: utf-8 -*-
"""Юнит-тест D4 (Ревизия 5): ранжирование инструментов под запрос.

Проверяет детерминированно (без сети): RU→EN-эвристика выбирает правильного
кандидата, лишние вызовы не подставляются (при нуле — пустой список), имя важнее
описания. Формат — модульные функции `test_*`.
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
                       input_schema={"type": "object"}, source="mcp",
                       provider="time", original_name="get_time"),
        ToolDescriptor(name="mcp.pipeline.search", description="Получить данные",
                       input_schema={"type": "object"}, source="mcp",
                       provider="pipeline", original_name="search"),
        ToolDescriptor(name="mcp.pipeline.summarize", description="Обработать текст",
                       input_schema={"type": "object"}, source="mcp",
                       provider="pipeline", original_name="summarize"),
        ToolDescriptor(name="mcp.pipeline.saveToFile", description="Сохранить результат",
                       input_schema={"type": "object"}, source="mcp",
                       provider="pipeline", original_name="saveToFile"),
        ToolDescriptor(name="mcp.scheduler.schedule_reminder", description="Напоминание",
                       input_schema={"type": "object"}, source="mcp",
                       provider="scheduler", original_name="schedule_reminder"),
    ]


def test_time_query_returns_get_time():
    from core.tool_routing import rank_tools
    res = rank_tools("который час", _tools())
    assert res and res[0].name == "mcp.time.get_time", res


def test_search_query_returns_search_not_time():
    from core.tool_routing import rank_tools
    res = rank_tools("собери данные", _tools())
    assert res and res[0].name == "mcp.pipeline.search", res


def test_save_and_remind_queries():
    from core.tool_routing import rank_tools
    assert rank_tools("сохрани результат", _tools())[0].name == "mcp.pipeline.saveToFile"
    assert rank_tools("напомни через час", _tools())[0].name \
        == "mcp.scheduler.schedule_reminder"
    # глагол-действие перевешивает существительное: «напомни о сводке» → remind.
    assert rank_tools("напомни о сводке", _tools())[0].name \
        == "mcp.scheduler.schedule_reminder"
    # «обработай … в сводку» → summarize (действие, не get_summary).
    assert rank_tools("обработай текст в сводку", _tools())[0].name \
        == "mcp.pipeline.summarize"


def test_no_match_returns_empty():
    from core.tool_routing import rank_tools
    assert rank_tools("абвгд что-то непонятное", _tools()) == []


def test_reasons_and_top_limit():
    from core.tool_routing import rank_tools
    res = rank_tools("сохрани файл результат", _tools(), top=2)
    assert 1 <= len(res) <= 2
    assert res[0].reasons, "должно быть обоснование"
    assert res[0].score >= res[-1].score


def test_empty_catalog():
    from core.tool_routing import rank_tools
    assert rank_tools("время", []) == []
