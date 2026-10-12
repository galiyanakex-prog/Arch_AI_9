# Сравнение режимов ответа RAG (части 1–2)

k = 5  ·  вопросов = 34

## Таблица «вопрос × режим»

| Вопрос | Режим | top-K до | top-K после | must_contain | Длина | Латентность, мс |
|---|---|---|---|---|---|---|
| q01 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q02 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q03 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q04 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q05 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q06 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q07 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q08 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q09 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q10 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q11 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q12 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q13 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q14 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q15 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q16 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q17 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q18 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q19 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q20 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q21 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q22 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q23 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q24 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| c01 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| c02 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| c03 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| c04 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| c05 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| c06 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| c07 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| c08 | no_rag | 0 | 0 | 0/1 | 39 | 0.0 |
| c09 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| c10 | no_rag | 0 | 0 | 0/2 | 39 | 0.0 |
| q01 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q02 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q03 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q04 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q05 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q06 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q07 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q08 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q09 | rag | 50 | 5 | 0/2 | 39 | 0.1 |
| q10 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q11 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q12 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q13 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q14 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q15 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q16 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q17 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q18 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q19 | rag | 50 | 5 | 0/2 | 39 | 0.1 |
| q20 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q21 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q22 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q23 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q24 | rag | 50 | 5 | 0/2 | 39 | 0.1 |
| c01 | rag | 50 | 5 | 0/2 | 39 | 0.1 |
| c02 | rag | 50 | 5 | 0/2 | 39 | 0.1 |
| c03 | rag | 50 | 5 | 0/2 | 39 | 0.1 |
| c04 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| c05 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| c06 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| c07 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| c08 | rag | 50 | 4 | 0/1 | 39 | 0.2 |
| c09 | rag | 50 | 5 | 0/2 | 39 | 0.1 |
| c10 | rag | 50 | 5 | 0/2 | 39 | 0.2 |
| q01 | rag_filter | 50 | 5 | 0/2 | 39 | 0.2 |
| q02 | rag_filter | 50 | 4 | 0/2 | 39 | 0.1 |
| q03 | rag_filter | 50 | 5 | 0/2 | 39 | 0.2 |
| q04 | rag_filter | 50 | 4 | 0/2 | 39 | 0.3 |
| q05 | rag_filter | 50 | 5 | 0/2 | 39 | 0.4 |
| q06 | rag_filter | 50 | 5 | 0/2 | 39 | 0.2 |
| q07 | rag_filter | 50 | 5 | 0/2 | 39 | 0.2 |
| q08 | rag_filter | 50 | 5 | 0/2 | 39 | 0.2 |
| q09 | rag_filter | 50 | 5 | 0/2 | 39 | 0.1 |
| q10 | rag_filter | 50 | 5 | 0/2 | 39 | 0.2 |
| q11 | rag_filter | 50 | 3 | 0/2 | 39 | 0.2 |
| q12 | rag_filter | 50 | 5 | 0/2 | 39 | 0.3 |
| q13 | rag_filter | 50 | 5 | 0/2 | 39 | 0.2 |
| q14 | rag_filter | 50 | 5 | 0/2 | 39 | 0.2 |
| q15 | rag_filter | 50 | 5 | 0/2 | 39 | 0.2 |
| q16 | rag_filter | 50 | 5 | 0/2 | 39 | 0.2 |
| q17 | rag_filter | 50 | 5 | 0/2 | 39 | 0.2 |
| q18 | rag_filter | 50 | 4 | 0/2 | 39 | 0.1 |
| q19 | rag_filter | 50 | 5 | 0/2 | 39 | 0.1 |
| q20 | rag_filter | 50 | 1 | 0/2 | 39 | 0.1 |
| q21 | rag_filter | 50 | 4 | 0/2 | 39 | 0.2 |
| q22 | rag_filter | 50 | 2 | 0/2 | 39 | 0.2 |
| q23 | rag_filter | 50 | 4 | 0/2 | 39 | 0.2 |
| q24 | rag_filter | 50 | 5 | 0/2 | 39 | 0.2 |
| c01 | rag_filter | 50 | 5 | 0/2 | 39 | 0.1 |
| c02 | rag_filter | 50 | 5 | 0/2 | 39 | 0.1 |
| c03 | rag_filter | 50 | 5 | 0/2 | 39 | 0.2 |
| c04 | rag_filter | 50 | 5 | 0/2 | 39 | 0.2 |
| c05 | rag_filter | 50 | 4 | 0/2 | 39 | 0.2 |
| c06 | rag_filter | 50 | 5 | 0/2 | 39 | 0.2 |
| c07 | rag_filter | 50 | 5 | 0/2 | 39 | 0.2 |
| c08 | rag_filter | 50 | 4 | 0/1 | 39 | 0.2 |
| c09 | rag_filter | 50 | 2 | 0/2 | 39 | 0.1 |
| c10 | rag_filter | 50 | 5 | 0/2 | 39 | 0.2 |
| q01 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| q02 | rag_filter_rewrite | 50 | 4 | 0/2 | 39 | 0.1 |
| q03 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| q04 | rag_filter_rewrite | 50 | 4 | 0/2 | 39 | 0.1 |
| q05 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| q06 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| q07 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| q08 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| q09 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| q10 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| q11 | rag_filter_rewrite | 50 | 3 | 0/2 | 39 | 0.1 |
| q12 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| q13 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| q14 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| q15 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| q16 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| q17 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| q18 | rag_filter_rewrite | 50 | 4 | 0/2 | 39 | 0.1 |
| q19 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| q20 | rag_filter_rewrite | 50 | 1 | 0/2 | 39 | 0.0 |
| q21 | rag_filter_rewrite | 50 | 4 | 0/2 | 39 | 0.1 |
| q22 | rag_filter_rewrite | 50 | 2 | 0/2 | 39 | 0.1 |
| q23 | rag_filter_rewrite | 50 | 4 | 0/2 | 39 | 0.1 |
| q24 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| c01 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| c02 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| c03 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.1 |
| c04 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.2 |
| c05 | rag_filter_rewrite | 50 | 4 | 0/2 | 39 | 0.2 |
| c06 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.2 |
| c07 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.2 |
| c08 | rag_filter_rewrite | 50 | 4 | 0/1 | 39 | 0.1 |
| c09 | rag_filter_rewrite | 50 | 2 | 0/2 | 39 | 0.1 |
| c10 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 0.2 |

## Вердикт

no_rag: источники 0/34, must_contain 0/67, латентность ~0.0 мс · rag: источники 34/34, must_contain 0/67, латентность ~0.2 мс · rag_filter: источники 34/34, must_contain 0/67, латентность ~0.2 мс · rag_filter_rewrite: источники 34/34, must_contain 0/67, латентность ~0.1 мс · RAG добавляет источники: 0 → 102. · фильтр vs без фильтра (must_contain): 0.0 → 0.0 — ✅ не хуже.

## Разбор расхождений

- **q01** — no_rag: ист.=0, must=0/2; rag: ист.=5, must=0/2; rag_filter: ист.=5, must=0/2; rag_filter_rewrite: ист.=5, must=0/2
- **q02** — no_rag: ист.=0, must=0/2; rag: ист.=5, must=0/2; rag_filter: ист.=4, must=0/2; rag_filter_rewrite: ист.=4, must=0/2
- **q03** — no_rag: ист.=0, must=0/2; rag: ист.=5, must=0/2; rag_filter: ист.=5, must=0/2; rag_filter_rewrite: ист.=5, must=0/2
