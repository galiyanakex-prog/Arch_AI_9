# Этап 5 — проверка истинного офлайна (ШАГ 5.5)

Дата: 2026-10-11 23:49
Внешний доступ заблокирован (HTTP(S)_PROXY → 127.0.0.1:1); loopback разрешён.
Команда: `python Kod.py --rag-ask "<вопрос>" --gen-provider lmstudio`

```
[RAG] Вопрос: единый интерфейс для всех видов памяти агента
[RAG] Ответ (опора: ok, 130773.5 мс):
## Один интерфейс для всех видов памяти агента

### Структура и основные принципы

1. **Базовый контракт модели памяти: MemoryLayer (ABC) + метаданные + задел PolicyEngine**

   [579ae9ac0dc8d21986355ff085e0b7e67d1c9569#579ae9ac0dc8d21986355ff085e0b7e67d1c9569#0]
   ```python
   from abc import ABC, abstractmethod

   class MemoryLayer(ABC):
       @abstractmethod
       def remember(self, content, **kwargs):
           """Запомнить объект в памяти."""
       
       @abstractmethod
       def recall(self, layers, ctx):
           """Получить объекты из памяти по слоям и контексту."""
   ```

2. **Обёртка над одним объектом памяти с метаданными (arch_prim R5)**

   [579ae9ac0dc8d21986355ff085e0b7e67d1c9569#579ae9ac0dc8d21986355ff085e0b7e67d1c9569#3]
   ```python
   class MemoryItem:
       def __init__(self, content, source="unknown", scope="", owner="", visibility="private", source_message_id="", role=""):
           self.content = content
           self.source = source  # user | model | document | system
           self.scope = scope    # user | task | session
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

3. **Единый интерфейс для всех типов памяти (краткосрочная / рабочая / долговременная / профиль)**

   [1382007ab384e3f8eddd5490609e45309d956a13#1382007ab384e3f8eddd5490609e45309d956a13#0]
   ```python
   from .base import MemoryLayer, MemoryContext, MemoryItem

   class ShortTermMemory(MemoryLayer):
       def remember(self, content, **kwargs):
           # Реализация для краткосрочной памяти
           pass

       def recall(self

[RAG] Источники (5):
  [1] memory/base.py · -*- coding: utf-8 -*- · 579ae9ac0dc8d21986355ff085e0b7e67d1c9569#0 · score=0.018
  [2] memory/base.py · Обёртка над одним объектом памяти с метаданными (arch_prim R5). · 579ae9ac0dc8d21986355ff085e0b7e67d1c9569#3 · score=0.0176
  [3] memory/manager.py · -*- coding: utf-8 -*- · 1382007ab384e3f8eddd5490609e45309d956a13#0 · score=0.0173
  [4] ND/models/Llama-3-8B-Lunaris.md · 14fd9360480aeb5b959349e5f16fa49899b978f4#1 · score=0.0166
  [5] core/invariants.py · -*- coding: utf-8 -*- · 5a49d570c6b338ecba6da557162e1dad2887c499#0 · score=0.0165
[RAG] Цитаты (4):
  [1] core/invariants.py · 5a49d570c6b338ecba6da557162e1dad2887c499#0
      «Неизменяемые правила, которые агент не имеет права нарушать (канон `Задание_Д14.txt`, целевое состояние `arch_den_14.md` §2.2–2.4, §2.10): * Invariant — одно правило (id, description, category, severi»
  [2] memory/base.py · 579ae9ac0dc8d21986355ff085e0b7e67d1c9569#0
      «# -*- coding: utf-8 -*- """Базовый контракт модели памяти: MemoryLayer (ABC) + метаданные + задел PolicyEngine.»
  [3] memory/base.py · 579ae9ac0dc8d21986355ff085e0b7e67d1c9569#3
      «class MemoryItem: """Элемент памяти: content + метаданные (scope/owner/visibility/source/...).""" def __init__(self, content, source: str = "unknown", scope: str = "", owner: str = "", visibility: str»
  [4] memory/base.py · 579ae9ac0dc8d21986355ff085e0b7e67d1c9569#0
      «Единый интерфейс для всех типов памяти (краткосрочная / рабочая / долговременная / профиль).»
exit=0
```

Проверка: внешний доступ к routerai.ru заблокирован, ответ получен локально.
