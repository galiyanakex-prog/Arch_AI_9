# -*- coding: utf-8 -*-
"""Реестр LLM-моделей: ModelSpec + ModelRegistry (Ревизия 8, этап 2).

Единая точка выбора модели/сервиса. Реестр читает `models.json` (+ env-пере-
определения), строит клиент по `ModelSpec` и хранит выбор пользователя в
`users/<user>/model_state.json`. `Agent` при этом **не знает** конкретных
провайдеров — он получает готовый `LLMClient` (контракт §6.1 неизменяем).

Секретов здесь нет: `API_KEY` живёт только в окружении.
"""
import json
import os
import time
from dataclasses import dataclass, field, replace

from core.llm_client import (
    LLMClient, RouterAIClient, MockClient, OpenAICompatClient, OllamaClient,
)

# Сервисы, которые умеет строить реестр.
SERVICES = ("cloud", "lmstudio", "ollama", "mock")
# Профили параметров (часть 4): имя → переопределения.
DEFAULT_PROFILES = {
    "default": {},
    "rag-strict": {"temperature": 0.1, "max_tokens": 700,
                   "context_window": 8192, "top_p": 0.9},
    "fast": {"temperature": 0.3, "max_tokens": 256,
             "context_window": 4096, "top_p": 0.9},
}


@dataclass
class ModelSpec:
    """Описание одной модели/сервиса из реестра."""

    id: str
    service: str
    model: str
    base_url: str = ""
    context_window: int = 8192
    quant: str = ""
    params: dict = field(default_factory=dict)
    profile: str = "default"
    local: bool = False
    timeout: int = 180
    label: str = ""
    role: str = "chat"          # chat | embedding

    def display(self) -> str:
        """Единая подпись для CLI/лога/HTTP: `service/model`."""
        return self.label or f"{self.service}/{self.model}"

    def with_profile(self, profiles: dict) -> "ModelSpec":
        """Возвращает копию спека с параметрами выбранного профиля.

        Неизвестный профиль → KeyError со списком доступных (часть 4, этап 7):
        молчаливое падение к дефолту скрыло бы опечатку в имени профиля.
        """
        if self.profile not in profiles:
            available = ", ".join(sorted(profiles)) or "(нет профилей)"
            raise KeyError(
                f"Профиль «{self.profile}» не найден. Доступны: {available}")
        overrides = dict(profiles.get(self.profile, {}))
        params = dict(self.params)
        for key in ("temperature", "max_tokens", "top_p", "num_ctx", "keep_alive"):
            if key in overrides:
                params[key] = overrides[key]
        context_window = overrides.get("context_window", self.context_window)
        return replace(self, params=params, context_window=context_window)


class ModelRegistry:
    """Реестр моделей: загрузка, выбор, построение клиента, health-check."""

    def __init__(self, path: str = None, log=None):
        self.path = path
        self.log = log or (lambda line: None)
        self.profiles = dict(DEFAULT_PROFILES)
        self.models: dict[str, ModelSpec] = {}
        self.current_id: str = "cloud:stepfun/step-3.5-flash"
        self.subagents: dict = {}
        if path:
            self.load(path)

    # --- Загрузка ---------------------------------------------------------------
    def load(self, path: str) -> "ModelRegistry":
        """Читает `models.json`; отсутствие/повреждение — деградация к дефолту."""
        self.path = path
        data = {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            self.log(f"[ModelRegistry] не удалось прочитать {path}: {error}")
        self.profiles = {**DEFAULT_PROFILES, **data.get("profiles", {})}
        self.subagents = data.get("subagents", {})
        self.models = {}
        for raw in data.get("models", []):
            spec = ModelSpec(
                id=raw["id"], service=raw.get("service", "cloud"),
                model=raw.get("model", raw["id"]),
                base_url=raw.get("base_url", ""),
                context_window=raw.get("context_window", 8192),
                quant=raw.get("quant", ""),
                params=raw.get("params", {}),
                profile=raw.get("profile", "default"),
                local=raw.get("local", False),
                timeout=raw.get("timeout_seconds", 180),
                label=raw.get("label", ""),
                role=raw.get("role", "chat"),
            )
            self.models[spec.id] = spec
        self.current_id = data.get("current", self.current_id)
        self._apply_env()
        return self

    def _apply_env(self):
        """Env-переопределения: AI9_MODEL, LMSTUDIO_URL, OLLAMA_CHAT_URL."""
        env_model = os.getenv("AI9_MODEL")
        if env_model and env_model in self.models:
            self.current_id = env_model
        lmstudio_url = os.getenv("LMSTUDIO_URL")
        ollama_url = os.getenv("OLLAMA_CHAT_URL")
        for spec in self.models.values():
            if spec.service == "lmstudio" and lmstudio_url:
                spec.base_url = lmstudio_url
            if spec.service == "ollama" and ollama_url:
                spec.base_url = ollama_url

    # --- Доступ -----------------------------------------------------------------
    def list(self, role: str = None) -> list:
        """Список спеков (опционально — только с заданной ролью)."""
        specs = list(self.models.values())
        if role is not None:
            specs = [s for s in specs if s.role == role]
        return specs

    def get(self, model_id: str) -> ModelSpec:
        """Спек по id; неизвестный id → KeyError со списком доступных."""
        if model_id not in self.models:
            available = ", ".join(sorted(self.models)) or "(реестр пуст)"
            raise KeyError(f"Модель «{model_id}» не найдена. Доступны: {available}")
        return self.models[model_id]

    def current(self) -> ModelSpec:
        """Текущий спек (по `current_id`)."""
        return self.get(self.current_id)

    def use(self, model_id: str, user_dir: str = None) -> ModelSpec:
        """Выбирает модель (валидация) и, если задан user_dir, пишет выбор."""
        spec = self.get(model_id)
        self.current_id = model_id
        if user_dir:
            self._save_state(user_dir, model_id)
        return spec

    def _save_state(self, user_dir: str, model_id: str):
        try:
            os.makedirs(user_dir, exist_ok=True)
            with open(os.path.join(user_dir, "model_state.json"), "w",
                      encoding="utf-8") as handle:
                json.dump({"current": model_id}, handle, ensure_ascii=False, indent=2)
        except OSError as error:
            self.log(f"[ModelRegistry] не удалось сохранить выбор: {error}")

    def load_state(self, user_dir: str) -> str:
        """Читает сохранённый выбор пользователя (если есть и валиден)."""
        try:
            with open(os.path.join(user_dir, "model_state.json"), "r",
                      encoding="utf-8") as handle:
                saved = json.load(handle).get("current")
            if saved in self.models:
                self.current_id = saved
        except (OSError, json.JSONDecodeError):
            pass
        return self.current_id

    # --- Построение клиента -----------------------------------------------------
    def build(self, spec: ModelSpec) -> LLMClient:
        """Строит LLMClient по спекe (с учётом профиля параметров)."""
        spec = spec.with_profile(self.profiles)
        if spec.service == "lmstudio":
            return OpenAICompatClient(spec.base_url, spec.model,
                                      max_tokens=spec.params.get("max_tokens"),
                                      timeout=spec.timeout, params=spec.params)
        if spec.service == "ollama":
            return OllamaClient(spec.base_url, spec.model,
                                max_tokens=spec.params.get("max_tokens"),
                                timeout=spec.timeout, params=spec.params,
                                keep_alive=spec.params.get("keep_alive"))
        if spec.service == "cloud":
            return RouterAIClient(model=spec.model,
                                  max_tokens=spec.params.get("max_tokens"))
        if spec.service == "mock":
            return MockClient(name=spec.model or "Mock")
        raise ValueError(f"Неизвестный сервис: {spec.service!r}")

    def build_current(self) -> LLMClient:
        return self.build(self.current())

    # --- Health-check -----------------------------------------------------------
    def probe(self, model_id: str) -> dict:
        """Живой health-check сервиса: доступность + латентность."""
        spec = self.get(model_id)
        started = time.time()
        try:
            if spec.service == "lmstudio":
                import requests
                response = requests.get(f"{spec.base_url.rstrip('/')}/v1/models",
                                        timeout=5)
                response.raise_for_status()
                ids = [m.get("id") for m in response.json().get("data", [])]
                # LM Studio отдаёт короткий id, а в спеке — полный путь с квантом.
                short = spec.model.split("/")[-1].split(":")[0].lower()
                if short.endswith("-gguf"):
                    short = short[:-5]
                ok = any(short == (i or "").lower() or short in (i or "").lower()
                         for i in ids)
                return {"ok": ok, "latency_ms": int((time.time() - started) * 1000),
                        "version": "lmstudio", "models": ids}
            if spec.service == "ollama":
                import requests
                response = requests.get(f"{spec.base_url.rstrip('/')}/api/version",
                                        timeout=5)
                response.raise_for_status()
                return {"ok": True, "latency_ms": int((time.time() - started) * 1000),
                        "version": response.json().get("version", "")}
            if spec.service == "mock":
                return {"ok": True, "latency_ms": 0, "version": "mock"}
            return {"ok": True, "latency_ms": int((time.time() - started) * 1000),
                    "version": "cloud"}
        except Exception as error:
            return {"ok": False, "latency_ms": int((time.time() - started) * 1000),
                    "version": "", "error": f"{type(error).__name__}: {error}"}

    def describe(self, model_id: str) -> dict:
        """Сводка для `/model status`: спек + профиль + параметры."""
        spec = self.get(model_id).with_profile(self.profiles)
        return {
            "id": spec.id, "service": spec.service, "model": spec.model,
            "local": spec.local, "quant": spec.quant,
            "context_window": spec.context_window, "profile": spec.profile,
            "params": spec.params, "label": spec.display(), "role": spec.role,
        }