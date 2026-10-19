# -*- coding: utf-8 -*-
"""Юнит-тесты хранилища (storage): иерархия, CRUD, ProfileRepository."""
import json
import os
import sys
import tempfile

# Путь к корню дня для импорта storage.*.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from storage.store import Store, safe_name
from storage.db import ProfileRepository


def make_store(tmp_path):
    repo = ProfileRepository(str(tmp_path / "profiles.db"))
    store = Store(str(tmp_path / "users"), profile_repo=repo)
    return store


def test_safe_name():
    assert safe_name("Подбор косметики") == "Подбор_косметики"
    assert safe_name("  a/b*c  ") == "a_b_c"
    assert safe_name("") == "task"


def test_hierarchy_created(tmp_path):
    store = make_store(tmp_path)
    store.ensure_session("alice", "Задача_1", "20260101_120000")
    base = tmp_path / "users" / "alice" / "tasks" / "Задача_1" / "sessions" / "20260101_120000"
    assert base.is_dir()


def test_profile_repo_roundtrip(tmp_path):
    store = make_store(tmp_path)
    profile = {"id": "bob", "name": "Боб", "style": {}, "constraints": {}, "context": {}}
    store.save_profile("bob", profile)
    assert store.profile_repo.exists("bob")
    loaded = store.load_profile("bob")
    assert loaded["name"] == "Боб"


def test_long_term_roundtrip(tmp_path):
    store = make_store(tmp_path)
    data = {"profile_ref": "bob", "tasks": [], "decisions": [], "knowledge": []}
    store.write_long_term("bob", data)
    loaded = store.read_long_term("bob")
    assert loaded["profile_ref"] == "bob"
    assert isinstance(loaded["tasks"], list)


def test_working_roundtrip(tmp_path):
    store = make_store(tmp_path)
    store.write_working("bob", "t1", {"description": "тест"})
    loaded = store.read_working("bob", "t1")
    assert loaded["description"] == "тест"
    # Поля гарантированно есть (канон структуры).
    for key in ("refs", "decisions", "constraints", "facts", "open_questions", "current_state"):
        assert key in loaded


def test_session_roundtrip(tmp_path):
    store = make_store(tmp_path)
    store.write_session("bob", "t1", "s1", {"messages": [{"id": "M1", "role": "user", "content": "hi"}]})
    loaded = store.read_session("bob", "t1", "s1")
    assert loaded["messages"][0]["content"] == "hi"


def test_list_tasks(tmp_path):
    store = make_store(tmp_path)
    store.ensure_task("bob", "a")
    store.ensure_task("bob", "b")
    tasks = store.list_tasks("bob")
    assert tasks == ["a", "b"]