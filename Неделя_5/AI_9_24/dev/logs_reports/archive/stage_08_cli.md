# stage_08_cli.md — Этап 8. CLI (Kod.py)

## Было
`Kod.py` существовал, но не имел токен-учёта/CSV (`/tokens`, `/cost`,
`--token-log`, `--price-*`, `--fresh`), что противоречило §7 п.16.

## Стало
Переписан по `ПРОМТ_cli.md`:
- Команды REPL: /memory /profile /tasks /task /deliver /compare /summary /state
  /tokens /cost /help /exit;
- Флаги: --user, --deliver, --mock, --fresh, --log, --token-log, --max-tokens,
  --price-in, --price-out, --memory-dir;
- Уроки дня 10 (п.16): try: import readline; sys.stdin/stdout.reconfigure(errors="replace");
  BASE_DIR; CSV-журнал токенов (append_token_log); локальная оценка токенов для /tokens,
  /cost и CSV (авторитет — usage живого API, в т.ч. retry 429 уже в LLM-клиенте);
- Журнал маршрутизации: log_line пишет `[Память] …` при каждом remember (п.4);
- /compare показывает разницу ответов с/без long_term + токены (п.14 демонстрация).

## Проверка
L1 `$PY -m py_compile Kod.py core/*.py memory/*.py storage/*.py` → exit 0.

## Статус
✅ Этап 8 закрыт. Следующий этап — Этап 9 «Отладка» (L1–L4 полностью зелёные).