# -*- coding: utf-8 -*-
"""Краткосрочная память: неизменяемые сообщения текущей сессии (parent_id).

Сообщения append-only, каждое имеет parent_id — задел ветвления из den_10:
контекст ветки восстанавливается обходом leaf → parent → … → root.
"""
from .base import MemoryLayer, MemoryContext, MemoryItem
from datetime import datetime


class ShortTermMemory(MemoryLayer):
    layer_name = "short_term"
    scope = "session"

    # ЕДИНСТВЕННЫЙ источник истины о размере окна краткосрочной памяти
    # (дозированная доставка: последние N сообщений в промт).
    window = 10

    def read(self, ctx: MemoryContext) -> dict:
        return self.store.read_session(ctx.user_id, ctx.task, ctx.session_id)

    def write(self, ctx: MemoryContext, item: MemoryItem) -> str:
        # Сообщения неизменяемы: append-only, дописываем в конец истории сессии.
        session = self.store.read_session(ctx.user_id, ctx.task, ctx.session_id)
        messages = session.get("messages", [])
        msg = dict(item.to_dict())
        role = msg.pop("role", "") or "user"
        # id — порядковый номер «M<N>»; при восстановлении по счётчику parent_id
        # хранит ссылку на предыдущее сообщение (корень — None).
        message_id = f"M{len(messages) + 1}"
        parent_id = messages[-1].get("id") if messages else None
        msg.update({
            "id": message_id,
            "parent_id": parent_id,
            "role": role,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        messages.append(msg)
        session["messages"] = messages
        path = self.store.write_session(ctx.user_id, ctx.task, ctx.session_id, session)
        self.log(f"[Память] short_term ← {message_id} (parent={parent_id}) → {path}")
        return f"session.json +{message_id}"

    def recent(self, ctx: MemoryContext, limit: int = None) -> list:
        """Последние N сообщений как role/content (N = window, если limit=None)."""
        messages = self.read(ctx).get("messages", [])
        n = self.window if limit is None else limit
        return [{"role": m.get("role", "user"), "content": m.get("content", "")}
                for m in messages[-n:]]

    def as_prompt_block(self, ctx: MemoryContext) -> str:
        # Окно краткосрочной памяти: последние N сообщений (история ≠ состояние).
        return "\n".join(f"{m['role']}: {m['content']}" for m in self.recent(ctx))
