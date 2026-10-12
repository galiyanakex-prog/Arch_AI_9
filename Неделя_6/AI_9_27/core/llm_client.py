# -*- coding: utf-8 -*-
"""LLM-клиент за интерфейсом: LLMClient (ABC) + RouterAIClient + MockClient.

Агент зависит ТОЛЬКО от абстракции LLMClient; конкретный провайдер инжектится
на старте. MockClient — детерминированная заглушка, закрывает тесты без живого
ключа (API_KEY=test-key).
"""
import os
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests

# OpenAI-совместимый эндпоинт RouterAI.
URL = "https://routerai.ru/api/v1/chat/completions"
MODEL = "stepfun/step-3.5-flash"
MODEL_CONTEXT_LIMIT = 262144   # окно модели (Step-3.5-Flash_params.md)
PRICE_IN_PER_M = 11.0          # ₽ / 1M входящих
PRICE_OUT_PER_M = 33.0         # ₽ / 1M исходящих
REQUEST_TIMEOUT = 30
# Паузы между повторами при HTTP 429.
RETRY_DELAYS = [2, 4, 8]

# Локальные клиенты (Ревизия 8) — только loopback: приватность и предсказуемость.
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def ensure_loopback(base_url: str) -> str:
    """Проверяет, что base_url указывает на loopback; иначе ValueError.

    Локальные клиенты (LM Studio, Ollama) обязаны ходить только на localhost —
    это гарантия, что приватный контур не утекает наружу (решение оператора).
    """
    host = urlparse(base_url).hostname
    if host not in LOOPBACK_HOSTS:
        raise ValueError(
            f"Локальный клиент допускает только loopback-адрес, получено: {base_url!r}")
    return base_url.rstrip("/")


@dataclass
class LLMReply:
    """Структурированный ответ LLM (режим tool-use).

    `content` — текст финального ответа; `tool_calls` — запрошенные вызовы
    инструментов: [{id, name, arguments(dict)}]; `raw` — сырой ответ провайдера
    (только текущий контекст, никогда в память).
    """

    content: str = ""
    tool_calls: list = field(default_factory=list)
    raw: object | None = None


def parse_tool_calls(message) -> list:
    """Извлекает tool_calls из message провайдера (нативный OpenAI-формат)."""
    calls = getattr(message, "tool_calls", None)
    if calls is None and isinstance(message, dict):
        calls = message.get("tool_calls")
    result = []
    for call in calls or []:
        func = getattr(call, "function", None)
        if func is None and isinstance(call, dict):
            func = call.get("function", {})
        name = getattr(func, "name", None) if not isinstance(func, dict) else func.get("name")
        raw_args = getattr(func, "arguments", None) if not isinstance(func, dict) else func.get("arguments")
        call_id = getattr(call, "id", None) if not isinstance(call, dict) else call.get("id")
        try:
            arguments = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
        except (json.JSONDecodeError, TypeError):
            arguments = {}
        if isinstance(name, str) and name:
            result.append({"id": call_id or f"call_{len(result)}",
                           "name": name, "arguments": arguments})
    return result


def parse_fallback_tool_call(content: str) -> dict | None:
    """Детерминированный fallback: LLM вернул JSON {"tool":..,"arguments":..}.

    Возвращает {"id","name","arguments"} либо None (тогда content — финальный текст).
    """
    if not content:
        return None
    text = content.strip()
    # снимаем возможные ```json ... ``` обёртки
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except (json.JSONDecodeError, TypeError):
        return None
    name = data.get("tool") or data.get("name")
    if not isinstance(name, str) or not name:
        return None
    return {"id": "call_fallback", "name": name,
            "arguments": data.get("arguments") or {}}


TOOL_PROTOCOL_PROMPT = (
    "У тебя есть инструменты. Если для ответа нужен инструмент, верни СТРОГО один "
    'JSON-объект вида {"tool": "<имя>", "arguments": {...}} и ничего больше. '
    'Если инструмент не нужен — верни обычный текст или {"final": "<ответ>"}.'
)


def render_tool_protocol(tools) -> str:
    """D2 (Ревизия 5): протокол инструментов, построенный ОТ КАТАЛОГА.

    Перечисляет квалифицированные имена (`mcp.<server>.<tool>`) и обязательные
    аргументы — чтобы fallback-путь не заставлял модель угадывать имена.
    Пустой каталог → базовый `TOOL_PROTOCOL_PROMPT`.
    """
    tools = list(tools or [])
    if not tools:
        return TOOL_PROTOCOL_PROMPT
    lines = [
        "У тебя есть инструменты. Если для ответа нужен инструмент, верни СТРОГО "
        'один JSON-объект вида {"tool": "<имя>", "arguments": {...}} и ничего больше.',
        "Доступные инструменты (используй ТОЧНОЕ имя):",
    ]
    for tool in tools:
        schema = getattr(tool, "input_schema", None) or {}
        required = schema.get("required") or []
        req = f"; обязательные аргументы: {', '.join(required)}" if required else ""
        desc = getattr(tool, "description", "") or ""
        first_line = desc.strip().splitlines()[0] if desc.strip() else "—"
        lines.append(f"- {tool.name} — {first_line}{req}")
    lines.append('Если инструмент не нужен — верни обычный текст или {"final": "<ответ>"}.')
    return "\n".join(lines)


class LLMClient(ABC):
    """Абстрактный LLM-клиент. Сигнатура `complete` неизменяема (контракт §6.1)."""

    @abstractmethod
    def complete(self, messages, **params) -> str:
        """Отправляет список сообщений и возвращает текст ответа (или None при сбое)."""

    def complete_with_tools(self, messages, tools=None, **params) -> LLMReply:
        """Режим tool-use: текст + запрошенные вызовы (по умолчанию — только текст)."""
        text = self.complete(messages, **params)
        if text is None:
            return LLMReply(content="")
        if tools:
            fallback = parse_fallback_tool_call(text)
            if fallback is not None:
                return LLMReply(content="", tool_calls=[fallback])
        return LLMReply(content=text)


class RouterAIClient(LLMClient):
    """Реальный клиент RouterAI (OpenAI-совместимый)."""

    def __init__(self, api_key: str = None, model: str = MODEL, max_tokens: int = None):
        self.api_key = api_key or os.getenv("API_KEY")
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, messages, **params) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {"model": self.model, "messages": messages}
        if self.max_tokens is not None:
            data["max_tokens"] = self.max_tokens
        data.update(params)

        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                response = requests.post(URL, headers=headers, json=data,
                                         timeout=REQUEST_TIMEOUT)
                if response.status_code == 429:
                    if attempt == len(RETRY_DELAYS):
                        print("[API] Лимит запросов: все повторы исчерпаны.")
                        return None
                    time.sleep(RETRY_DELAYS[attempt])
                    continue
                response.raise_for_status()
                result = response.json()
                if "choices" not in result or not result["choices"]:
                    return None
                return result["choices"][0]["message"]["content"] or ""
            except requests.exceptions.RequestException as error:
                print(f"[API] Ошибка сети/HTTP: {error}")
                return None
            except (KeyError, IndexError, ValueError) as error:
                print(f"[API] Неожиданный формат ответа: {error}")
                return None
        return None

    def complete_with_tools(self, messages, tools=None, **params) -> LLMReply:
        """Нативный OpenAI-совместимый tool-use с fallback на текстовый протокол.

        Если провайдер вернул tool_calls — используем их; иначе пробуем разобрать
        fallback-JSON из текста; иначе — обычный ответ.
        """
        if not tools:
            text = self.complete(messages, **params)
            return LLMReply(content=text or "")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {"model": self.model, "messages": messages, "tools": tools,
                "tool_choice": "auto"}
        if self.max_tokens is not None:
            data["max_tokens"] = self.max_tokens
        data.update(params)
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                response = requests.post(URL, headers=headers, json=data,
                                         timeout=REQUEST_TIMEOUT)
                if response.status_code == 429:
                    if attempt == len(RETRY_DELAYS):
                        return LLMReply(content="")
                    time.sleep(RETRY_DELAYS[attempt])
                    continue
                response.raise_for_status()
                message = response.json()["choices"][0]["message"]
            except requests.exceptions.RequestException as error:
                print(f"[API] Ошибка сети/HTTP: {error}")
                return LLMReply(content="")
            except (KeyError, IndexError, ValueError) as error:
                print(f"[API] Неожиданный формат ответа: {error}")
                return LLMReply(content="")
            calls = parse_tool_calls(message)
            if calls:
                return LLMReply(content="", tool_calls=calls, raw=message)
            content = (message.get("content") if isinstance(message, dict)
                       else getattr(message, "content", "")) or ""
            fallback = parse_fallback_tool_call(content)
            if fallback is not None:
                return LLMReply(content="", tool_calls=[fallback], raw=message)
            return LLMReply(content=content, raw=message)
        return LLMReply(content="")


class OpenAICompatClient(LLMClient):
    """Основной локальный клиент (решение №21): OpenAI-совместимый сервер.

    LM Studio, llama.cpp server и любой будущий локальный сервер отдают
    `POST {base}/v1/chat/completions`. Отличия от RouterAIClient: нет внешнего
    хоста и нет Authorization; адрес обязан быть loopback.
    """

    def __init__(self, base_url: str, model: str, max_tokens: int = None,
                 timeout: int = 180, params: dict = None):
        self.base_url = ensure_loopback(base_url)
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.params = dict(params or {})

    def _payload(self, messages, tools=None, **params):
        data = {"model": self.model, "messages": messages}
        if self.max_tokens is not None:
            data["max_tokens"] = self.max_tokens
        data.update(self.params)
        data.update(params)
        if tools:
            data["tools"] = tools
            data["tool_choice"] = "auto"
        return data

    def complete(self, messages, **params) -> str:
        url = f"{self.base_url}/v1/chat/completions"
        data = self._payload(messages, **params)
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                response = requests.post(url, json=data, timeout=self.timeout)
                if response.status_code == 429:
                    if attempt == len(RETRY_DELAYS):
                        print("[LM Studio] Лимит запросов: все повторы исчерпаны.")
                        return None
                    time.sleep(RETRY_DELAYS[attempt])
                    continue
                response.raise_for_status()
                result = response.json()
                if "choices" not in result or not result["choices"]:
                    return None
                return result["choices"][0]["message"]["content"] or ""
            except requests.exceptions.RequestException as error:
                print(f"[LM Studio] Ошибка сети/HTTP: {error}")
                return None
            except (KeyError, IndexError, ValueError) as error:
                print(f"[LM Studio] Неожиданный формат ответа: {error}")
                return None
        return None

    def complete_with_tools(self, messages, tools=None, **params) -> LLMReply:
        """Нативный tool-use с fallback на текстовый протокол (как у RouterAI)."""
        if not tools:
            return LLMReply(content=self.complete(messages, **params) or "")
        url = f"{self.base_url}/v1/chat/completions"
        data = self._payload(messages, tools=tools, **params)
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                response = requests.post(url, json=data, timeout=self.timeout)
                if response.status_code == 429:
                    if attempt == len(RETRY_DELAYS):
                        return LLMReply(content="")
                    time.sleep(RETRY_DELAYS[attempt])
                    continue
                response.raise_for_status()
                message = response.json()["choices"][0]["message"]
            except requests.exceptions.RequestException as error:
                print(f"[LM Studio] Ошибка сети/HTTP: {error}")
                return LLMReply(content="")
            except (KeyError, IndexError, ValueError) as error:
                print(f"[LM Studio] Неожиданный формат ответа: {error}")
                return LLMReply(content="")
            calls = parse_tool_calls(message)
            if calls:
                return LLMReply(content="", tool_calls=calls, raw=message)
            content = (message.get("content") if isinstance(message, dict)
                       else getattr(message, "content", "")) or ""
            fallback = parse_fallback_tool_call(content)
            if fallback is not None:
                return LLMReply(content="", tool_calls=[fallback], raw=message)
            return LLMReply(content=content, raw=message)
        return LLMReply(content="")


class OllamaClient(LLMClient):
    """Альтернативный локальный клиент: Ollama `/api/chat` (не OpenAI-формат).

    Нативного function-calling у эндпоинта не предполагаем — `complete_with_tools`
    использует базовый fallback-протокол (`parse_fallback_tool_call`). Адрес —
    только loopback.
    """

    def __init__(self, base_url: str, model: str, max_tokens: int = None,
                 timeout: int = 180, params: dict = None, keep_alive: str = None):
        self.base_url = ensure_loopback(base_url)
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.params = dict(params or {})
        self.keep_alive = keep_alive

    def _options(self, **params):
        options = {}
        if self.max_tokens is not None:
            options["num_predict"] = self.max_tokens
        for key in ("temperature", "top_p", "num_ctx"):
            if key in self.params:
                options[key] = self.params[key]
        for key in ("temperature", "top_p", "num_ctx", "num_predict"):
            if key in params:
                options[key] = params[key]
        return options

    def complete(self, messages, **params) -> str:
        url = f"{self.base_url}/api/chat"
        data = {"model": self.model, "messages": messages, "stream": False,
                "options": self._options(**params)}
        if self.keep_alive is not None:
            data["keep_alive"] = self.keep_alive
        for attempt in range(2):
            try:
                response = requests.post(url, json=data, timeout=self.timeout)
                response.raise_for_status()
                result = response.json()
                message = result.get("message") or {}
                return message.get("content") or ""
            except requests.exceptions.RequestException as error:
                if attempt == 1:
                    print(f"[Ollama] Ошибка сети/HTTP: {error}")
                    return None
                time.sleep(RETRY_DELAYS[attempt])
            except (KeyError, ValueError) as error:
                print(f"[Ollama] Неожиданный формат ответа: {error}")
                return None
        return None


class MockClient(LLMClient):
    """Детерминированная заглушка для тестов и прогонов без живого ключа.

    Возвращает ответ, отражающий поданный контекст: перечисляет, какие блоки
    памяти/сообщения видит, — это позволяет сценариям проверять «доставку»
    слоёв без реальных вызовов API.
    """

    def __init__(self, name: str = "Mock"):
        self.name = name
        self.calls = []

    def complete(self, messages, **params) -> str:
        self.calls.append(messages)
        # Собираем видимый контекст: роли и первые символы содержимого.
        seen = []
        for msg in messages:
            role = msg.get("role", "?")
            content = str(msg.get("content", ""))
            seen.append(f"{role}:{content[:80]}")
        return f"[{self.name}] вижу {len(messages)} сообщений: " + " || ".join(seen)

    def complete_with_tools(self, messages, tools=None, **params) -> LLMReply:
        """Детерминированный tool-use: по намерению в запросе предлагает вызов."""
        self.calls.append(messages)
        if not tools:
            return LLMReply(content=self.complete(messages, **params))
        # Последний user-запрос (до подмешивания tool-результатов).
        query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                query = str(msg.get("content", ""))
                break
        names = {t["function"]["name"] for t in tools
                 if isinstance(t, dict) and "function" in t}
        # Есть ли в истории результат инструмента? → формируем финальный ответ.
        for msg in messages:
            if msg.get("role") in ("tool", "function"):
                return LLMReply(content=(
                    f"[{self.name}] Инструмент вызван; результат: "
                    f"{str(msg.get('content', ''))[:200]}"))
        lowered = query.lower()
        # День 17: намерение «который час / время / time» → вызов get_time.
        if any(w in lowered for w in ("час", "врем", "time", "timezone")):
            for name in names:
                if "get_time" in name:
                    tz = "Europe/Moscow" if "москв" in lowered else "UTC"
                    return LLMReply(tool_calls=[
                        {"id": "call_mock_time", "name": name,
                         "arguments": {"timezone_name": tz}}])
        if "москв" in lowered:
            for name in names:
                if "search_locations" in name or "location" in name:
                    return LLMReply(tool_calls=[
                        {"id": "call_mock_1", "name": name,
                         "arguments": {"query": "Москва"}}])
        return LLMReply(content=self.complete(messages, **params))