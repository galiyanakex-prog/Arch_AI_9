# -*- coding: utf-8 -*-
"""Субагенты: вспомогательные CLI-сессии на локальных LLM (Ревизия 8, этап 4).

Субагент — **не** новая подсистема диалога, а **дочерний процесс** `Kod.py` с
флагом `--oneshot`: один обмен → ответ → выход. Так переиспользуется весь
существующий REPL/память/гейты, а подпись модели в логе субагента появляется
автоматически (требование «во всех CLI-сессиях»).

Безопасность: `shell=False`, аргументы — списком; жёсткий `timeout` с `kill`
по истечении; лимит одновременных субагентов; запрет облачного сервиса, если
запрошен локальный контур; запись — только в `users/sub_*/` и `stages/`.
"""
import os
import re
import signal
import subprocess
import time

from storage.store import safe_name

# Сервисы, допустимые для субагента (только локальные).
LOCAL_SERVICES = ("lmstudio", "ollama")


class SubagentError(Exception):
    """Отказ до запуска: неизвестный сервис, нет локальной модели, лимит и т.п."""


class SubagentRunner:
    """Запуск дочерних CLI-сессий `Kod.py --oneshot` на локальной модели."""

    def __init__(self, base_dir: str, registry=None, python: str = None,
                 log=None, max_parallel: int = 2, default_timeout: int = 120,
                 user_prefix: str = "sub_", stages_dir: str = None):
        self.base_dir = base_dir
        self.registry = registry
        self.python = python or os.path.join(base_dir, ".venv", "bin", "python")
        self.log = log or (lambda line: None)
        self.max_parallel = max_parallel
        self.default_timeout = default_timeout
        self.user_prefix = user_prefix
        self.stages_dir = stages_dir or os.path.join(
            base_dir, "dev", "logs_reports", "stages")
        # Активные процессы: id → Popen (для лимита и /subagent list).
        self.active: dict = {}
        self.history: list = []

    # --- Разрешение модели ------------------------------------------------------
    def resolve_model(self, service: str, model: str = None) -> str:
        """id модели для сервиса: явный `model` либо первый chat-спек сервиса."""
        if service not in LOCAL_SERVICES:
            raise SubagentError(
                f"Сервис «{service}» недопустим для субагента. "
                f"Локальные: {', '.join(LOCAL_SERVICES)}.")
        if model:
            return model
        if self.registry is not None:
            for spec in self.registry.list(role="chat"):
                if spec.service == service:
                    return spec.id
        raise SubagentError(
            f"Для сервиса «{service}» нет локальной chat-модели в реестре. "
            f"Укажите --model явно.")

    # --- Запуск -----------------------------------------------------------------
    def run(self, task_text: str, service: str = "lmstudio", model: str = None,
            timeout: int = None, local_only: bool = True, wait: bool = True) -> dict:
        """Запускает субагента. `wait=True` — ждёт завершения и возвращает итог."""
        task_text = (task_text or "").strip()
        if not task_text:
            raise SubagentError("Пустая задача для субагента.")
        if local_only and service not in LOCAL_SERVICES:
            raise SubagentError(
                f"Запрошен локальный контур, но сервис «{service}» — не локальный.")
        model_id = self.resolve_model(service, model)

        # Лимит одновременных субагентов (по умолчанию 2).
        self._reap()
        if len(self.active) >= self.max_parallel:
            raise SubagentError(
                f"Достигнут лимит одновременных субагентов ({self.max_parallel}). "
                f"Дождитесь завершения активных.")

        slug = safe_name(task_text)[:40] or "task"
        sub_id = f"{slug}_{int(time.time())}"
        user_id = f"{self.user_prefix}{slug}"
        os.makedirs(self.stages_dir, exist_ok=True)
        log_path = os.path.join(self.stages_dir, f"subagent_{slug}.md")

        command = [
            self.python, os.path.join(self.base_dir, "Kod.py"),
            "--user", user_id,
            "--model", model_id,
            "--oneshot", task_text,
            "--log", log_path,
        ]
        started = time.time()
        process = subprocess.Popen(
            command, cwd=self.base_dir, shell=False,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, start_new_session=True)
        self.active[sub_id] = process
        self.log(f"[Субагент] запущен id={sub_id} service={service} "
                 f"model={model_id} pid={process.pid}")

        result = {
            "id": sub_id, "service": service, "model": model_id,
            "pid": process.pid, "user": user_id, "log": log_path,
            "task": task_text, "status": "running", "output": "",
            "returncode": None, "duration": 0.0,
        }
        if not wait:
            self.history.append(result)
            return result

        limit = timeout or self.default_timeout
        try:
            output, _ = process.communicate(timeout=limit)
            result["output"] = output or ""
            result["returncode"] = process.returncode
            result["status"] = "ok" if process.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            self._kill(process)
            output, _ = process.communicate()
            result["output"] = output or ""
            result["status"] = "timed_out"
            result["returncode"] = process.returncode
        finally:
            result["duration"] = round(time.time() - started, 2)
            self.active.pop(sub_id, None)
            self.history.append(result)
            self.log(f"[Субагент] id={sub_id} статус={result['status']} "
                     f"({result['duration']} с)")
        return result

    # --- Служебное --------------------------------------------------------------
    def _kill(self, process):
        """Жёсткое завершение процесса и его группы (start_new_session)."""
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                process.kill()
            except OSError:
                pass

    def _reap(self):
        """Убирает из active завершившиеся процессы (без ожидания)."""
        for sub_id, process in list(self.active.items()):
            if process.poll() is not None:
                self.active.pop(sub_id, None)

    def list_active(self) -> list:
        self._reap()
        return [{"id": sub_id, "pid": process.pid}
                for sub_id, process in self.active.items()]


# --- Детерминированный анализатор фразы «сделай локально в <service>» -----------
_SUBAGENT_RE = re.compile(
    r"сделай\s+локально\s+в\s+(lm\s*studio|lmstudio|ollama)\s*[:\-—]?\s*(.+)",
    re.IGNORECASE)
_SERVICE_ALIASES = {"lm studio": "lmstudio", "lmstudio": "lmstudio", "ollama": "ollama"}


def detect_local_subagent_request(text: str):
    """Распознаёт фразу «сделай локально в <service>: <задача>».

    Возвращает `(service, task)` либо `None`. Тот же принцип, что
    `TextActionAnalyzer`: детерминированно, без LLM.
    """
    match = _SUBAGENT_RE.search(text or "")
    if not match:
        return None
    raw_service = re.sub(r"\s+", " ", match.group(1).strip().lower())
    service = _SERVICE_ALIASES.get(raw_service)
    task = match.group(2).strip()
    if not service or not task:
        return None
    return service, task
