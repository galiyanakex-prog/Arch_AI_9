# -*- coding: utf-8 -*-
"""gateway/users.py — регистрация и вход (пароли — только хэшами).

Хранилище — SQLite (`gateway/users.db`). Пароль НИКОГДА не хранится и не логируется
открытым текстом: только соль + PBKDF2-HMAC-SHA256. Этот модуль не знает про фасад —
только про пользователей и сессии.
"""
import hashlib
import hmac
import os
import sqlite3
import time

_PBKDF2_ROUNDS = 200_000
_SALT_BYTES = 16


def _connect(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    """Создаёт таблицы пользователей и истории (идемпотентно)."""
    with _connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "  login TEXT PRIMARY KEY,"
            "  salt TEXT NOT NULL,"
            "  pwhash TEXT NOT NULL,"
            "  created_at REAL NOT NULL)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS history ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  login TEXT NOT NULL,"
            "  role TEXT NOT NULL,"
            "  text TEXT NOT NULL,"
            "  model TEXT,"
            "  created_at REAL NOT NULL)")
        # Идемпотентность повтора (этап 11): один request_id → один ответ.
        # status: 'pending' (запрос принят, ответа ещё нет) | 'done' (ответ есть).
        conn.execute(
            "CREATE TABLE IF NOT EXISTS requests ("
            "  login TEXT NOT NULL,"
            "  request_id TEXT NOT NULL,"
            "  status TEXT NOT NULL,"
            "  answer TEXT,"
            "  model TEXT,"
            "  created_at REAL NOT NULL,"
            "  PRIMARY KEY (login, request_id))")
        conn.commit()


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                               _PBKDF2_ROUNDS).hex()


def exists(db_path: str, login: str) -> bool:
    with _connect(db_path) as conn:
        row = conn.execute("SELECT 1 FROM users WHERE login = ?", (login,)).fetchone()
        return row is not None


def register(db_path: str, login: str, password: str) -> bool:
    """Регистрация: логин + пароль. Пароль — только хэшем. False — логин занят."""
    login = (login or "").strip()
    if not login or not password:
        raise ValueError("Логин и пароль обязательны.")
    if exists(db_path, login):
        return False
    salt = os.urandom(_SALT_BYTES)
    with _connect(db_path) as conn:
        conn.execute("INSERT INTO users (login, salt, pwhash, created_at) "
                     "VALUES (?, ?, ?, ?)",
                     (login, salt.hex(), _hash(password, salt), time.time()))
        conn.commit()
    return True


def verify(db_path: str, login: str, password: str) -> bool:
    """Проверка пароля: постоянное время сравнения (hmac.compare_digest)."""
    with _connect(db_path) as conn:
        row = conn.execute("SELECT salt, pwhash FROM users WHERE login = ?",
                           ((login or "").strip(),)).fetchone()
    if row is None:
        return False
    salt = bytes.fromhex(row["salt"])
    return hmac.compare_digest(_hash(password, salt), row["pwhash"])


def user_exists(db_path: str, login: str) -> bool:
    return exists(db_path, login)


# --- История чата (хранится на VPS, переживает переподключение) ---------------

def add_message(db_path: str, login: str, role: str, text: str,
                model: str = None, keep: int = 200) -> None:
    """Добавляет реплику в историю; хранит не больше `keep` последних."""
    with _connect(db_path) as conn:
        conn.execute("INSERT INTO history (login, role, text, model, created_at) "
                     "VALUES (?, ?, ?, ?, ?)",
                     (login, role, text, model, time.time()))
        # Обрезка истории: оставляем последние `keep` реплик пользователя.
        conn.execute(
            "DELETE FROM history WHERE login = ? AND id NOT IN ("
            "  SELECT id FROM history WHERE login = ? ORDER BY id DESC LIMIT ?)",
            (login, login, keep))
        conn.commit()


def get_history(db_path: str, login: str) -> list:
    """История переписки пользователя (хронологический порядок)."""
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT role, text, model, created_at FROM history "
            "WHERE login = ? ORDER BY id ASC", (login,)).fetchall()
    return [dict(row) for row in rows]


# --- Идемпотентность повтора (этап 11) ---------------------------------------

def get_request(db_path: str, login: str, request_id: str):
    """Состояние запроса по request_id: dict или None.

    Возвращает {'status': 'pending'|'done', 'answer': str|None, 'model': str|None}.
    """
    if not request_id:
        return None
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT status, answer, model FROM requests "
            "WHERE login = ? AND request_id = ?", (login, request_id)).fetchone()
    return dict(row) if row is not None else None


def begin_request(db_path: str, login: str, request_id: str) -> bool:
    """Регистрирует запрос как 'pending'. False — такой request_id уже был.

    Вызывается ДО обращения к фасаду: повторный запрос с тем же id не пойдёт
    на фасад заново (защита от дубликата ответа при обрыве).
    """
    if not request_id:
        return True
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO requests "
            "(login, request_id, status, answer, model, created_at) "
            "VALUES (?, ?, 'pending', NULL, NULL, ?)",
            (login, request_id, time.time()))
        conn.commit()
        return cur.rowcount > 0


def finish_request(db_path: str, login: str, request_id: str, answer: str,
                   model: str = None) -> None:
    """Помечает запрос как 'done' и сохраняет ответ (для повтора)."""
    if not request_id:
        return
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE requests SET status = 'done', answer = ?, model = ? "
            "WHERE login = ? AND request_id = ?",
            (answer, model, login, request_id))
        conn.commit()


def drop_request(db_path: str, login: str, request_id: str) -> None:
    """Убирает запись запроса (если ответ не получен — повтор разрешён снова)."""
    if not request_id:
        return
    with _connect(db_path) as conn:
        conn.execute("DELETE FROM requests WHERE login = ? AND request_id = ?",
                     (login, request_id))
        conn.commit()
