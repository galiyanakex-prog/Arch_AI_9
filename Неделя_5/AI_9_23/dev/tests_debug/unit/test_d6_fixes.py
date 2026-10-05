# -*- coding: utf-8 -*-
"""Юнит-тест D6 (Ревизия 5): пакет мелких исправлений.

Проверяет детерминированно (без сети):
  * `/mcp connect <id>` поднимает ТОЛЬКО целевой сервер (gateway.start(only_server));
  * `ToolExecutionResult.text` — полный, `summary` — усечённый; пайплайн несёт
    полный текст между шагами;
  * терминальные стадии (done/failed/paused) — только read-only;
  * assistant-сообщение в tool-use цикле — с валидным `tool_calls`.

Формат — модульные функции `test_*`.
"""
import asyncio
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def test_connect_only_target_server():
    from integrations.mcp.config import MCPServerConfig
    from integrations.mcp.gateway import MCPGateway
    from integrations.mcp.transport import FakeMCPTransport

    tools = [{"name": "get_time", "description": "t",
              "inputSchema": {"type": "object", "properties": {}, "required": []}}]
    servers = [
        MCPServerConfig(server_id="time", transport="stdio", command="python", enabled=True),
        MCPServerConfig(server_id="scheduler", transport="stdio", command="python", enabled=True),
    ]
    transports = {
        "time": FakeMCPTransport(tools, server_id="time"),
        "scheduler": FakeMCPTransport(tools, server_id="scheduler"),
    }
    gw = MCPGateway(servers, transports)
    asyncio.run(gw.start(only_server="time"))
    st = gw.status()["servers"]
    assert st["time"] == "ready", st
    assert st["scheduler"] == "disconnected", st


def test_text_full_summary_truncated():
    from core.tools import ToolExecutionResult
    long = "x" * 1200
    r = ToolExecutionResult(execution_id="1", tool="mcp.pipeline.search",
                            status="succeeded", summary=long[:500], text=long)
    assert len(r.summary) == 500
    assert len(r.text) == 1200


def test_pipeline_carries_full_text():
    from core.tool_pipeline import Pipeline, PipelineStep, run_pipeline
    from core.tools import ToolExecutionResult, ToolExecutionState

    class _Exec:
        def __init__(self):
            self.seen = []

        def execute(self, request, **kw):
            self.seen.append(dict(request.arguments))
            full = "F" * 900
            return ToolExecutionResult(execution_id="e", tool=request.name,
                                       status=ToolExecutionState.SUCCEEDED.value,
                                       summary=full[:500], text=full)

    ex = _Exec()
    pipe = Pipeline("p", [
        PipelineStep("mcp.pipeline.search", {"query": "q"}),
        PipelineStep("mcp.pipeline.summarize", input_key="text"),
    ])
    run = run_pipeline(pipe, ex, user_id="u", task="t")
    assert run.ok
    # Второй шаг получил ПОЛНЫЙ текст (900), а не усечённый (500).
    assert len(ex.seen[1]["text"]) == 900, len(ex.seen[1]["text"])
    assert len(run.output) == 900


def test_terminal_stage_read_only_only():
    from core.tool_policy import ToolPolicy
    from core.tools import ToolDescriptor
    pol = ToolPolicy()
    ro = ToolDescriptor(name="mcp.time.get_time", description="t",
                        input_schema={"type": "object"}, source="mcp",
                        provider="time", original_name="get_time")
    mut = ToolDescriptor(name="mcp.pipeline.saveToFile", description="s",
                         input_schema={"type": "object"}, source="mcp",
                         provider="pipeline", original_name="saveToFile")
    from core.tools import ToolCallRequest
    assert pol.check(ro, ToolCallRequest("mcp.time.get_time", {}),
                     task_stage="done").allowed
    d = pol.check(mut, ToolCallRequest("mcp.pipeline.saveToFile", {"name": "x", "content": "y"}),
                  task_stage="done")
    assert not d.allowed and "терминальн" in d.reason, d


def test_assistant_message_has_valid_tool_calls():
    from core.agent import Agent
    from core.llm_client import LLMClient, LLMReply
    from core.tools import ToolExecutionResult, ToolExecutionState

    captured = {}

    class _Client(LLMClient):
        def __init__(self):
            self._n = 0

        def complete(self, messages, **params):
            return "final"

        def complete_with_tools(self, messages, tools=None, **params):
            self._n += 1
            if self._n == 1:
                return LLMReply(tool_calls=[{"id": "c1", "name": "mcp.demo.echo",
                                             "arguments": {"text": "hi"}}])
            captured["messages"] = list(messages)
            return LLMReply(content="done")

    class _Exec:
        def execute(self, request, **kw):
            return ToolExecutionResult(execution_id="e", tool=request.name,
                                       status=ToolExecutionState.SUCCEEDED.value,
                                       summary="hi", text="hi")

    class _Reg:
        def snapshot(self):
            class S:
                tools = [1]
            return S()

    agent = Agent.__new__(Agent)
    agent.llm = _Client()
    agent.max_tool_iterations = 3
    agent.tool_executor = _Exec()
    agent.tool_registry = _Reg()
    agent.user_id = ""
    agent.task = "t"
    agent.task_state = None
    agent.constraints = None
    agent.deliver = {"tools"}
    agent.log = lambda *a, **k: None
    agent._record_external_action = lambda r: None

    class _Ctx:
        tools = [type("T", (), {"name": "mcp.demo.echo", "description": "e",
                                "input_schema": {"type": "object"}})()]

    out = agent._respond_with_tools([{"role": "user", "content": "hi"}], _Ctx())
    assert out == "done"
    msgs = captured["messages"]
    asst = [m for m in msgs if m.get("role") == "assistant" and m.get("tool_calls")]
    assert asst, "assistant-сообщение должно нести tool_calls"
    tc = asst[0]["tool_calls"][0]
    assert tc["id"] and tc["type"] == "function" and tc["function"]["name"] == "mcp.demo.echo"
    tool_msg = [m for m in msgs if m.get("role") == "tool"][0]
    assert tool_msg["tool_call_id"] == "c1"
