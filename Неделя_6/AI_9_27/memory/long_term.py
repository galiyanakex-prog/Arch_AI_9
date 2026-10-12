# -*- coding: utf-8 -*-
"""Долговременная память: ссылка на профиль, задачи (со ссылками), решения.

Канон куратора (Суть_N3 §4.8 п.6): профиль представлен ССЫЛКОЙ (profile_ref),
а не физическим содержимым; плюс список задач и достигнутые решения
(выполнена / не выполнена) и устойчивые знания.
"""
from .base import MemoryLayer, MemoryContext, MemoryItem


class LongTermMemory(MemoryLayer):
    layer_name = "long_term"
    scope = "user"

    def read(self, ctx: MemoryContext) -> dict:
        return self.store.read_long_term(ctx.user_id)

    def write(self, ctx: MemoryContext, item: MemoryItem) -> str:
        # Контент — словарь с командами вида {поле: значение}; задачи и решения
        # добавляются как элементы списков.
        data = self.read(ctx)
        updates = item.content if isinstance(item.content, dict) else {}
        for key, value in updates.items():
            if key == "tasks":
                data.setdefault("tasks", []).append(value)
            elif key == "decisions":
                data.setdefault("decisions", []).append({
                    "text": value,
                    "status": updates.get("status", "выполнена"),
                    "source_message_id": item.source_message_id,
                })
            elif key == "knowledge":
                data.setdefault("knowledge", []).append(value)
            else:
                data[key] = value
        path = self.store.write_long_term(ctx.user_id, data)
        self.log(f"[Память] long_term ← {list(updates.keys())} → {path}")
        return f"long_term_memory.json {list(updates.keys())}"

    def as_prompt_block(self, ctx: MemoryContext) -> str:
        data = self.read(ctx)
        lines = [f"Профиль: ссылка users/{data.get('profile_ref') or ctx.user_id}/profile.json"]
        for task in data.get("tasks", []):
            name = task.get("name", task) if isinstance(task, dict) else task
            lines.append(f"Задача: {name}")
        for decision in data.get("decisions", []):
            text = decision.get("text", decision) if isinstance(decision, dict) else decision
            status = decision.get("status", "") if isinstance(decision, dict) else ""
            lines.append(f"Решение ({status}): {text}" if status else f"Решение: {text}")
        for knowledge in data.get("knowledge", []):
            lines.append(f"Знание: {knowledge}")
        return "\n".join(lines)