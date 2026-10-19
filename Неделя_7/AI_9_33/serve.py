# -*- coding: utf-8 -*-
"""serve.py — тонкий HTTP-фасад агента на хосте (Ревизия 8, этап 9, S1).

ЕДИНСТВЕННАЯ ОБЯЗАННОСТЬ: принять запрос → передать агенту → вернуть ответ.
Здесь НЕТ бизнес-логики: ни памяти, ни лимитов, ни прав доступа, ни истории
чата, ни выбора модели «в обход» реестра. Всё это — либо в агенте, либо на VPS
(шлюз, этап 10). Правило: «или в агент, или на VPS»; третье запрещено.

Границы (мастер-план §4, этап 9):
  - слушает ТОЛЬКО 127.0.0.1:8090 (loopback); наружу не смотрит никогда;
  - очередь на 1 запрос (решение №16): второй ждёт, а не падает;
  - подпись модели (`model`) — обязательное поле каждого ответа;
  - фасад НЕ импортирует `rag/` напрямую (только через агента);
  - удаление `serve.py` не меняет поведение агента в терминале.

Запуск:
    python serve.py                 # 127.0.0.1:8090, RAG выключен
    python serve.py --rag           # с RAG-слоем (индекс грузится лениво)
    python serve.py --mock          # заглушка (без ключа/сети)
"""
import argparse
import os
import sys
import threading
import time

# Kod.py парсит argv при импорте — подставляем «пустой» argv ДО импорта, чтобы
# фасад не зависел от аргументов командной строки своего процесса. Собственные
# аргументы фасада сохраняем и разбираем в main().
_ORIG_ARGV = list(sys.argv)
sys.argv = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "serve.py")]
import Kod  # noqa: E402  (импорт после подмены argv — намеренно)

from flask import Flask, jsonify, request  # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Конфигурация фасада (без секретов) --------------------------------------
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8090
# Сколько секунд ждать освобождения очереди, прежде чем вернуть 503.
QUEUE_WAIT_SECONDS = 600.0

app = Flask(__name__)

# Очередь на 1 запрос: один обрабатываемый запрос одновременно (решение №16).
_queue_lock = threading.Lock()
# Кэш агентов по пользователю: один процесс, память/сессии живут между запросами.
_agents = {}
_agents_lock = threading.Lock()
# Настройки, заданные при старте (--rag/--mock/--model).
_runtime = {"rag": False, "mock": False, "model": None}
# Счётчик обменов на пользователя (номер строки в tokens.csv).
_exchange_counts = {}


def _is_loopback(host: str) -> bool:
    """Только loopback-адреса (границы модуля: наружу фасад не смотрит)."""
    return host in ("127.0.0.1", "localhost", "::1")


def _get_agent(user_id: str):
    """Агент пользователя (кэш). Новый пользователь инициализируется без интервью."""
    with _agents_lock:
        agent = _agents.get(user_id)
        if agent is not None:
            return agent
        rag_cfg = Kod._build_rag_config(Kod.args) if _runtime["rag"] else None
        agent = Kod.build_agent(
            user_id=user_id, mock=_runtime["mock"],
            rag_enabled=_runtime["rag"], rag_config=rag_cfg,
            model_id=_runtime["model"])
        profile_repo = agent.store.profile_repo
        if not profile_repo.exists(user_id):
            agent.initialize_user(user_id, name=user_id, answers={})
        else:
            agent.load_state(user_id)
        _agents[user_id] = agent
        return agent


def _switch_model(agent, provider=None, model=None):
    """Переключение модели тем же путём, что `/model use` (без обхода реестра)."""
    registry = getattr(agent, "model_registry", None)
    if registry is None:
        return None
    model_id = model
    if not model_id and provider:
        spec = next((s for s in registry.list(role="chat") if s.service == provider),
                    None)
        model_id = spec.id if spec is not None else None
    if not model_id:
        return None
    spec = registry.get(model_id)
    client = registry.build(spec)
    registry.use(model_id, user_dir=agent.store.user_dir(agent.user_id)
                 if agent.user_id else None)
    agent.set_model(client, label=spec.display())
    Kod._apply_local_rag_template(agent)
    return spec.display()


def _usage(text: str, answer: str) -> dict:
    """Локальная оценка токенов (авторитет — usage живого API, здесь — оценка)."""
    prompt_tokens = Kod.estimate_tokens(text)
    completion_tokens = Kod.estimate_tokens(answer or "")
    return {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens, "estimated": True}


def _sources_payload(agent) -> list:
    sources = getattr(agent, "last_answer_sources", None) or []
    return [s.to_dict() if hasattr(s, "to_dict") else dict(s) for s in sources]


def _quotes_payload(agent) -> list:
    quotes = getattr(agent, "last_answer_quotes", None) or []
    return [q.to_dict() if hasattr(q, "to_dict") else dict(q) for q in quotes]


def _error(message: str, status: int):
    return jsonify({"error": message, "model": None}), status


# --- Маршруты -----------------------------------------------------------------

@app.route("/ask", methods=["POST"])
def ask():
    """{user, text, provider?, model?, profile?} → {answer, model, sources, ...}."""
    data = request.get_json(silent=True) or {}
    user_id = (data.get("user") or "").strip()
    text = (data.get("text") or "").strip()
    if not user_id:
        return _error("Поле 'user' обязательно.", 400)
    if not text:
        return _error("Поле 'text' обязательно.", 400)

    acquired = _queue_lock.acquire(timeout=QUEUE_WAIT_SECONDS)
    if not acquired:
        return _error("Сервис занят, попробуйте позже.", 503)
    try:
        agent = _get_agent(user_id)
        if data.get("provider") or data.get("model"):
            try:
                _switch_model(agent, provider=data.get("provider"),
                              model=data.get("model"))
            except KeyError as error:
                return _error(str(error), 400)
        if data.get("profile"):
            agent.switch_profile(data["profile"])

        started = time.time()
        answer = agent.respond(text)
        duration = round(time.time() - started, 3)
        if answer is None:
            return _error("Ответ не получен (LLM недоступен).", 502)

        usage = _usage(text, answer)
        # Учёт: Den_log.md + tokens.csv (видны user, модель, токены, длительность).
        Kod.log_line(f"[Фасад] user={user_id} model={agent.model_label()} "
                     f"tokens={usage['total_tokens']} duration={duration}s")
        _exchange_counts[user_id] = _exchange_counts.get(user_id, 0) + 1
        Kod.append_token_log(_exchange_counts[user_id], usage["prompt_tokens"], 0.0,
                             model=agent.model_label())
        return jsonify({
            "answer": answer,
            "model": agent.model_label(),
            "sources": _sources_payload(agent),
            "quotes": _quotes_payload(agent),
            "verdict": getattr(agent, "last_answer_verdict", "unchecked"),
            "usage": usage,
            "duration_seconds": duration,
        })
    except Exception as error:  # noqa: BLE001 — фасад не отдаёт traceback наружу
        Kod.log_line(f"[Фасад] ошибка /ask: {type(error).__name__}: {error}")
        return _error(f"Ошибка агента: {type(error).__name__}: {error}", 500)
    finally:
        _queue_lock.release()


@app.route("/models", methods=["GET"])
def models():
    """Провайдеры и модели из ModelRegistry (для выпадающих списков шлюза)."""
    try:
        registry = Kod.ModelRegistry(Kod.MODELS_PATH, log=Kod.log_line)
        items = []
        for spec in registry.list():
            items.append({
                "id": spec.id, "service": spec.service, "model": spec.model,
                "local": spec.local, "role": spec.role, "label": spec.display(),
                "quant": spec.quant, "context_window": spec.context_window,
                "profile": spec.profile,
            })
        providers = sorted({s.service for s in registry.list()})
        return jsonify({"current": registry.current_id, "providers": providers,
                        "models": items})
    except Exception as error:  # noqa: BLE001
        return _error(f"Реестр недоступен: {type(error).__name__}: {error}", 500)


@app.route("/model", methods=["POST"])
def set_model():
    """{user, provider?, model?} → переключение модели (тот же путь, что /model use)."""
    data = request.get_json(silent=True) or {}
    user_id = (data.get("user") or "").strip()
    if not user_id:
        return _error("Поле 'user' обязательно.", 400)
    acquired = _queue_lock.acquire(timeout=QUEUE_WAIT_SECONDS)
    if not acquired:
        return _error("Сервис занят, попробуйте позже.", 503)
    try:
        agent = _get_agent(user_id)
        try:
            label = _switch_model(agent, provider=data.get("provider"),
                                  model=data.get("model"))
        except KeyError as error:
            return _error(str(error), 400)
        if label is None:
            return _error("Не указана модель/провайдер.", 400)
        return jsonify({"model": agent.model_label(), "switched_to": label})
    except Exception as error:  # noqa: BLE001
        return _error(f"Ошибка переключения: {type(error).__name__}: {error}", 500)
    finally:
        _queue_lock.release()


@app.route("/interview", methods=["POST"])
def interview():
    """{user, name?, answers?} → существующий механизм интервью агента."""
    data = request.get_json(silent=True) or {}
    user_id = (data.get("user") or "").strip()
    if not user_id:
        return _error("Поле 'user' обязательно.", 400)
    acquired = _queue_lock.acquire(timeout=QUEUE_WAIT_SECONDS)
    if not acquired:
        return _error("Сервис занят, попробуйте позже.", 503)
    try:
        agent = _get_agent(user_id)
        name = (data.get("name") or user_id).strip()
        answers = data.get("answers") or {}
        agent.initialize_user(user_id, name=name, answers=answers)
        return jsonify({"user": user_id, "initialized": True,
                        "model": agent.model_label()})
    except Exception as error:  # noqa: BLE001
        return _error(f"Ошибка интервью: {type(error).__name__}: {error}", 500)
    finally:
        _queue_lock.release()


@app.route("/interview/questions", methods=["GET"])
def interview_questions():
    """Канонические вопросы интервью + отпечаток (для сверки шлюзом, решение №26).

    Тонкий маршрут: «принял → отдал». Источник — `core.agent.INTERVIEW_QUESTIONS`.
    """
    from core.agent import INTERVIEW_QUESTIONS, interview_questions_fingerprint
    questions = [{"key": key, "question": question}
                 for key, question in INTERVIEW_QUESTIONS]
    return jsonify({"version": interview_questions_fingerprint(),
                    "questions": questions})


@app.route("/state", methods=["GET"])
def state():
    """?user=… → модель, RAG, стадия задачи, жив ли сервис."""
    user_id = (request.args.get("user") or "").strip()
    if not user_id:
        return _error("Параметр 'user' обязателен.", 400)
    try:
        agent = _get_agent(user_id)
        task_state = getattr(agent, "task_state", None)
        return jsonify({
            "user": user_id,
            "model": agent.model_label(),
            "rag_enabled": bool(getattr(agent, "rag_enabled", False)),
            "task": getattr(agent, "task", None),
            "task_stage": task_state.stage.value if task_state else None,
            "busy": _queue_lock.locked(),
            "alive": True,
        })
    except Exception as error:  # noqa: BLE001
        return _error(f"Ошибка состояния: {type(error).__name__}: {error}", 500)


def main():
    parser = argparse.ArgumentParser(description="Тонкий HTTP-фасад агента (loopback).")
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help="Адрес прослушивания (только loopback).")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="Порт (по умолчанию 8090).")
    parser.add_argument("--rag", action="store_true", help="Включить RAG-слой.")
    parser.add_argument("--mock", action="store_true", help="Заглушка (без ключа).")
    parser.add_argument("--model", default=None, help="Модель по умолчанию (id).")
    cli = parser.parse_args(_ORIG_ARGV[1:])

    if not _is_loopback(cli.host):
        raise ValueError(f"Фасад слушает только loopback, а не {cli.host!r}.")
    _runtime.update(rag=cli.rag, mock=cli.mock, model=cli.model)
    print(f"[Фасад] слушает http://{cli.host}:{cli.port} "
          f"(RAG={'вкл' if cli.rag else 'выкл'}, mock={cli.mock})")
    app.run(host=cli.host, port=cli.port, threaded=True)


if __name__ == "__main__":
    main()
