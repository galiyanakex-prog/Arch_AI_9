# -*- coding: utf-8 -*-
"""Лёгкий раннер юнит-тестов без pytest (venv дня не содержит pytest, §6.1).

Запуск: $PY tests_debug/unit_runner.py [модуль]
  без аргумента — все test_*.py из tests_debug/unit/;
  с аргументом  — только указанный модуль (например test_storage).
Выход 0 — все тесты зелёные; 1 — есть падения (с трейсбеком).
"""
import importlib.util
import inspect
import os
import sys
import tempfile
import traceback
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNIT_DIR = os.path.join(BASE_DIR, "tests_debug", "unit")
# Все временные артефакты прогонов — только в tests_debug/.tmp (не в /tmp и не в users/ дня).
TMP_ROOT = os.path.join(BASE_DIR, "tests_debug", ".tmp")
sys.path.insert(0, BASE_DIR)


def load_module(path):
    name = os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_tmpdir():
    """Общая временная директория для тестов (pathlib.Path)."""
    os.makedirs(TMP_ROOT, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="unit_", dir=TMP_ROOT))


def main():
    if not os.path.isdir(UNIT_DIR):
        print("Каталог unit не найден:", UNIT_DIR)
        return 1

    only = sys.argv[1] if len(sys.argv) > 1 else None
    test_files = sorted(
        os.path.join(UNIT_DIR, f) for f in os.listdir(UNIT_DIR)
        if f.startswith("test_") and f.endswith(".py")
        and (only is None or f == only or f.startswith(only))
    )

    passed = 0
    failed = 0

    for path in test_files:
        module = load_module(path)
        tests = [
            (name, fn) for name, fn in vars(module).items()
            if name.startswith("test_") and callable(fn)
        ]
        for name, fn in tests:
            tmp_path = make_tmpdir()
            # Передаём tmp_path только если функция его принимает (иначе TypeError).
            sig = inspect.signature(fn)
            try:
                if len(sig.parameters) > 0:
                    fn(tmp_path)
                else:
                    fn()
                passed += 1
                print(f"  OK  {os.path.basename(path)}::{name}")
            except Exception as error:
                failed += 1
                print(f"FAIL  {os.path.basename(path)}::{name}: {error}")
                traceback.print_exc()

    print(f"\nИтого: {passed} OK, {failed} FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())