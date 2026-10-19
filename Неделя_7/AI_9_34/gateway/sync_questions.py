# -*- coding: utf-8 -*-
"""gateway/sync_questions.py — обновление снапшота вопросов интервью на VPS.

Запускается **на хосте** (там, где есть ядро `core/agent.py`). Читает канонические
вопросы из `core.agent.INTERVIEW_QUESTIONS`, пересобирает `gateway/questions.json`
(снапшот с отпечатком) и печатает готовые команды: скопировать снапшот на VPS и
перезапустить шлюз.

Зачем: вопросы интервью — единый источник истины (решение №26). Если на хосте
вопросы изменили, снапшот на VPS устареет, и шлюз покажет
«вопросы интервью устарели, обратитесь к администратору». Этот скрипт устраняет
расхождение.

Использование (на хосте, из корня AI_9):
    .venv/bin/python gateway/sync_questions.py
    .venv/bin/python gateway/sync_questions.py --print-only   # только показать
"""
import argparse
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from core.agent import (  # noqa: E402
    INTERVIEW_QUESTIONS, interview_questions_fingerprint,
)

SNAPSHOT_PATH = os.path.join(BASE_DIR, "gateway", "questions.json")
VPS_SNAPSHOT = "/home/t/doc/AI_9/gateway/questions.json"


def build_snapshot() -> dict:
    """Снапшот вопросов: отпечаток + список `{key, question}` (канон из ядра)."""
    return {
        "version": interview_questions_fingerprint(),
        "questions": [{"key": key, "question": question}
                      for key, question in INTERVIEW_QUESTIONS],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Пересобрать снапшот вопросов интервью для шлюза на VPS.")
    parser.add_argument("--print-only", action="store_true",
                        help="Только показать снапшот, не записывать файл.")
    args = parser.parse_args()

    snapshot = build_snapshot()
    print(f"[sync_questions] отпечаток: {snapshot['version']}")
    for item in snapshot["questions"]:
        print(f"  - {item['key']}: {item['question']}")

    if args.print_only:
        return 0

    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as handle:
        json.dump(snapshot, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"[sync_questions] записан снапшот: {SNAPSHOT_PATH}")

    print("\nСкопируйте снапшот на VPS и перезапустите шлюз (команды на ХОСТЕ):")
    print(f"  rsync -av gateway/questions.json mcp-vps:{VPS_SNAPSHOT}")
    print("  ssh mcp-vps 'systemctl --user restart ai9-gateway'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
