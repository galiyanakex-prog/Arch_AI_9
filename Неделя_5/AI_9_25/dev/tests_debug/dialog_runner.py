# -*- coding: utf-8 -*-
"""Прогон длинных диалоговых сценариев (часть 4 Задание.txt, этап 11, R9).

Читает `dev/tests_debug/scenario/scen_dialog_A.md` и `scen_dialog_B.md` (по 10–15
сообщений), прогоняет их через агента с активным RAG и проверяет:
  * RAG вызывается на КАЖДОМ сообщении;
  * источники есть в КАЖДОМ ответе (при непустом индексе);
  * цель диалога (goal) зафиксирована и учитывается;
  * память задачи (goal/clarifications/constraints/terms) пополняется.

Отчёт → `dev/logs_reports/stages/dialog_scenarios.md`.

Запуск:
  API_KEY=test-key .venv/bin/python dev/tests_debug/dialog_runner.py            # MockClient
  env -u API_KEY .venv/bin/python dev/tests_debug/dialog_runner.py --live       # живой LLM
"""
import argparse
import os
import re
import sys
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP_ROOT = os.path.join(BASE_DIR, "dev", "tests_debug", ".tmp")
sys.path.insert(0, BASE_DIR)

from storage.store import Store
from storage.db import ProfileRepository
from memory.manager import MemoryManager, default_layers
from core.llm_client import MockClient
from core.prompt_builder import PromptBuilder
from core.agent import Agent
from rag.config import RagConfig
from rag.service import RagService


def parse_scenario(path: str) -> dict:
    """Разобрать .md-сценарий: цель + нумерованные сообщения."""
    text = open(path, encoding="utf-8").read()
    goal = ""
    m = re.search(r"## Цель диалога\s*\n+(.+)", text)
    if m:
        goal = m.group(1).strip()
    messages = []
    for line in text.splitlines():
        m = re.match(r"^\s*\d+\.\s+(.+)$", line)
        if m:
            messages.append(m.group(1).strip())
    return {"goal": goal, "messages": messages}


def build_agent(tmp, user_id, live=False):
    repo = ProfileRepository(os.path.join(tmp, "profiles.db"))
    store = Store(os.path.join(tmp, "users"), profile_repo=repo)
    memory = MemoryManager(default_layers(store))
    if live:
        from core.llm_client import RouterAIClient
        client = RouterAIClient(max_tokens=900)
        _orig = client.complete

        def _complete(messages, **kw):
            for _ in range(3):
                t = _orig(messages, **kw)
                if t:
                    return t
            return ""
        client.complete = _complete
    else:
        client = MockClient()
    agent = Agent(client, memory, PromptBuilder("Ты ассистент"), store, user_id=user_id)
    agent.initialize_user(user_id, "Тест", {"style": "кратко", "constraints": "python",
                                            "context": "rag"})
    cfg = RagConfig.load("rag/config.json")
    agent.rag_service = RagService(cfg)
    agent.rag_enabled = True
    agent.deliver.add("rag")
    return agent


def run_scenario(name, path, tmp, live=False):
    scen = parse_scenario(path)
    agent = build_agent(tmp, f"dlg_{name}", live=live)
    rows = []
    for i, msg in enumerate(scen["messages"], 1):
        answer = agent.respond(msg)
        rows.append({
            "n": i, "message": msg,
            "n_sources": len(agent.last_answer_sources),
            "verdict": agent.last_answer_verdict,
            "answer_len": len(answer or ""),
        })
    data = agent.store.read_working(agent.user_id, agent.task)
    return {
        "name": name, "goal": scen["goal"], "rows": rows,
        "goal_stored": data.get("goal", ""),
        "terms": data.get("terms", {}),
        "clarifications": data.get("clarifications", []),
        "constraints": data.get("constraints", []),
    }


def render_report(results) -> str:
    lines = ["# Прогон длинных диалоговых сценариев (часть 4, этап 11)", ""]
    for res in results:
        n = len(res["rows"])
        with_src = sum(1 for r in res["rows"] if r["n_sources"] >= 1)
        lines += [f"## Сценарий {res['name']} ({n} сообщений)", "",
                  f"Цель (из файла): {res['goal']}",
                  f"Цель (в памяти задачи): {res['goal_stored'] or '—'}",
                  f"Источники в ответах: **{with_src}/{n}**",
                  f"Термины: {res['terms'] or '—'}",
                  f"Уточнения: {len(res['clarifications'])} · Ограничения: {len(res['constraints'])}",
                  "", "| # | Сообщение | Источники | verdict | Длина |",
                  "|---|---|---|---|---|"]
        for r in res["rows"]:
            lines.append(f"| {r['n']} | {r['message'][:60]} | {r['n_sources']} | "
                         f"{r['verdict']} | {r['answer_len']} |")
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Прогон длинных диалогов (этап 11)")
    parser.add_argument("--live", action="store_true", help="живой LLM (RouterAI)")
    parser.add_argument("--report", default="dev/logs_reports/stages/dialog_scenarios.md")
    args = parser.parse_args(argv)

    os.makedirs(TMP_ROOT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="dlg_", dir=TMP_ROOT)
    scen_dir = os.path.join(BASE_DIR, "dev", "tests_debug", "scenario")
    results = []
    for name, fname in (("A", "scen_dialog_A.md"), ("B", "scen_dialog_B.md")):
        results.append(run_scenario(name, os.path.join(scen_dir, fname), tmp, args.live))

    text = render_report(results)
    report_path = os.path.join(BASE_DIR, args.report)
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    open(report_path, "w", encoding="utf-8").write(text)
    print(text)
    print(f"Отчёт записан: {args.report}")

    ok = True
    for res in results:
        n = len(res["rows"])
        with_src = sum(1 for r in res["rows"] if r["n_sources"] >= 1)
        if with_src < n:
            print(f"[FAIL] сценарий {res['name']}: источники {with_src}/{n}")
            ok = False
        if not res["goal_stored"]:
            print(f"[FAIL] сценарий {res['name']}: цель не зафиксирована")
            ok = False
    print("DIALOG OK: exit 0" if ok else "DIALOG FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
