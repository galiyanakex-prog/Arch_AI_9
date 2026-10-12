# -*- coding: utf-8 -*-
"""Примитив-смоук этапа M1 (миграция den_15): ядро строгой машины состояний.

Прогон инлайн (migr_plan_1.md, шаг 1.9): can_transition, try_transition,
InvalidTransitionError, полный поток с утверждением, миграция снимков,
пауза/resume, transition-обёртка, save/load round-trip, refusal_text.
Временные файлы — только в dev/tests_debug/.tmp/.
"""
import json
import os
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

from core.state_machine import (
    TaskStage, TaskState, can_transition, try_transition,
    InvalidTransitionError, refusal_text, transition, approve_plan, pause_task,
    resume_task, run_task, save_state, load_state,
)


class Stub:
    def plan(self, objective):
        return ["Собрать данные", "Обработать", "Проверить"]

    def execute(self, step):
        return f"Результат: {step}"


def main():
    # 1. can_transition: разрешённые/запрещённые
    assert can_transition(TaskStage.PLANNING, TaskStage.PLAN_APPROVED) is True
    assert can_transition(TaskStage.PLAN_APPROVED, TaskStage.IMPLEMENTATION) is True
    assert can_transition(TaskStage.IMPLEMENTATION, TaskStage.VALIDATION) is True
    assert can_transition(TaskStage.VALIDATION, TaskStage.DONE) is True
    assert can_transition(TaskStage.PLANNING, TaskStage.IMPLEMENTATION) is False
    assert can_transition(TaskStage.NEW, TaskStage.IMPLEMENTATION) is False
    assert can_transition(TaskStage.IMPLEMENTATION, TaskStage.DONE) is False
    assert can_transition(TaskStage.PAUSED, TaskStage.IMPLEMENTATION) is False
    assert can_transition(TaskStage.DONE, TaskStage.NEW) is False
    print("1. can_transition OK")

    # 2. try_transition: отказ не меняет состояние + ошибка объясняет
    st = TaskState(task_id="t", objective="REST API", stage=TaskStage.PLANNING,
                   steps=["a", "b"], current_step=0)
    try:
        try_transition(st, TaskStage.IMPLEMENTATION)
        raise AssertionError("ожидался InvalidTransitionError")
    except InvalidTransitionError as error:
        assert "запрещён" in str(error) and "planning" in str(error)
    assert st.stage == TaskStage.PLANNING and st.current_step == 0
    assert st.steps == ["a", "b"] and st.results == []
    assert st.transition_log[-1]["allowed"] is False
    assert "утверд" in st.transition_log[-1]["reason"].lower()
    print("2. try_transition отказ OK")

    # 3. Полный поток: new → planning (остановка) → approve → implementation → done
    st = TaskState(task_id="t2", objective="Сделать REST API", stage=TaskStage.NEW)
    run_task(st, Stub(), lambda r: True)
    assert st.stage == TaskStage.PLANNING and len(st.steps) == 3
    assert st.expected_action == "утвердить план (/approve)"
    run_task(st, Stub(), lambda r: True)
    assert st.stage == TaskStage.PLANNING
    message = approve_plan(st)
    assert st.stage == TaskStage.PLAN_APPROVED and "утверждён" in message
    run_task(st, Stub(), lambda r: True)
    assert st.stage == TaskStage.IMPLEMENTATION and st.current_step == 1
    passes = 0
    while st.stage not in (TaskStage.DONE, TaskStage.FAILED) and passes < 50:
        run_task(st, Stub(), lambda r: True)
        passes += 1
    assert st.stage == TaskStage.DONE and len(st.results) == 3
    assert len(st.results) == len(set(st.results))
    print("3. Полный поток с утверждением OK")

    # 4. run_task из planning не перепрыгивает утверждение
    st2 = TaskState(task_id="t3", objective="X", stage=TaskStage.NEW)
    run_task(st2, Stub(), lambda r: True)
    passes = 0
    while (st2.stage not in (TaskStage.DONE, TaskStage.FAILED, TaskStage.PAUSED)
           and passes < 50):
        run_task(st2, Stub(), lambda r: True)
        passes += 1
    assert st2.stage == TaskStage.PLANNING
    assert not any(e["to"] == "implementation" for e in st2.transition_log)
    print("4. run_task из planning останавливается OK")

    # 5. Миграция снимков: "execution" → IMPLEMENTATION; без журнала → []
    st3 = TaskState.from_dict({"task_id": "t4", "objective": "старая",
                               "stage": "execution", "current_step": 1,
                               "steps": ["a", "b"], "results": ["r"]})
    assert st3.stage == TaskStage.IMPLEMENTATION and st3.transition_log == []
    st4 = TaskState.from_dict({"task_id": "t5", "objective": "без stage"})
    assert st4.stage == TaskStage.NEW
    print("5. Миграция снимков OK")

    # 6. Пауза/resume на новых стадиях + отказ из DONE
    st5 = TaskState(task_id="t6", objective="Y", stage=TaskStage.PLAN_APPROVED)
    pause_task(st5)
    assert st5.stage == TaskStage.PAUSED
    assert st5.previous_stage == TaskStage.PLAN_APPROVED
    resume_task(st5)
    assert st5.stage == TaskStage.PLAN_APPROVED
    st6 = TaskState(task_id="t7", objective="Z", stage=TaskStage.DONE)
    pause_task(st6)
    assert st6.stage == TaskStage.DONE
    assert st6.transition_log[-1]["allowed"] is False
    print("6. Пауза/resume + отказ из DONE OK")

    # 7. transition() — обёртка обратной совместимости
    st7 = TaskState(task_id="t8", objective="W", stage=TaskStage.FAILED)
    assert transition(st7, TaskStage.PLANNING) is True
    assert transition(st7, TaskStage.IMPLEMENTATION) is False
    assert st7.stage == TaskStage.PLANNING
    print("7. transition-обёртка OK")

    # 8. save/load round-trip с журналом (включая отказ — из блока 2)
    tmp_root = os.path.join(BASE_DIR, "dev", "tests_debug", ".tmp")
    os.makedirs(tmp_root, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="m1_", dir=tmp_root)
    path = os.path.join(tmp, "task_state.json")
    st.transition_log.append({"from": "planning", "to": "implementation",
                              "allowed": False, "reason": "тест-отказ",
                              "at": "2026-09-22 00:00:00"})
    save_state(st, path)
    loaded = load_state(path)
    assert loaded == st
    with open(path, encoding="utf-8") as file:
        raw = json.load(file)
    assert raw["stage"] == "done" and isinstance(raw["transition_log"], list)
    assert any(e["allowed"] is False for e in raw["transition_log"])
    print("8. save/load round-trip OK")

    # 9. refusal_text: правило + корректный шаг
    r1 = refusal_text(TaskStage.PLANNING, TaskStage.IMPLEMENTATION)
    assert "нельзя делать реализацию до утверждённого плана" in r1.lower()
    assert "/approve" in r1
    r2 = refusal_text(TaskStage.IMPLEMENTATION, TaskStage.DONE)
    assert "нельзя делать финал без валидации" in r2.lower()
    print("9. refusal_text OK")

    print("M1 SMOKE: ВСЁ OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
