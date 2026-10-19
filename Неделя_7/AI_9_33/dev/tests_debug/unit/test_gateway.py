# -*- coding: utf-8 -*-
"""Юнит-тесты шлюза на VPS (Ревизия 8, этап 10, S2).

Flask test client, без сети: фасад — заглушка (StubFacade). Проверяем контракты
шлюза: регистрация создаёт пользователя и не хранит пароль открытым; вход выдаёт
сессию, без входа — отказ; лимит срабатывает на 7-м запросе и НЕ срабатывает на
6-и; запрос длиннее лимита отклоняется без обращения к фасаду; недоступный фасад →
503 с текстом, не зависание; выбор модели уходит в запрос к фасаду.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

from gateway import app as gateway_app  # noqa: E402
from gateway import users as users_db  # noqa: E402


class StubFacade:
    """Заглушка фасада: считает вызовы, умеет «падать» (недоступность)."""

    def __init__(self):
        self.calls = []
        self.unavailable = False
        # Отпечаток вопросов, который «отдаёт хост» (по умолчанию — как в снапшоте).
        self.questions_version = gateway_app.questions_snapshot.snapshot_version()

    def _maybe_fail(self):
        if self.unavailable:
            raise gateway_app.FacadeUnavailable("туннель лёг")

    def get_models(self):
        self._maybe_fail()
        self.calls.append(("models",))
        return 200, {"current": "cloud:stepfun/step-3.5-flash",
                     "providers": ["cloud", "lmstudio"],
                     "models": [{"id": "lmstudio:qwen3b", "service": "lmstudio",
                                 "model": "qwen3b", "label": "lmstudio/qwen3b"}]}

    def ask(self, user, text, provider=None, model=None):
        self._maybe_fail()
        self.calls.append(("ask", user, text, provider, model))
        return 200, {"answer": "ответ-заглушка", "model": model or "cloud/x",
                     "sources": [], "quotes": [], "verdict": "unchecked",
                     "usage": {}, "duration_seconds": 0.1}

    def set_model(self, user, provider=None, model=None):
        self._maybe_fail()
        self.calls.append(("model", user, provider, model))
        return 200, {"model": model or provider, "switched_to": model or provider}

    def interview(self, user, name=None, answers=None):
        self._maybe_fail()
        self.calls.append(("interview", user, name, answers))
        return 200, {"user": user, "initialized": True, "model": "cloud/x"}

    def interview_questions(self):
        self._maybe_fail()
        self.calls.append(("questions",))
        return 200, {"version": self.questions_version,
                     "questions": [{"key": "style", "question": "…"}]}


def _make(tmp_path, facade=None):
    """Свежее приложение шлюза с изолированной БД и заглушкой фасада."""
    db = os.path.join(str(tmp_path), "users.db")
    facade = facade or StubFacade()
    # Секрет сессии — из env, чтобы тесты не создавали gateway/.secret.
    os.environ.setdefault("GATEWAY_SECRET", "test-secret")
    app = gateway_app.create_app(config=gateway_app.load_config(),
                                 facade=facade, db_path=db)
    app.config["TESTING"] = True
    return app, facade, db


def _register(client, login="alice", password="secret"):
    return client.post("/register", data={"login": login, "password": password})


# --- регистрация и вход -------------------------------------------------------

def test_register_creates_user_without_plaintext_password(tmp_path):
    """Регистрация создаёт пользователя; пароль НЕ хранится открытым текстом."""
    app, _, db = _make(tmp_path)
    client = app.test_client()
    resp = _register(client, "alice", "s3cret!")
    assert resp.status_code in (302, 303)
    assert users_db.exists(db, "alice")
    # В БД нет открытого пароля: только соль и хэш.
    import sqlite3
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT salt, pwhash FROM users WHERE login='alice'").fetchone()
    assert row is not None
    assert "s3cret!" not in row[0] and "s3cret!" not in row[1]
    assert len(row[1]) == 64  # hex PBKDF2-SHA256


def test_register_duplicate_login_rejected(tmp_path):
    """Повторная регистрация того же логина → 409."""
    app, _, _ = _make(tmp_path)
    client = app.test_client()
    _register(client, "bob", "pw")
    resp = _register(client, "bob", "pw2")
    assert resp.status_code == 409


def test_login_grants_session_and_wrong_password_denied(tmp_path):
    """Верный пароль → сессия; неверный → 401."""
    app, _, _ = _make(tmp_path)
    client = app.test_client()
    _register(client, "carol", "right")
    client.get("/logout")
    assert client.post("/login", data={"login": "carol", "password": "wrong"}).status_code == 401
    resp = client.post("/login", data={"login": "carol", "password": "right"})
    assert resp.status_code in (302, 303)
    # Сессия работает: /chat доступен.
    assert client.get("/chat").status_code == 200


def test_api_requires_login(tmp_path):
    """Без входа JSON-API → 401 (отказ)."""
    app, _, _ = _make(tmp_path)
    client = app.test_client()
    assert client.post("/api/ask", json={"text": "привет"}).status_code == 401
    assert client.get("/api/models").status_code == 401


# --- лимиты -------------------------------------------------------------------

def test_rate_limit_blocks_seventh_allows_sixth(tmp_path):
    """6 запросов проходят, 7-й → 429 (лимит 6/мин)."""
    app, facade, _ = _make(tmp_path)
    client = app.test_client()
    _register(client, "dave", "pw")
    codes = [client.post("/api/ask", json={"text": f"вопрос {i}"}).status_code
             for i in range(7)]
    assert codes[:6] == [200] * 6
    assert codes[6] == 429
    # На фасад ушло ровно 6 запросов (7-й отклонён до обращения).
    assert sum(1 for c in facade.calls if c[0] == "ask") == 6


def test_long_query_rejected_before_facade(tmp_path):
    """Запрос длиннее лимита → 413, фасад НЕ вызывается."""
    app, facade, _ = _make(tmp_path)
    client = app.test_client()
    _register(client, "erin", "pw")
    long_text = "я" * 8001
    resp = client.post("/api/ask", json={"text": long_text})
    assert resp.status_code == 413
    assert not any(c[0] == "ask" for c in facade.calls)


# --- недоступный фасад --------------------------------------------------------

def test_unavailable_facade_returns_503(tmp_path):
    """Недоступный фасад → 503 с текстом, не зависание."""
    app, facade, _ = _make(tmp_path)
    client = app.test_client()
    _register(client, "frank", "pw")
    facade.unavailable = True
    resp = client.post("/api/ask", json={"text": "привет"})
    assert resp.status_code == 503
    assert "недоступен" in resp.get_json()["error"]


# --- выбор модели уходит на фасад ---------------------------------------------

def test_model_choice_goes_to_facade(tmp_path):
    """Выбор модели уходит в запрос к фасаду (POST /model)."""
    app, facade, _ = _make(tmp_path)
    client = app.test_client()
    _register(client, "gina", "pw")
    resp = client.post("/api/model", json={"provider": "lmstudio", "model": "lmstudio:qwen3b"})
    assert resp.status_code == 200
    assert any(c[0] == "model" for c in facade.calls)


# --- интервью и история -------------------------------------------------------

def test_interview_goes_to_facade(tmp_path):
    """Интервью уходит на фасад (POST /interview)."""
    app, facade, _ = _make(tmp_path)
    client = app.test_client()
    _register(client, "hank", "pw")
    resp = client.post("/interview", data={"name": "Ханк", "style": "краткий",
                                           "constraints": "", "context": ""})
    assert resp.status_code in (302, 303)
    assert any(c[0] == "interview" for c in facade.calls)


# --- вопросы интервью: единый источник истины (решение №26) -------------------

def test_interview_form_shown_when_questions_fresh(tmp_path):
    """Отпечатки совпали → форма интервью показывается (200)."""
    app, facade, _ = _make(tmp_path)
    client = app.test_client()
    _register(client, "quinn", "pw")
    resp = client.get("/interview")
    assert resp.status_code == 200
    assert any(c[0] == "questions" for c in facade.calls)


def test_interview_stale_questions_message(tmp_path):
    """Отпечатки разошлись → сообщение «вопросы устарели», формы нет (409)."""
    app, facade, _ = _make(tmp_path)
    facade.questions_version = "deadbeef"  # хост «обновил» вопросы
    client = app.test_client()
    _register(client, "rita", "pw")
    resp = client.get("/interview")
    assert resp.status_code == 409
    body = resp.get_data(as_text=True)
    assert "устарели" in body
    assert "администратору" in body


def test_interview_unavailable_facade_returns_503(tmp_path):
    """Недоступный фасад при открытии интервью → 503, не зависание."""
    app, facade, _ = _make(tmp_path)
    client = app.test_client()
    _register(client, "sam", "pw")
    facade.unavailable = True
    resp = client.get("/interview")
    assert resp.status_code == 503


# --- секрет сессии: автосекрет в gateway/.secret (решение №27) ----------------

def test_session_secret_autogenerated_file(tmp_path):
    """Без env GATEWAY_SECRET секрет генерируется и кладётся в файл."""
    from gateway import config as gateway_config
    saved = os.environ.pop("GATEWAY_SECRET", None)
    try:
        secret_path = os.path.join(str(tmp_path), ".secret")
        cfg = {"session": {"secret_env": "GATEWAY_SECRET",
                           "secret_file": secret_path}}
        first = gateway_config.session_secret(cfg)
        assert first and first != "dev-insecure-gateway-secret"
        assert os.path.exists(secret_path)
        # Повторный вызов читает тот же секрет из файла (стабильность сессий).
        assert gateway_config.session_secret(cfg) == first
    finally:
        if saved is not None:
            os.environ["GATEWAY_SECRET"] = saved


def test_session_secret_from_env(tmp_path):
    """Env GATEWAY_SECRET имеет приоритет над файлом."""
    from gateway import config as gateway_config
    saved = os.environ.get("GATEWAY_SECRET")
    os.environ["GATEWAY_SECRET"] = "env-secret"
    try:
        cfg = {"session": {"secret_env": "GATEWAY_SECRET",
                           "secret_file": os.path.join(str(tmp_path), ".secret")}}
        assert gateway_config.session_secret(cfg) == "env-secret"
    finally:
        if saved is None:
            os.environ.pop("GATEWAY_SECRET", None)
        else:
            os.environ["GATEWAY_SECRET"] = saved


def test_history_persists_on_vps(tmp_path):
    """История чата хранится на VPS и переживает переподключение."""
    app, _, db = _make(tmp_path)
    client = app.test_client()
    _register(client, "ivy", "pw")
    client.post("/api/ask", json={"text": "первый вопрос"})
    history = users_db.get_history(db, "ivy")
    roles = [m["role"] for m in history]
    assert "user" in roles and "assistant" in roles
    # Новый клиент (переподключение) видит ту же историю.
    client2 = app.test_client()
    client2.post("/login", data={"login": "ivy", "password": "pw"})
    resp = client2.get("/api/history")
    assert resp.status_code == 200
    assert len(resp.get_json()["history"]) == len(history)


# --- идемпотентность повтора (этап 11) ----------------------------------------

def test_repeat_request_id_returns_same_answer_without_duplicate(tmp_path):
    """Повтор с тем же request_id → тот же ответ, без дублей и без нового вызова."""
    app, facade, db = _make(tmp_path)
    client = app.test_client()
    _register(client, "jack", "pw")
    rid = "req-123"
    first = client.post("/api/ask", json={"text": "вопрос", "request_id": rid})
    assert first.status_code == 200
    asks_after_first = sum(1 for c in facade.calls if c[0] == "ask")
    # Повтор с тем же id.
    second = client.post("/api/ask", json={"text": "вопрос", "request_id": rid})
    assert second.status_code == 200
    assert second.get_json()["answer"] == first.get_json()["answer"]
    assert second.get_json().get("repeated") is True
    # На фасад ушёл ровно один запрос (повтор не гонит заново).
    assert sum(1 for c in facade.calls if c[0] == "ask") == asks_after_first
    # В истории ровно одна пара user/assistant (нет дублей).
    history = users_db.get_history(db, "jack")
    assert sum(1 for m in history if m["role"] == "user") == 1
    assert sum(1 for m in history if m["role"] == "assistant") == 1


def test_different_request_ids_create_separate_answers(tmp_path):
    """Разные request_id → разные записи (идемпотентность не мешает новым)."""
    app, facade, db = _make(tmp_path)
    client = app.test_client()
    _register(client, "kate", "pw")
    client.post("/api/ask", json={"text": "раз", "request_id": "a"})
    client.post("/api/ask", json={"text": "два", "request_id": "b"})
    assert sum(1 for c in facade.calls if c[0] == "ask") == 2
    history = users_db.get_history(db, "kate")
    assert sum(1 for m in history if m["role"] == "user") == 2


def test_unavailable_facade_does_not_leave_half_answer(tmp_path):
    """Обрыв во время генерации не оставляет «половину ответа» в истории."""
    app, facade, db = _make(tmp_path)
    client = app.test_client()
    _register(client, "leo", "pw")
    facade.unavailable = True
    resp = client.post("/api/ask", json={"text": "вопрос", "request_id": "x"})
    assert resp.status_code == 503
    # Реплики ассистента нет (ответ не получен) — «половины» не записано.
    history = users_db.get_history(db, "leo")
    assert not any(m["role"] == "assistant" for m in history)
    # Запрос снят с «pending»: повтор после восстановления разрешён.
    assert users_db.get_request(db, "leo", "x") is None


def test_pending_request_blocks_duplicate(tmp_path):
    """Пока запрос в работе (pending), повтор с тем же id → 409, не дубликат."""
    app, facade, db = _make(tmp_path)
    client = app.test_client()
    _register(client, "mia", "pw")
    # Имитируем «зависший» запрос: pending без ответа.
    users_db.begin_request(db, "mia", "busy")
    resp = client.post("/api/ask", json={"text": "вопрос", "request_id": "busy"})
    assert resp.status_code == 409
    assert not any(c[0] == "ask" for c in facade.calls)


# --- границы: шлюз не тянет ядро агента ---------------------------------------

def test_gateway_does_not_import_agent_core():
    """Шлюз не импортирует Kod.py/rag/ — только HTTP к фасаду."""
    source = open(os.path.join(BASE_DIR, "gateway", "app.py"), encoding="utf-8").read()
    assert "import Kod" not in source
    assert "import rag" not in source
    assert "from rag" not in source
