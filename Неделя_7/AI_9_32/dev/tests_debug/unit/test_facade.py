# -*- coding: utf-8 -*-
"""Юнит-тесты тонкого HTTP-фасада (Ревизия 8, этап 9, S1).

Flask test client, без сети: агент — MockClient. Проверяем контракты фасада:
маршруты отвечают; неизвестный пользователь создаётся по существующему механизму;
в ответе всегда есть поле `model`; ошибка агента → понятный HTTP-статус, не 500 с
traceback; очередь держит параллельные запросы; фасад не импортирует `rag/` напрямую.
"""
import os
import sys
import threading
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, BASE_DIR)

# serve.py подменяет argv сам, но подстрахуемся: пустой argv до импорта.
sys.argv = [os.path.join(BASE_DIR, "serve.py")]
import serve  # noqa: E402


def _reset():
    """Сброс кэша агентов и очереди между тестами (изоляция)."""
    with serve._agents_lock:
        serve._agents.clear()
    serve._runtime.update(rag=False, mock=True, model=None)
    if serve._queue_lock.locked():
        serve._queue_lock.release()


def _client():
    serve.app.config["TESTING"] = True
    return serve.app.test_client()


# --- маршруты отвечают --------------------------------------------------------

def test_ask_returns_answer_and_model():
    """POST /ask → непустой ответ + обязательное поле `model`."""
    _reset()
    client = _client()
    resp = client.post("/ask", json={"user": "facade_u1", "text": "привет"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["answer"]
    assert data["model"]
    assert "usage" in data and "sources" in data and "verdict" in data


def test_ask_requires_user_and_text():
    """Пустые user/text → 400, без обращения к агенту."""
    _reset()
    client = _client()
    assert client.post("/ask", json={"text": "x"}).status_code == 400
    assert client.post("/ask", json={"user": "u"}).status_code == 400


def test_models_lists_registry():
    """GET /models → провайдеры и модели из реестра."""
    _reset()
    client = _client()
    resp = client.get("/models")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["current"]
    assert "lmstudio" in data["providers"]
    assert any(m["id"].startswith("lmstudio:") for m in data["models"])


def test_state_reports_model_and_stage():
    """GET /state?user=… → модель, RAG, стадия задачи, alive."""
    _reset()
    client = _client()
    resp = client.get("/state?user=facade_u2")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["model"]
    assert data["alive"] is True
    assert "task_stage" in data


def test_state_requires_user():
    """GET /state без user → 400."""
    _reset()
    client = _client()
    assert client.get("/state").status_code == 400


# --- неизвестный пользователь создаётся ---------------------------------------

def test_unknown_user_is_created():
    """Неизвестный пользователь создаётся по существующему механизму (профиль)."""
    _reset()
    client = _client()
    client.post("/ask", json={"user": "facade_new", "text": "привет"})
    agent = serve._agents["facade_new"]
    assert agent.store.profile_repo.exists("facade_new")


def test_interview_initializes_user():
    """POST /interview → профиль создан, ответ несёт model."""
    _reset()
    client = _client()
    resp = client.post("/interview", json={
        "user": "facade_iv", "name": "Тест",
        "answers": {"style": "краткий", "constraints": "", "context": ""}})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["initialized"] is True
    assert data["model"]
    assert serve._agents["facade_iv"].store.profile_repo.exists("facade_iv")


def test_interview_questions_returns_canon_and_fingerprint():
    """GET /interview/questions → канон вопросов + отпечаток (решение №26)."""
    _reset()
    client = _client()
    resp = client.get("/interview/questions")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["version"]
    keys = [q["key"] for q in data["questions"]]
    assert keys == ["style", "constraints", "context"]
    # Отпечаток совпадает с каноном ядра.
    from core.agent import interview_questions_fingerprint
    assert data["version"] == interview_questions_fingerprint()


# --- переключение модели ------------------------------------------------------

def test_model_switch_changes_label():
    """POST /model → переключение тем же путём, что /model use (подпись меняется)."""
    _reset()
    client = _client()
    client.post("/ask", json={"user": "facade_m", "text": "привет"})
    resp = client.post("/model", json={
        "user": "facade_m",
        "model": "lmstudio:Qwen2.5-Coder-3B-Instruct-Distill-Qwen3-Coder-Next-abliterated-Q6_K"})
    assert resp.status_code == 200
    assert "lmstudio" in resp.get_json()["model"]


def test_model_switch_unknown_id_is_400():
    """Неизвестный id → 400 (KeyError реестра), не 500."""
    _reset()
    client = _client()
    client.post("/ask", json={"user": "facade_m2", "text": "привет"})
    resp = client.post("/model", json={"user": "facade_m2", "model": "bogus:id"})
    assert resp.status_code == 400


# --- очередь на 1 запрос ------------------------------------------------------

def test_queue_serializes_parallel_requests():
    """Очередь держит параллельные запросы: оба получают ответ, ошибок нет."""
    _reset()
    client = _client()
    results = []

    def worker(n):
        resp = client.post("/ask", json={"user": f"facade_q{n}", "text": "привет"})
        results.append(resp.status_code)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert results == [200, 200]


def test_queue_busy_returns_503():
    """Занятая очередь дольше лимита → 503 с текстом, не зависание."""
    _reset()
    client = _client()
    # Имитируем занятую очередь: держим лок в другом потоке.
    serve._queue_lock.acquire()
    saved = serve.QUEUE_WAIT_SECONDS
    serve.QUEUE_WAIT_SECONDS = 0.2
    try:
        resp = client.post("/ask", json={"user": "facade_busy", "text": "привет"})
        assert resp.status_code == 503
        assert "занят" in resp.get_json()["error"]
    finally:
        serve.QUEUE_WAIT_SECONDS = saved
        serve._queue_lock.release()


# --- ошибка агента → понятный статус ------------------------------------------

def test_agent_error_returns_clean_status():
    """Ошибка агента → понятный HTTP-статус, не 500 с traceback."""
    _reset()
    client = _client()
    client.post("/ask", json={"user": "facade_err", "text": "привет"})
    agent = serve._agents["facade_err"]

    def boom(_text):
        raise RuntimeError("сломалось")

    agent.respond = boom
    resp = client.post("/ask", json={"user": "facade_err", "text": "привет"})
    assert resp.status_code == 500
    data = resp.get_json()
    assert "error" in data
    assert "Traceback" not in data["error"]


# --- границы: loopback и отсутствие прямого импорта rag/ ----------------------

def test_loopback_guard():
    """Фасад слушает только loopback (границы модуля)."""
    assert serve._is_loopback("127.0.0.1")
    assert serve._is_loopback("localhost")
    assert not serve._is_loopback("0.0.0.0")
    assert not serve._is_loopback("91.188.212.77")


def test_facade_does_not_import_rag_directly():
    """Фасад не импортирует `rag/` напрямую (только через агента)."""
    source = open(os.path.join(BASE_DIR, "serve.py"), encoding="utf-8").read()
    assert "import rag" not in source
    assert "from rag" not in source
