# -*- coding: utf-8 -*-
"""gateway/app.py — шлюз на VPS: вход, регистрация, интервью, чат, лимиты.

Шлюз стоит между интернетом и домашним агентом. Он НЕ содержит бизнес-логики
агента: память, RAG, выбор модели «в обход» реестра — всё это на хосте (фасад
`serve.py`). Здесь только: пользователи, сессии, история чата, лимиты и
проксирование запросов на фасад через SSH-туннель.

Границы (мастер-план §4, этап 10):
  - публичный порт — 8080 (решение №22); MCP :8000/:8010/:8020 не трогаются;
  - пароли — только хэшами (см. `users.py`); секрет сессии — env `GATEWAY_SECRET`
    или автосекрет `gateway/.secret` (решение №27);
  - лимиты: 6 запросов/мин на пользователя → 429; > 8000 символов → отказ
    ДО обращения к фасаду; лимит частоты — in-memory (решение №25);
  - недоступный фасад → 503 с понятным текстом, не зависание;
  - вопросы интервью — снапшот с отпечатком, сверяется с хостом (решение №26);
  - идемпотентность повтора (этап 11): один `request_id` → один ответ; повтор
    после обрыва не дублирует реплики и не гонит запрос на фасад заново;
  - шлюз НЕ импортирует `Kod.py`/`rag/` — только HTTP к фасаду.

Запуск (на VPS):
    python -m gateway.app
"""
import os
import sys
import threading
import time
from collections import deque

import requests
from flask import (Flask, jsonify, redirect, render_template, request, session,
                   url_for)

# Пакет `gateway` импортируется и как модуль (`python -m gateway.app`), и как
# отдельный файл — поддерживаем оба варианта импорта соседей.
try:
    from .config import load_config, session_secret
    from . import users as users_db
    from . import questions as questions_snapshot
except ImportError:  # запуск как `python gateway/app.py`
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from config import load_config, session_secret  # type: ignore
    import users as users_db  # type: ignore
    import questions as questions_snapshot  # type: ignore

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(BASE_DIR, "users.db")

# Сообщение при расхождении вопросов интервью (решение №26).
STALE_QUESTIONS_MESSAGE = ("Вопросы интервью устарели — обратитесь к администратору.")


class FacadeUnavailable(Exception):
    """Фасад (домашний агент) недоступен: туннель лёг или дом выключен."""


class FacadeClient:
    """HTTP-клиент фасада хоста (через SSH reverse tunnel). Без бизнес-логики."""

    def __init__(self, base_url: str, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict = None):
        url = self.base_url + path
        try:
            response = requests.request(method, url, json=payload,
                                        timeout=self.timeout)
        except requests.RequestException as error:
            raise FacadeUnavailable(str(error)) from error
        if response.status_code >= 500:
            raise FacadeUnavailable(f"фасад вернул {response.status_code}")
        try:
            return response.status_code, response.json()
        except ValueError:
            return response.status_code, {"error": "некорректный ответ фасада"}

    def get_models(self):
        return self._request("GET", "/models")

    def ask(self, user, text, provider=None, model=None):
        payload = {"user": user, "text": text}
        if provider:
            payload["provider"] = provider
        if model:
            payload["model"] = model
        return self._request("POST", "/ask", payload)

    def set_model(self, user, provider=None, model=None):
        payload = {"user": user}
        if provider:
            payload["provider"] = provider
        if model:
            payload["model"] = model
        return self._request("POST", "/model", payload)

    def interview(self, user, name=None, answers=None):
        return self._request("POST", "/interview",
                             {"user": user, "name": name, "answers": answers or {}})

    def interview_questions(self):
        """Канонические вопросы интервью с хоста (для сверки отпечатка, №26)."""
        return self._request("GET", "/interview/questions")


def create_app(config: dict = None, facade=None, db_path: str = None) -> Flask:
    """Собирает Flask-приложение шлюза. `facade` — заглушка для тестов."""
    cfg = config or load_config()
    db_path = db_path or DEFAULT_DB
    users_db.init_db(db_path)
    facade = facade or FacadeClient(cfg["host_facade_url"],
                                    cfg["facade_timeout_seconds"])

    app = Flask(__name__)
    app.secret_key = session_secret(cfg)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = \
        cfg["session"]["max_age_minutes"] * 60

    limits = cfg["limits"]
    keep = cfg["history_keep_messages"]
    # Лимит частоты: окно 60 с, счётчик на пользователя.
    # ВАЖНО (решение №25): счётчики живут В ПАМЯТИ процесса и сбрасываются при
    # рестарте шлюза. Это осознанное ограничение (лимит — против случайного
    # флуда, не против злоумышленника); персистентность решено НЕ вводить
    # (этап 11). Значения (6/мин, 8000 символов) — в gateway.json, не в коде.
    # Блокировка — чтобы параллельные запросы не «проскочили» лимит гонкой
    # (Flask работает в threaded=True).
    rate_window = 60.0
    rate_state = {}
    rate_lock = threading.Lock()

    def _rate_ok(login: str) -> bool:
        """True — запрос разрешён; False — превышен лимит (6/мин)."""
        now = time.time()
        with rate_lock:
            stamps = rate_state.setdefault(login, deque())
            while stamps and now - stamps[0] > rate_window:
                stamps.popleft()
            if len(stamps) >= limits["requests_per_minute"]:
                return False
            stamps.append(now)
            return True

    def _current_user():
        return session.get("login")

    def _log(event: str, **fields):
        # Лог пишет «кто, когда, сколько символов, какая модель» — но НЕ текст
        # ответа (решение №28): ответ и так хранится в истории чата на VPS и в
        # Den_log.md фасада. Это защита приватности переписок и объёма журнала.
        parts = " ".join(f"{k}={v}" for k, v in fields.items())
        print(f"[Шлюз] {event} {parts}".rstrip(), flush=True)

    # --- Страницы -------------------------------------------------------------

    @app.route("/")
    def index():
        if _current_user():
            return redirect(url_for("chat"))
        return redirect(url_for("login"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "GET":
            return render_template("register.html")
        login = (request.form.get("login") or "").strip()
        password = request.form.get("password") or ""
        if not login or not password:
            return render_template("register.html",
                                   error="Логин и пароль обязательны."), 400
        if not users_db.register(db_path, login, password):
            return render_template("register.html",
                                   error="Такой логин уже занят."), 409
        session["login"] = login
        session.permanent = True
        _log("register", login=login)
        return redirect(url_for("interview"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            return render_template("login.html")
        login = (request.form.get("login") or "").strip()
        password = request.form.get("password") or ""
        if not users_db.verify(db_path, login, password):
            _log("login_failed", login=login)
            return render_template("login.html",
                                   error="Неверный логин или пароль."), 401
        session["login"] = login
        session.permanent = True
        _log("login", login=login)
        return redirect(url_for("chat"))

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/interview", methods=["GET", "POST"])
    def interview():
        login = _current_user()
        if not login:
            return redirect(url_for("login"))
        # Вопросы — из снапшота (единый источник истины, решение №26).
        questions = questions_snapshot.questions_for_form()
        if request.method == "GET":
            # Сверяем отпечаток снапшота с хостовым. Расхождение/недоступность →
            # форму не показываем, а просим обратиться к администратору.
            try:
                _, host = facade.interview_questions()
                host_version = host.get("version")
            except FacadeUnavailable:
                return render_template("interview.html", questions=[],
                                       error="Сервис временно недоступен."), 503
            if not questions_snapshot.is_fresh(host_version):
                _log("interview_stale", login=login,
                     local=questions_snapshot.snapshot_version(),
                     host=host_version)
                return render_template("interview.html", questions=[],
                                       error=STALE_QUESTIONS_MESSAGE), 409
            return render_template("interview.html", questions=questions)
        name = (request.form.get("name") or login).strip()
        answers = {key: (request.form.get(key) or "").strip()
                   for key, _ in questions}
        try:
            facade.interview(login, name=name, answers=answers)
        except FacadeUnavailable:
            return render_template("interview.html", questions=questions,
                                   error="Сервис временно недоступен."), 503
        _log("interview", login=login)
        return redirect(url_for("chat"))

    @app.route("/chat")
    def chat():
        login = _current_user()
        if not login:
            return redirect(url_for("login"))
        history = users_db.get_history(db_path, login)
        return render_template("chat.html", login=login, history=history)

    # --- JSON API -------------------------------------------------------------

    @app.route("/api/models")
    def api_models():
        if not _current_user():
            return jsonify({"error": "Требуется вход."}), 401
        try:
            status, data = facade.get_models()
        except FacadeUnavailable:
            return jsonify({"error": "Сервис временно недоступен."}), 503
        return jsonify(data), status

    @app.route("/api/model", methods=["POST"])
    def api_model():
        login = _current_user()
        if not login:
            return jsonify({"error": "Требуется вход."}), 401
        data = request.get_json(silent=True) or {}
        try:
            status, payload = facade.set_model(login, provider=data.get("provider"),
                                               model=data.get("model"))
        except FacadeUnavailable:
            return jsonify({"error": "Сервис временно недоступен."}), 503
        _log("model", login=login, model=data.get("model") or data.get("provider"))
        return jsonify(payload), status

    @app.route("/api/ask", methods=["POST"])
    def api_ask():
        login = _current_user()
        if not login:
            return jsonify({"error": "Требуется вход."}), 401
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"error": "Пустой запрос."}), 400
        # Лимит длины — ДО обращения к фасаду (решение №17).
        if len(text) > limits["max_query_chars"]:
            return jsonify({"error": f"Запрос длиннее {limits['max_query_chars']} "
                                     f"символов — сократите."}), 413
        # Лимит частоты — 6/мин на пользователя.
        if not _rate_ok(login):
            return jsonify({"error": "Слишком часто, подождите минуту."}), 429

        # Идемпотентность повтора (этап 11): один request_id → один ответ.
        # Повтор после обрыва с тем же id НЕ гонит запрос на фасад заново и НЕ
        # дублирует реплики в истории.
        request_id = (data.get("request_id") or "").strip()
        if request_id:
            existing = users_db.get_request(db_path, login, request_id)
            if existing and existing["status"] == "done":
                _log("ask_repeat", login=login, request_id=request_id)
                return jsonify({"answer": existing["answer"],
                                "model": existing["model"], "sources": [],
                                "quotes": [], "verdict": "unchecked",
                                "usage": {}, "duration_seconds": 0.0,
                                "repeated": True}), 200
            if existing and existing["status"] == "pending":
                # Первый запрос ещё в работе (или шлюз упал во время генерации).
                # Не запускаем второй — иначе получим дубликат ответа.
                return jsonify({"error": "Запрос уже обрабатывается, подождите."}), 409
            users_db.begin_request(db_path, login, request_id)

        users_db.add_message(db_path, login, "user", text, keep=keep)
        try:
            status, payload = facade.ask(login, text,
                                         provider=data.get("provider"),
                                         model=data.get("model"))
        except FacadeUnavailable:
            # Ответа нет — снимаем «pending», чтобы повтор был возможен.
            users_db.drop_request(db_path, login, request_id)
            _log("ask_unavailable", login=login, chars=len(text))
            return jsonify({"error": "Сервис временно недоступен."}), 503
        if status >= 400:
            users_db.drop_request(db_path, login, request_id)
            return jsonify(payload), status
        answer = payload.get("answer", "")
        model = payload.get("model")
        # Реплика ассистента пишется ТОЛЬКО после полного ответа: обрыв во время
        # генерации не оставляет «половину ответа, записанную как полный».
        users_db.add_message(db_path, login, "assistant", answer, model=model,
                             keep=keep)
        users_db.finish_request(db_path, login, request_id, answer, model=model)
        _log("ask", login=login, chars=len(text), model=model)
        return jsonify(payload), status

    @app.route("/api/history")
    def api_history():
        login = _current_user()
        if not login:
            return jsonify({"error": "Требуется вход."}), 401
        return jsonify({"history": users_db.get_history(db_path, login)})

    # Для тестов: сброс счётчиков лимита.
    app.rate_state = rate_state
    return app


def main():
    cfg = load_config()
    app = create_app(cfg)
    host = os.getenv("GATEWAY_HOST", "0.0.0.0")
    port = int(os.getenv("GATEWAY_PORT", cfg["public_port"]))
    print(f"[Шлюз] слушает http://{host}:{port} → фасад {cfg['host_facade_url']}",
          flush=True)
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
