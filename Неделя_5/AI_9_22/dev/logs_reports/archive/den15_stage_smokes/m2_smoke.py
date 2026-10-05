# -*- coding: utf-8 -*-
"""Смоук этапа M2 (миграция den_15): хранение transition_log + миграция снимков.

Доказательство на уровне фасада Store + Agent (migr_plan_2.md, шаг 2.4):
round-trip transition_log (успехи и отказы), миграция старого снимка дня 14
("execution" → implementation), битый файл не роняет приложение, зеркало
current_state синхронно. Временные файлы — только в dev/tests_debug/.tmp/.
"""
import json
import os
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

from storage.store import Store
from storage.db import ProfileRepository
from memory.manager import MemoryManager, default_layers
from core.llm_client import MockClient
from core.prompt_builder import PromptBuilder
from core.agent import Agent, StubExecutor, default_validator
from core.state_machine import TaskStage


def build(tmp):
    repo = ProfileRepository(os.path.join(tmp, "profiles.db"))
    store = Store(os.path.join(tmp, "users"), profile_repo=repo)
    memory = MemoryManager(default_layers(store))
    return Agent(MockClient(), memory, PromptBuilder("Ты ассистент"), store,
                 user_id="u", executor=StubExecutor(), validator=default_validator)


def main():
    tmp_root = os.path.join(BASE_DIR, "dev", "tests_debug", ".tmp")
    os.makedirs(tmp_root, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="m2_", dir=tmp_root)

    # 1. Round-trip transition_log через фасад Store + Agent (успехи и отказы).
    agent = build(tmp)
    agent.initialize_user("u", "И", {"style": "a", "constraints": "b", "context": "c"})
    agent.start_task("Сделать REST API")
    agent.step_task()                                  # new → planning (план)
    agent.attempt_transition("implementation")         # отказ (план не утверждён)
    agent.approve_plan()                               # planning → plan_approved
    agent.step_task()                                  # → implementation, шаг 0
    snap = agent.store.read_task_state("u", agent.task)
    assert snap["stage"] == "implementation"
    log = snap["transition_log"]
    assert any(e["allowed"] is False and e["to"] == "implementation" for e in log)
    assert any(e["allowed"] is True and e["to"] == "plan_approved" for e in log)

    # «Перезапуск»: новый агент читает тот же снимок — журнал равен.
    agent2 = build(tmp)
    agent2.load_state("u")
    assert agent2.task_state.stage == TaskStage.IMPLEMENTATION
    assert agent2.task_state.transition_log == log
    assert agent2.task_state.current_step == 1
    print("1. round-trip transition_log (успехи + отказы) OK")

    # 2. Миграция старого снимка дня 14: "execution" → implementation, журнал [].
    old = {
        "task_id": "Старая_задача", "objective": "старая задача дня 14",
        "stage": "execution", "current_step": 2,
        "steps": ["Шаг 1", "Шаг 2", "Шаг 3"],
        "expected_action": "Шаг 3", "results": ["r1", "r2"],
        "previous_stage": None, "error": None,
    }
    agent.store.write_task_state("u", "Старая_задача", old)
    agent3 = build(tmp)
    agent3.load_state("u")
    # load_state берёт первую задачу из long_term — переключаем явно.
    agent3.switch_task("Старая_задача")
    assert agent3.task_state is not None
    assert agent3.task_state.stage == TaskStage.IMPLEMENTATION
    assert agent3.task_state.transition_log == []
    assert agent3.task_state.current_step == 2
    print("2. миграция снимка дня 14 (execution → implementation) OK")

    # 3. Битый task_state.json не роняет приложение (задачи нет → старт с NEW).
    task_dir = os.path.dirname(agent.store.task_state_path("u", agent3.task))
    with open(os.path.join(task_dir, "task_state.json"), "w", encoding="utf-8") as f:
        f.write("{не json")
    agent4 = build(tmp)
    agent4.load_state("u")
    agent4.switch_task("Старая_задача")
    assert agent4.task_state is None            # битый снимок = задачи нет
    agent4.start_task("Новая после битой")      # старт с NEW — не падает
    assert agent4.task_state.stage in (TaskStage.NEW, TaskStage.PLANNING)
    print("3. битый снимок не роняет приложение OK")

    # 4. Зеркало current_state в working_memory.json синхронно.
    agent5 = build(tmp)
    agent5.initialize_user("u2", "И", {"style": "a", "constraints": "b", "context": "c"})
    agent5.start_task("Зеркальная задача")
    agent5.step_task()                          # → planning
    agent5.approve_plan()                       # → plan_approved
    working = agent5.store.read_working("u2", agent5.task)
    assert working.get("current_state") == "plan_approved"
    agent5.step_task()                          # → implementation
    working = agent5.store.read_working("u2", agent5.task)
    assert working.get("current_state") == "implementation"
    print("4. зеркало current_state синхронно OK")

    print("M2 SMOKE: ВСЁ OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
