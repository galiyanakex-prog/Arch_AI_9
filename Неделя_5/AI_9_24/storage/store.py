# -*- coding: utf-8 -*-
"""Фасад хранилища: каноническая иерархия users/<id>/tasks/<task>/sessions/<id>.

Канон куратора (Суть_N3 §4.8 п.3):
  users/<user_id>/
  ├── profile.json                 # зеркало профиля default (JSON, источник — SQLite)
  ├── profiles/<profile_id>.json   # зеркала всех профилей (персонализация)
  ├── long_term_memory.json        # ссылка на профиль + задачи + решения
  └── tasks/<task_name>/
      ├── task_state.json          # снимок TaskState (автомат задачи, День 13)
      ├── working_memory.json      # описание задачи, ссылки на сессии, резюме жизненного цикла
      ├── sessions_resume.md       # резюме сессий (только данные о задаче)
      └── sessions/<session_id>/
          └── session.json         # краткосрочная память: сообщения сессии

Store — единственный, кто знает пути. Остальные слои (MemoryLayer) получают
контекст {user_id, task, session_id} и работают через этот фасад, не трогая
файловую систему напрямую (инкапсуляция через фасады, из arch_prim R3).
"""
import json
import os
import re


def safe_name(name: str) -> str:
    """Безопасное имя каталога/файла: буквы, цифры, дефис, подчёркивание.

    Пробелы и прочие символы заменяются на подчёркивание, чтобы имя задачи
    «Подбор косметики» превратилось в допустимый каталог «Подбор_косметики».
    """
    name = (name or "").strip()
    name = re.sub(r"[^0-9A-Za-zА-Яа-яЁё\-_ ]+", " ", name)
    name = re.sub(r"\s+", "_", name).strip("_")
    return name[:80] or "task"


class Store:
    """Фасад файлового хранилища поверх канонической иерархии пользователя."""

    def __init__(self, root: str, profile_repo=None, log=None):
        # Корень всех пользователей: <BASE_DIR>/users.
        self.root = root
        # Репозиторий профилей в SQLite (может быть None — тогда профиль только в JSON).
        self.profile_repo = profile_repo
        self.log = log or (lambda line: None)
        os.makedirs(self.root, exist_ok=True)

    def user_dir(self, user_id: str) -> str:
        return os.path.join(self.root, safe_name(user_id))

    def task_dir(self, user_id: str, task_name: str) -> str:
        return os.path.join(self.user_dir(user_id), "tasks", safe_name(task_name))

    def session_dir(self, user_id: str, task_name: str, session_id: str) -> str:
        return os.path.join(self.task_dir(user_id, task_name), "sessions", safe_name(session_id))

    def ensure_user(self, user_id: str) -> str:
        """Создаёт каталоги пользователя под все канонические файлы. Идемпотентно."""
        path = self.user_dir(user_id)
        os.makedirs(path, exist_ok=True)
        return path

    def ensure_task(self, user_id: str, task_name: str) -> str:
        path = self.task_dir(user_id, task_name)
        os.makedirs(os.path.join(path, "sessions"), exist_ok=True)
        return path

    def ensure_session(self, user_id: str, task_name: str, session_id: str) -> str:
        path = self.session_dir(user_id, task_name, session_id)
        os.makedirs(path, exist_ok=True)
        return path

    def read_json(self, filepath: str, default):
        """Читает JSON; при отсутствии/повреждении возвращает default (не падает)."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return default

    def write_json(self, filepath: str, data) -> str:
        """Пишет JSON; каталог создаётся автоматически. Возвращает путь файла."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return filepath

    # --- Профили (несколько на пользователя, arch_den_12 §2.4–2.5) ----------------
    def profiles_dir(self, user_id: str) -> str:
        """Каталог зеркал всех профилей: users/<id>/profiles/."""
        return os.path.join(self.user_dir(user_id), "profiles")

    def profile_path(self, user_id: str, profile_id: str = "default") -> str:
        """Путь зеркала профиля: users/<id>/profiles/<pid>.json.

        Совместимость: users/<id>/profile.json остаётся зеркалом default —
        его пишет save_profile(profile_id='default') дополнительно.
        """
        return os.path.join(self.profiles_dir(user_id), f"{safe_name(profile_id)}.json")

    def save_profile(self, user_id: str, profile: dict, profile_id: str = "default") -> str:
        """Сохраняет профиль: в SQLite (авторитет) + зеркало profiles/<pid>.json.

        Для профиля default дополнительно пишется старое зеркало profile.json
        (обратная совместимость с днём 11).
        """
        self.ensure_user(user_id)
        path = self.write_json(self.profile_path(user_id, profile_id), profile)
        if profile_id == "default":
            self.write_json(os.path.join(self.user_dir(user_id), "profile.json"), profile)
        if self.profile_repo is not None:
            self.profile_repo.save_profile(user_id, profile, profile_id)
        return path

    def load_profile(self, user_id: str, profile_id: str = None):
        """Профиль по id (None/"" → дефолтный). Авторитет — SQLite, зеркало — fallback."""
        if self.profile_repo is not None:
            profile = self.profile_repo.load_profile(user_id, profile_id)
            if profile is not None:
                return profile
        if profile_id:
            return self.read_json(self.profile_path(user_id, profile_id), None)
        # Fallback без id: зеркало default → старое profile.json (день 11).
        profile = self.read_json(self.profile_path(user_id, "default"), None)
        if profile is None:
            profile = self.read_json(os.path.join(self.user_dir(user_id), "profile.json"), None)
        return profile

    def list_profiles(self, user_id: str) -> list:
        """Список профилей [(profile_id, is_default: bool)] — из SQLite, без БД — по каталогу."""
        if self.profile_repo is not None:
            return self.profile_repo.list_profiles(user_id)
        pdir = self.profiles_dir(user_id)
        if not os.path.isdir(pdir):
            return []
        return sorted(
            (os.path.splitext(f)[0], f == "default.json")
            for f in os.listdir(pdir) if f.endswith(".json")
        )

    def set_default_profile(self, user_id: str, profile_id: str) -> bool:
        """Делает профиль дефолтным (False — если профиля нет / нет БД)."""
        if self.profile_repo is None:
            return False
        return self.profile_repo.set_default(user_id, profile_id)

    # --- Долговременная память ---------------------------------------------------
    def long_term_path(self, user_id: str) -> str:
        return os.path.join(self.user_dir(user_id), "long_term_memory.json")

    def read_long_term(self, user_id: str) -> dict:
        data = self.read_json(self.long_term_path(user_id), None)
        if data is None:
            data = {"profile_ref": user_id, "tasks": [], "decisions": [], "knowledge": []}
        data.setdefault("profile_ref", user_id)
        data.setdefault("tasks", [])
        data.setdefault("decisions", [])
        data.setdefault("knowledge", [])
        return data

    def write_long_term(self, user_id: str, data: dict) -> str:
        self.ensure_user(user_id)
        return self.write_json(self.long_term_path(user_id), data)

    # --- Рабочая память -----------------------------------------------------------
    def working_path(self, user_id: str, task_name: str) -> str:
        return os.path.join(self.task_dir(user_id, task_name), "working_memory.json")

    def read_working(self, user_id: str, task_name: str) -> dict:
        data = self.read_json(self.working_path(user_id, task_name), None)
        if data is None:
            data = {
                "description": "",
                "refs": [],
                "lifecycle_summary": "",
                "decisions": [],
                "constraints": [],
                "facts": [],
                "open_questions": [],
                "current_state": "new",
            }
        for key in ("description", "refs", "lifecycle_summary", "decisions",
                    "constraints", "facts", "open_questions"):
            data.setdefault(key, [] if key not in ("description", "lifecycle_summary") else "")
        data.setdefault("current_state", "new")
        return data

    def write_working(self, user_id: str, task_name: str, data: dict) -> str:
        self.ensure_task(user_id, task_name)
        return self.write_json(self.working_path(user_id, task_name), data)

    # --- Состояние задачи (state machine, День 13) --------------------------------
    def task_state_path(self, user_id: str, task_name: str) -> str:
        """Путь снимка состояния задачи: users/<id>/tasks/<task>/task_state.json."""
        return os.path.join(self.task_dir(user_id, task_name), "task_state.json")

    def read_task_state(self, user_id: str, task_name: str):
        """Снимок TaskState как dict; None — состояния ещё нет (или файл битый).

        Не падает на отсутствующем/повреждённом файле: задача стартует с NEW.
        Миграция имён стадий ("execution" → implementation) — в
        TaskState.from_dict (День 15): фасад отдаёт снимок как есть.
        """
        return self.read_json(self.task_state_path(user_id, task_name), None)

    def write_task_state(self, user_id: str, task_name: str, data: dict) -> str:
        """Пишет снимок состояния задачи (каталог задачи создаётся). Возвращает путь."""
        self.ensure_task(user_id, task_name)
        return self.write_json(self.task_state_path(user_id, task_name), data)

    # --- Инварианты задачи (День 14) ----------------------------------------------
    def invariants_path(self, user_id: str, task_name: str) -> str:
        """Путь набора инвариантов: users/<id>/tasks/<task>/invariants.json.

        Отдельный от диалога файл: очистка session.json НЕ удаляет инварианты
        (arch_den_14.md §2.6).
        """
        return os.path.join(self.task_dir(user_id, task_name), "invariants.json")

    def read_invariants(self, user_id: str, task_name: str):
        """Набор инвариантов задачи как dict; None — набора ещё нет (или файл битый).

        Не падает на отсутствующем/повреждённом файле: набор пуст → все действия
        разрешены (поведение дней 11–13).
        """
        return self.read_json(self.invariants_path(user_id, task_name), None)

    def write_invariants(self, user_id: str, task_name: str, data: dict) -> str:
        """Пишет набор инвариантов (каталог задачи создаётся). Возвращает путь."""
        self.ensure_task(user_id, task_name)
        return self.write_json(self.invariants_path(user_id, task_name), data)

    # --- Резюме сессий задачи -----------------------------------------------------
    def sessions_resume_path(self, user_id: str, task_name: str) -> str:
        return os.path.join(self.task_dir(user_id, task_name), "sessions_resume.md")

    def read_sessions_resume(self, user_id: str, task_name: str) -> str:
        path = self.sessions_resume_path(user_id, task_name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def write_sessions_resume(self, user_id: str, task_name: str, text: str) -> str:
        self.ensure_task(user_id, task_name)
        path = self.sessions_resume_path(user_id, task_name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    # --- Краткосрочная память (сессия) ---------------------------------------------
    def session_path(self, user_id: str, task_name: str, session_id: str) -> str:
        return os.path.join(self.session_dir(user_id, task_name, session_id), "session.json")

    def read_session(self, user_id: str, task_name: str, session_id: str) -> dict:
        data = self.read_json(self.session_path(user_id, task_name, session_id), None)
        if data is None:
            data = {"messages": []}
        data.setdefault("messages", [])
        return data

    def write_session(self, user_id: str, task_name: str, session_id: str, data: dict) -> str:
        self.ensure_session(user_id, task_name, session_id)
        return self.write_json(self.session_path(user_id, task_name, session_id), data)

    # --- Утилиты -------------------------------------------------------------------
    def list_tasks(self, user_id: str) -> list:
        """Список имён задач пользователя (по каталогам, сортировка по имени)."""
        tasks_dir = os.path.join(self.user_dir(user_id), "tasks")
        if not os.path.isdir(tasks_dir):
            return []
        return sorted(
            entry for entry in os.listdir(tasks_dir)
            if os.path.isdir(os.path.join(tasks_dir, entry))
        )

    # --- MCP: конфиг серверов + каталог инструментов (День 16) ----------------------
    def mcp_dir(self, user_id: str) -> str:
        """Каталог MCP-интеграций: users/<id>/integrations/mcp/."""
        return os.path.join(self.user_dir(user_id), "integrations", "mcp")

    def mcp_servers_path(self, user_id: str) -> str:
        """Путь конфига серверов: users/<id>/integrations/mcp/servers.json."""
        return os.path.join(self.mcp_dir(user_id), "servers.json")

    def read_mcp_servers(self, user_id: str):
        """Конфиг серверов; отсутствующий/битый файл → None (дефолт у вызывающего)."""
        return self.read_json(self.mcp_servers_path(user_id), None)

    def write_mcp_servers(self, user_id: str, data: dict) -> str:
        """Пишет конфиг серверов (каталог integrations/mcp создаётся)."""
        return self.write_json(self.mcp_servers_path(user_id), data)

    def tool_catalog_path(self, user_id: str) -> str:
        """Путь снимка каталога: users/<id>/integrations/mcp/catalog.json."""
        return os.path.join(self.mcp_dir(user_id), "catalog.json")

    def read_tool_catalog(self, user_id: str):
        """Снимок каталога; отсутствующий/битый файл → None (пустой каталог)."""
        return self.read_json(self.tool_catalog_path(user_id), None)

    def save_tool_catalog(self, user_id: str, data: dict) -> str:
        """Пишет снимок ToolCatalogSnapshot (каталог integrations/mcp создаётся)."""
        return self.write_json(self.tool_catalog_path(user_id), data)

    # --- MCP: аудит вызовов инструментов (задел дня 17+) ----------------------------
    def tool_audit_path(self, user_id: str, task_name: str) -> str:
        """Путь журнала вызовов: users/<id>/tasks/<task>/tool_audit.jsonl.

        Отдельно от transition_log: успешный вызов инструмента сам по себе
        не создаёт запись о переходе (инструмент ≠ переход).
        """
        return os.path.join(self.task_dir(user_id, task_name), "tool_audit.jsonl")

    def append_tool_audit(self, user_id: str, task_name: str, record: dict) -> str:
        """Append-only запись вызова инструмента (задел дня 17+)."""
        self.ensure_task(user_id, task_name)
        path = self.tool_audit_path(user_id, task_name)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path

    def load_tool_audit(self, user_id: str, task_name: str) -> list:
        """Читает журнал вызовов; отсутствующий/битый файл → []."""
        path = self.tool_audit_path(user_id, task_name)
        records = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        return records

    # --- Планировщик фоновых задач (День 18) ---------------------------------------
    def scheduler_dir(self, user_id: str) -> str:
        """Каталог данных планировщика: users/<id>/integrations/mcp/scheduler/."""
        return os.path.join(self.mcp_dir(user_id), "scheduler")

    def scheduler_path(self, user_id: str, name: str) -> str:
        """Путь JSON-файла планировщика (jobs/observations/summaries)."""
        return os.path.join(self.scheduler_dir(user_id), f"{safe_name(name)}.json")

    def read_scheduler(self, user_id: str, name: str, default):
        """Данные планировщика; отсутствующий/битый файл → default (не падает)."""
        return self.read_json(self.scheduler_path(user_id, name), default)

    def write_scheduler(self, user_id: str, name: str, data) -> str:
        """Пишет JSON планировщика (каталог scheduler создаётся). Возвращает путь."""
        return self.write_json(self.scheduler_path(user_id, name), data)

    # --- RAG-модуль (День 21, Ревизия 6) ------------------------------------------
    def rag_root(self) -> str:
        """Глобальный корень RAG: <BASE_DIR>/rag (индекс вне users/, решение №3)."""
        return os.path.join(os.path.dirname(self.root), "rag")

    def rag_index_dir(self) -> str:
        """Каталог артефактов индекса: <BASE_DIR>/rag/index."""
        return os.path.join(self.rag_root(), "index")

    def read_rag_config(self, default):
        """Конфиг RAG (rag/config.json); отсутствующий/битый → default (не падает)."""
        return self.read_json(os.path.join(self.rag_root(), "config.json"), default)

    def write_rag_config(self, data) -> str:
        """Пишет конфиг RAG (каталог rag создаётся). Возвращает путь."""
        return self.write_json(os.path.join(self.rag_root(), "config.json"), data)