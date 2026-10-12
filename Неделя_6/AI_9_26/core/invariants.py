# -*- coding: utf-8 -*-
"""Инварианты и ограничения состояния (День 14).

Неизменяемые правила, которые агент не имеет права нарушать (канон
`Задание_Д14.txt`, целевое состояние `arch_den_14.md` §2.2–2.4, §2.10):

  * Invariant        — одно правило (id, description, category, severity, active);
  * ConstraintSet    — набор правил — ОТДЕЛЬНАЯ сущность (не память, не профиль,
                       не история диалога); хранится своим файлом и переживает
                       очистку истории и перезапуск процесса;
  * ProposedAction   — предлагаемое действие, которое проверяется кодом;
  * InvariantChecker — интерфейс (ABC) + RuleBasedChecker: детерминированная
                       проверка действия ДО изменения состояния/запуска инструмента;
  * update_invariant — изменение правила ТОЛЬКО отдельной авторизованной операцией.

«Код запрещает, промт рекомендует»: правила попадают в промт как рекомендация
(этап M3), но жёсткий запрет обеспечивает именно эта проверка. Обычное сообщение
пользователя НЕ считается разрешением нарушить инвариант.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional

# Известные технологии/языки — для детерминированной проверки по id-неймспейсу.
KNOWN_FRAMEWORKS = {"django", "fastapi", "flask"}
KNOWN_LANGUAGES = {"python", "kotlin", "java", "javascript", "go"}


@dataclass
class Invariant:
    """Одно неизменяемое правило (канон `Задание_Д14.txt`)."""

    id: str                       # "framework.django"
    description: str              # "Использовать Django, а не FastAPI или Flask"
    category: str                 # stack | architecture | technical | business
    severity: str = "error"       # error — блокирует; warning — только предупреждает
    active: bool = True


@dataclass
class ConstraintSet:
    """Набор инвариантов — отдельная сущность (не TaskState и не история диалога).

    Состояние задачи и инварианты — разные вещи:
      TaskState:     текущий этап; шаг; результаты; ожидаемое действие.
      ConstraintSet: обязательные правила; архитектурные решения; ограничения.
    """

    invariants: list = field(default_factory=list)

    def active(self) -> list:
        """Только включённые правила (выключенные не проверяются и не блокируют)."""
        return [inv for inv in self.invariants if inv.active]

    def by_id(self, invariant_id: str) -> Optional[Invariant]:
        """Правило по id или None."""
        for inv in self.invariants:
            if inv.id == invariant_id:
                return inv
        return None

    def to_dict(self) -> dict:
        """Снимок для JSON (`invariants.json`)."""
        return {"invariants": [asdict(inv) for inv in self.invariants]}

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "ConstraintSet":
        """Восстановление набора из JSON; битый/пустой вход → пустой набор.

        Пустой набор = все действия разрешены (поведение дней 11–13); приложение
        не падает на отсутствующем/повреждённом файле.
        """
        if not data or not isinstance(data, dict):
            return cls()
        invariants = []
        for item in data.get("invariants") or []:
            try:
                invariants.append(Invariant(
                    id=item["id"],
                    description=item.get("description", ""),
                    category=item.get("category", ""),
                    severity=item.get("severity", "error"),
                    active=bool(item.get("active", True)),
                ))
            except (KeyError, TypeError, AttributeError):
                continue
        return cls(invariants=invariants)


@dataclass
class ProposedAction:
    """Предлагаемое действие агента — то, что проверяется кодом перед исполнением.

    Поля покрывают каталог-пример (`arch_den_14.md` §2.4); расширяемые поля
    (language, target_file, package, ...) добавляются под конкретные инварианты.
    Поля MCP-вызова (action_type/tool_name/arguments, День 16) — опциональны и
    обратно совместимы: одно правило «нельзя менять схему БД» работает и для
    локальной функции, и для MCP-инструмента.
    """

    description: str
    technology: Optional[str] = None
    adds_dependency: bool = False
    changes_database_schema: bool = False
    language: Optional[str] = None
    # --- MCP-вызов (День 16, опционально) ---
    action_type: str = ""              # "tool_call" | "local" | ...
    tool_name: Optional[str] = None    # квалифицированное имя ("mcp.weather.…")
    arguments: Optional[dict] = None   # аргументы вызова


def _rule_for(inv: Invariant):
    """Предикат «действие нарушает правило» для известного id (иначе None).

    Проверка детерминированная и не зависит от LLM: сопоставляем поля
    ProposedAction с id-неймспейсом правила (framework.*, stack.*) или с
    конкретным id (dependencies.no-new, database.no-schema-changes). Правила по
    неймспейсу расширяемы: добавленный `framework.flask` заработает без правок.
    """
    if inv.id.startswith("framework."):
        allowed = inv.id.split(".", 1)[1]
        return lambda a: a.technology in KNOWN_FRAMEWORKS and a.technology != allowed
    if inv.id.startswith("stack."):
        allowed = inv.id.split(".", 1)[1]
        return lambda a: a.language is not None and a.language != allowed
    if inv.id == "dependencies.no-new":
        return lambda a: bool(a.adds_dependency)
    if inv.id == "database.no-schema-changes":
        return lambda a: bool(a.changes_database_schema)
    if inv.id.startswith("tool.deny."):
        # Запрет конкретного инструмента (День 16): id «tool.deny.<qualified_name>».
        banned = inv.id.split(".", 2)[2]
        return lambda a: a.action_type == "tool_call" and a.tool_name == banned
    return None


class InvariantChecker(ABC):
    """Интерфейс проверки действия на соответствие инвариантам.

    Возвращает список нарушений (пустой список = действие разрешено). Конкретная
    реализация инжектится в Agent (полиморфизм, тестируемость без LLM).
    """

    @abstractmethod
    def check(self, action: ProposedAction, constraints: ConstraintSet) -> list:
        """Блокирующие нарушения (severity='error'): непусто → действие запрещено."""

    @abstractmethod
    def warnings(self, action: ProposedAction, constraints: ConstraintSet) -> list:
        """Неблокирующие предупреждения (severity='warning'): действие выполняется."""


class RuleBasedChecker(InvariantChecker):
    """Детерминированная реализация: правила по id-неймспейсу, без вызовов LLM.

    Несколько нарушений возвращаются одновременно (не только первое).
    """

    def _collect(self, action: ProposedAction, constraints: ConstraintSet,
                 severity: str) -> list:
        violations = []
        for inv in constraints.active():
            if inv.severity != severity:
                continue
            rule = _rule_for(inv)
            if rule is not None and rule(action):
                violations.append(f"Нарушен инвариант {inv.id}: {inv.description}")
        return violations

    def check(self, action: ProposedAction, constraints: ConstraintSet) -> list:
        return self._collect(action, constraints, "error")

    def warnings(self, action: ProposedAction, constraints: ConstraintSet) -> list:
        return self._collect(action, constraints, "warning")


def add_invariant(constraints: ConstraintSet, invariant: Invariant) -> None:
    """Добавляет правило; при совпадении id запись обновляется (идемпотентно)."""
    existing = constraints.by_id(invariant.id)
    if existing is not None:
        constraints.invariants[constraints.invariants.index(existing)] = invariant
    else:
        constraints.invariants.append(invariant)


def update_invariant(constraints: ConstraintSet, invariant_id: str,
                     new_description: str, authorized: bool = False) -> None:
    """Изменяет описание правила — ТОЛЬКО отдельной авторизованной операцией.

    Обычная фраза в диалоге («а давай теперь на FastAPI») не меняет правило:
    без authorized=True поднимается PermissionError (канон `Задание_Д14.txt`).
    """
    if not authorized:
        raise PermissionError(
            "Изменение инвариантов требует отдельного подтверждения.")
    inv = constraints.by_id(invariant_id)
    if inv is None:
        raise KeyError(f"Инвариант не найден: {invariant_id}")
    inv.description = new_description


def toggle_invariant(constraints: ConstraintSet, invariant_id: str,
                     active: bool) -> bool:
    """Включает/выключает правило. False — если правила с таким id нет."""
    inv = constraints.by_id(invariant_id)
    if inv is None:
        return False
    inv.active = bool(active)
    return True


def example_constraints() -> ConstraintSet:
    """Каталог-пример набора инвариантов (`arch_den_14.md` §2.4, Python-проект)."""
    return ConstraintSet(invariants=[
        Invariant(id="stack.python", category="stack",
                  description="Использовать только Python 3.12"),
        Invariant(id="framework.django", category="architecture",
                  description="Использовать Django, а не FastAPI или Flask"),
        Invariant(id="dependencies.no-new", category="technical",
                  description="Не добавлять новые внешние зависимости"),
        Invariant(id="database.no-schema-changes", category="business",
                  description="Не изменять схему базы данных"),
    ])
