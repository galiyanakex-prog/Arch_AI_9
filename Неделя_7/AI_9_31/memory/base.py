# -*- coding: utf-8 -*-
"""Базовый контракт модели памяти: MemoryLayer (ABC) + метаданные + задел PolicyEngine.

Единый интерфейс для всех типов памяти (краткосрочная / рабочая / долговременная /
профиль). Каждый объект памяти несёт метаданные (scope, owner, visibility, source,
source_message_id). PolicyEngine здесь — пустой интерфейс-задел под фильтр инвариантов
следующих дней (в Дне 11 рабочий фильтр НЕ реализуем).
"""
from abc import ABC, abstractmethod


# Канонический контекст пути: что читать/писать и куда.
# Передаётся в каждый метод слоёв вместо «догадывания» путей.
class MemoryContext:
    """Адресный контекст: чья память и в рамках какой задачи/сессии/профиля читаем."""

    def __init__(self, user_id: str, task: str = "", session_id: str = "",
                 profile_id: str = ""):
        self.user_id = user_id
        self.task = task
        self.session_id = session_id
        # profile_id — аддитивный параметр (персонализация): "" → активный/дефолтный
        # профиль. Существующие вызовы с 3 аргументами работают без изменений.
        self.profile_id = profile_id

    def as_dict(self) -> dict:
        return {"user_id": self.user_id, "task": self.task,
                "session_id": self.session_id, "profile_id": self.profile_id}


# Обёртка над одним объектом памяти с метаданными (arch_prim R5).
class MemoryItem:
    """Элемент памяти: content + метаданные (scope/owner/visibility/source/...)."""

    def __init__(self, content, source: str = "unknown", scope: str = "",
                 owner: str = "", visibility: str = "private",
                 source_message_id: str = "", role: str = ""):
        self.content = content
        self.source = source          # user | model | document | system
        self.scope = scope            # user | task | session
        self.owner = owner
        self.visibility = visibility  # private (заделы под scope/visibility)
        self.source_message_id = source_message_id
        self.role = role              # user | assistant (для краткосрочной памяти)

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "source": self.source,
            "scope": self.scope,
            "owner": self.owner,
            "visibility": self.visibility,
            "source_message_id": self.source_message_id,
            "role": self.role,
        }


class MemoryLayer(ABC):
    """Единый контракт памяти: всякий тип — это read/write + блок в промт.

    layer_name: short_term | working | long_term | profile
    scope:      session | task | user
    """
    layer_name: str = "memory"
    scope: str = "user"

    def __init__(self, store, log=None):
        self.store = store
        self.log = log or (lambda line: None)

    @abstractmethod
    def read(self, ctx: MemoryContext) -> dict:
        """Возвращает содержимое слоя для контекста ctx (dict)."""

    @abstractmethod
    def write(self, ctx: MemoryContext, item: MemoryItem) -> str:
        """Сохраняет объект памяти. Возвращает строку «куда легло» (для лога)."""

    @abstractmethod
    def as_prompt_block(self, ctx: MemoryContext) -> str:
        """Текстовый блок этого слоя для подстановки в промт."""


# Задел под фильтр инвариантов/прав следующих дней (в Дне 11 не работает).
class PolicyEngine:
    """Пустой интерфейс-задел. Рабочий фильтр инвариантов — следующие дни недели 3."""