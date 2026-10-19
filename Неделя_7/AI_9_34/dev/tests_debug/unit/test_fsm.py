# -*- coding: utf-8 -*-
"""Юнит-тесты Task State Machine (День 15) — адаптация test_fsm Дня 13.

Покрывает прежний список (переходы по ALLOWED_TRANSITIONS, пауза/продолжение,
сохранение/загрузка JSON, «перезапуск», неповторение завершённых шагов,
валидация done/failed) под новый поток Дня 15: new → planning (остановка на
утверждении) → approve → plan_approved → implementation → validation → done.
Всё на заглушках, без сети; файлы — только .tmp/.
"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from core.state_machine import (
    TaskStage, TaskState, ALLOWED_TRANSITIONS, transition, can_transition,
    approve_plan, pause_task, resume_task, save_state, load_state, run_task,
)


# --- Заглушки (без LLM и сети) -----------------------------------------------------
def execute_step(step):
    """Заглушка исполнителя шага."""
    return f"Результат шага: {step}"


def validate_results(results):
    """Заглушка валидатора: результат непустой → успех."""
    return len(results) > 0


class StubExecutor:
    """Детерминированный executor для run_task (контракт .plan/.execute)."""

    def plan(self, objective):
        return ["Получить данные", "Обработать данные", "Проверить результат"]

    def execute(self, step):
        return execute_step(step)


def make_state(stage=TaskStage.NEW, **kwargs):
    defaults = dict(task_id="task-001", objective="Тестовая задача", stage=stage)
    defaults.update(kwargs)
    return TaskState(**defaults)


def run_to_end(state, executor, validator, limit=50):
    """Крутит автомат до done/failed/paused/planning (утверждение — человек)."""
    passes = 0
    while (state.stage not in (TaskStage.DONE, TaskStage.FAILED,
                               TaskStage.PAUSED, TaskStage.PLANNING)
           and passes < limit):
        run_task(state, executor, validator)
        passes += 1
    return state


# --- 1. Переходы этапов ------------------------------------------------------------
def test_transition_allowed():
    state = make_state(stage=TaskStage.PLAN_APPROVED)
    assert transition(state, TaskStage.IMPLEMENTATION) is True
    assert state.stage == TaskStage.IMPLEMENTATION


def test_transition_forbidden_keeps_stage():
    state = make_state(stage=TaskStage.PLANNING)  # план не утверждён
    assert transition(state, TaskStage.IMPLEMENTATION) is False
    assert state.stage == TaskStage.PLANNING


def test_transition_map_matches_can_transition():
    for source, targets in ALLOWED_TRANSITIONS.items():
        for stage in TaskStage:
            assert can_transition(source, stage) == (stage in targets)


# --- 2. Пауза и продолжение --------------------------------------------------------
def test_pause_and_resume():
    state = TaskState(
        task_id="1",
        objective="Тестовая задача",
        stage=TaskStage.IMPLEMENTATION,
        current_step=2,
        steps=["Шаг 1", "Шаг 2", "Шаг 3"],
        expected_action="Выполнить шаг 3",
    )
    state = pause_task(state)
    assert state.stage == TaskStage.PAUSED
    assert state.previous_stage == TaskStage.IMPLEMENTATION
    assert state.current_step == 2

    state = resume_task(state)
    assert state.stage == TaskStage.IMPLEMENTATION
    assert state.current_step == 2
    assert state.expected_action == "Выполнить шаг 3"


def test_pause_on_any_working_stage():
    for stage in (TaskStage.NEW, TaskStage.PLANNING, TaskStage.PLAN_APPROVED,
                  TaskStage.IMPLEMENTATION, TaskStage.VALIDATION):
        state = make_state(stage=stage, current_step=1)
        pause_task(state)
        assert state.stage == TaskStage.PAUSED and state.previous_stage == stage
        resume_task(state)
        assert state.stage == stage and state.current_step == 1


def test_pause_refused_on_terminal_stages():
    for stage in (TaskStage.DONE, TaskStage.FAILED):
        state = make_state(stage=stage)
        pause_task(state)
        assert state.stage == stage            # состояние не изменилось
        assert state.transition_log[-1]["allowed"] is False


def test_pause_idempotent():
    state = make_state(stage=TaskStage.IMPLEMENTATION)
    pause_task(state)
    pause_task(state)  # повторная пауза — no-op
    assert state.stage == TaskStage.PAUSED
    assert state.previous_stage == TaskStage.IMPLEMENTATION  # не перезаписан


def test_resume_not_paused_is_noop():
    state = make_state(stage=TaskStage.IMPLEMENTATION, current_step=1)
    resume_task(state)
    assert state.stage == TaskStage.IMPLEMENTATION and state.current_step == 1


# --- 3. Сохранение и загрузка (JSON) ------------------------------------------------
def test_save_load_roundtrip(tmp_path):
    path = str(tmp_path / "task_state.json")
    state = make_state(
        stage=TaskStage.PAUSED, current_step=1,
        steps=["Найти", "Собрать", "Сравнить"],
        expected_action="Собрать информацию",
        results=["Найдены Django, Flask, FastAPI"],
        previous_stage=TaskStage.IMPLEMENTATION,
    )
    save_state(state, path)
    loaded = load_state(path)
    assert loaded == state
    # На диске — канонический снимок (enum как строки, журнал на месте).
    with open(path, encoding="utf-8") as file:
        raw = json.load(file)
    assert raw["stage"] == "paused"
    assert raw["previous_stage"] == "implementation"
    assert isinstance(raw["transition_log"], list)


def test_load_missing_or_broken_returns_none(tmp_path):
    assert load_state(str(tmp_path / "нет.json")) is None
    broken = tmp_path / "битый.json"
    broken.write_text("{не json", encoding="utf-8")
    assert load_state(str(broken)) is None


def test_restart_continues_from_saved_step(tmp_path):
    """«Перезапуск»: save → load → продолжение с current_step, план не перестроен."""
    path = str(tmp_path / "task_state.json")
    state = make_state(stage=TaskStage.IMPLEMENTATION, current_step=1,
                       steps=["Получить данные", "Обработать данные", "Проверить результат"],
                       results=[execute_step("Получить данные")])
    pause_task(state)
    save_state(state, path)

    restored = load_state(path)          # новый «процесс» читает тот же файл
    resume_task(restored)
    assert restored.stage == TaskStage.IMPLEMENTATION
    assert restored.current_step == 1    # шаг 0 НЕ повторяется
    assert restored.steps == state.steps  # план тот же

    run_to_end(restored, StubExecutor(), validate_results)
    assert restored.stage == TaskStage.DONE
    assert len(restored.results) == 3    # без дубля первого шага


# --- 4. Основной цикл: утверждение + шаги не повторяются ----------------------------
def test_completed_steps_not_repeated():
    state = make_state()
    executor = StubExecutor()
    run_task(state, executor, validate_results)   # new → planning (план построен)
    approve_plan(state)                           # planning → plan_approved
    run_task(state, executor, validate_results)   # plan_approved → implementation, шаг 0
    assert state.current_step == 1 and len(state.results) == 1

    pause_task(state)
    resume_task(state)
    run_to_end(state, executor, validate_results)
    assert state.stage == TaskStage.DONE
    assert len(state.results) == 3 == len(set(state.results))  # без дублей
    assert state.current_step == 3                              # монотонен


def test_expected_action_points_to_next_step():
    state = make_state()
    executor = StubExecutor()
    run_task(state, executor, validate_results)   # new → planning
    assert state.expected_action == "утвердить план (/approve)"
    approve_plan(state)                           # → plan_approved
    assert state.expected_action == "начать реализацию (/step или /run)"
    run_task(state, executor, validate_results)   # → implementation, шаг 0
    assert state.expected_action == "Обработать данные"  # следующий шаг


# --- 5. Валидация: успех → done, ошибка → failed ------------------------------------
def test_validation_success_goes_done():
    state = make_state()
    run_task(state, StubExecutor(), validate_results)   # → planning
    approve_plan(state)                                 # → plan_approved
    run_to_end(state, StubExecutor(), validate_results)
    assert state.stage == TaskStage.DONE and state.error is None


def test_validation_failure_goes_failed():
    state = make_state()
    run_task(state, StubExecutor(), validate_results)   # → planning
    approve_plan(state)                                 # → plan_approved
    run_to_end(state, StubExecutor(), lambda results: False)
    assert state.stage == TaskStage.FAILED
    assert state.error == "Проверка результата не пройдена"


def test_failed_recovery_only_to_planning():
    state = make_state(stage=TaskStage.FAILED, error="x")
    assert transition(state, TaskStage.IMPLEMENTATION) is False
    assert transition(state, TaskStage.PLANNING) is True
    assert state.stage == TaskStage.PLANNING