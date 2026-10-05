# -*- coding: utf-8 -*-
"""Рабочая память: пересчитываемое состояние задачи, НЕ лог сообщений.

Содержит (канон куратора): описание задачи, ссылки на сессии+таймкоды,
резюме жизненного цикла, структурированные блоки decisions/constraints/facts/
open_questions, плюс текущую стадию task state machine.
"""
from .base import MemoryLayer, MemoryContext, MemoryItem


class WorkingMemory(MemoryLayer):
    layer_name = "working"
    scope = "task"

    def read(self, ctx: MemoryContext) -> dict:
        return self.store.read_working(ctx.user_id, ctx.task)

    def write(self, ctx: MemoryContext, item: MemoryItem) -> str:
        # Рабочая память — состояние: пересчитываем/обновляем, а не дописываем.
        data = self.read(ctx)
        # item.content — словарь {поле: значение}, которым обновляем рабочую память.
        updates = item.content if isinstance(item.content, dict) else {}
        for key, value in updates.items():
            if key == "current_state":
                data[key] = value
            elif key in ("refs", "decisions", "constraints", "facts", "open_questions"):
                # Списки: refs дополняются, остальные — append нового элемента.
                if key == "refs":
                    data.setdefault(key, []).append(value)
                else:
                    data.setdefault(key, []).append({"text": value, "source_message_id": item.source_message_id})
            else:
                # description / lifecycle_summary и прочие скалярные поля.
                data[key] = value
        path = self.store.write_working(ctx.user_id, ctx.task, data)
        self.log(f"[Память] working ← {list(updates.keys())} → {path}")
        return f"working_memory.json {list(updates.keys())}"

    def as_prompt_block(self, ctx: MemoryContext) -> str:
        data = self.read(ctx)
        lines = [f"Задача: {data.get('description') or (ctx.task or '(без названия)')}"]
        if data.get("lifecycle_summary"):
            lines.append(f"Резюме жизненного цикла: {data['lifecycle_summary']}")
        for field, label in (
            ("decisions", "Решения"),
            ("constraints", "Ограничения"),
            ("facts", "Факты"),
            ("open_questions", "Открытые вопросы"),
        ):
            items = data.get(field, [])
            if items:
                joined = "; ".join(item.get("text", item) for item in items)
                lines.append(f"{label}: {joined}")
        # Инжект формализованного состояния задачи (День 13, arch_den_13 §2.7):
        # этап / шаг N/M / ожидаемое действие — из авторитетного task_state.json.
        # LLM видит стадию и «отождествляет себя с ней», а код не даёт выйти за
        # рамки разрешённых переходов (двойная защита: промт + запрет в коде).
        lines.extend(self._task_state_lines(ctx))
        if data.get("current_state"):
            lines.append(f"Стадия задачи: {data['current_state']}")
        return "\n".join(lines)

    def _task_state_lines(self, ctx: MemoryContext) -> list:
        """Строки состояния задачи из task_state.json (нет снимка → пусто).

        Миграция Дня 15: стадия implementation (бывший execution — снимки
        Дней 13/14 мигрируются при загрузке в TaskState.from_dict).
        """
        state = self.store.read_task_state(ctx.user_id, ctx.task)
        if not state:
            return []
        lines = []
        stage = state.get("stage", "")
        steps = state.get("steps", []) or []
        current = state.get("current_step", 0)
        # Этап + позиция шага (шаг N/M) + текст текущего шага.
        if stage == "implementation" and steps:
            idx = min(current, len(steps) - 1)
            lines.append(f"Этап: {stage} (шаг {current}/{len(steps)}): {steps[idx]}")
        elif stage == "plan_approved":
            lines.append(f"Этап: {stage} (план утверждён, шаг {current}/{len(steps)})")
        else:
            lines.append(f"Этап: {stage}")
        if stage == "paused":
            previous = state.get("previous_stage") or "—"
            lines.append(f"Пауза (вернуться к: {previous})")
        action = state.get("expected_action")
        if action:
            lines.append(f"Ожидаемое действие: {action}")
        if state.get("error"):
            lines.append(f"Ошибка: {state['error']}")
        return lines
