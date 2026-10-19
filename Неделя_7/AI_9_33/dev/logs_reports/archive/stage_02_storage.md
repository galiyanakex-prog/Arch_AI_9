# stage_02_storage.md — Этап 2. Хранилище (storage/*)

## Было
Файлы `storage/__init__.py`, `storage/store.py`, `storage/db.py` уже существовали
(созданы в предыдущей сессии), но не были сверены с обновлённым метапромтом.

## Стало
Сверено с `ПРОМТ_storage.md` (создан/актуализирован на Этапе 0). Контракт
полностью покрыт:
- `safe_name` (нормализация имён) — есть;
- `ProfileRepository` (SQLite: `profiles(user_id PK, profile_json, updated_at)`,
  upsert, exists) — есть;
- `Store` (user_dir/task_dir/session_dir, ensure_*, save/load_profile с зеркалом
  profile.json, read/write long_term/working/session, sessions_resume, list_tasks,
  read_json/write_json) — все сигнатуры присутствуют;
- схема `session.json` с `messages[]` (id/parent_id/role/content/created_at) — читается
  дефолтом `{messages:[]}`, parent_id формируется в слое short_term (Этап 3).

Вспомогательный артефакт: `tests_debug/unit_runner.py` (лёгкий раннер без pytest,
допустим по §6.1; pytest в venv отсутствует). Раннер передаёт `tmp_path` только если
тест его принимает.

## Проверка
`$PY dev/tests_debug/unit_runner.py test_storage` → 7 OK, 0 FAIL, exit 0.

## Статус
✅ Этап 2 закрыт. Следующий этап — Этап 3 «Память» (memory/*, сверка с
ПРОМТ_memory.md).