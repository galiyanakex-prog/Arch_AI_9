# -*- coding: utf-8 -*-
"""REPL-смоук этапов M3+M4 (миграция den_15): контроль переходов через CLI.

Канон «Проверьте» из `Задание_Д15.txt` (migr_plan_4.md, шаг 4.3):
  ветка 1 — /plan → /goto implementation (ОТКАЗАНО, состояние не изменилось) →
    /approve → /goto done (ОТКАЗАНО) → /run → done → /goto new (ОТКАЗАНО,
    терминальная) → /transitions (журнал с отказами);
  ветка 2 — /plan → /approve → /step → /pause → перезапуск процесса →
    /resume → /run → done (шаг не повторён).
Прогон через subprocess CLI в --mock; временные файлы — только в .tmp/.
"""
import json
import os
import subprocess
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP_ROOT = os.path.join(BASE_DIR, "dev", "tests_debug", ".tmp")


def run_cli(tmp, stdin, user=None):
    env = dict(os.environ)
    env["API_KEY"] = "test-key"
    cmd = [sys.executable, os.path.join(BASE_DIR, "Kod.py"),
           "--mock", "--memory-dir", os.path.join(tmp, "users"),
           "--log", os.path.join(tmp, "log.md"),
           "--token-log", os.path.join(tmp, "tokens.csv")]
    if user:
        cmd += ["--user", user]
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True,
                          timeout=60, env=env, cwd=BASE_DIR)


def main():
    os.makedirs(TMP_ROOT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="m34_", dir=TMP_ROOT)

    # --- Ветка 1: отказы /goto + флоу /approve + терминальная done -------------
    stdin = ("u\nИ\nкраткий\nPython\nцель\n"
             "/plan Сделать REST API\n"
             "/goto implementation\n"
             "/state\n"
             "/approve\n"
             "/goto done\n"
             "/run\n"
             "/goto new\n"
             "/transitions\n"
             "/exit\n")
    proc = run_cli(tmp, stdin)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out

    # /plan: план построен, стадия planning (остановка на утверждении).
    assert "утвердить план (/approve)" in out, out
    # /goto implementation из planning: ОТКАЗАНО + правило + состояние не изменено.
    assert "ОТКАЗАНО" in out, out
    assert "нельзя делать реализацию до утверждённого плана" in out.lower(), out
    assert "Состояние не изменено: planning" in out, out
    # /state после отказа: стадия НЕ изменилась (planning), 1 отказ в журнале.
    assert "Этап: planning" in out, out
    assert "Отказов в журнале переходов: 1" in out, out
    # /approve: план утверждён.
    assert "plan_approved" in out and "утверждён" in out, out
    # /goto done из plan_approved: ОТКАЗАНО («нельзя финал без валидации»).
    assert "нельзя завершать задачу без реализации и валидации" in out.lower(), out
    # /run: доведено до done.
    assert "Этап: done" in out, out
    # /goto new из done: ОТКАЗАНО (терминальная).
    assert "терминальная" in out, out
    # /transitions: журнал с отказами.
    assert "ОТКАЗАНО —" in out or "ОТКАЗАНО" in out, out
    assert "Журнал" in out and "отказов: 3" in out, out
    print("ветка 1: отказы /goto + /approve + терминальная done OK")

    # Снимок: журнал переходов на диске (3 отказа + успехи).
    snap_path = None
    for root, _dirs, files in os.walk(os.path.join(tmp, "users")):
        if "task_state.json" in files:
            snap_path = os.path.join(root, "task_state.json")
    assert snap_path, "task_state.json не найден"
    with open(snap_path, encoding="utf-8") as file:
        raw = json.load(file)
    assert raw["stage"] == "done"
    refused = [e for e in raw["transition_log"] if not e["allowed"]]
    assert len(refused) == 3, raw["transition_log"]
    assert all(e["reason"] for e in refused)
    print("снимок: transition_log с 3 отказами на диске OK")

    # --- Ветка 2: пауза → перезапуск процесса → resume → run → done -------------
    tmp2 = tempfile.mkdtemp(prefix="m34b_", dir=TMP_ROOT)
    stdin1 = ("u\nИ\nкраткий\nPython\nцель\n"
              "/plan Тестовая цель\n"
              "/approve\n"
              "/step\n"
              "/pause\n"
              "/exit\n")
    proc1 = run_cli(tmp2, stdin1)
    out1 = proc1.stdout + proc1.stderr
    assert proc1.returncode == 0, out1
    assert "Этап: paused" in out1, out1
    assert "Вернуться после паузы к: implementation" in out1, out1

    # Перезапуск: новый процесс, тот же memory-dir.
    stdin2 = "/resume\n/run\n/state\n/exit\n"
    proc2 = run_cli(tmp2, stdin2, user="u")
    out2 = proc2.stdout + proc2.stderr
    assert proc2.returncode == 0, out2
    assert "Этап: implementation" in out2, out2   # resume → прежняя стадия
    assert "Этап: done" in out2, out2

    # Шаг не повторён: 3 результата без дублей (шаг 0 выполнен до паузы).
    snap2 = None
    for root, _dirs, files in os.walk(os.path.join(tmp2, "users")):
        if "task_state.json" in files:
            snap2 = os.path.join(root, "task_state.json")
    with open(snap2, encoding="utf-8") as file:
        raw2 = json.load(file)
    assert raw2["stage"] == "done"
    assert len(raw2["results"]) == 3
    assert len(raw2["results"]) == len(set(raw2["results"]))
    print("ветка 2: пауза → перезапуск → resume → done (без дублей) OK")

    print("M3+M4 REPL SMOKE: ВСЁ OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
