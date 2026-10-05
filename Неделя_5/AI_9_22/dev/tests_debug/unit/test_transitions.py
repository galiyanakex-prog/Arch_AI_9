# -*- coding: utf-8 -*-
"""Юнит-тесты контролируемых переходов (День 15) — канон arch_den_15 §3.2.

Покрывает весь список из `Задание_Д15.txt`: can_transition разрешённые/
запрещённые, try_transition не меняет состояние при отказе,
InvalidTransitionError объясняет, полный поток с утверждением, /run не
перепрыгивает утверждение, журнал попыток/отказов, реакция ассистента
(REFUSAL_RULES), пауза/продолжение, перезапуск не сбрасывает, миграция
снимка, пауза — не лазейка. Всё на заглушках, без сети; файлы — .tmp/.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from core.state_machine import (
    TaskStage, TaskState, ALLOWED_TRANSITIONS, can_transition, try_transition,
    InvalidTransitionError, refusal_text, approve_plan, pause_task, resume_task,
    run_task, save_state, load_state,
)


class StubExecutor:
    def plan(self, objective):
        return ["Собрать данные", "Обработать данные", "Проверить результат"]

    def execute(self, step):
        return f"Результат шага: {step}"


def validate_results(results):
    return len(results) > 0


def make_state(stage=TaskStage.NEW, **kwargs):
    defaults = dict(task_id="task-001", objective="Тестовая задача", stage=stage)
    defaults.update(kwargs)
    return TaskState(**defaults)


def run_to_end(state, limit=50):
    passes = 0
    while (state.stage not in (TaskStage.DONE, TaskStage.FAILED,
                               TaskStage.PAUSED, TaskStage.PLANNING)
           and passes < limit):
        run_task(state, StubExecutor(), validate_results)
        passes += 1
    return state


# --- 1. can_transition: разрешённые / запрещённые ----------------------------------
def test_can_transition_allowed():
    assert can_transition(TaskStage.PLANNING, TaskStage.PLAN_APPROVED)
    assert can_transition(TaskStage.PLAN_APPROVED, TaskStage.IMPLEMENTATION)
    assert can_transition(TaskStage.IMPLEMENTATION, TaskStage.VALIDATION)
    assert can_transition(TaskStage.VALIDATION, TaskStage.DONE)
    assert can_transition(TaskStage.NEW, TaskStage.PLANNING)


def test_can_transition_forbidden():
    assert not can_transition(TaskStage.NEW, TaskStage.IMPLEMENTATION)
    assert not can_transition(TaskStage.PLANNING, TaskStage.IMPLEMENTATION)
    assert not can_transition(TaskStage.IMPLEMENTATION, TaskStage.DONE)
    assert not can_transition(TaskStage.PLANNING, TaskStage.DONE)
    assert not can_transition(TaskStage.DONE, TaskStage.NEW)
    assert not can_transition(TaskStage.PAUSED, TaskStage.IMPLEMENTATION)
    assert not can_transition(TaskStage.PAUSED, TaskStage.DONE)


# --- 2. try_transition: отказ не меняет состояние -----------------------------------
def test_try_transition_rejects_without_state_change():
    state = make_state(stage=TaskStage.PLANNING, current_step=0,
                       steps=["a", "b"], results=["r"])
    try:
        try_transition(state, TaskStage.IMPLEMENTATION)
        raise AssertionError("ожидался InvalidTransitionError")
    except InvalidTransitionError:
        pass
    assert state.stage == TaskStage.PLANNING
    assert state.current_step == 0 and state.steps == ["a", "b"]
    assert state.results == ["r"]


def test_invalid_transition_error_explains():
    state = make_state(stage=TaskStage.PLANNING)
    try:
        try_transition(state, TaskStage.IMPLEMENTATION)
    except InvalidTransitionError as error:
        text = str(error)
        assert "запрещён" in text
        assert "planning" in text and "implementation" in text
        assert "plan_approved" in text          # список разрешённых
        assert error.current == TaskStage.PLANNING
        assert error.proposed == TaskStage.IMPLEMENTATION


# --- 3. Полный поток с утверждением --------------------------------------------------
def test_full_flow_with_approval():
    state = make_state()
    run_task(state, StubExecutor(), validate_results)   # new → planning
    assert state.stage == TaskStage.PLANNING
    assert state.expected_action == "утвердить план (/approve)"
    approve_plan(state)                                 # → plan_approved
    assert state.stage == TaskStage.PLAN_APPROVED
    run_to_end(state)                                   # → implementation → validation → done
    assert state.stage == TaskStage.DONE
    assert len(state.results) == 3
    assert len(state.results) == len(set(state.results))   # без дублей


# --- 4. /run не перепрыгивает утверждение --------------------------------------------
def test_run_does_not_skip_approval():
    state = make_state()
    run_task(state, StubExecutor(), validate_results)   # → planning
    run_to_end(state)                                   # крутит — но останавливается
    assert state.stage == TaskStage.PLANNING
    assert not any(e["to"] == "implementation" for e in state.transition_log)


# --- 5. Журнал попыток и отказов ------------------------------------------------------
def test_transition_log_records_attempts():
    state = make_state()
    run_task(state, StubExecutor(), validate_results)   # new → planning (allowed=True)
    assert state.transition_log[-1] == {**state.transition_log[-1],
                                        "allowed": True}
    try:
        try_transition(state, TaskStage.IMPLEMENTATION)
    except InvalidTransitionError:
        pass
    entry = state.transition_log[-1]
    assert entry["allowed"] is False
    assert entry["from"] == "planning" and entry["to"] == "implementation"
    assert entry["reason"]                              # правило записано
    approve_plan(state)
    assert state.transition_log[-1]["allowed"] is True
    assert state.transition_log[-1]["to"] == "plan_approved"


# --- 6. Реакция ассистента: правило + корректный шаг ---------------------------------
def test_refusal_texts():
    r1 = refusal_text(TaskStage.PLANNING, TaskStage.IMPLEMENTATION)
    assert "нельзя делать реализацию до утверждённого плана" in r1.lower()
    assert "/approve" in r1
    r2 = refusal_text(TaskStage.IMPLEMENTATION, TaskStage.DONE)
    assert "нельзя делать финал без валидации" in r2.lower()
    r3 = refusal_text(TaskStage.DONE, TaskStage.NEW)
    assert "терминальная" in r3.lower()
    r4 = refusal_text(TaskStage.PAUSED, TaskStage.IMPLEMENTATION)
    assert "/resume" in r4


# --- 7. Пауза/продолжение -------------------------------------------------------------
def test_pause_resume_same_position():
    state = make_state()
    run_task(state, StubExecutor(), validate_results)
    approve_plan(state)
    run_task(state, StubExecutor(), validate_results)   # → implementation, шаг 0
    pause_task(state)
    assert state.stage == TaskStage.PAUSED
    assert state.previous_stage == TaskStage.IMPLEMENTATION
    assert state.current_step == 1
    resume_task(state)
    assert state.stage == TaskStage.IMPLEMENTATION
    assert state.current_step == 1
    # Доступные переходы после resume — те же.
    assert can_transition(TaskStage.IMPLEMENTATION, TaskStage.VALIDATION)
    assert not can_transition(TaskStage.IMPLEMENTATION, TaskStage.DONE)


# --- 8. Перезапуск не сбрасывает и не перескакивает ----------------------------------
def test_restart_preserves_state_and_log(tmp_path):
    path = str(tmp_path / "task_state.json")
    state = make_state()
    run_task(state, StubExecutor(), validate_results)
    try:
        try_transition(state, TaskStage.IMPLEMENTATION)   # отказ для журнала
    except InvalidTransitionError:
        pass
    approve_plan(state)
    run_task(state, StubExecutor(), validate_results)     # → implementation
    pause_task(state)
    save_state(state, path)

    restored = load_state(path)                           # «перезапуск»
    assert restored.stage == TaskStage.PAUSED
    assert restored.current_step == state.current_step
    assert restored.transition_log == state.transition_log
    resume_task(restored)
    assert restored.stage == TaskStage.IMPLEMENTATION
    assert restored.current_step == state.current_step    # тот же шаг
    run_to_end(restored)
    assert restored.stage == TaskStage.DONE
    assert len(restored.results) == 3


# --- 9. Миграция снимка дня 14 --------------------------------------------------------
def test_snapshot_migration():
    state = TaskState.from_dict({
        "task_id": "old", "objective": "старая задача",
        "stage": "execution", "current_step": 1,
        "steps": ["a", "b"], "results": ["r"],
    })
    assert state.stage == TaskStage.IMPLEMENTATION
    assert state.transition_log == []
    assert state.current_step == 1


# --- 10. Пауза — не лазейка -----------------------------------------------------------
def test_pause_is_not_loophole():
    assert not can_transition(TaskStage.PAUSED, TaskStage.IMPLEMENTATION)
    assert not can_transition(TaskStage.PAUSED, TaskStage.DONE)
    assert not can_transition(TaskStage.PAUSED, TaskStage.PLANNING)
    # Выход из паузы — только resume_task() → previous_stage.
    state = make_state(stage=TaskStage.PLAN_APPROVED)
    pause_task(state)
    resume_task(state)
    assert state.stage == TaskStage.PLAN_APPROVED         # прежняя стадия


# --- 11. Карта = arch §2.3 построчно --------------------------------------------------
def test_map_matches_canon():
    assert ALLOWED_TRANSITIONS[TaskStage.NEW] == {
        TaskStage.PLANNING, TaskStage.PAUSED, TaskStage.FAILED}
    assert ALLOWED_TRANSITIONS[TaskStage.PLANNING] == {
        TaskStage.PLAN_APPROVED, TaskStage.PAUSED, TaskStage.FAILED}
    assert ALLOWED_TRANSITIONS[TaskStage.PLAN_APPROVED] == {
        TaskStage.IMPLEMENTATION, TaskStage.PLANNING, TaskStage.PAUSED,
        TaskStage.FAILED}
    assert ALLOWED_TRANSITIONS[TaskStage.IMPLEMENTATION] == {
        TaskStage.VALIDATION, TaskStage.PLANNING, TaskStage.PAUSED,
        TaskStage.FAILED}
    assert ALLOWED_TRANSITIONS[TaskStage.VALIDATION] == {
        TaskStage.DONE, TaskStage.IMPLEMENTATION, TaskStage.PLANNING,
        TaskStage.PAUSED, TaskStage.FAILED}
    assert ALLOWED_TRANSITIONS[TaskStage.PAUSED] == set()
    assert ALLOWED_TRANSITIONS[TaskStage.DONE] == set()
    assert ALLOWED_TRANSITIONS[TaskStage.FAILED] == {TaskStage.PLANNING}


# --- 12. approve_plan: идемпотентность и отказы ---------------------------------------
def test_approve_plan_idempotent_and_refusals():
    state = make_state(stage=TaskStage.PLAN_APPROVED)
    message = approve_plan(state)
    assert state.stage == TaskStage.PLAN_APPROVED         # не изменилось
    assert "уже утверждён" in message
    state2 = make_state(stage=TaskStage.NEW)
    message2 = approve_plan(state2)
    assert state2.stage == TaskStage.NEW
    assert "/plan" in message2
