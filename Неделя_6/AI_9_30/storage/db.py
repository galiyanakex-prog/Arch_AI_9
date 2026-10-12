# -*- coding: utf-8 -*-
"""Профили пользователей: JSON в БД SQLite (канон куратора, Суть_N3 §4.8 п.6).

Профиль — отдельная сущность; на одного пользователя — НЕСКОЛЬКО профилей
(персонализация, arch_den_12 §2.4): ключ (user_id, profile_id), первый профиль
автоматически становится дефолтным (is_default=1). Авторитетный источник —
таблица profiles в SQLite; файлы users/<id>/profiles/<pid>.json — читаемые
зеркала, которые пишет Store (см. store.py).

Обратная совместимость: БД старой схемы (user_id PRIMARY KEY, один профиль)
мигрируется при открытии — строки переносятся как profile_id='default',
is_default=1 (одна транзакция, данные не теряются).
"""
import json
import os
import sqlite3
from datetime import datetime


class ProfileRepository:
    """Хранилище профилей (JSON) в SQLite: несколько профилей на user_id."""

    def __init__(self, db_path: str, log=None):
        # Путь к файлу базы (обычно users/profiles.db).
        self.db_path = db_path
        self.log = log or (lambda line: None)
        # Каталог базы создаём заранее, чтобы sqlite.connect не упал на первом старте.
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._init_db()

    def _connect(self):
        """Открывает соединение; row_factory — для доступа по имени колонки."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _table_columns(self, conn) -> set:
        """Множество колонок существующей таблицы profiles (пусто, если её нет)."""
        rows = conn.execute("PRAGMA table_info(profiles)").fetchall()
        return {row["name"] for row in rows}

    def _init_db(self):
        """Создаёт таблицу profiles новой схемы; старую схему мигрирует.

        Идемпотентно: новая БД создаётся сразу с (user_id, profile_id);
        существующая старая схема (без profile_id) переносится в новую.
        """
        with self._connect() as conn:
            columns = self._table_columns(conn)
            if columns and "profile_id" not in columns:
                self._migrate_legacy(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    user_id TEXT NOT NULL,
                    profile_id TEXT NOT NULL DEFAULT 'default',
                    profile_json TEXT NOT NULL,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, profile_id)
                )
                """
            )

    def _migrate_legacy(self, conn):
        """Миграция старой схемы (user_id PRIMARY KEY) в новую — одна транзакция.

        Каждый профиль пользователя становится profile_id='default', is_default=1;
        в profile_json дописывается поле profile_id. Данные не теряются.
        """
        conn.execute("ALTER TABLE profiles RENAME TO profiles_legacy")
        conn.execute(
            """
            CREATE TABLE profiles (
                user_id TEXT NOT NULL,
                profile_id TEXT NOT NULL DEFAULT 'default',
                profile_json TEXT NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, profile_id)
            )
            """
        )
        rows = conn.execute(
            "SELECT user_id, profile_json, updated_at FROM profiles_legacy"
        ).fetchall()
        for row in rows:
            try:
                profile = json.loads(row["profile_json"])
            except (json.JSONDecodeError, TypeError):
                profile = {}
            if isinstance(profile, dict):
                profile.setdefault("profile_id", "default")
            conn.execute(
                """
                INSERT INTO profiles(user_id, profile_id, profile_json, is_default, updated_at)
                VALUES(?, 'default', ?, 1, ?)
                """,
                (row["user_id"],
                 json.dumps(profile, ensure_ascii=False),
                 row["updated_at"]),
            )
        conn.execute("DROP TABLE profiles_legacy")
        self.log(f"[Хранилище] миграция старой схемы profiles → (user_id, profile_id): {len(rows)} строк")

    def save_profile(self, user_id: str, profile: dict, profile_id: str = "default") -> str:
        """Сохраняет (вставляет или обновляет) профиль пользователя.

        Первый профиль пользователя автоматически становится дефолтным
        (is_default=1). В profile_json дописывается profile_id.
        Возвращает строку «куда легло» для журнала маршрутизации памяти.
        """
        updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(profile, dict):
            profile = dict(profile)
            profile["profile_id"] = profile_id
        payload = json.dumps(profile, ensure_ascii=False)
        with self._connect() as conn:
            # Первый профиль → is_default=1 (дефолт выбирается автоматически).
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
            is_default = 1 if row["n"] == 0 else 0
            conn.execute(
                """
                INSERT INTO profiles(user_id, profile_id, profile_json, is_default, updated_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(user_id, profile_id) DO UPDATE SET
                    profile_json = excluded.profile_json,
                    updated_at = excluded.updated_at
                """,
                (user_id, profile_id, payload, is_default, updated),
            )
        self.log(f"[Хранилище] profile «{profile_id}» = JSON в SQLite "
                 f"(таблица profiles, user_id={user_id})")
        return f"SQLite:profiles:{user_id}:{profile_id}"

    def load_profile(self, user_id: str, profile_id: str = None):
        """Возвращает профиль как dict или None.

        profile_id None/"" → дефолтный профиль; нет такого профиля → None
        (битый JSON тоже трактуется как None).
        """
        with self._connect() as conn:
            if profile_id:
                row = conn.execute(
                    "SELECT profile_json FROM profiles WHERE user_id = ? AND profile_id = ?",
                    (user_id, profile_id),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT profile_json FROM profiles
                    WHERE user_id = ? ORDER BY is_default DESC, profile_id LIMIT 1
                    """,
                    (user_id,),
                ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["profile_json"])
        except (json.JSONDecodeError, TypeError):
            return None

    def list_profiles(self, user_id: str) -> list:
        """Список профилей пользователя: [(profile_id, is_default: bool)], sorted."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT profile_id, is_default FROM profiles WHERE user_id = ? ORDER BY profile_id",
                (user_id,),
            ).fetchall()
        return [(row["profile_id"], bool(row["is_default"])) for row in rows]

    def get_default(self, user_id: str):
        """profile_id дефолтного профиля или None, если профилей нет."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT profile_id FROM profiles WHERE user_id = ? AND is_default = 1",
                (user_id,),
            ).fetchone()
        return row["profile_id"] if row else None

    def set_default(self, user_id: str, profile_id: str) -> bool:
        """Делает профиль дефолтным. False — если такого профиля нет."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM profiles WHERE user_id = ? AND profile_id = ?",
                (user_id, profile_id),
            ).fetchone()
            if row is None:
                return False
            conn.execute(
                "UPDATE profiles SET is_default = 0 WHERE user_id = ?", (user_id,)
            )
            conn.execute(
                "UPDATE profiles SET is_default = 1 WHERE user_id = ? AND profile_id = ?",
                (user_id, profile_id),
            )
        self.log(f"[Хранилище] профиль по умолчанию: {user_id} → «{profile_id}»")
        return True

    def exists(self, user_id: str) -> bool:
        """Есть ли ХОТЯ БЫ один профиль (семантика прежняя: отличаем старых и новых)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM profiles WHERE user_id = ? LIMIT 1", (user_id,)
            ).fetchone()
        return row is not None
