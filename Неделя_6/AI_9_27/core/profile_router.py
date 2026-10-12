# -*- coding: utf-8 -*-
"""Профиль-роутер: детерминированный выбор профиля по тексту запроса.

«Общий профиль-роутер» из канона куратора (arch_den_12 §2.6): выбирает конкретный
профиль-«призму» по доменной области запроса. Оценка: +2 за вхождение каждого
триггера профиля (регистронезависимо), +1 за вхождение domain; победитель —
профиль с максимумом (>0); ничья или ноль → None (остаёмся на текущем/дефолтном).

Роутер БЕЗ LLM — детерминированный, тестируется без живого ключа.
"""


class ProfileRouter:
    """Выбор активного профиля по запросу пользователя (триггеры + домен)."""

    def __init__(self, store, log=None):
        self.store = store
        self.log = log or (lambda line: None)

    def _score(self, profile: dict, text_lower: str) -> int:
        """Счёт профиля: +2 за каждый триггер, +1 за домен (регистронезависимо)."""
        score = 0
        for trigger in profile.get("triggers") or []:
            if trigger and str(trigger).lower() in text_lower:
                score += 2
        domain = profile.get("domain") or ""
        if domain and domain.lower() in text_lower:
            score += 1
        return score

    def _candidates(self, user_id: str, text: str) -> list:
        """[(profile_id, score, profile)] по всем профилям пользователя."""
        result = []
        text_lower = (text or "").lower()
        for profile_id, _is_default in self.store.list_profiles(user_id):
            profile = self.store.load_profile(user_id, profile_id) or {}
            result.append((profile_id, self._score(profile, text_lower), profile))
        return result

    def route(self, user_id: str, text: str):
        """Возвращает profile_id победителя или None (ничья/ноль → остаёмся на текущем)."""
        candidates = self._candidates(user_id, text)
        scored = [(pid, score) for pid, score, _ in candidates if score > 0]
        if not scored:
            self.log("[Роутер] без совпадений → default")
            return None
        best = max(score for _, score in scored)
        winners = [pid for pid, score in scored if score == best]
        if len(winners) > 1:
            # Ничья: однозначного победителя нет — не переключаем.
            self.log(f"[Роутер] ничья {winners} (счёт {best}) → остаёмся на текущем")
            return None
        winner = winners[0]
        self.log(f"[Роутер] запрос → профиль {winner} (счёт {best})")
        return winner

    def explain(self, user_id: str, text: str) -> str:
        """Человекочитаемый разбор решения (для /profile route <текст>)."""
        candidates = self._candidates(user_id, text)
        lines = [f"[Роутер] разбор запроса: «{text}»"]
        for profile_id, score, profile in candidates:
            triggers = ", ".join(profile.get("triggers") or []) or "—"
            domain = profile.get("domain") or "—"
            lines.append(f"  {profile_id}: счёт {score} (триггеры: {triggers}; домен: {domain})")
        decision = self.route(user_id, text)
        if decision:
            lines.append(f"  решение → профиль «{decision}»")
        else:
            lines.append("  решение → без переключения (ничья или ноль; остаёмся на текущем/дефолтном)")
        return "\n".join(lines)
