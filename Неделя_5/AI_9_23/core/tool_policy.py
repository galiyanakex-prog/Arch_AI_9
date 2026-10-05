# -*- coding: utf-8 -*-
"""core/tool_policy.py — проверки вызова инструмента перед исполнением (День 16).

Минимальный policy pipeline (канон `Рекомендации_MCP_d16.txt`, ступени 1–6):
  1) инструмент существует в каталоге;
  2) инструмент включён (`ToolDescriptor.enabled`);
  3) аргументы соответствуют входной схеме (мягкая проверка required/properties);
  4) текущая стадия задачи разрешает вызов (`allowed_stages`);
  5) инварианты задачи разрешают действие (`InvariantChecker` поверх ProposedAction);
  6) если требуется — вызов ждёт подтверждения человека (`requires_confirmation`).

Политика НЕ вызывает `StateMachine` (инструмент ≠ переход) и не исполняет тул —
только решает «можно ли». Результат — `PolicyDecision`.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.invariants import ConstraintSet, ProposedAction
from core.tools import TERMINAL_STAGES, infer_read_only


@dataclass
class PolicyDecision:
    """Итог проверки вызова: allowed + причина + признак «ждёт подтверждения»."""

    allowed: bool
    reason: str = ""
    needs_confirmation: bool = False


def _schema_errors(arguments: dict, schema: dict) -> list[str]:
    """Мягкая проверка аргументов по JSON-схеме (required + типы свойств)."""
    errors: list[str] = []
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return errors
    arguments = arguments or {}
    for name in schema.get("required", []) or []:
        if name not in arguments:
            errors.append(f"отсутствует обязательный аргумент «{name}»")
    props = schema.get("properties") or {}
    type_map = {"string": str, "number": (int, float), "integer": int,
                "boolean": bool, "array": list, "object": dict}
    for name, value in arguments.items():
        expected = props.get(name, {}).get("type") if isinstance(props.get(name), dict) else None
        py_type = type_map.get(expected)
        if py_type is not None and not isinstance(value, py_type):
            errors.append(f"аргумент «{name}»: ожидался {expected}")
    return errors


class ToolPolicy:
    """Проверки вызова (ступени 1–6). Детерминирована, без сети и LLM."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def check(self, descriptor, request, task_stage: str = "",
              constraints: ConstraintSet | None = None,
              checker=None) -> PolicyDecision:
        """Полная проверка запроса на вызов инструмента.

        descriptor — ToolDescriptor (уже найденный в каталоге);
        request — ToolCallRequest; task_stage — текущая стадия (строка);
        constraints/checker — инварианты задачи и их проверка (опционально).
        """
        if not self.enabled:
            return PolicyDecision(False, "policy pipeline выключен")
        if descriptor is None:
            return PolicyDecision(False, "инструмент не найден в каталоге")
        if not descriptor.enabled:
            return PolicyDecision(False, f"инструмент «{descriptor.name}» выключен")

        errors = _schema_errors(dict(request.arguments or {}), descriptor.input_schema)
        if errors:
            return PolicyDecision(False, "аргументы не соответствуют схеме: "
                                   + "; ".join(errors))

        # D6: терминальные стадии (done/failed/paused) — только read-only.
        # Проверяем ДО стадийного фильтра: read-only разрешён и на терминальной
        # стадии (её нет в ALL_WORKING_STAGES), мутация — запрещена с внятной причиной.
        if task_stage in TERMINAL_STAGES:
            if not infer_read_only(descriptor.original_name):
                return PolicyDecision(False,
                    f"стадия «{task_stage}» терминальна: разрешены только read-only "
                    f"инструменты, «{descriptor.name}» изменяет состояние")
        elif task_stage and task_stage not in (descriptor.allowed_stages or set()):
            return PolicyDecision(False,
                f"стадия «{task_stage}» не разрешает инструмент «{descriptor.name}»")

        if constraints is not None and checker is not None:
            action = ProposedAction(
                description=f"Вызов инструмента {descriptor.name}",
                action_type="tool_call", tool_name=descriptor.name,
                arguments=dict(request.arguments or {}),
            )
            violations = checker.check(action, constraints)
            if violations:
                return PolicyDecision(False, "; ".join(violations))

        if descriptor.requires_confirmation:
            return PolicyDecision(True, "требуется подтверждение", needs_confirmation=True)
        return PolicyDecision(True)