# -*- coding: utf-8 -*-
"""Task State Machine — строгая машина состояний задачи (День 15).

Модернизация автомата Дня 13/14 по канону `Задание_Д15.txt` и
`arch_den_15.md` §2.2–2.9: жизненный цикл задачи — контролируемые переходы.

  * TaskStage — 8 допустимых состояний: NEW, PLANNING, PLAN_APPROVED (новое),
    IMPLEMENTATION (бывший execution — канон имён из задания), VALIDATION,
    DONE, PAUSED, FAILED; любое состояние вне набора — недопустимое;
  * ALLOWED_TRANSITIONS — явная карта разрешённых переходов (whitelist):
    запреты задания реализуются ОТСУТСТВИЕМ дуг (planning → implementation
    нет — «нельзя реализацию до утверждённого плана»; в DONE — только из
    VALIDATION — «нельзя финал без валидации»);
  * can_transition(from, to) -> bool — единственный источник истины: карта;
  * try_transition(state, proposed) — единственная точка смены этапа:
    недопустимый переход → InvalidTransitionError, состояние НЕ меняется,
    попытка пишется в transition_log (allowed=False);
  * InvalidTransitionError — объясняет правило и список разрешённых;
  * REFUSAL_RULES / refusal_text — детерминированные тексты отказов
    (правило + корректный следующий шаг), без LLM;
  * transition_log — журнал переходов (успехи и отказы), переживает
    перезапуск вместе со снимком;
  * approve_plan() — утверждение плана: planning → plan_approved
    (контрольный пункт проходит только человек);
  * pause_task()/resume_task() — пауза на любой рабочей стадии и возврат
    в previous_stage (пауза — не лазейка: из PAUSED выход только resume);
  * run_task() — один проход автомата: new → planning (план построен,
    остановка на утверждении) → [approve] → plan_approved → implementation
    (шаги) → validation → done | failed.

Главная идея задания: LLM составляет план и наполняет шаги, но код карты
переходов не даёт «перепрыгнуть» этап — даже если пользователь или LLM
просят «сразу к реализации».
"""
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional


class TaskStage(str, Enum):
    """Допустимые состояния задачи (канон `Задание_Д15.txt`).

    4 базовых этапа куратора (planning → execution → validation → done)
    детализируются, не удаляются: execution расщепляется на plan_approved +
    implementation; добавляется входная стадия new; расширения Дня 13
    (paused/failed) сохраняются.
    """

    NEW = "new"                      # задача создана, но ещё не начата
    PLANNING = "planning"            # план строится/построен, не утверждён
    PLAN_APPROVED = "plan_approved"  # план утверждён пользователем (/approve)
    IMPLEMENTATION = "implementation"  # реализация (бывший execution)
    VALIDATION = "validation"        # проверка/тестирование
    DONE = "done"                    # завершена (терминальная)
    PAUSED = "paused"                # пауза (возврат в previous_stage)
    FAILED = "failed"                # ошибка (восстановление — /task retry)


# Миграция снимков Дней 13/14: "execution" → implementation (канон имён Дня 15).
STAGE_ALIASES = {"execution": TaskStage.IMPLEMENTATION}

# Рабочие стадии: пауза разрешена (DONE/FAILED — отказ с объяснением).
WORKING_STAGES = (TaskStage.NEW, TaskStage.PLANNING, TaskStage.PLAN_APPROVED,
                  TaskStage.IMPLEMENTATION, TaskStage.VALIDATION)


@dataclass
class TaskState:
    """Формализованное состояние задачи (канон `Задание_Д15.txt`).

    В любой момент явно записаны: этап (stage), текущий шаг (current_step +
    steps), ожидаемое действие (expected_action) и журнал переходов
    (transition_log — попытки и отказы, append-only).
    """

    task_id: str
    objective: str

    stage: TaskStage = TaskStage.NEW
    current_step: int = 0
    steps: list = field(default_factory=list)

    expected_action: Optional[str] = None
    results: list = field(default_factory=list)

    previous_stage: Optional[TaskStage] = None   # куда вернуться после паузы
    error: Optional[str] = None
    transition_log: list = field(default_factory=list)  # журнал переходов

    # --- Сериализация (снимок task_state.json) -----------------------------------
    def to_dict(self) -> dict:
        """Снимок для JSON: enum → .value, журнал копируется."""
        data = asdict(self)
        data["stage"] = self.stage.value
        data["previous_stage"] = self.previous_stage.value if self.previous_stage else None
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "TaskState":
        """Восстановление из снимка (миграция снимков Дней 13/14).

        "execution" → IMPLEMENTATION (алиас); отсутствие transition_log → [];
        отсутствие stage → NEW (входная стадия — явная). Битые данные
        (неизвестная стадия и т.п.) → ValueError (вызывающий решает: битый
        файл = задачи нет, старт с NEW).
        """
        data = dict(data)
        raw_stage = data.pop("stage", None)
        if raw_stage is None:
            data["stage"] = TaskStage.NEW
        else:
            data["stage"] = STAGE_ALIASES.get(raw_stage) or TaskStage(raw_stage)
        if data.get("previous_stage"):
            data["previous_stage"] = TaskStage(data["previous_stage"])
        else:
            data["previous_stage"] = None
        data.setdefault("transition_log", [])
        return cls(**data)


# Разрешённые переходы (whitelist: разрешено только перечисленное; всё
# остальное запрещено по умолчанию — запрет реализуется отсутствием дуги).
# Ключевые запреты канона: из PLANNING НЕТ дуги в IMPLEMENTATION («нельзя
# реализацию до утверждённого плана»); в DONE — только из VALIDATION
# («нельзя финал без валидации»); из PAUSED — пусто (выход только
# resume_task() → previous_stage: пауза — не лазейка).
ALLOWED_TRANSITIONS = {
    TaskStage.NEW:            {TaskStage.PLANNING, TaskStage.PAUSED, TaskStage.FAILED},
    TaskStage.PLANNING:       {TaskStage.PLAN_APPROVED, TaskStage.PAUSED, TaskStage.FAILED},
    TaskStage.PLAN_APPROVED:  {TaskStage.IMPLEMENTATION, TaskStage.PLANNING,
                               TaskStage.PAUSED, TaskStage.FAILED},
    TaskStage.IMPLEMENTATION: {TaskStage.VALIDATION, TaskStage.PLANNING,
                               TaskStage.PAUSED, TaskStage.FAILED},
    TaskStage.VALIDATION:     {TaskStage.DONE, TaskStage.IMPLEMENTATION,
                               TaskStage.PLANNING, TaskStage.PAUSED, TaskStage.FAILED},
    TaskStage.PAUSED:         set(),                    # выход только через resume_task()
    TaskStage.DONE:           set(),                    # терминальная
    TaskStage.FAILED:         {TaskStage.PLANNING},     # восстановление — явный /task retry
}


def can_transition(from_state: TaskStage, to_state: TaskStage) -> bool:
    """Разрешён ли переход. Единственный источник истины — ALLOWED_TRANSITIONS."""
    return to_state in ALLOWED_TRANSITIONS.get(from_state, set())


# Тексты правил отказов (детерминированно, без LLM): правило + корректный
# следующий шаг. Пары без специального правила — общий шаблон refusal_text.
REFUSAL_RULES = {
    (TaskStage.NEW, TaskStage.IMPLEMENTATION):
        "Нельзя делать реализацию до утверждённого плана. "
        "Сначала сформируйте план: /plan <цель>, затем утвердите: /approve",
    (TaskStage.PLANNING, TaskStage.IMPLEMENTATION):
        "Нельзя делать реализацию до утверждённого плана. "
        "Сначала утвердите план: /approve",
    (TaskStage.NEW, TaskStage.DONE):
        "Нельзя завершать задачу без плана, реализации и валидации. "
        "Сначала: /plan <цель> → /approve → /run",
    (TaskStage.PLANNING, TaskStage.DONE):
        "Нельзя завершать задачу без реализации и валидации. "
        "Сначала утвердите план (/approve) и выполните шаги (/run)",
    (TaskStage.PLAN_APPROVED, TaskStage.DONE):
        "Нельзя завершать задачу без реализации и валидации. "
        "Сначала выполните шаги (/run) и пройдите валидацию",
    (TaskStage.IMPLEMENTATION, TaskStage.DONE):
        "Нельзя делать финал без валидации. "
        "Сначала завершите шаги — автомат сам перейдёт в validation",
}


def refusal_text(current: TaskStage, proposed: TaskStage) -> str:
    """Текст правила для попытки перехода current → proposed (без LLM).

    Специальное правило из REFUSAL_RULES → правило + корректный шаг;
    терминальные/пауза — свои объяснения; прочее — общий шаблон со списком
    разрешённых из текущей стадии.
    """
    rule = REFUSAL_RULES.get((current, proposed))
    if rule:
        return rule
    if current == TaskStage.DONE:
        return ("done — терминальная стадия: задача завершена, переходы "
                "невозможны (новая задача: /plan <цель>)")
    if current == TaskStage.PAUSED:
        return ("Из паузы возврат только в прежнюю стадию: /resume "
                "(пауза — не способ обойти утверждение плана или валидацию)")
    allowed = sorted(s.value for s in ALLOWED_TRANSITIONS.get(current, set()))
    return (f"Переход {current.value} → {proposed.value} не разрешён картой "
            f"переходов. Разрешено из {current.value}: {', '.join(allowed) or '—'}")


class InvalidTransitionError(Exception):
    """Недопустимый переход: состояние не меняется, попытка логируется.

    Сообщение объясняет правило и список разрешённых переходов из текущей
    стадии (канон `Задание_Д15.txt`).
    """

    def __init__(self, current: TaskStage, proposed: TaskStage):
        self.current = current
        self.proposed = proposed
        allowed = sorted(s.value for s in ALLOWED_TRANSITIONS.get(current, set()))
        super().__init__(
            f"Переход {current.value} → {proposed.value} запрещён. "
            f"Разрешено из {current.value}: {', '.join(allowed) or '—'}."
        )


def _noop(line: str) -> None:
    """Пустой логгер по умолчанию (модуль не зависит от печати)."""
    return None


def _log_transition(state: TaskState, frm: TaskStage, to: TaskStage,
                    allowed: bool, reason: str = "") -> None:
    """Запись в журнал переходов: при КАЖДОЙ попытке (успех и отказ).

    Append-only: журнал не переписывается, переживает перезапуск вместе со
    снимком. allowed=False — попытка отклонена, состояние не менялось.
    """
    state.transition_log.append({
        "from": frm.value,
        "to": to.value,
        "allowed": allowed,
        "reason": reason,
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


def try_transition(state: TaskState, proposed: TaskStage) -> TaskState:
    """Единственная точка смены этапа (канон `Задание_Д15.txt`).

    Недопустимый переход → InvalidTransitionError: состояние НЕ меняется,
    попытка пишется в transition_log (allowed=False, reason — правило).
    Допустимый — меняет stage и пишет запись allowed=True.
    """
    if not can_transition(state.stage, proposed):
        reason = refusal_text(state.stage, proposed)
        _log_transition(state, state.stage, proposed, allowed=False, reason=reason)
        raise InvalidTransitionError(state.stage, proposed)
    _log_transition(state, state.stage, proposed, allowed=True)
    state.stage = proposed
    return state


def transition(state: TaskState, target: TaskStage, log: Callable = None) -> bool:
    """Обёртка над try_transition (обратная совместимость callers Дней 13/14).

    Возвращает True, если переход разрешён и выполнен; False — если запрещён
    (состояние не меняется — уже обеспечено try_transition; в лог пишется
    ворнинг). «Код запрещает, промт рекомендует».
    """
    log = log or _noop
    try:
        try_transition(state, target)
        log(f"[Автомат] {state.transition_log[-1]['from']} → {target.value}")
        return True
    except InvalidTransitionError as error:
        log(f"[Автомат] переход запрещён: {error}")
        return False


def approve_plan(state: TaskState, log: Callable = None) -> str:
    """Утверждение плана: planning → plan_approved (только человек, /approve).

    Идемпотентна по смыслу: из plan_approved — «план уже утверждён» (без
    изменения состояния); из прочих стадий — отказ с объяснением и
    корректным шагом. Возвращает текст результата для CLI/лога.
    """
    log = log or _noop
    if state.stage == TaskStage.PLANNING:
        try_transition(state, TaskStage.PLAN_APPROVED)
        state.expected_action = "начать реализацию (/step или /run)"
        message = ("[Автомат] planning → plan_approved: план утверждён "
                   f"({len(state.steps)} шагов)")
        log(message)
        return message
    if state.stage == TaskStage.PLAN_APPROVED:
        message = "[Автомат] /approve: план уже утверждён (можно /step или /run)"
        log(message)
        return message
    if state.stage == TaskStage.NEW:
        message = ("[Автомат] /approve: плана ещё нет — сначала постройте его: "
                   "/plan <цель>")
        log(message)
        return message
    if state.stage in (TaskStage.IMPLEMENTATION, TaskStage.VALIDATION):
        message = (f"[Автомат] /approve: план уже утверждён — идёт "
                   f"{state.stage.value}")
        log(message)
        return message
    message = (f"[Автомат] /approve: утверждение плана невозможно на стадии "
               f"{state.stage.value}")
    log(message)
    return message


def pause_task(state: TaskState, log: Callable = None) -> TaskState:
    """Пауза на любой рабочей стадии. paused — НЕ потеря состояния.

    Разрешена из NEW/PLANNING/PLAN_APPROVED/IMPLEMENTATION/VALIDATION; из
    DONE/FAILED — отказ с объяснением (состояние не меняется, попытка в
    журнале). Сохраняет previous_stage и позицию шага; идемпотентна.
    expected_action НЕ перезаписывается: после resume ожидаемое действие
    восстанавливается (факт паузы несёт сам stage == PAUSED).
    """
    log = log or _noop
    if state.stage == TaskStage.PAUSED:
        return state
    if state.stage not in WORKING_STAGES:
        reason = (f"Пауза невозможна на стадии {state.stage.value}: "
                  "задача завершена или в восстановлении")
        _log_transition(state, state.stage, TaskStage.PAUSED,
                        allowed=False, reason=reason)
        log(f"[Автомат] /pause: {reason}")
        return state
    previous = state.stage
    _log_transition(state, state.stage, TaskStage.PAUSED, allowed=True)
    state.previous_stage = previous
    state.stage = TaskStage.PAUSED
    return state


def resume_task(state: TaskState, log: Callable = None) -> TaskState:
    """Продолжение после паузы — возврат в previous_stage с того же шага.

    Идемпотентна: если задача не на паузе — no-op. current_step и
    expected_action не трогаются — план не перестраивается, выполненные шаги
    не повторяются. Пауза — не лазейка: возврат ТОЛЬКО в прежнюю стадию.
    """
    if state.stage != TaskStage.PAUSED:
        return state
    target = state.previous_stage or TaskStage.IMPLEMENTATION
    _log_transition(state, state.stage, target, allowed=True)
    state.stage = target
    state.previous_stage = None
    return state


def save_state(state: TaskState, filename: str) -> None:
    """Сохраняет состояние в JSON (включая transition_log).

    ensure_ascii=False, indent=2 — человекочитаемый снимок на диске.
    """
    data = state.to_dict()
    directory = os.path.dirname(filename)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def load_state(filename: str) -> Optional[TaskState]:
    """Загружает состояние из JSON после «перезапуска».

    Миграция снимков Дней 13/14 ("execution" → implementation, отсутствие
    transition_log → []). Битый/отсутствующий файл → None (не роняет
    приложение: задача стартует с NEW).
    """
    try:
        with open(filename, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None
    try:
        return TaskState.from_dict(data)
    except (ValueError, KeyError, TypeError):
        return None


def _build_plan(state: TaskState, executor, log: Callable) -> None:
    """Сборка плана: LLM (или заглушка) составляет шаги; код принимает список."""
    state.steps = list(executor.plan(state.objective))
    state.current_step = 0
    state.expected_action = "утвердить план (/approve)"
    log(f"[Автомат] план построен ({len(state.steps)} шагов), "
        "ожидает утверждения (/approve)")


def _implementation_pass(state: TaskState, executor, log: Callable) -> None:
    """Один проход реализации: шаг → результат; шаги кончились → validation."""
    if state.current_step >= len(state.steps):
        state.expected_action = "провести валидацию"
        try_transition(state, TaskStage.VALIDATION)
        return
    step = state.steps[state.current_step]
    result = executor.execute(step)          # здесь агент вызывает инструмент/LLM
    state.results.append(result)
    state.current_step += 1
    # Ожидаемое действие — СЛЕДУЮЩИЙ шаг (семантика снимка: current_step=1 ↔
    # expected_action=steps[1]); шаги кончились — валидация.
    if state.current_step < len(state.steps):
        state.expected_action = state.steps[state.current_step]
    else:
        state.expected_action = "провести валидацию"


def run_task(state: TaskState, executor, validator: Callable, log: Callable = None) -> TaskState:
    """Один проход автомата (канон `Задание_Д15.txt`: утверждение — человек).

    executor — объект с .plan(objective) -> list[str] и .execute(step) -> Any
    (живая LLM или детерминированная заглушка); validator(results) -> bool.
    Каждый вызов = один атомарный шаг; завершённые шаги НЕ повторяются.

    Поток: new → planning (план построен, ОСТАНОВКА на утверждении) →
    [approve_plan] → plan_approved → implementation (первый шаг в этом же
    проходе) → шаги → validation → done | failed. Из planning проход НЕ
    переходит в реализацию: /run не может обойти утверждение плана.
    """
    log = log or _noop

    if state.stage == TaskStage.NEW:
        # Входная стадия: переход к планированию + сборка плана.
        try_transition(state, TaskStage.PLANNING)
        _build_plan(state, executor, log)

    elif state.stage == TaskStage.PLANNING:
        # План построен (или строится): остановка — утверждение только человеком.
        if not state.steps:
            _build_plan(state, executor, log)
        else:
            state.expected_action = "утвердить план (/approve)"
            log("[Автомат] план ожидает утверждения (/approve) — "
                "переход в реализацию без утверждения запрещён")

    elif state.stage == TaskStage.PLAN_APPROVED:
        # Утверждённый план: переход в реализацию + первый шаг этим же проходом.
        try_transition(state, TaskStage.IMPLEMENTATION)
        _implementation_pass(state, executor, log)

    elif state.stage == TaskStage.IMPLEMENTATION:
        _implementation_pass(state, executor, log)

    elif state.stage == TaskStage.VALIDATION:
        if validator(state.results):
            state.expected_action = None
            try_transition(state, TaskStage.DONE)
        else:
            state.error = "Проверка результата не пройдена"
            try_transition(state, TaskStage.FAILED)

    # PAUSED/DONE/FAILED — no-op: пауза снимается /resume, failed — /task retry.

    return state