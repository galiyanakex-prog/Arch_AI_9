# -*- coding: utf-8 -*-
"""core/tool_executor.py — процедура контролируемого вызова инструмента (День 16).

Единственная точка исполнения MCP-тула: policy-проверки → вызов через gateway →
результат → аудит (`tool_audit.jsonl`). НЕ вызывает `StateMachine` (инструмент ≠
переход): успешный вызов не создаёт запись в `transition_log`.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict

from core.tools import (
    ToolCallRequest, ToolExecutionResult, ToolExecutionState,
)


def _args_hash(arguments: dict) -> str:
    """Хэш аргументов (сырые аргументы в аудит не пишем — только отпечаток)."""
    payload = json.dumps(arguments or {}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class ToolExecutor:
    """Исполнение вызова: policy → gateway → результат → аудит."""

    def __init__(self, registry, policy, gateway, store=None, checker=None,
                 log=None) -> None:
        self.registry = registry
        self.policy = policy
        self.gateway = gateway
        self.store = store
        self.checker = checker
        self.log = log or (lambda line: None)
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"exec-{self._counter:04d}"

    def _audit(self, user_id, task, record: dict) -> None:
        if self.store is not None and user_id:
            try:
                self.store.append_tool_audit(user_id, task or "Основная_задача", record)
            except Exception as exc:  # аудит не должен ронять вызов
                self.log(f"[Инструменты] аудит не записан: {exc}")

    def execute(self, request: ToolCallRequest, *, user_id: str = "", task: str = "",
                task_stage: str = "", constraints=None) -> ToolExecutionResult:
        """Выполнить запрос инструмента под проверками policy."""
        execution_id = self._next_id()
        started = time.time()

        descriptor = None
        try:
            descriptor = self.registry.get(request.name) if self.registry else None
        except KeyError as exc:
            descriptor = None
            missing = str(exc)

        if descriptor is None:
            result = ToolExecutionResult(
                execution_id=execution_id, tool=request.name,
                status=ToolExecutionState.DENIED.value,
                summary=f"Инструмент не найден: {request.name}",
                is_error=True, call_id=request.call_id,
            )
            self._audit(user_id, task, self._record(result, request, started, "not_found"))
            return result

        decision = self.policy.check(descriptor, request, task_stage=task_stage,
                                     constraints=constraints, checker=self.checker)
        if not decision.allowed or decision.needs_confirmation:
            status = (ToolExecutionState.WAITING_CONFIRMATION.value
                      if decision.needs_confirmation else ToolExecutionState.DENIED.value)
            result = ToolExecutionResult(
                execution_id=execution_id, tool=descriptor.name, status=status,
                summary=decision.reason or "вызов отклонён policy",
                is_error=not decision.needs_confirmation, call_id=request.call_id,
            )
            self._audit(user_id, task, self._record(result, request, started, "policy"))
            self.log(f"[Инструменты] {descriptor.name}: {status} — {decision.reason}")
            return result

        # Разрешено → вызов через gateway (маршрут по provider сервера).
        result = self._invoke(descriptor, request, execution_id)
        result = ToolExecutionResult(
            execution_id=execution_id, tool=descriptor.name, status=result.status,
            summary=result.summary, raw=result.raw, is_error=result.is_error,
            call_id=request.call_id, text=getattr(result, "text", "") or result.summary,
        )
        self._audit(user_id, task, self._record(result, request, started, "invoked"))
        self.log(f"[Инструменты] {descriptor.name}: {result.status}")
        return result

    def _invoke(self, descriptor, request: ToolCallRequest, execution_id: str):
        """Вызов шлюза; устойчиво к sync-фасаду (MCPGatewaySync) и async-шлюзу."""
        import asyncio
        import inspect
        result = self.gateway.call_tool(descriptor.provider, descriptor.original_name,
                                        dict(request.arguments or {}), execution_id)
        if inspect.isawaitable(result):
            result = asyncio.run(result)
        return result

    @staticmethod
    def _record(result: ToolExecutionResult, request: ToolCallRequest,
                started: float, phase: str) -> dict:
        return {
            "execution_id": result.execution_id,
            "tool": result.tool,
            "provider": getattr(request, "provider", "") or "",
            "status": result.status,
            "phase": phase,
            "arguments_hash": _args_hash(request.arguments),
            "call_id": request.call_id,
            "duration_ms": int((time.time() - started) * 1000),
            "error": result.summary if result.is_error else "",
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }