# -*- coding: utf-8 -*-
"""Проверка опоры ответа на источники (этап 9, R7) — решение пользователя №4.

При активном RAG ответ обязан опираться на найденные чанки, и это проверяется
КОДОМ, а не только промптом. Ответ раскладывается на предложения; для каждого
ищется лучший чанк и вычисляется:

  (а) покрытие стем-токенов     — доля значимых слов предложения, встречающихся
                                  в чанке (после normalize + stem, стоп-слова
                                  исключены: регистр/падеж/опечатки-в-регистрах
                                  не ломают оценку);
  (б) пересечение сущностей     — заглавные словосочетания, латинские
                                  идентификаторы, snake_case;
  (в) строгое совпадение чисел  — числа и даты проверяются ТОЧНО (числа — самый
                                  частый тип галлюцинаций): число из ответа,
                                  отсутствующее в чанке (и вообще ни в одном
                                  найденном источнике), помечает предложение как
                                  unsupported.

Вердикт (GroundingReport.verdict):
  ok            — ссылки есть, предложения подтверждены;
  partial       — ссылок нет вовсе, либо ссылки битые / заметная доля неподтверждённых;
  hallucination — провалены числа либо больше половины предложений unsupported.

Границы модуля (§5): только stdlib; rag/ НЕ импортирует core/.
"""
from __future__ import annotations

import re

from rag.text import normalize, split_sentences, stem, tokenize
from rag.types import GroundingReport

# --- извлечение ссылок [doc_id#chunk_id] -----------------------------------------
# chunk_id содержит '#' (sha1#номер), поэтому ссылка выглядит как [sha#sha#N];
# обязательный '#' отсекает случайные квадратные скобки ([1], [текст](url)).
_CITATION_RE = re.compile(r"\[([0-9A-Za-z]+#[0-9A-Za-z#]+)\]")

# --- извлечение чисел и дат --------------------------------------------------------
_DATE_RE = re.compile(r"\d{4}[.-]\d{1,2}[.-]\d{1,2}|\d{1,2}[.]\d{1,2}[.]\d{2,4}")
_NUMBER_RE = re.compile(r"\d+(?:[ ,\u00a0]\d{3})*(?:[.,]\d+)?")

# Сущности: snake_case / латинские идентификаторы с точками-дефисами;
# заглавные словосочетания (2+ слова с большой буквы — имена, продукты, разделы).
_IDENT_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*(?:[._-][A-Za-z0-9_]+)+\b")
_CAP_PHRASE_RE = re.compile(r"\b[А-ЯЁA-Z][а-яёa-z0-9]+(?:\s+[А-ЯЁA-Z][а-яёa-z0-9]+)+\b")

# Минимальная длина стем-токена, учитываемого в покрытии (отсекает «и», «на»).
_MIN_TOKEN_LEN = 3


def _number_keys(text: str) -> set:
    """Канонические ключи всех чисел/дат текста (для ТОЧНОГО сравнения).

    Канонизация: пробелы/NBSP — разделители тысяч (удаляются); запятая с
    1–2 цифрами на конце — десятичная (→ точка); дефисные даты сохраняются
    целиком и дополнительно в цифровом виде («2024-01-15» ↔ «15.01.2024»).
    """
    keys = set()

    def add(key: str):
        keys.add(key)
        if key.isdigit():
            keys.add(str(int(key)))       # «01» ↔ «1» (день месяца без ведущего нуля)

    for date in _DATE_RE.findall(text):
        add(date)
        add(re.sub(r"\D", "", date))
    for token in _NUMBER_RE.findall(text):
        t = token.replace(" ", "").replace("\u00a0", "")
        # «1,024» / «1.024» — тысячи; «0,5» / «1.5» — дробь.
        m = re.fullmatch(r"(\d+)[.,](\d+)", t)
        if m and len(m.group(2)) == 3:
            add(m.group(1) + m.group(2))          # 1,024 → 1024
            add(m.group(1) + "." + m.group(2))    # и дробный вариант
        elif m:
            add(m.group(1) + "." + m.group(2))
        else:
            add(t)
    return keys


def _entities(text: str) -> set:
    """Сущности предложения/чанка: идентификаторы + заглавные словосочетания."""
    found = set()
    for m in _IDENT_RE.findall(text):
        found.add(m.lower())
    for m in _CAP_PHRASE_RE.findall(text):
        found.add(normalize(m))
    return found


def _stems(text: str) -> set:
    """Значимые стем-токены (стоп-слова и короткие слова исключены)."""
    from rag.text import STOPWORDS
    return {stem(t) for t in tokenize(text)
            if len(t) >= _MIN_TOKEN_LEN and t not in STOPWORDS}


def _best_chunk(sentence: str, hits, s_stems, s_entities):
    """Лучший чанк для предложения: покрытие + 0.5·сущности. Возвращает (hit, cov, ent)."""
    best, best_cov, best_ent = None, 0.0, 0.0
    for hit in hits:
        c_stems = _stems(hit.text)
        cov = len(s_stems & c_stems) / len(s_stems) if s_stems else 1.0
        c_entities = _entities(hit.text)
        ent = len(s_entities & c_entities) / len(s_entities) if s_entities else 1.0
        if best is None or cov + 0.5 * ent > best_cov + 0.5 * best_ent:
            best, best_cov, best_ent = hit, cov, ent
    return best, best_cov, best_ent


def extract_citations(answer: str) -> list:
    """Список ссылок вида doc_id#chunk_id из текста ответа."""
    return _CITATION_RE.findall(answer or "")


def ground(answer: str, hits: list, cfg) -> GroundingReport:
    """Проверить, насколько ответ опирается на hits. cfg — RagConfig (grounding-секция).

    mode=off → verdict=unchecked без вычислений. Пороги: cfg.grounding.coverage_min
    (доля покрытия стем-токенов до «supported»), numbers_strict (числа проверяются
    точно), список статусов предложений — в GroundingReport.sentences.
    """
    gcfg = cfg.grounding if hasattr(cfg, "grounding") else cfg
    if gcfg.mode == "off":
        return GroundingReport(verdict="unchecked",
                               stats={"mode": "off", "n_sentences": 0})

    valid_refs = {f"{h.doc_id}#{h.chunk_id}" for h in hits}
    # Числа ВСЕХ источников: число, взятое из другого цитируемого чанка, —
    # не галлюцинация (строгость остаётся точной, но без ложных срабатываний
    # при кросс-цитировании).
    all_number_keys = set()
    for hit in hits:
        all_number_keys |= _number_keys(hit.text or "")

    citations = extract_citations(answer)
    bad_citations = [c for c in citations if c not in valid_refs]

    sentences = split_sentences(answer or "")
    rows = []
    n_supported = n_weak = n_unsupported = 0
    cov_sum = 0.0
    n_numbers = n_numbers_missing = 0
    missing_all = set()

    for sent in sentences:
        # Ссылки [sha1#sha1#N] вырезаются ДО анализа: их hex-хвосты и цифры —
        # не утверждения ответа (иначе sha1 давал бы ложные «числа» и просадку
        # покрытия).
        sent_clean = _CITATION_RE.sub(" ", sent)
        s_stems = _stems(sent_clean)
        s_entities = _entities(sent_clean)
        best, cov, ent = _best_chunk(sent_clean, hits, s_stems, s_entities) if hits \
            else (None, 0.0, 0.0)
        sent_numbers = _number_keys(sent_clean)
        missing = sorted(sent_numbers - all_number_keys) if gcfg.numbers_strict else []
        n_numbers += len(sent_numbers)
        n_numbers_missing += len(missing)
        missing_all.update(missing)
        cov_sum += cov

        if missing:
            status = "unsupported"          # выдуманное число — самый тяжкий случай
        elif not s_stems or cov >= gcfg.coverage_min:
            status = "supported"            # нечего проверять либо покрытие достаточное
        elif cov >= gcfg.coverage_min / 2 or ent >= 0.5:
            status = "weak"
        else:
            status = "unsupported"
        n_supported += status == "supported"
        n_weak += status == "weak"
        n_unsupported += status == "unsupported"
        rows.append({
            "text": sent[:120],
            "status": status,
            "best_chunk_id": best.chunk_id if best else "",
            "coverage": round(cov, 3),
            "entities": round(ent, 3),
            "numbers_missing": missing,
        })

    n = len(sentences)
    unsupported_share = (n_unsupported / n) if n else 0.0
    citations_ok = bool(citations) and not bad_citations

    if not citations:
        verdict = "partial"                 # решение №4: без ссылок ответ не принят
    elif n_numbers_missing or unsupported_share > 0.5:
        verdict = "hallucination"
    elif not citations_ok or unsupported_share > 0.25:
        verdict = "partial"
    else:
        verdict = "ok"

    return GroundingReport(
        verdict=verdict,
        sentences=tuple(rows),
        citations_ok=citations_ok,
        regenerated=False,
        stats={
            "mode": gcfg.mode,
            "n_sentences": n,
            "n_supported": n_supported,
            "n_weak": n_weak,
            "n_unsupported": n_unsupported,
            "coverage_avg": round(cov_sum / n, 3) if n else 0.0,
            "n_numbers": n_numbers,
            "n_numbers_missing": n_numbers_missing,
            "missing_preview": sorted(missing_all)[:5],
            "n_citations": len(citations),
            "n_bad_citations": len(bad_citations),
        },
    )


# Фидбэк-промпт авто-перегенерации (strict). Живёт в rag/ — core/ не импортируется;
# агент подставляет номер ответа и список источников в готовые щели.
FEEDBACK_TEMPLATE = (
    "Твой предыдущий ответ (фрагмент): «{answer}»\n"
    "Проверка опоры на источники не пройдена: {reason}.\n"
    "Переформулируй ответ, опираясь ТОЛЬКО на перечисленные источники ({n} шт.): "
    "убери утверждения без подтверждения и выдуманные числа, каждое утверждение "
    "пометь ссылкой [doc_id#chunk_id]. Если ответа в источниках нет — скажи об этом."
)


def feedback_prompt(report: GroundingReport, answer: str, n_sources: int) -> str:
    """Собрать фидбэк-промпт для ОДНОЙ авто-перегенерации (strict)."""
    st = report.stats
    if st.get("n_numbers_missing"):
        preview = ", ".join(st.get("missing_preview", []))
        reason = ("в ответе есть числа, которых нет в источниках: "
                  f"{preview} (всего {st['n_numbers_missing']})")
    elif not report.citations_ok:
        reason = "ответ без корректных ссылок [doc_id#chunk_id]"
    else:
        reason = (f"{st.get('n_unsupported', 0)} из {st.get('n_sentences', 0)} "
                  "утверждений не подтверждаются источниками")
    return FEEDBACK_TEMPLATE.format(answer=answer[:300], reason=reason, n=n_sources)


def render_report(report: GroundingReport, max_sentences: int = 6) -> str:
    """Человекочитаемый вывод для /rag check и транскриптов."""
    st = report.stats
    lines = [f"Вердикт: {report.verdict}"
             + (" (после авто-перегенерации)" if report.regenerated else "")]
    lines.append(
        f"  Предложений: {st.get('n_sentences', 0)} "
        f"(подтверждено {st.get('n_supported', 0)}, слабо {st.get('n_weak', 0)}, "
        f"не подтверждено {st.get('n_unsupported', 0)}); "
        f"покрытие среднее: {st.get('coverage_avg', 0)}")
    lines.append(
        f"  Ссылки: {st.get('n_citations', 0)} (битых {st.get('n_bad_citations', 0)}); "
        f"чисел: {st.get('n_numbers', 0)}, вне источников: {st.get('n_numbers_missing', 0)}")
    for row in report.sentences[:max_sentences]:
        mark = {"supported": "+", "weak": "~", "unsupported": "!"}.get(row["status"], "?")
        extra = f", числа вне: {', '.join(row['numbers_missing'])}" \
            if row["numbers_missing"] else ""
        lines.append(f"  [{mark}] ({row['coverage']:.2f}{extra}) {row['text']}")
    if len(report.sentences) > max_sentences:
        lines.append(f"  … ещё {len(report.sentences) - max_sentences}")
    return "\n".join(lines)