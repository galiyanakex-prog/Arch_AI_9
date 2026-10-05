# -*- coding: utf-8 -*-
"""Профиль пользователя: style + constraints + context (+ domain/triggers/skills).

Три составляющие по лекции (Суть_N3 §3.4): стиль, констрейнты, контекст.
Профиль — отдельная сущность, JSON в SQLite (ProfileRepository); на пользователя
несколько профилей (персонализация, arch_den_12 §2.3): слой читает/пишет
АКТИВНЫЙ профиль (ctx.profile_id; пусто → дефолтный). Профиль = декларативный
пайплайн скиллов: инструкции skills подмешиваются в промт (исполнение —
следующие дни).
"""
from .base import MemoryLayer, MemoryContext, MemoryItem


class Profile(MemoryLayer):
    layer_name = "profile"
    scope = "user"

    def read(self, ctx: MemoryContext) -> dict:
        # Активный профиль из контекста; None/"" → дефолтный (обратная совместимость).
        profile = self.store.load_profile(ctx.user_id, ctx.profile_id or None)
        if profile is None:
            return {}
        return profile

    def write(self, ctx: MemoryContext, item: MemoryItem) -> str:
        # Профиль — merge: обновляем только переданные поля, остальное сохраняем.
        # Инвариант merge действует для АКТИВНОГО профиля (ctx.profile_id).
        profile_id = ctx.profile_id or "default"
        current = self.read(ctx) or {"id": ctx.user_id, "profile_id": profile_id,
                                     "name": "", "style": {},
                                     "constraints": {}, "context": {}}
        updates = item.content if isinstance(item.content, dict) else {}
        for key, value in updates.items():
            if key in ("style", "constraints", "context") and isinstance(value, dict):
                current.setdefault(key, {}).update(value)
            else:
                current[key] = value
        # profile_id фиксируется в самом профиле (зеркало и SQLite согласованы).
        current["profile_id"] = profile_id
        path = self.store.save_profile(ctx.user_id, current, profile_id)
        self.log(f"[Память] profile «{profile_id}» ← {list(updates.keys())} → {path} (JSON в SQLite)")
        return f"profile.json ({list(updates.keys())})"

    def as_prompt_block(self, ctx: MemoryContext) -> str:
        profile = self.read(ctx)
        if not profile:
            return ""
        lines = []
        # Заголовок активного профиля — первой строкой (персонализация).
        name = profile.get("name") or ""
        pid = profile.get("profile_id") or ctx.profile_id or "default"
        lines.append(f"Профиль: {name} ({pid})" if name else f"Профиль: ({pid})")
        if name:
            lines.append(f"Имя: {name}")
        style = profile.get("style", {})
        if style:
            lines.append("Стиль: " + "; ".join(f"{k}: {v}" for k, v in style.items()))
        constraints = profile.get("constraints", {})
        if constraints:
            lines.append("Ограничения: " + "; ".join(f"{k}: {v}" for k, v in constraints.items()))
        context = profile.get("context", {})
        if context:
            lines.append("Контекст: " + "; ".join(f"{k}: {v}" for k, v in context.items()))
        # Пайплайн скиллов: упорядоченные инструкции подмешиваются в промт.
        skills = profile.get("skills") or []
        if skills:
            lines.append("Пайплайн скиллов:")
            for i, skill in enumerate(skills, 1):
                if isinstance(skill, dict):
                    sname = skill.get("name", f"skill{i}")
                    instr = skill.get("instructions", "")
                    lines.append(f"{i}. {sname}: {instr}" if instr else f"{i}. {sname}")
                else:
                    lines.append(f"{i}. {skill}")
        domain = profile.get("domain")
        if domain:
            lines.append(f"Домен: {domain}")
        return "\n".join(lines)