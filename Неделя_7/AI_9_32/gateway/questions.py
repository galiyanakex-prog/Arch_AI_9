# -*- coding: utf-8 -*-
"""gateway/questions.py — снапшот вопросов интервью на VPS (решение №26).

Вопросы интервью — единый источник истины: канон живёт в `core/agent.py`
(`INTERVIEW_QUESTIONS` + отпечаток). Шлюз на VPS не может импортировать ядро
(граница этапа 10), поэтому хранит **снапшот** `gateway/questions.json` с тем же
отпечатком. При открытии формы шлюз сверяет свой отпечаток с хостовым
(`GET /interview/questions`); расхождение → «вопросы интервью устарели».

Обновление снапшота — скриптом `gateway/sync_questions.py` (запускается на хосте).
"""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATH = os.path.join(BASE_DIR, "questions.json")


def load_snapshot(path: str = None) -> dict:
    """Читает снапшот вопросов: `{"version": <отпечаток>, "questions": [...]}`.

    Отсутствие/порча файла → пустой снапшот (шлюз покажет «вопросы устарели»).
    """
    path = path or DEFAULT_PATH
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"version": None, "questions": []}
    questions = data.get("questions") or []
    return {"version": data.get("version"), "questions": questions}


def snapshot_version(path: str = None) -> str:
    """Отпечаток снапшота (None, если файла нет)."""
    return load_snapshot(path).get("version")


def questions_for_form(path: str = None) -> list:
    """Список `(key, question)` для шаблона формы интервью."""
    return [(item.get("key"), item.get("question"))
            for item in load_snapshot(path).get("questions", [])]


def is_fresh(host_version: str, path: str = None) -> bool:
    """True — снапшот совпадает с хостовым отпечатком (вопросы актуальны)."""
    local = snapshot_version(path)
    return bool(local) and local == host_version
