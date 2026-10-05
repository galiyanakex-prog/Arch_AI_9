# -*- coding: utf-8 -*-
"""Оркестратор Agent: идентификация, интервью, цикл «сообщение → память → промт → LLM».

Жизненный цикл (канон arch_den_11 §2.7):
  старт → идентификация user_id → загрузка профиля + long-term + список задач;
  новый id → интервью (style/constraints/context) → создание users/<id>/... и
  первая задача по смыслу сессии;
цикл:
  сообщение → remember(...) по типам → PromptBuilder(deliver=...) →
  LLMClient.complete → ответ; переход на другую задачу фиксируется отметкой +
  новой задачей со ссылкой на сессию-источник.

Агент не владеет файлами/БД напрямую: работает через MemoryManager и PromptBuilder
(инкапсуляция через фасады, arch_prim R3).
"""
from dataclasses import asdict, replace
from datetime import datetime
import json
import time

from memory.base import MemoryContext, MemoryItem
from memory.manager import MemoryManager
from storage.store import safe_name
from core.prompt_builder import PromptBuilder
from core.llm_client import LLMClient
from core.profile_router import ProfileRouter
from core.state_machine import (
    TaskStage, TaskState, run_task, pause_task, resume_task, transition,
    approve_plan, try_transition, can_transition, refusal_text,
    InvalidTransitionError,
)
from core.invariants import (
    ConstraintSet, ProposedAction, Invariant, InvariantChecker, RuleBasedChecker,
    add_invariant as _add_invariant, update_invariant as _update_invariant,
    toggle_invariant as _toggle_invariant,
)

# Детерминированный анализатор текста → ProposedAction (по умолчанию). Работает без
# живого ключа: распознаёт известный стек/фреймворк/признаки зависимости и схемы БД.
KNOWN_FRAMEWORKS = ("fastapi", "django", "flask")
KNOWN_LANGUAGES = ("python", "kotlin", "java", "javascript", "go")


class PromptContext:
    """Контекст, который PromptBuilder собирает в список сообщений."""

    def __init__(self, query: str, memory_blocks: dict, summary: str = "",
                 short_term_messages: list = None, invariants=None,
                 tools=None, tools_block: str = "", max_tools: int = 20,
                 max_schema_tokens: int = 600, rag_block: str = ""):
        self.query = query
        self.memory_blocks = memory_blocks
        self.summary = summary
        self.short_term_messages = short_term_messages or []
        # Инварианты (День 14): строка или ConstraintSet → блок [system: invariants].
        self.invariants = invariants
        # Инструменты (День 16): список ToolDescriptor → блок [tools] (под лимитами).
        self.tools = tools or []
        self.tools_block = tools_block
        self.max_tools = max_tools
        self.max_schema_tokens = max_schema_tokens
        # RAG (Ревизия 6): готовый текст блока [rag] (источники + инструкция).
        # Пусто → PromptBuilder блок не добавляет (без --rag промпт не меняется).
        self.rag_block = rag_block


class LLMExecutor:
    """Инжектируемая зависимость автомата: LLM составляет план и наполняет шаги.

    Канон arch_den_13 §2.4: `run_task(state, executor, validator)` принимает executor
    с методами `.plan(objective) -> list[str]` и `.execute(step) -> Any`. Здесь LLM
    строит список шагов (по одному в строке) и выполняет каждый шаг запросом с блоком
    рабочей памяти (этап/шаг/действие). В тестах инжектится детерминированная заглушка.
    """

    def __init__(self, llm: LLMClient, agent: "Agent" = None, log=None):
        self.llm = llm
        self.agent = agent
        self.log = log or (lambda line: None)

    def plan(self, objective: str) -> list:
        """Просит LLM разбить цель на шаги; парсит ответ в список строк."""
        messages = [
            {"role": "system", "content":
                "Ты планировщик. Разбей задачу на 2-4 коротких шага. "
                "Выведи только список: по одному шагу в строке, без нумерации и пояснений."},
            {"role": "user", "content": objective},
        ]
        answer = self.llm.complete(messages)
        if not answer:
            return ["Выполнить задачу"]
        steps = [line.strip(" -•\t") for line in str(answer).splitlines() if line.strip()]
        return steps or ["Выполнить задачу"]

    def execute(self, step: str):
        """Выполняет один шаг: LLM-запрос с блоком рабочей памяти (этап/шаг/действие)."""
        messages = [
            {"role": "system", "content":
                "Ты исполнитель. Работай строго в рамках текущего шага, не перепрыгивая этапы."},
            {"role": "user", "content": step},
        ]
        # Подмешиваем блок working (этап/шаг/ожидаемое действие), если агент доступен.
        if self.agent is not None and getattr(self.agent, "user_id", None):
            try:
                ctx = MemoryContext(self.agent.user_id, self.agent.task,
                                    self.agent.session_id,
                                    profile_id=self.agent.active_profile or "")
                block = self.agent.memory.layers["working"].as_prompt_block(ctx)
                messages.insert(1, {"role": "system", "content": block})
            except Exception:
                pass
        result = self.llm.complete(messages)
        return result if result is not None else f"Результат шага: {step}"


def default_validator(results: list) -> bool:
    """Заглушка валидатора из `Задание_Д13.txt`: результат непустой → успех."""
    return len(results) > 0


class StubExecutor:
    """Детерминированная заглушка исполнителя (режим --mock, тесты, сценарии).

    Тот же контракт, что у `LLMExecutor` (`.plan`/`.execute`), но без сети: план из
    трёх шагов по цели, результат шага — предсказуемая строка. Позволяет проверять
    жизненный цикл автомата (шаги, пауза, продолжение) независимо от ответов LLM.
    """

    def plan(self, objective: str) -> list:
        goal = (objective or "задача").strip().rstrip(".")
        return [f"Собрать данные: {goal}", "Обработать данные", "Проверить результат"]

    def execute(self, step: str):
        return f"Результат шага: {step}"


class TextActionAnalyzer:
    """Детерминированный анализатор: текст запроса → ProposedAction (без LLM).

    Закрывает проверку инвариантов в детерминированном режиме (--mock, тесты): по
    ключевым словам распознаёт предлагаемый стек/фреймворк и признаки «добавить
    зависимость» / «изменить схему БД». Это позволяет InvariantChecker блокировать
    конфликтующие запросы без живого ключа. В боевом режиме анализатор инжектируем
    (LLM), но проверка остаётся кодом.
    """

    def analyze(self, user_message: str) -> ProposedAction:
        text = (user_message or "").lower()
        action = ProposedAction(description=user_message)

        for fw in KNOWN_FRAMEWORKS:
            if fw in text:
                action.technology = fw
                break
        for lang in KNOWN_LANGUAGES:
            if lang in text:
                action.language = lang
                break

        if any(word in text for word in ("зависимост", "библиотек", "установи",
                                         "пакет", "pip install", "требуется библиотека")):
            action.adds_dependency = True
        if any(word in text for word in ("схем", "таблиц", "миграц", "структуру баз",
                                         "alter table", "измени базу")):
            action.changes_database_schema = True
        return action


def default_action_analyzer() -> TextActionAnalyzer:
    """Анализатор действий по умолчанию (детерминированный)."""
    return TextActionAnalyzer()


class Agent:
    # Роль реплики → source для MemoryItem (единый источник соответствия).
    ROLES = {"user": "user", "assistant": "model"}

    def __init__(self, llm: LLMClient, memory: MemoryManager, prompts: PromptBuilder,
                 store, user_id: str = None, default_task: str = None, log=None,
                 executor=None, validator=None, checker: InvariantChecker = None,
                 action_analyzer=None):
        self.llm = llm
        self.memory = memory
        self.prompts = prompts
        self.store = store
        self.log = log or (lambda line: None)

        # Идентификация: user_id определяется на старте (ввод или --user).
        self.user_id = user_id
        self.default_task = default_task or "Основная_задача"
        self.task = self.default_task
        # Набор включаемых блоков промта; invariants — отдельный блок (День 14),
        # включается наравне со слоями памяти (дозированная доставка сохраняется).
        self.deliver = {"profile", "invariants", "long_term", "working", "short_term"}
        # Бюджет промта (входящие токены, локальная оценка): None — обрезание
        # выключено (поведение дней 11–14 не меняется); число — необязательные
        # блоки опускаются при превышении (роль и текущий запрос — всегда).
        self.prompt_budget = None

        # Персонализация: активный профиль сессии (None → default), авто-роутинг
        # и детерминированный роутер профилей (только если у store есть репозиторий).
        self.active_profile = None
        self.auto_route = False
        self.router = ProfileRouter(store, log=self.log) \
            if getattr(store, "profile_repo", None) is not None else None

        # Состояние задачи (День 13): формализованный автомат. None — задачи ещё нет.
        # executor/validator — инжектируемые зависимости автомата (arch §2.4):
        # по умолчанию LLM составляет план и наполняет шаги, валидатор — заглушка.
        self.task_state = None
        self.executor = executor or LLMExecutor(llm, agent=self, log=self.log)
        self.validator = validator or default_validator

        # Инварианты (День 14): набор правил задачи + проверка кодом + анализатор
        # действий. Всё инжектируемое (полиморфизм, тестируемость без LLM).
        self.constraints = ConstraintSet()
        self.checker = checker or RuleBasedChecker()
        self.action_analyzer = action_analyzer or default_action_analyzer()
        # Счётчик вызовов инструмента — доказательство «запрещённое не исполняется».
        self.tool_calls = 0

        # MCP-слой (День 16): опциональные зависимости, по умолчанию выключены
        # (без --mcp поведение = den_15). Инжектируются DI в Kod.build_agent.
        self.mcp_gateway = None
        self.tool_registry = None
        self.tool_executor = None
        self.tool_policy = None
        # Планировщик фоновых задач (День 18): внешний worker, не LLM. None — фон
        # не поднят (без --scheduler поведение = den_15). Инжектируется в DI.
        self.scheduler = None
        # Лимит итераций агентного tool-use цикла (защита от зацикливания).
        self.max_tool_iterations = 5

        # RAG-слой (Ревизия 6): опциональные зависимости, по умолчанию выключены
        # (без --rag поведение и промпт = прежние). Инжектируются DI в Kod.build_agent.
        # rag_service — фасад rag.RagService; rag_enabled — искать ли источники на
        # каждом запросе; rag_block_enabled — класть ли блок [rag] в промпт
        # (--no-rag-block: ищем и логируем [RAG], но в промпт не подмешиваем).
        self.rag_service = None
        self.rag_enabled = False
        self.rag_block_enabled = True
        self.rag_top_k = None          # None → cfg.retrieval.final_k
        self.rag_mode = None           # None → cfg.retrieval.mode
        # Последние найденные чанки (для /rag check на этапе 9 и объяснимости).
        self.last_rag_hits = []
        # Кэш поиска в пределах ОДНОГО обмена: Kod.py после respond() пересобирает
        # контекст для оценки токенов — повторный поиск по тому же запросу не нужен
        # (каждый dense-поиск = вызов эмбеддера). Инвалидация — по message_counter.
        self._rag_turn = None
        self._rag_turn_hits: list = []
        # Оценка токенов авто-перегенерации grounding (Kod.py прибавляет к сессии).
        self.last_grounding_extra_tokens = 0

        # Текущая сессия (для краткосрочной памяти).
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Счётчик сообщений для source_message_id.
        self.message_counter = 0
        # Пользователь уже инициализирован (профиль создан)?
        self.initialized = False

    # --- Идентификация и интервью-инициализация ----------------------------------
    def interview_questions(self) -> list:
        """Три вопроса персонализации (стиль / констрейнты / контекст)."""
        return [
            ("style", "Какой стиль ответов предпочитаете? (краткий/подробный, формальный/разговорный)"),
            ("constraints", "Какие ограничения учесть? (стек, темы-табу, языки)"),
            ("context", "Какой контекст задачи? (чем занимаетесь, цель)"),
        ]

    def initialize_user(self, user_id: str, name: str, answers: dict) -> None:
        """Создаёт профиль, дерево задач и первую задачу по смыслу сессии."""
        self.user_id = user_id
        self.store.ensure_user(user_id)

        profile = {
            "id": user_id,
            "name": name,
            "style": {"answers": answers.get("style", "")},
            "constraints": {"answers": answers.get("constraints", "")},
            "context": {"answers": answers.get("context", "")},
        }
        # Профиль — через слой profile (явная маршрутизация).
        self.memory.remember(
            "profile", MemoryContext(user_id), content=profile, source="system"
        )

        # Первая задача по смыслу сессии + долговременная память (ссылка на задачи).
        first_task = self.default_task
        self.memory.remember(
            "working",
            MemoryContext(user_id, first_task, self.session_id),
            content={"description": "Первая задача (по смыслу первой сессии)"},
            source="system",
        )
        self.memory.remember(
            "long_term",
            MemoryContext(user_id),
            content={"tasks": {"name": first_task, "ref": f"tasks/{first_task}"}},
            source="system",
        )
        self.task = first_task
        self.initialized = True
        self.log(f"[Агент] Пользователь {user_id} инициализирован (интервью пройдено)")

    def load_state(self, user_id: str) -> None:
        """Загрузка памяти пользователя: профиль + long-term + список задач."""
        self.user_id = user_id
        long_term = self.memory.layers["long_term"].read(MemoryContext(user_id))
        tasks = long_term.get("tasks", [])
        if tasks:
            first = tasks[0]
            self.task = first.get("name", first) if isinstance(first, dict) else first
        self.initialized = True
        # Подтягиваем формализованное состояние активной задачи (если оно есть).
        self.load_task_state()
        # Инварианты активной задачи (отдельно от диалога, День 14).
        self.load_constraints()

    # --- Персонализация: активный профиль ----------------------------------------
    def switch_profile(self, profile_id: str) -> bool:
        """Переключает активный профиль сессии. False — если профиля нет."""
        known = [pid for pid, _ in self.store.list_profiles(self.user_id)]
        if profile_id not in known:
            return False
        self.active_profile = profile_id
        self.log(f"[Агент] активный профиль: {profile_id}")
        return True

    # --- Жизненный цикл задачи (Task State Machine, День 13) ----------------------
    def load_task_state(self) -> None:
        """Загружает TaskState активной задачи из task_state.json (или None).

        Вызывается при load_state(user_id) и switch_task(): переключение задачи
        подтягивает её собственное состояние («продолжение с того же места»).
        """
        if not self.user_id:
            self.task_state = None
            return
        data = self.store.read_task_state(self.user_id, self.task)
        if not data:
            self.task_state = None
            return
        try:
            self.task_state = TaskState.from_dict(data)
            self.log(f"[Автомат] загружено состояние «{self.task}»: {self.task_state.stage.value} "
                     f"(шаг {self.task_state.current_step}/{len(self.task_state.steps)})")
        except (ValueError, KeyError, TypeError):
            self.task_state = None

    def _persist_task_state(self) -> None:
        """Единая точка персистентности: сейв task_state.json + зеркало current_state."""
        if self.task_state is None or not self.user_id:
            return
        data = self.task_state.to_dict()
        self.store.write_task_state(self.user_id, self.task, data)
        # Зеркало стадии в working_memory.json (обратная совместимость с днями 11–12).
        ctx = MemoryContext(self.user_id, self.task, self.session_id)
        self.memory.layers["working"].write(
            ctx, MemoryItem(content={"current_state": self.task_state.stage.value},
                            source="system"))

    def start_task(self, objective: str) -> TaskState:
        """Новая задача: task_id по цели, stage=NEW, отметки в памяти, сейв.

        Поток Дня 15: new → planning (план строится) → остановка на утверждении
        (/approve) — реализация только после явного утверждения человеком.
        """
        task_id = safe_name(objective) or self.default_task
        self.task_state = TaskState(task_id=task_id, objective=objective,
                                    stage=TaskStage.NEW)
        # Отметка в рабочей и долговременной памяти (механика switch_task дня 11).
        self.memory.remember(
            "working", MemoryContext(self.user_id, self.task, self.session_id),
            content={"description": objective}, source="system")
        self.memory.remember(
            "long_term", MemoryContext(self.user_id),
            content={"tasks": {"name": self.task, "ref": f"tasks/{self.task}"}},
            source="system")
        self._persist_task_state()
        self.log(f"[Автомат] новая задача «{objective}» → {self.task_state.stage.value}")
        return self.task_state

    def step_task(self) -> TaskState:
        """Один проход автомата (run_task) + персистентность. None — задачи нет."""
        if self.task_state is None:
            self.log("[Автомат] /step: нет активной задачи (сначала /plan <цель>)")
            return None
        run_task(self.task_state, self.executor, self.validator, log=self.log)
        self._persist_task_state()
        return self.task_state

    def run_to_end(self, max_passes: int = 50) -> TaskState:
        """Крутить автомат до done/failed/paused (с защитой от бесконечного цикла).

        Из planning останавливается: утверждение плана — контрольный пункт,
        который проходит только человек (/approve), /run его не обходит.
        """
        if self.task_state is None:
            self.log("[Автомат] /run: нет активной задачи (сначала /plan <цель>)")
            return None
        passes = 0
        while (self.task_state.stage not in
               (TaskStage.DONE, TaskStage.FAILED, TaskStage.PAUSED,
                TaskStage.PLANNING)
               and passes < max_passes):
            run_task(self.task_state, self.executor, self.validator, log=self.log)
            self._persist_task_state()
            passes += 1
        if self.task_state.stage == TaskStage.PLANNING:
            self.log("[Автомат] /run: план ожидает утверждения (/approve) — "
                     "переход в реализацию без утверждения запрещён")
        return self.task_state

    def pause(self) -> bool:
        """Пауза на любой рабочей стадии. False — если задачи нет / не на рабочей стадии."""
        if self.task_state is None:
            self.log("[Автомат] /pause: нет активной задачи")
            return False
        if self.task_state.stage in (TaskStage.PAUSED, TaskStage.DONE, TaskStage.FAILED):
            self.log(f"[Автомат] /pause: нельзя pause на этапе "
                     f"{self.task_state.stage.value}")
            return False
        pause_task(self.task_state, log=self.log)
        self._persist_task_state()
        self.log(f"[Автомат] пауза (вернуться к: "
                 f"{self.task_state.previous_stage.value})")
        return True

    def resume(self) -> bool:
        """Продолжение с того же этапа и шага, без повторного плана/объяснений."""
        if self.task_state is None:
            self.log("[Автомат] /resume: нет активной задачи")
            return False
        if self.task_state.stage != TaskStage.PAUSED:
            self.log(f"[Автомат] /resume: задача не на паузе "
                     f"(этап {self.task_state.stage.value})")
            return False
        resume_task(self.task_state, log=self.log)
        self._persist_task_state()
        self.log(f"[Автомат] продолжение: этап {self.task_state.stage.value}, "
                 f"шаг {self.task_state.current_step}/{len(self.task_state.steps)}")
        return True

    def retry_task(self) -> bool:
        """Восстановление из failed → planning (единственный выход из FAILED)."""
        if self.task_state is None or self.task_state.stage != TaskStage.FAILED:
            self.log("[Автомат] /task retry: задача не в состоянии failed")
            return False
        transition(self.task_state, TaskStage.PLANNING, log=self.log)
        self.task_state.steps = []
        self.task_state.results = []
        self.task_state.current_step = 0
        self.task_state.error = None
        self.task_state.expected_action = "утвердить план (/approve)"
        self._persist_task_state()
        return True

    # --- Контролируемые переходы (День 15) ---------------------------------------
    def approve_plan(self) -> str:
        """Утверждение плана (/approve): planning → plan_approved.

        Из других стадий — отказ с объяснением (состояние не меняется).
        Возвращает текст результата для CLI.
        """
        if self.task_state is None:
            message = "[Автомат] /approve: нет активной задачи (сначала /plan <цель>)"
            self.log(message)
            return message
        message = approve_plan(self.task_state, log=self.log)
        self._persist_task_state()
        return message

    def attempt_transition(self, target: str) -> str:
        """Попытка явного перехода (/goto <этап>): try_transition + отказ с правилом.

        Допустимый переход — выполняется; недопустимый — InvalidTransitionError:
        состояние НЕ меняется, попытка в transition_log, отказ называет правило
        и корректный следующий шаг. Возвращает текст результата для CLI.
        """
        if self.task_state is None:
            message = "[Автомат] /goto: нет активной задачи (сначала /plan <цель>)"
            self.log(message)
            return message
        try:
            proposed = TaskStage(target.strip().lower())
        except ValueError:
            known = ", ".join(s.value for s in TaskStage)
            message = f"[Автомат] /goto: неизвестная стадия «{target}». Стадии: {known}"
            self.log(message)
            return message
        try:
            try_transition(self.task_state, proposed)
            self._persist_task_state()
            message = (f"[Автомат] переход выполнен: "
                       f"{self.task_state.transition_log[-1]['from']} → {proposed.value}")
            self.log(message)
            return message
        except InvalidTransitionError:
            rule = refusal_text(self.task_state.stage, proposed)
            self._persist_task_state()
            message = (f"[Автомат] Попытка перехода {self.task_state.stage.value} → "
                       f"{proposed.value}: ОТКАЗАНО\n"
                       f"[Автомат] Правило: {rule}\n"
                       f"[Автомат] Состояние не изменено: {self.task_state.stage.value}")
            self.log(f"[Автомат] Попытка {self.task_state.stage.value} → "
                     f"{proposed.value}: ОТКАЗАНО — {rule}")
            return message

    def transitions_report(self) -> str:
        """Карта разрешённых переходов + журнал transition_log (для /transitions)."""
        from core.state_machine import ALLOWED_TRANSITIONS
        lines = ["[Переходы] Карта разрешённых переходов:"]
        for stage in TaskStage:
            targets = ALLOWED_TRANSITIONS.get(stage, set())
            names = ", ".join(t.value for t in sorted(targets, key=lambda s: s.value)) or "—"
            marker = " ← текущая" if (self.task_state is not None
                                      and self.task_state.stage == stage) else ""
            lines.append(f"  {stage.value} → {names}{marker}")
        if self.task_state is None:
            lines.append("[Переходы] Нет активной задачи (журнал пуст)")
            return "\n".join(lines)
        log = self.task_state.transition_log
        refused = sum(1 for entry in log if not entry.get("allowed"))
        lines.append(f"[Переходы] Журнал ({len(log)} записей, отказов: {refused}):")
        for entry in log[-10:]:
            verdict = "OK" if entry.get("allowed") else "ОТКАЗАНО"
            reason = f" — {entry['reason']}" if entry.get("reason") else ""
            lines.append(f"  [{entry['at']}] {entry['from']} → {entry['to']}: "
                         f"{verdict}{reason}")
        return "\n".join(lines)

    # --- Инварианты и ограничения состояния (День 14) ----------------------------
    def load_constraints(self) -> None:
        """Загружает набор инвариантов активной задачи из invariants.json.

        Вызывается при load_state(user_id) и switch_task(): переключение задачи
        подтягивает ЕЁ собственный набор. Отсутствие файла → пустой набор (все
        действия разрешены, поведение дней 11–13).
        """
        if not self.user_id:
            self.constraints = ConstraintSet()
            return
        data = self.store.read_invariants(self.user_id, self.task)
        self.constraints = ConstraintSet.from_dict(data)
        if self.constraints.invariants:
            self.log(f"[Инварианты] загружено {len(self.constraints.invariants)} правил "
                     f"для «{self.task}»")

    def save_constraints(self) -> str:
        """Сохраняет набор инвариантов задачи (сейв при изменении и при exit)."""
        if not self.user_id:
            return ""
        return self.store.write_invariants(self.user_id, self.task,
                                           self.constraints.to_dict())

    def check_invariants(self, action: ProposedAction) -> list:
        """Проверка действия кодом: список блокирующих нарушений ([] = разрешено)."""
        return self.checker.check(action, self.constraints)

    def invariant_warnings(self, action: ProposedAction) -> list:
        """Неблокирующие предупреждения (severity='warning')."""
        return self.checker.warnings(action, self.constraints)

    def propose_action(self, user_message: str) -> ProposedAction:
        """Формирует ProposedAction из сообщения (LLM/детерминированный анализатор)."""
        return self.action_analyzer.analyze(user_message)

    def add_invariant(self, invariant: Invariant) -> None:
        """Добавляет инвариант в набор задачи и сохраняет файл."""
        _add_invariant(self.constraints, invariant)
        self.save_constraints()
        self.log(f"[Инварианты] добавлен {invariant.id} ({invariant.category})")

    def update_invariant(self, invariant_id: str, new_description: str,
                         authorized: bool = False) -> None:
        """Изменяет инвариант — ТОЛЬКО авторизованной операцией (иначе PermissionError)."""
        _update_invariant(self.constraints, invariant_id, new_description,
                          authorized=authorized)
        self.save_constraints()
        self.log(f"[Инварианты] изменён {invariant_id}")

    def toggle_invariant(self, invariant_id: str, active: bool) -> bool:
        """Включает/выключает инвариант и сохраняет файл."""
        ok = _toggle_invariant(self.constraints, invariant_id, active)
        if ok:
            self.save_constraints()
            self.log(f"[Инварианты] {invariant_id} → {'on' if active else 'off'}")
        return ok

    def _refusal_message(self, action: ProposedAction, violations: list) -> str:
        """Отказ с объяснением (канон `arch_den_14.md` §2.9).

        Называет: (1) что хотел пользователь, (2) какой инвариант нарушен,
        (3) почему обязателен, (4) допустимую альтернативу.
        """
        first_id = ""
        if violations:
            # Формат нарушения: «Нарушен инвариант <id>: <описание>».
            tail = violations[0].split("инвариант ", 1)[-1]
            first_id = tail.split(":", 1)[0].strip()
        lines = ["Я не могу выполнить этот запрос в текущей конфигурации.", ""]
        lines.append(f"Действие: {action.description}")
        lines.append("Причина: запрос нарушает инвариант(ы):")
        for violation in violations:
            lines.append(f"  - {violation}")
        lines.append("")
        lines.append("Инварианты обязательны: они фиксируют принятые архитектурные и "
                     "технические решения проекта и не меняются обычным сообщением.")
        lines.append("Могу предложить альтернативу: реализовать нужную функциональность "
                     "в рамках действующих инвариантов.")
        if first_id:
            lines.append(f"Если вы хотите изменить это правило, сначала нужно явно "
                         f"обновить инвариант {first_id} (команда /invariant set).")
        return "\n".join(lines)

    def propose_and_check(self, user_message: str) -> dict:
        """Рабочий цикл: план (ProposedAction) → проверка кодом → выполнить/отказать.

        Проверка выполняется ДО изменения состояния/запуска инструмента. Возвращает
        dict {allowed, action, violations, warnings, message}. При нарушениях
        инструмент НЕ вызывается (self.tool_calls не растёт).
        """
        action = self.propose_action(user_message)
        violations = self.check_invariants(action)
        warnings = self.invariant_warnings(action)

        if violations:
            self.log(f"[Инварианты] действие запрещено: {action.description}")
            for violation in violations:
                self.log(f"[Инварианты] - {violation}")
            return {"allowed": False, "action": action, "violations": violations,
                    "warnings": warnings, "message": self._refusal_message(action, violations)}

        for warning in warnings:
            self.log(f"[Инварианты] warning: {warning}")
        return {"allowed": True, "action": action, "violations": [], "warnings": warnings,
                "message": self._execute(action)}

    def _execute(self, action: ProposedAction) -> str:
        """Единственное место «выполнения» действия — только при отсутствии нарушений."""
        self.tool_calls += 1
        self.log(f"[Инварианты] действие разрешено и выполнено: {action.description}")
        return f"Действие выполнено: {action.description}"

    # --- Цикл: сообщение → память → промт → LLM → ответ --------------------------
    def check_grounding(self, answer: str, mode: str = None):
        """Проверить опору ответа на ПОСЛЕДНИЕ найденные источники (этап 9, R7).

        Возвращает GroundingReport; None — если RAG/фасад выключены или источников
        не было (тогда проверять не на что). Ошибки не роняют ответ.
        """
        if self.rag_service is None or not self.last_rag_hits:
            return None
        if not hasattr(self.rag_service, "ground"):
            return None                         # фасад без grounding (duck-typing)
        try:
            return self.rag_service.ground(answer, hits=self.last_rag_hits, mode=mode)
        except Exception as exc:
            self.log(f"[RAG] grounding не выполнен ({type(exc).__name__}: {exc})")
            return None

    def _grounding_guard(self, messages: list, answer: str) -> str:
        """Strict-режим (решение №4): hallucination → ОДНА авто-перегенерация.

        Порядок: проверка → при verdict=hallucination фидбэк-промпт («оперись на
        N источников, убери неподтверждённое») → повторная проверка → если снова
        провал — явная пометка в ответе. Цикла нет: максимум max_regenerations
        (по умолчанию 1) попыток. warn/off ничего не меняют.
        """
        if self.rag_service is None or not self.last_rag_hits:
            return answer
        if not (self.rag_enabled and self.rag_block_enabled):
            return answer                       # блок не подмешивался — цитировать не из чего
        if not hasattr(self.rag_service, "ground"):
            return answer                       # фасад без grounding (duck-typing)
        gcfg = getattr(self.rag_service.cfg, "grounding", None)
        if gcfg is None or gcfg.mode == "off":
            return answer
        report = self.check_grounding(answer)
        if report is None or report.verdict != "hallucination":
            return answer
        if gcfg.mode != "strict" or gcfg.max_regenerations < 1:
            self.log("[RAG] grounding: verdict=hallucination "
                     f"(режим {gcfg.mode} — авто-перегенерация не выполняется)")
            return answer

        feedback = self.rag_service.grounding_feedback(
            report, answer, len(self.last_rag_hits))
        retry_messages = list(messages) + [
            {"role": "assistant", "content": answer},
            {"role": "user", "content": feedback},
        ]
        try:
            candidate = self.llm.complete(retry_messages)
        except Exception as exc:
            self.log(f"[RAG] авто-перегенерация не удалась ({type(exc).__name__}: {exc})")
            candidate = None
        if not candidate:
            return answer
        # Учёт доп. обмена (оценка): Kod.py прибавит к токенам и стоимости сессии.
        self.last_grounding_extra_tokens += sum(
            max(1, len(m.get("content", "")) // 4) for m in retry_messages)
        report2 = self.check_grounding(candidate)
        if report2 is not None:
            report2 = replace(report2, regenerated=True)
        if report2 is not None and report2.verdict == "hallucination":
            self.log("[RAG] grounding: после авто-перегенерации снова hallucination — "
                     "в ответ добавлена явная пометка")
            return (candidate + "\n\n"
                    "⚠ [RAG] Ответ не полностью подтверждён найденными источниками — "
                    "проверьте утверждения, помеченные ссылками.")
        self.log("[RAG] grounding: авто-перегенерация помогла "
                 f"(verdict={report2.verdict if report2 else 'unchecked'})")
        return candidate

    def _rag_retrieve(self, query: str) -> list:
        """Один поиск по RAG на запрос: сохранить last_rag_hits + строка [RAG] в лог.

        Возвращает список Hit ([] — выключено/пусто/ошибка). Ошибки RAG НЕ роняют
        ответ агента: фасад RagService.search уже деградирует к [], а логирование
        защищено — блок [rag] просто отсутствует, агент отвечает по памяти.
        """
        if not (self.rag_enabled and self.rag_service is not None):
            return []
        # Один поиск на обмен: повторный build_context того же обмена берёт hits
        # из кэша (не платит эмбеддером и не пишет дубль в лог).
        if self._rag_turn == self.message_counter:
            return self._rag_turn_hits
        started = time.time()
        try:
            if getattr(self.rag_service.cfg.retrieval, "multi_query", False):
                # Multi-query (этап 10): переформулировки через LLM + склейка RRF.
                # Токены переформулирования учитываются в оценке сессии.
                variants = self.rag_service.rephrase(query, llm=self.llm.complete)
                self.last_grounding_extra_tokens += sum(
                    max(1, len(v) // 4) for v in variants)
                hits = self.rag_service.search_multi(
                    query, variants=variants, k=self.rag_top_k, mode=self.rag_mode)
            else:
                hits = self.rag_service.search(query, k=self.rag_top_k, mode=self.rag_mode)
        except Exception as exc:                     # страховка: фасад уже глотает
            self.log(f"[RAG] поиск не удался ({type(exc).__name__}: {exc}) — блок опущен")
            self.last_rag_hits = []
            self._rag_turn = self.message_counter
            self._rag_turn_hits = []
            return []
        self._rag_turn = self.message_counter
        self._rag_turn_hits = hits
        self.last_rag_hits = hits
        latency_ms = round((time.time() - started) * 1000, 1)
        mode = self.rag_mode or getattr(self.rag_service.cfg.retrieval, "mode", "?")
        if not hits:
            self.log(f"[RAG] запрос «{query[:60]}» → 0 источников "
                     f"(режим={mode}, {latency_ms} мс)")
            return hits
        self.log(f"[RAG] запрос «{query[:60]}» → {len(hits)} ист. "
                 f"(режим={mode}, {latency_ms} мс):")
        for rank, hit in enumerate(hits, 1):
            scores = hit.scores or {}
            brief = ", ".join(f"{k}={v}" for k, v in scores.items() if v is not None)
            self.log(f"[RAG]   {rank}. {hit.chunk_id}  score={hit.score:.4f}  "
                     f"[{brief}]  {hit.source}")
        return hits

    def build_context(self, query: str) -> PromptContext:
        """Составляет PromptContext: блоки памяти + краткосрочная история."""
        ctx = MemoryContext(self.user_id, self.task, self.session_id,
                            profile_id=self.active_profile or "")

        # Дозированная доставка: блоки только для выбранных слоёв.
        blocks = self.memory.build_blocks(self.deliver, ctx)

        # Краткосрочная память — сообщения как список role/content
        # (окно — у слоя ShortTermMemory, единственный владелец).
        short_messages = self.memory.layers["short_term"].recent(ctx)

        summary = self.store.read_sessions_resume(self.user_id, self.task)
        tools = []
        if self.tool_registry is not None:
            try:
                tools = list(self.tool_registry.snapshot().tools)
            except Exception:
                tools = []

        # RAG (Ревизия 6): один поиск на запрос; hits → last_rag_hits (этап 9),
        # текст блока → PromptContext.rag_block (только если блок включён).
        rag_block = ""
        hits = self._rag_retrieve(query)
        if hits and self.rag_block_enabled:
            try:
                rag_block = self.rag_service.context_block(query, hits=hits)
            except Exception as exc:
                self.log(f"[RAG] блок не собран ({type(exc).__name__}: {exc}) — блок опущен")
                rag_block = ""

        return PromptContext(query, blocks, summary=summary,
                             short_term_messages=short_messages,
                             invariants=self.constraints, tools=tools,
                             rag_block=rag_block)

    def respond(self, user_message: str) -> str:
        """Полный цикл обработки одного сообщения пользователя."""
        self.message_counter += 1
        message_id = f"M{self.message_counter}"
        # Оценка доп. обменов этого хода (multi-query на этапе 10, авто-перегенерация
        # grounding на этапе 9). Сброс ДО build_context: multi-query пишет токены там.
        self.last_grounding_extra_tokens = 0

        # 0. Авто-роутинг: профиль выбирается ДО сборки промта — активный профиль
        #    подключён к каждому запросу (персонализация).
        if self.auto_route and self.router is not None:
            candidate = self.router.route(self.user_id, user_message)
            if candidate and candidate != (self.active_profile or ""):
                self.switch_profile(candidate)

        # 1. Явное сохранение сообщения в краткосрочную память (source=user).
        self.remember_message("user", user_message, message_id)

        # 2. Сборка промта (дозированная доставка: только слои из self.deliver;
        #    бюджет: None — без обрезания, число — необязательные блоки опускаются).
        prompt_ctx = self.build_context(user_message)
        messages = self.prompts.build(prompt_ctx, self.deliver,
                                      budget=self.prompt_budget)

        # 3. Ответ LLM. Если включён MCP-слой с каталогом инструментов — полный
        #    tool-use цикл (LLM запрашивает тул → исполняем → возвращаем результат).
        if self.tool_executor is not None and self.tool_registry is not None \
                and self.tool_registry.snapshot().tools:
            answer = self._respond_with_tools(messages, prompt_ctx)
        else:
            answer = self.llm.complete(messages)
        if answer is None:
            return None

        # 3.5. Grounding (этап 9, решение №4): strict + hallucination → одна
        #      авто-перегенерация с фидбэком; при повторном провале — пометка.
        #      Делается ДО сохранения в память: в память должен лечь финальный ответ.
        answer = self._grounding_guard(messages, answer)

        # 4. Сохранение ответа и обновление рабочей памяти (жизненный цикл).
        self.remember_message("assistant", answer, message_id + "a")
        self.log(f"[Агент] {message_id}: ответ получен (доставка: {sorted(self.deliver)})")
        return answer

    def _tool_specs(self, tools) -> list:
        """ToolDescriptor[] → спецификация OpenAI tools (function-calling)."""
        return [{
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.input_schema or {"type": "object"},
            },
        } for tool in tools]

    def _respond_with_tools(self, messages: list, prompt_ctx) -> str:
        """Агентный tool-use цикл: LLM → tool call → исполнение → LLM → ответ.

        Ограничен `max_tool_iterations`; ошибки исполнителя возвращаются модели как
        результат (не роняют цикл). Сырой ответ инструмента — только текущий контекст,
        в память пишется лишь нормализованная запись (см. ToolExecutor/`external_actions`).
        """
        from core.tools import ToolCallRequest  # локальный импорт: без циклов модулей
        from core.llm_client import render_tool_protocol

        tools = list(prompt_ctx.tools)
        specs = self._tool_specs(tools)
        # Добавляем протокол инструментов в роль-инструкцию (fallback-путь).
        # D2: протокол строится ОТ КАТАЛОГА (имена + обязательные аргументы).
        if not any("[tools]" in m.get("content", "") for m in messages):
            messages = [{"role": "system", "content": render_tool_protocol(tools)}] + messages
        for _ in range(self.max_tool_iterations):
            reply = self.llm.complete_with_tools(messages, tools=specs) \
                if hasattr(self.llm, "complete_with_tools") \
                else None
            if reply is None or not reply.tool_calls:
                return (reply.content if reply else None) or ""
            for call in reply.tool_calls:
                call_id = call.get("id", "") or f"call_{call['name']}"
                request = ToolCallRequest(name=call["name"],
                                          arguments=call.get("arguments", {}),
                                          call_id=call_id)
                result = self.tool_executor.execute(
                    request, user_id=self.user_id, task=self.task,
                    task_stage=(self.task_state.stage.value if self.task_state else ""),
                    constraints=self.constraints)
                self._record_external_action(result)
                # D6: канонический формат assistant-сообщения с валидным tool_calls
                # (OpenAI-совместимо), а не текстовый «tool_call: …».
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": json.dumps(call.get("arguments", {}),
                                                    ensure_ascii=False),
                        },
                    }],
                })
                # D6: в контекст — ПОЛНЫЙ текст результата (не усечённый summary).
                messages.append({"role": "tool", "name": call["name"],
                                 "tool_call_id": call_id,
                                 "content": (getattr(result, "text", "")
                                             or result.summary
                                             or f"status={result.status}")})
        return "Достигнут лимит вызовов инструментов за один запрос."

    def _record_external_action(self, result) -> None:
        """Нормализованная запись о вызове инструмента в рабочую память (без сырого)."""
        if not self.user_id:
            return
        try:
            ctx = MemoryContext(self.user_id, self.task, self.session_id)
            self.memory.remember(
                "working", ctx,
                content={"external_actions": {
                    "execution_id": result.execution_id, "tool": result.tool,
                    "status": result.status, "summary": (result.summary or "")[:200]}},
                source="system")
        except Exception as exc:
            self.log(f"[Агент] external_actions не записаны: {exc}")

    def remember_message(self, role: str, content: str, message_id: str) -> str:
        """Сохраняет реплику в краткосрочную память (append-only)."""
        if role not in self.ROLES:      # защита от опечатки/дрейфа роли
            role = "user"
        source = self.ROLES[role]
        ctx = MemoryContext(self.user_id, self.task, self.session_id)
        item = MemoryItem(
            content=content, source=source, scope="session", owner=self.user_id,
            source_message_id=message_id, role=role,
        )
        return self.memory.layers["short_term"].write(ctx, item)

    def switch_task(self, new_task: str, reason: str = "") -> None:
        """Переход на принципиально другую задачу: отметка в сессии + новая задача.

        Канон куратора: в текущей сессии ставится отметка о переходе, создаётся
        новая задача со ссылкой на сессию-источник.
        """
        old_task = self.task
        old_session = self.session_id

        # Отметка перехода в рабочей памяти текущей задачи.
        ctx_old = MemoryContext(self.user_id, old_task, old_session)
        self.memory.remember(
            "working", ctx_old,
            content={"open_questions": f"Переход на задачу «{new_task}» (сессия {old_session})"},
            source="system",
        )

        # Новая задача со ссылкой на сессию-источник.
        self.memory.remember(
            "working",
            MemoryContext(self.user_id, new_task, self.session_id),
            content={"description": f"Новая задача «{new_task}» (из сессии {old_session})"},
            source="system",
        )
        self.memory.remember(
            "long_term",
            MemoryContext(self.user_id),
            content={"tasks": {"name": new_task, "ref": f"tasks/{new_task}", "source_session": old_session}},
            source="system",
        )

        self.task = new_task
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Переключение задачи подтягивает её собственное состояние (arch §2.8).
        self.load_task_state()
        # ...и её собственный набор инвариантов (arch_den_14 §2.5).
        self.load_constraints()
        self.log(f"[Агент] Переход на задачу «{new_task}» (источник: сессия {old_session})")

    def save_state(self) -> None:
        """Сохранение состояния: рабочая память + resume-заметка."""
        ctx = MemoryContext(self.user_id, self.task, self.session_id)
        self.memory.remember(
            "working", ctx,
            content={"lifecycle_summary": f"Сессия {self.session_id} продолжена "
                     f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"},
            source="system",
        )
        self.store.write_sessions_resume(
            self.user_id, self.task,
            f"# Резюме сессий задачи «{self.task}»\n\nПоследняя сессия: {self.session_id}\n",
        )
        # Персистентность автомата: resume переживает перезапуск процесса (arch §2.5).
        self._persist_task_state()
        # Персистентность инвариантов: набор переживает перезапуск (arch_den_14 §2.5).
        self.save_constraints()