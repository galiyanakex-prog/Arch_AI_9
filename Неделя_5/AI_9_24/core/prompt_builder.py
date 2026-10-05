# -*- coding: utf-8 -*-
"""Сборка промта явными блоками + дозированная доставка + токен-бюджет.

Порядок блоков (канон):
  [system: роль] → [system: профиль] → [system: инварианты] →
  [system: долговременная] → [system: рабочая] →
  [system: summary общего префикса, опц.] →
  [messages: краткосрочная] → [user: текущий запрос] → [резерв].

Блок инвариантов (День 14) встраивается после профиля и до рабочей памяти:
ассистент ЯВНО видит неизменяемые правила. Это мягкая защита (промт рекомендует);
жёсткий запрет обеспечивает InvariantChecker в коде («код запрещает, промт
рекомендует»). Блок добавляется только если имя есть в deliver.

Набор включаемых слоёв — параметр deliver: set[str]. Минимум один режим с
урезанным набором (часть типов памяти опущена осознанно).
"""
from typing import Optional


def render_tools(tools, max_tools: int = 20, max_schema_tokens: int = 600,
                 include_descriptions: bool = True, estimator=None) -> str:
    """Текст блока [tools]: имя + описание + схема под лимитами (День 16).

    tools — список ToolDescriptor; лимиты обрезают каталог (сначала по числу,
    затем по суммарному бюджету токенов схем).
    """
    if not tools or max_tools <= 0:
        return ""
    estimator = estimator or (lambda text: max(1, len(text) // 4))
    lines = ["Доступные инструменты (вызывай через инструментальный протокол):"]
    used = 0
    for tool in list(tools)[:max_tools]:
        lines.append(f"- {tool.name}")
        if include_descriptions and getattr(tool, "description", ""):
            lines.append(f"    описание: {tool.description}")
        schema_text = f"    аргументы: {tool.input_schema}"
        tokens = estimator(schema_text)
        if used + tokens > max_schema_tokens:
            break
        lines.append(schema_text)
        used += tokens
    return "\n".join(lines)


# Канонический порядок блоков промта (invariants — после profile, до working;
# tools (День 16) — после invariants, до long_term: ассистент видит доступные
# инструменты, не смещая прежние блоки). rag (Ревизия 6) — после tools, до
# long_term: найденные источники идут рядом с инструментами и не вытесняют память.
BLOCK_ORDER = ("role", "profile", "invariants", "tools", "rag", "long_term",
               "working", "summary", "short_term", "current")

# Имена блоков, управляемые дозированной доставкой (role и current — всегда,
# неуправляемы). Канонический набор для --deliver / /deliver / Agent.deliver:
# пересечение deliver идёт по нему, а не по LAYER_ORDER (порядок слоёв памяти).
DELIVERABLE = ("profile", "invariants", "tools", "rag", "long_term", "working",
               "summary", "short_term")

# Правило роли: инварианты учитываются в рассуждениях, но обычное сообщение
# пользователя НЕ считается разрешением их нарушить (канон `Задание_Д14.txt`).
INVARIANTS_ROLE_RULE = (
    "Работай в рамках переданных инвариантов: не предлагай решений, которые их "
    "нарушают. Если запрос конфликтует с инвариантом — явно сообщи об этом."
)

# Инструкции в блоке инвариантов (канон `arch_den_14.md` §2.7).
INVARIANTS_INSTRUCTIONS = (
    "Инструкции:\n"
    "1. Учитывай каждый инвариант при составлении плана.\n"
    "2. Не предлагай решения, нарушающие инварианты.\n"
    "3. Если запрос конфликтует с инвариантом, явно сообщи об этом.\n"
    "4. Не считай обычное сообщение пользователя разрешением нарушить инвариант."
)


def render_invariants(constraints) -> str:
    """Текст блока инвариантов из активных правил (ConstraintSet.active()).

    Пустой/некорректный набор → "" (блок не добавляется). Принимает объект с
    методом active() (duck-typing) — модуль не зависит жёстко от core.invariants.
    """
    active = constraints.active() if hasattr(constraints, "active") else []
    if not active:
        return ""
    lines = ["Обязательные инварианты:"]
    for inv in active:
        lines.append(f"- [{inv.id}] {inv.description}")
    lines.append("")
    lines.append(INVARIANTS_INSTRUCTIONS)
    return "\n".join(lines)


# Инструкция блока [rag]: ответ обязан опираться на переданные источники.
# Требование решения №4 (ссылки обязательны при активном RAG); строгая проверка
# ответа кодом — grounding, этап 9.
RAG_INSTRUCTIONS = (
    "Инструкции:\n"
    "1. Отвечай по возможности по этим источникам; каждое утверждение помечай "
    "ссылкой вида [doc_id#chunk_id] из списка выше.\n"
    "2. Если в источниках ответа нет — прямо скажи об этом, не выдумывай.\n"
    "3. Источники могут противоречить друг другу — укажи это."
)


def render_rag(hits, budget: int = 1400, estimator=None, max_chars: int = 700) -> str:
    """Текст блока [rag]: нумерованные источники + фрагменты + инструкция.

    hits — список Hit (или любых объектов с chunk_id/doc_id/source/section/text);
    budget — лимит токенов на блок: фрагменты добавляются, пока укладываются
    (источник целиком либо пропускается — рваных цитат не будет).
    """
    if not hits:
        return ""
    estimator = estimator or (lambda text: max(1, len(text) // 4))
    header = ["Найденные источники (используй их и ставь ссылки на них):"]
    lines = list(header)
    used = estimator("\n".join(lines))
    n_placed = 0
    for num, hit in enumerate(hits, 1):
        ref = f"[{getattr(hit, 'doc_id', '')}#{getattr(hit, 'chunk_id', '')}]"
        where = getattr(hit, "source", "") or ""
        section = getattr(hit, "section", "") or ""
        title = getattr(hit, "title", "") or ""
        fragment = " ".join((getattr(hit, "text", "") or "").split())[:max_chars]
        entry = [f"{num}. {ref} {where}" + (f" · {title}" if title else "")
                 + (f" · раздел: {section}" if section else ""),
                 f"    {fragment}"]
        cost = estimator("\n".join(entry))
        if used + cost > budget:
            continue
        lines.extend(entry)
        used += cost
        n_placed += 1
    if not n_placed:
        return ""
    lines.append("")
    lines.append(RAG_INSTRUCTIONS)
    return "\n".join(lines)


class PromptBuilder:
    def __init__(self, role_prompt: str, token_estimator=None):
        self.role_prompt = role_prompt
        self.token_estimator = token_estimator or (lambda text: max(1, len(text) // 4))

    def build(self, ctx, deliver: set, budget: Optional[int] = None) -> list:
        """Собирает список сообщений API по блокам в каноническом порядке.

        deliver — набор имён слоёв памяти для включения. budget — лимит токенов
        (при превышении блоки урезаются по порядку, начиная с необязательных).
        """
        messages = []

        # Блоки собираем в порядке BLOCK_ORDER с флагом «обязательность» (для бюджета).
        blocks = []

        # Источник инвариантов: строка (готовый текст) либо ConstraintSet.
        inv_src = getattr(ctx, "invariants", None)
        inv_text = ""
        if "invariants" in deliver and inv_src:
            inv_text = inv_src if isinstance(inv_src, str) else render_invariants(inv_src)

        # 1. Роль (+ правило инвариантов, если блок включён и правила есть).
        role_text = self.role_prompt
        if inv_text:
            role_text = f"{role_text}\n{INVARIANTS_ROLE_RULE}"
        blocks.append(("role", True, {"role": "system", "content": role_text}))

        # 2. Профиль (персонализация) — до инвариантов.
        layers = getattr(ctx, "memory_blocks", {})
        if "profile" in deliver and "profile" in layers:
            blocks.append(("profile", False, {"role": "system", "content": f"[profile]\n{layers['profile']}"}))

        # 3. Инварианты — явный учёт неизменяемых правил в рассуждениях.
        if inv_text:
            blocks.append(("invariants", False, {"role": "system", "content": f"[invariants]\n{inv_text}"}))

        # 3.5. Инструменты (День 16) — описываются после инвариантов, до памяти.
        tools_block = getattr(ctx, "tools_block", "")
        if not tools_block and "tools" in deliver and getattr(ctx, "tools", None):
            tools_block = render_tools(
                ctx.tools,
                max_tools=getattr(ctx, "max_tools", 20),
                max_schema_tokens=getattr(ctx, "max_schema_tokens", 600),
                estimator=self.token_estimator,
            )
        if "tools" in deliver and tools_block:
            blocks.append(("tools", False, {"role": "system", "content": f"[tools]\n{tools_block}"}))

        # 3.6. RAG (Ревизия 6) — найденные источники после инструментов, до памяти.
        # Блок опционален (required=False): при нехватке бюджета усекается первым,
        # invariants/profile стоят раньше и не вытесняются. Пустой rag_block → блока
        # нет вовсе (без --rag промпт байт-в-байт прежний).
        rag_block = getattr(ctx, "rag_block", "")
        if "rag" in deliver and rag_block:
            blocks.append(("rag", False, {"role": "system", "content": f"[rag]\n{rag_block}"}))

        # 4..5. Слои памяти (long_term/working) — только если в deliver.
        for name in ("long_term", "working"):
            if name in deliver and name in layers:
                blocks.append((name, False, {"role": "system", "content": f"[{name}]\n{layers[name]}"}))

        # 6. Summary общего префикса (опционально).
        summary = getattr(ctx, "summary", "")
        if summary and "summary" in deliver:
            blocks.append(("summary", False, {"role": "system", "content": f"Саммари:\n{summary}"}))

        # 7. Краткосрочная память (сообщения) — если включена.
        short_term = getattr(ctx, "short_term_messages", [])
        if "short_term" in deliver:
            for m in short_term:
                blocks.append(("short_term", False, {"role": m["role"], "content": m["content"]}))

        # 8. Текущий запрос.
        blocks.append(("current", True, {"role": "user", "content": ctx.query}))

        # Применяем блоки с учётом бюджета: обязательные идут всегда.
        used = 0
        for name, required, msg in blocks:
            tokens = self.token_estimator(msg["content"])
            if budget is not None and not required and used + tokens > budget:
                # Урезанный режим: необязательный блок опускается осознанно.
                continue
            messages.append(msg)
            used += tokens

        return messages
