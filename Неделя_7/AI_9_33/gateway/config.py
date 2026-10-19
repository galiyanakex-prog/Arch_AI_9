# -*- coding: utf-8 -*-
"""gateway/config.py — загрузка конфигурации шлюза (без секретов в файле).

Конфиг — `gateway/gateway.json`; секрет сессии берётся из окружения
(`GATEWAY_SECRET`), а если его нет — генерируется случайно и кладётся в
`gateway/.secret` (решение №27). Предсказуемого dev-секрета в коде НЕТ.
Здесь нет бизнес-логики: только разбор файла и разумные дефолты.
"""
import json
import os
import secrets

DEFAULTS = {
    "host_facade_url": "http://127.0.0.1:8090",
    "facade_timeout_seconds": 180,
    "public_port": 8080,
    "limits": {"requests_per_minute": 6, "max_query_chars": 8000},
    "session": {"secret_env": "GATEWAY_SECRET", "secret_file": "gateway/.secret",
                "max_age_minutes": 720},
    "history_keep_messages": 200,
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config(path: str = None) -> dict:
    """Читает gateway.json и дополняет дефолтами (отсутствующие ключи)."""
    path = path or os.path.join(BASE_DIR, "gateway.json")
    data = dict(DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        for key, value in loaded.items():
            if key.startswith("_"):
                continue
            if isinstance(value, dict) and isinstance(data.get(key), dict):
                data[key].update(value)
            else:
                data[key] = value
    except (OSError, json.JSONDecodeError):
        pass
    return data


def _secret_file_path(cfg: dict) -> str:
    """Путь к файлу автосекрета (относительный — от корня пакета `gateway/`)."""
    rel = cfg.get("session", {}).get("secret_file", "gateway/.secret")
    if os.path.isabs(rel):
        return rel
    # `gateway/.secret` → рядом с пакетом; иное — относительно корня AI_9.
    name = os.path.basename(rel)
    return os.path.join(BASE_DIR, name)


def session_secret(cfg: dict) -> str:
    """Секрет подписи сессии (решение №27).

    Порядок: 1) env `GATEWAY_SECRET`; 2) файл `gateway/.secret`; 3) сгенерировать
    случайный секрет и сохранить в файл. Предсказуемого dev-секрета нет.
    """
    env_name = cfg.get("session", {}).get("secret_env", "GATEWAY_SECRET")
    secret = os.getenv(env_name)
    if secret:
        return secret

    path = _secret_file_path(cfg)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            stored = handle.read().strip()
        if stored:
            return stored
    except OSError:
        pass

    generated = secrets.token_hex(32)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(generated + "\n")
        os.chmod(path, 0o600)
        print(f"[Шлюз] GATEWAY_SECRET не задан — сгенерирован автосекрет: {path}",
              flush=True)
    except OSError as error:
        print(f"[Шлюз] ВНИМАНИЕ: не удалось сохранить автосекрет ({error}); "
              f"секрет будет только в памяти процесса.", flush=True)
    return generated
