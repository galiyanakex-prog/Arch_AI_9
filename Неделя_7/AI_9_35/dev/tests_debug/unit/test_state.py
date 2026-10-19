# -*- coding: utf-8 -*-
"""Юнит-тесты state machine: этапы, разрешённые/запрещённые переходы (День 15).

Мигрировано с Дня 13 (next_state) на канон Дня 15: TaskStage — 8 состояний,
проверка переходов — can_transition()/ALLOWED_TRANSITIONS. Полный автомат
(dataclass TaskState, pause/resume, save/load, run_task, try_transition,
InvalidTransitionError, transition_log) покрыт в test_fsm.py и
test_transitions.py.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from core.state_machine import TaskStage, ALLOWED_TRANSITIONS, can_transition


def test_eight_stages():
    # Канон Дня 15: 8 допустимых состояний (4 базовых детализированы + расширения).
    base = {"planning", "implementation", "validation", "done"}
    values = {s.value for s in TaskStage}
    assert base <= values
    assert values == base | {"new", "plan_approved", "paused", "failed"}


def test_allowed_transitions():
    assert can_transition(TaskStage.NEW, TaskStage.PLANNING)
    assert can_transition(TaskStage.PLANNING, TaskStage.PLAN_APPROVED)
    assert can_transition(TaskStage.PLAN_APPROVED, TaskStage.IMPLEMENTATION)
    assert can_transition(TaskStage.PLAN_APPROVED, TaskStage.PLANNING)
    assert can_transition(TaskStage.IMPLEMENTATION, TaskStage.VALIDATION)
    assert can_transition(TaskStage.IMPLEMENTATION, TaskStage.PLANNING)
    assert can_transition(TaskStage.VALIDATION, TaskStage.DONE)
    assert can_transition(TaskStage.VALIDATION, TaskStage.IMPLEMENTATION)
    assert can_transition(TaskStage.VALIDATION, TaskStage.PLANNING)


def test_forbidden_transitions():
    # «нельзя реализацию до утверждённого плана» — дуги нет.
    assert not can_transition(TaskStage.NEW, TaskStage.IMPLEMENTATION)
    assert not can_transition(TaskStage.PLANNING, TaskStage.IMPLEMENTATION)
    # «нельзя финал без валидации» — в DONE только из VALIDATION.
    assert not can_transition(TaskStage.PLANNING, TaskStage.DONE)
    assert not can_transition(TaskStage.PLAN_APPROVED, TaskStage.DONE)
    assert not can_transition(TaskStage.IMPLEMENTATION, TaskStage.DONE)
    assert not can_transition(TaskStage.DONE, TaskStage.PLANNING)
    assert not can_transition(TaskStage.PLANNING, TaskStage.VALIDATION)


def test_done_terminal():
    assert ALLOWED_TRANSITIONS[TaskStage.DONE] == set()


def test_paused_and_failed_extensions():
    # paused — выход только через resume_task() (не через transition): множество пустое.
    assert ALLOWED_TRANSITIONS[TaskStage.PAUSED] == set()
    # failed — восстановление только явным переходом в planning (/task retry).
    assert ALLOWED_TRANSITIONS[TaskStage.FAILED] == {TaskStage.PLANNING}
    # пауза допустима с любой рабочей стадии (включая новые NEW/PLAN_APPROVED).
    for stage in (TaskStage.NEW, TaskStage.PLANNING, TaskStage.PLAN_APPROVED,
                  TaskStage.IMPLEMENTATION, TaskStage.VALIDATION):
        assert can_transition(stage, TaskStage.PAUSED)