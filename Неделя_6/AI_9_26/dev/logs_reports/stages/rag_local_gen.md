# Этап 5 — полностью локальный RAG (retrieval + генерация)

Дата: 2026-10-11 23:26
Команда: `python Kod.py --rag-ask "<вопрос>" --gen-provider lmstudio`
Генератор: lmstudio (боевая Qwen2.5-Coder-3B-...-Q6_K), эмбеддинги: ollama bge-m3

## Вопрос: как запретить агенту менять технологический стек проекта

```
[RAG] Вопрос: как запретить агенту менять технологический стек проекта
[RAG] Ответ (опора: partial, 146371.8 мс):
## Запрет агенту менять технологический стек проекта

### Поиск в источниках

**Источник 1: `core/invariants.py`**
```python
# -*- coding: utf-8 -*-
"""
Invariant checker for the agent's state. 
Invariants are rules that the agent cannot violate (canonical "Задание_Д14.txt", goal state "arch_den_14.md" §2.2–2.4, §2.10).
* Invariant — one rule (id, description, category, severity, active);
* ConstraintSet — set of rules — separate entity (not memory, not profile, not history); 
  stored in its own file and survives state cleanup and restart;
* ProposedAction — suggested action that is checked by code;
* InvariantChecker — interface (ABC) + RuleBasedChecker: deterministic check before state change/instrument launch.
"""
```
**Источник 2: `core/invariants.py`**
```python
# ... 
def toggle_invariant(constraints: ConstraintSet, invariant_id: str, active: bool) -> bool:
    """Inverts the rule's activation status."""
    inv = constraints.by_id(invariant_id)
    if inv is None:
        return False
    inv.active = bool(active)
    return True
```
**Источник 3: `dev/Проверка.md`**
```markdown
## Сценарий 3 — Изоляция прав, деградация и регрессия

**Цель демонстрации:** показать, что права сервера ограничиваются на уровне **discovery** (`denied_tools`), при сбое MCP агент **деградирует, а не падает**, и что без `--mcp` поведение агента = предыдущий день (MCP-слой не собирается). 
```

### Решение

**Агент не может менять технологический стек проекта по следующим причинам:**

1. **Инварианты и ограничения состояния:** Агент использует инварианты (см. [doc_id#chunk_id] core/invariants.py) для контроля за правильностью использования технических решений. Эти правила не могут быть изменены или отключены вручную.

2. **Деградация при сбое MCP:** В случае сбоя MCP-сервера агент переходит в режим "деградации" (см. [doc_id#chunk_id] dev/Проверка.md), что позволяет ему продолжать работу без полного отказа, не меняя текущий технологический стек.

3. **Без `--mcp` поведение агента = предыдущий день:** Если агент запускается без MCP-сервера (`--mcp` отсутствует), его поведение сохраняет состояние из прошлого дня, не меняя технологический стек.

### Заключение

Агент не может менять технологический стек проекта по следующим причинам:
* Используется система инвариантов для контроля за правиль

[RAG] Источники (5):
  [1] core/invariants.py · -*- coding: utf-8 -*- · 5a49d570c6b338ecba6da557162e1dad2887c499#0 · score=0.0179
  [2] core/invariants.py · Известные технологии/языки — для детерминированной проверки по id-неймспейсу. · 5a49d570c6b338ecba6da557162e1dad2887c499#7 · score=0.0174
  [3] dev/Проверка.md · Проверка_2.md — короткий сценарий ручной проверки (день 20, живой прогон) > Сценарий 3 — Изоляция прав, деградация и регрессия · b6216ef6a3dc333b6a59b9e2d22ee1c9b9434809#25 · score=0.017
  [4] dev/Проверка.md · Проверка_2.md — короткий сценарий ручной проверки (день 20, живой прогон) > Сценарий 3 — Изоляция прав, деградация и регрессия · b6216ef6a3dc333b6a59b9e2d22ee1c9b9434809#29 · score=0.0165
  [5] integrations/mcp/config.py · `degraded` на недоступных по умолчанию адресах, не меняя overall_state(). · 9eb3588a77dd9bfc303a161d7e2bc008e361625b#8 · score=0.0156
[RAG] Цитаты (5):
  [1] core/invariants.py · 5a49d570c6b338ecba6da557162e1dad2887c499#0
      «# -*- coding: utf-8 -*- """Инварианты и ограничения состояния (День 14).»
  [2] core/invariants.py · 5a49d570c6b338ecba6da557162e1dad2887c499#7
      «Обычная фраза в диалоге («а давай теперь на FastAPI») не меняет правило: без authorized=True поднимается PermissionError (канон `Задание_Д14.txt`).»
  [3] core/invariants.py · 5a49d570c6b338ecba6da557162e1dad2887c499#0
      «Неизменяемые правила, которые агент не имеет права нарушать (канон `Задание_Д14.txt`, целевое состояние `arch_den_14.md` §2.2–2.4, §2.10): * Invariant — одно правило (id, description, category, severi»
  [4] core/invariants.py · 5a49d570c6b338ecba6da557162e1dad2887c499#7
      «False — если правила с таким id нет.""" inv = constraints.by_id(invariant_id) if inv is None: return False inv.active = bool(active) return True def example_constraints() -> ConstraintSet: """Каталог-»
  [5] dev/Проверка.md · b6216ef6a3dc333b6a59b9e2d22ee1c9b9434809#25
      «## Сценарий 3 — Изоляция прав, деградация и регрессия **Цель демонстрации:** показать, что права сервера ограничиваются на уровне **discovery** (`denied_tools`), при сбое MCP агент **деградирует, а не»
```

## Вопрос: в каком порядке блоки собираются в промт для модели

```
[RAG] Вопрос: в каком порядке блоки собираются в промт для модели
[RAG] Ответ (опора: hallucination, 252521.4 мс):
## Описание порядка блоков промта

### По источникам:

1. **core/prompt_builder.py** (ссылка: [2180fabb3ba04a0c91cb6d515453f1a0421de70b#2180fabb3ba04a0c91cb6d515453f1a0421de70b#2])
   - **Канонический порядок блоков промта**: `[system: роль] → [system: профиль] → [system: инварианты] → [system: долговременная] → [system: рабочая] → [system: summary общего префикса, опц.] → [messages: краткосрочная] → [user: текущий запрос] → [резерв].**

2. **memory/manager.py** (ссылка: [1382007ab384e3f8eddd5490609e45309d956a13#1382007ab384e3f8eddd5490609e45309d956a13#3])
   - **Канонический порядок слоёв (он же порядок блоков в промте)**: `("profile", "long_term", "working", "short_term")`

3. **memory/base.py** (ссылка: [579ae9ac0dc8d21986355ff085e0b7e67d1c9569#579ae9ac0dc8d21986355ff085e0b7e67d1c9569#3])
   - **Обёртка над одним объектом памяти с метаданными (arch_prim R5)**: `class MemoryItem:`

**Источники не противоречат друг другу.**

[RAG] Источники (5):
  [1] core/prompt_builder.py · Канонический порядок блоков промта (invariants — после profile, до working; · 2180fabb3ba04a0c91cb6d515453f1a0421de70b#2 · score=0.018
  [2] core/prompt_builder.py · -*- coding: utf-8 -*- · 2180fabb3ba04a0c91cb6d515453f1a0421de70b#0 · score=0.0177
  [3] memory/manager.py · Канонический порядок слоёв (он же порядок блоков в промте). · 1382007ab384e3f8eddd5490609e45309d956a13#3 · score=0.0175
  [4] memory/manager.py · Канонический порядок слоёв (он же порядок блоков в промте). · 1382007ab384e3f8eddd5490609e45309d956a13#1 · score=0.0168
  [5] memory/base.py · Обёртка над одним объектом памяти с метаданными (arch_prim R5). · 579ae9ac0dc8d21986355ff085e0b7e67d1c9569#3 · score=0.0157
[RAG] Цитаты (4):
  [1] memory/manager.py · 1382007ab384e3f8eddd5490609e45309d956a13#3
      «""" result = {} for name in layers: if name in self.layers: result[name] = self.layers[name].read(ctx) return result def build_blocks(self, deliver, ctx: MemoryContext) -> dict: """Собирает текстовые »
  [2] core/prompt_builder.py · 2180fabb3ba04a0c91cb6d515453f1a0421de70b#0
      «Порядок блоков (канон): [system: роль] → [system: профиль] → [system: инварианты] → [system: долговременная] → [system: рабочая] → [system: summary общего префикса, опц.] → [messages: краткосрочная] →»
  [3] memory/manager.py · 1382007ab384e3f8eddd5490609e45309d956a13#1
      «LAYER_ORDER = ("profile", "long_term", "working", "short_term") def default_layers(store, log=None): """Стандартный набор из четырёх слоёв памяти.""" return { "short_term": ShortTermMemory(store, log=»
  [4] memory/base.py · 579ae9ac0dc8d21986355ff085e0b7e67d1c9569#3
      «# Обёртка над одним объектом памяти с метаданными (arch_prim R5).»
```

## Вопрос: единый интерфейс для всех видов памяти агента

```
[RAG] Вопрос: единый интерфейс для всех видов памяти агента
[RAG] Ответ (опора: ok, 144588.6 мс):
## Определение единого интерфейса для всех видов памяти агента

### 1. Структура базового контракта модели памяти: `MemoryLayer (ABC) + метаданные + задел PolicyEngine`

**[579ae9ac0dc8d21986355ff085e0b7e67d1c9569#579ae9ac0dc8d21986355ff085e0b7e67d1c9569#0]**

```python
from abc import ABC, abstractmethod

class MemoryLayer(ABC):
    @abstractmethod
    def remember(self, content, **kwargs):
        """Запомнить объект в памяти."""
    
    @abstractmethod
    def recall(self, layers: list, ctx: dict) -> dict:
        """Получить объекты из памяти по слоям и контексту."""
    
    @abstractmethod
    def clear(self, **kwargs):
        """Очистить память."""
```

**[579ae9ac0dc8d21986355ff085e0b7e67d1c9569#579ae9ac0dc8d21986355ff085e0b7e67d1c9569#3]**

```python
class MemoryItem:
    def __init__(self, content, source="unknown", scope="", owner="", visibility="private", 
                 source_message_id="", role=""):
        self.content = content
        self.source = source  # user | model | document | system
        self.scope = scope     # user | task | session
        self.owner = owner
        self.visibility = visibility  # private (заделы под scope/visibility)
        self.source_message_id = source_message_id
        self.role = role  # user | assistant (для краткосрочной памяти)
    
    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "source": self.source,
            "scope": self.scope,
            "owner": self.owner,
            "visibility": self.visibility,
            "source_message_id": self.source_message_id,
            "role": self.role
        }
```

### 2. Определение интерфейса для MemoryManager

**[1382007ab384e3f8eddd5490609e45309d956a13#1382007ab384e3f8eddd5490609e45309d956a13#0]**

```python
from .base import MemoryLayer, MemoryContext, MemoryItem

class MemoryManager:
    def __init__(self):
        self.layers = {
            "short_term": ShortTermMemory(),
            "working": WorkingMemory(),
            "long_term": LongTermMemory(),
            "profile": Profile()
        }
    
    def remember(self, layer: str, content, **kwargs):
        """Зап

[RAG] Источники (5):
  [1] memory/base.py · -*- coding: utf-8 -*- · 579ae9ac0dc8d21986355ff085e0b7e67d1c9569#0 · score=0.018
  [2] memory/base.py · Обёртка над одним объектом памяти с метаданными (arch_prim R5). · 579ae9ac0dc8d21986355ff085e0b7e67d1c9569#3 · score=0.0176
  [3] memory/manager.py · -*- coding: utf-8 -*- · 1382007ab384e3f8eddd5490609e45309d956a13#0 · score=0.0173
  [4] ND/models/Llama-3-8B-Lunaris.md · 14fd9360480aeb5b959349e5f16fa49899b978f4#1 · score=0.0166
  [5] core/invariants.py · -*- coding: utf-8 -*- · 5a49d570c6b338ecba6da557162e1dad2887c499#0 · score=0.0165
[RAG] Цитаты (3):
  [1] memory/base.py · 579ae9ac0dc8d21986355ff085e0b7e67d1c9569#0
      «Единый интерфейс для всех типов памяти (краткосрочная / рабочая / долговременная / профиль).»
  [2] memory/base.py · 579ae9ac0dc8d21986355ff085e0b7e67d1c9569#3
      «class MemoryItem: """Элемент памяти: content + метаданные (scope/owner/visibility/source/...).""" def __init__(self, content, source: str = "unknown", scope: str = "", owner: str = "", visibility: str»
  [3] memory/manager.py · 1382007ab384e3f8eddd5490609e45309d956a13#0
      «""" from .base import MemoryLayer, MemoryContext, MemoryItem from .short_term import ShortTermMemory from .working import WorkingMemory from .long_term import LongTermMemory from .profile import Profi»
```

