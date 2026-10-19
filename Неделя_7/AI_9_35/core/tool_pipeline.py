# -*- coding: utf-8 -*-
"""core/tool_pipeline.py — автоцепочка MCP-инструментов (День 18, задание 2).

Контракт пайплайна «получить → обработать → сохранить» поверх существующего
`ToolRegistry`/`ToolExecutor`: каждый шаг — вызов инструмента через ту же процедуру
контроля (policy → gateway → аудит). Результат шага N передаётся в аргумент шага N+1
(`input_key`). Пайплайн **не трогает `StateMachine`** (инструмент ≠ переход) и не
знает о MCP SDK (модель MCP не протекает в core).

Пример (задание 2):
    pipeline = Pipeline("report", [
        PipelineStep("mcp.pipeline.search", {"query": "python"}),
        PipelineStep("mcp.pipeline.summarize", input_key="text"),
        PipelineStep("mcp.pipeline.saveToFile", {"name": "report"}, input_key="content"),
    ])
    run = run_pipeline(pipeline, agent.tool_executor, user_id="u", task="Основная_задача")
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.tools import ToolCallRequest, ToolExecutionState


@dataclass
class PipelineStep:
    """Один шаг пайплайна: инструмент + статические аргументы + куда принять вход."""

    tool: str
    args: dict = field(default_factory=dict)
    input_key: str = ""       # имя аргумента, куда подставить результат прошлого шага
    optional: bool = False    # если шаг упал и optional — пайплайн продолжается


@dataclass
class Pipeline:
    """Последовательность шагов пайплайна."""

    name: str
    steps: list[PipelineStep] = field(default_factory=list)


@dataclass
class PipelineRun:
    """Результат прогона пайплайна: статус каждого шага + финальный вывод."""

    name: str
    ok: bool
    steps: list = field(default_factory=list)   # [{tool, status, summary, arguments}]
    output: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "ok": self.ok, "steps": self.steps,
                "output": self.output}


def run_pipeline(pipeline: Pipeline, executor, *, user_id: str = "", task: str = "",
                 task_stage: str = "", constraints=None) -> PipelineRun:
    """Выполнить цепочку автоматически, передавая данные между шагами.

    Результат шага N (ПОЛНЫЙ `ToolExecutionResult.text`, D6) подставляется в
    аргумент `input_key` шага N+1 — без усечения до 500 символов. Каждый вызов
    идёт через `ToolExecutor` (policy + аудит). Пайплайн останавливается на первом
    неуспешном обязательном шаге.
    """
    run = PipelineRun(name=pipeline.name, ok=True)
    previous = ""
    for index, step in enumerate(pipeline.steps):
        arguments = dict(step.args or {})
        if step.input_key and previous:
            arguments[step.input_key] = previous
        request = ToolCallRequest(name=step.tool, arguments=arguments,
                                  call_id=f"{pipeline.name}-step{index}")
        result = executor.execute(request, user_id=user_id, task=task,
                                  task_stage=task_stage, constraints=constraints)
        full_text = getattr(result, "text", "") or result.summary or ""
        entry = {"tool": step.tool, "status": result.status,
                 "summary": result.summary, "arguments": arguments}
        run.steps.append(entry)
        if result.status == ToolExecutionState.SUCCEEDED.value:
            previous = full_text
            run.output = full_text
        else:
            run.ok = False
            if not step.optional:
                break
    return run
