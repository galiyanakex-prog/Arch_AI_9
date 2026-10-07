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
| q01 | rag | 50 | 5 | 0/2 | 39 | 5.5 |
| q02 | rag | 50 | 5 | 0/2 | 39 | 3.0 |
| q03 | rag | 50 | 5 | 0/2 | 39 | 4.3 |
| q04 | rag | 50 | 5 | 0/2 | 39 | 2.9 |
| q05 | rag | 50 | 5 | 0/2 | 39 | 3.7 |
| q06 | rag | 50 | 5 | 0/2 | 39 | 3.8 |
| q07 | rag | 50 | 5 | 0/2 | 39 | 2.9 |
| q08 | rag | 50 | 5 | 0/2 | 39 | 3.9 |
| q09 | rag | 50 | 5 | 0/2 | 39 | 4.0 |
| q10 | rag | 50 | 5 | 0/2 | 39 | 3.3 |
| q11 | rag | 50 | 5 | 0/2 | 39 | 2.7 |
| q12 | rag | 50 | 5 | 0/2 | 39 | 4.0 |
| q13 | rag | 50 | 5 | 0/2 | 39 | 3.4 |
| q14 | rag | 50 | 5 | 0/2 | 39 | 5.2 |
| q15 | rag | 50 | 5 | 0/2 | 39 | 4.4 |
| q16 | rag | 50 | 5 | 0/2 | 39 | 4.3 |
| q17 | rag | 50 | 5 | 0/2 | 39 | 3.4 |
| q18 | rag | 50 | 5 | 0/2 | 39 | 3.5 |
| q19 | rag | 50 | 5 | 0/2 | 39 | 1.3 |
| q20 | rag | 50 | 5 | 0/2 | 39 | 3.7 |
| q21 | rag | 50 | 5 | 0/2 | 39 | 3.6 |
| q22 | rag | 50 | 5 | 0/2 | 39 | 5.2 |
| q23 | rag | 50 | 5 | 0/2 | 39 | 4.3 |
| q24 | rag | 50 | 5 | 0/2 | 39 | 2.7 |
| c01 | rag | 50 | 5 | 0/2 | 39 | 3.8 |
| c02 | rag | 50 | 5 | 0/2 | 39 | 3.6 |
| c03 | rag | 50 | 5 | 0/2 | 39 | 3.0 |
| c04 | rag | 50 | 5 | 0/2 | 39 | 4.9 |
| c05 | rag | 50 | 5 | 0/2 | 39 | 5.2 |
| c06 | rag | 50 | 5 | 0/2 | 39 | 3.2 |
| c07 | rag | 50 | 5 | 0/2 | 39 | 3.5 |
| c08 | rag | 50 | 4 | 0/1 | 39 | 3.4 |
| c09 | rag | 50 | 5 | 0/2 | 39 | 2.2 |
| c10 | rag | 50 | 5 | 0/2 | 39 | 2.9 |
| q01 | rag_filter | 50 | 5 | 0/2 | 39 | 3.8 |
| q02 | rag_filter | 50 | 4 | 0/2 | 39 | 2.3 |
| q03 | rag_filter | 50 | 5 | 0/2 | 39 | 4.0 |
| q04 | rag_filter | 50 | 5 | 0/2 | 39 | 2.9 |
| q05 | rag_filter | 50 | 5 | 0/2 | 39 | 3.5 |
| q06 | rag_filter | 50 | 5 | 0/2 | 39 | 3.9 |
| q07 | rag_filter | 50 | 5 | 0/2 | 39 | 3.2 |
| q08 | rag_filter | 50 | 5 | 0/2 | 39 | 4.2 |
| q09 | rag_filter | 50 | 5 | 0/2 | 39 | 4.1 |
| q10 | rag_filter | 50 | 5 | 0/2 | 39 | 4.2 |
| q11 | rag_filter | 50 | 3 | 0/2 | 39 | 1.9 |
| q12 | rag_filter | 50 | 5 | 0/2 | 39 | 4.1 |
| q13 | rag_filter | 50 | 5 | 0/2 | 39 | 3.3 |
| q14 | rag_filter | 50 | 5 | 0/2 | 39 | 4.7 |
| q15 | rag_filter | 50 | 5 | 0/2 | 39 | 5.2 |
| q16 | rag_filter | 50 | 5 | 0/2 | 39 | 4.3 |
| q17 | rag_filter | 50 | 5 | 0/2 | 39 | 3.4 |
| q18 | rag_filter | 50 | 4 | 0/2 | 39 | 1.4 |
| q19 | rag_filter | 50 | 5 | 0/2 | 39 | 1.3 |
| q20 | rag_filter | 50 | 2 | 0/2 | 39 | 2.1 |
| q21 | rag_filter | 50 | 5 | 0/2 | 39 | 3.4 |
| q22 | rag_filter | 50 | 2 | 0/2 | 39 | 3.0 |
| q23 | rag_filter | 50 | 5 | 0/2 | 39 | 4.3 |
| q24 | rag_filter | 50 | 5 | 0/2 | 39 | 2.7 |
| c01 | rag_filter | 50 | 5 | 0/2 | 39 | 3.9 |
| c02 | rag_filter | 50 | 5 | 0/2 | 39 | 3.4 |
| c03 | rag_filter | 50 | 5 | 0/2 | 39 | 3.1 |
| c04 | rag_filter | 50 | 5 | 0/2 | 39 | 4.7 |
| c05 | rag_filter | 50 | 5 | 0/2 | 39 | 6.3 |
| c06 | rag_filter | 50 | 5 | 0/2 | 39 | 3.0 |
| c07 | rag_filter | 50 | 5 | 0/2 | 39 | 3.1 |
| c08 | rag_filter | 50 | 4 | 0/1 | 39 | 2.9 |
| c09 | rag_filter | 50 | 2 | 0/2 | 39 | 0.6 |
| c10 | rag_filter | 50 | 5 | 0/2 | 39 | 2.8 |
| q01 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 3.3 |
| q02 | rag_filter_rewrite | 50 | 4 | 0/2 | 39 | 2.1 |
| q03 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 3.7 |
| q04 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 3.0 |
| q05 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 3.1 |
| q06 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 3.3 |
| q07 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 2.7 |
| q08 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 3.9 |
| q09 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 3.6 |
| q10 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 2.8 |
| q11 | rag_filter_rewrite | 50 | 3 | 0/2 | 39 | 1.8 |
| q12 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 3.4 |
| q13 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 2.8 |
| q14 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 4.0 |
| q15 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 6.8 |
| q16 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 3.8 |
| q17 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 2.7 |
| q18 | rag_filter_rewrite | 50 | 4 | 0/2 | 39 | 1.4 |
| q19 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 1.0 |
| q20 | rag_filter_rewrite | 50 | 2 | 0/2 | 39 | 2.4 |
| q21 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 2.8 |
| q22 | rag_filter_rewrite | 50 | 2 | 0/2 | 39 | 2.6 |
| q23 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 3.6 |
| q24 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 2.3 |
| c01 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 3.3 |
| c02 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 3.4 |
| c03 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 2.6 |
| c04 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 4.2 |
| c05 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 5.5 |
| c06 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 5.3 |
| c07 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 3.0 |
| c08 | rag_filter_rewrite | 50 | 4 | 0/1 | 39 | 2.9 |
| c09 | rag_filter_rewrite | 50 | 2 | 0/2 | 39 | 0.5 |
| c10 | rag_filter_rewrite | 50 | 5 | 0/2 | 39 | 2.7 |

## Вердикт

no_rag: источники 0/34, must_contain 0/67, латентность ~0.0 мс · rag: источники 34/34, must_contain 0/67, латентность ~3.7 мс · rag_filter: источники 34/34, must_contain 0/67, латентность ~3.4 мс · rag_filter_rewrite: источники 34/34, must_contain 0/67, латентность ~3.1 мс · RAG добавляет источники: 0 → 102. · фильтр vs без фильтра (must_contain): 0.0 → 0.0 — ✅ не хуже.

## Разбор расхождений

- **q01** — no_rag: ист.=0, must=0/2; rag: ист.=5, must=0/2; rag_filter: ист.=5, must=0/2; rag_filter_rewrite: ист.=5, must=0/2
- **q02** — no_rag: ист.=0, must=0/2; rag: ист.=5, must=0/2; rag_filter: ист.=4, must=0/2; rag_filter_rewrite: ист.=4, must=0/2
- **q03** — no_rag: ист.=0, must=0/2; rag: ист.=5, must=0/2; rag_filter: ист.=5, must=0/2; rag_filter_rewrite: ист.=5, must=0/2
