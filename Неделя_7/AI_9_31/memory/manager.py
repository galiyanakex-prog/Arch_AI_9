# -*- coding: utf-8 -*-
"""MemoryManager: явная маршрутизация «что куда» + дозированная доставка.

Единственная точка записи в память — remember(layer, ...). Никакого
«автосохранения всего подряд»: каждый вызов явно называет слой и логирует,
что куда легло. recall(layers, ctx) возвращает только запрошенные слои —
набор включаемых типов памяти задаётся параметром (дозированная доставка).
"""
from .base import MemoryLayer, MemoryContext, MemoryItem
from .short_term import ShortTermMemory
from .working import WorkingMemory
from .long_term import LongTermMemory
from .profile import Profile

# Канонический порядок слоёв (он же порядок блоков в промте).
LAYER_ORDER = ("profile", "long_term", "working", "short_term")


def default_layers(store, log=None):
    """Стандартный набор из четырёх слоёв памяти."""
    return {
        "short_term": ShortTermMemory(store, log=log),
        "working": WorkingMemory(store, log=log),
        "long_term": LongTermMemory(store, log=log),
        "profile": Profile(store, log=log),
    }


class MemoryManager:
    def __init__(self, layers: dict, log=None):
        self.layers = layers
        self.log = log or (lambda line: None)

    def remember(self, layer: str, ctx: MemoryContext = None, content=None,
                 source: str = "unknown", source_message_id: str = "", **item) -> str:
        """Явное сохранение в слой. Возвращает строку «что куда легло».

        content — значение, кладущееся в слой (dict — структурное обновление,
        иначе скаляр). source/source_message_id — метаданные объекта памяти.
        """
        if layer not in self.layers:
            raise KeyError(f"Неизвестный слой памяти: {layer}")

        if content is None:
            # Позволяет передавать значения прямо через **item (например, name=...).
            content = item

        memory_item = MemoryItem(
            content=content,
            source=source,
            scope=self.layers[layer].scope,
            owner=ctx.user_id if ctx else "",
            source_message_id=source_message_id,
        )
        where = self.layers[layer].write(ctx, memory_item)
        self.log(f"[Память] remember({layer}) → {where}")
        return where

    def recall(self, layers, ctx: MemoryContext) -> dict:
        """Дозированная доставка: читает только слои из набора layers.

        Возвращает dict {имя_слоя: содержимое}. Набор — параметр, поэтому
        часть типов памяти можно осознанно опустить.
        """
        result = {}
        for name in layers:
            if name in self.layers:
                result[name] = self.layers[name].read(ctx)
        return result

    def build_blocks(self, deliver, ctx: MemoryContext) -> dict:
        """Собирает текстовые блоки промта по выбранным слоям (в каноническом порядке)."""
        blocks = {}
        for name in LAYER_ORDER:
            if name in deliver and name in self.layers:
                text = self.layers[name].as_prompt_block(ctx)
                if text:
                    blocks[name] = text
        return blocks

    def report(self, ctx: MemoryContext) -> str:
        """Снимок «какие данные в каком типе памяти» для /memory."""
        lines = []
        for name in LAYER_ORDER:
            if name not in self.layers:
                continue
            content = self.layers[name].read(ctx)
            lines.append(f"[{name}] {content}")
        return "\n".join(lines)
