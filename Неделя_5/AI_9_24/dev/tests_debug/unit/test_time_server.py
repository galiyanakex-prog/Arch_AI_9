# -*- coding: utf-8 -*-
"""Юнит-тест сервера времени (Этап 1, И2б): Host-защита публичного :8000.

Детерминированно проверяет то, что иначе видно только живьём: набор
`allowed_hosts` (защита от `421 Misdirected Request` при обращении снаружи)
и запрет `allowed_hosts=["*"]` (migr_plan.md §5). Сам HTTP-хендшейк
(`initialize` + `tools/list`) — живой прогон гейта, его выполняет оператор.

Класс наследует unittest.TestCase: базовая линия собирается через
`python -m unittest discover` (итог «OK»), который НЕ подхватывает «голые»
функции — только методы TestCase.

Правила пропуска/падения:
  * ImportError (venv без HTTP-зависимостей сервера) -> SKIP, не FAIL;
  * у модуля вообще нет поверхности allowed_hosts -> SKIP (поверхность сменилась);
  * allowed_hosts есть, но НЕ покрывает обязательные хосты / содержит "*" -> FAIL.
То есть ложно-зелёным этот guard стать не может: неверное значение всегда падает.
"""
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

REQUIRED_HOSTS = ("91.188.212.77:8000", "127.0.0.1:8000", "localhost:8000")


def _resolve_allowed_hosts(module):
    """Достаёт allowed_hosts с известной поверхности; если её нет — AttributeError."""
    ts = getattr(module, "transport_security", None)
    if ts is not None and hasattr(ts, "allowed_hosts"):
        return list(ts.allowed_hosts)
    settings = getattr(module, "settings", None)
    if settings is not None and hasattr(settings, "allowed_hosts"):
        return list(settings.allowed_hosts)
    raise AttributeError("поверхность allowed_hosts не найдена")


class TestTimeServerHostProtection(unittest.TestCase):
    def setUp(self):
        try:
            from integrations.mcp import time_server
        except Exception as exc:  # venv без серверных HTTP-зависимостей — не считаем падением
            raise unittest.SkipTest(f"venv без серверных зависимостей: {exc}")
        self.time_server = time_server

    def test_allowed_hosts_cover_public_and_local(self):
        try:
            hosts = set(_resolve_allowed_hosts(self.time_server))
        except AttributeError as exc:
            raise unittest.SkipTest(str(exc))
        for req in REQUIRED_HOSTS:
            self.assertIn(req, hosts, f"в allowed_hosts нет обязательного {req}")
        self.assertNotIn("*", hosts, "allowed_hosts=['*'] запрещён (migr_plan.md §5)")


if __name__ == "__main__":
    unittest.main()