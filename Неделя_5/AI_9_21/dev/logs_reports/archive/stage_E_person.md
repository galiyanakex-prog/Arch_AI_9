# stage_E_person.md — Этап E. Персонализация (несколько профилей + профиль-роутер)

> Метапромт: `dev/meta_promt/ПРОМТ_person.md`; архитектура: `ND/arch/arch_den_12.md`
> (§2.3–2.7, §2.10–2.11, §4.3). Порядок фаз — §1.1 метапромта (хранилище → память →
> роутер → агент → CLI → тесты → документация).

## Было
Модель памяти дня 11 (4 слоя, все проверки зелёные: L2 31 OK, L4 5 сценариев,
гейт 9/9). Профиль — один на пользователя: `profiles(user_id PRIMARY KEY)`,
зеркало `users/<id>/profile.json`, `MemoryContext(user_id, task, session_id)`,
блок профиля = Имя/Стиль/Ограничения/Контекст, `/profile` без подкоманд.

## Стало (по фазам)

### Фаза A. Хранилище: несколько профилей
- `storage/db.py`: схема `profiles(user_id, profile_id, profile_json, is_default,
  updated_at)` PK `(user_id, profile_id)`; миграция старой схемы через
  `PRAGMA table_info` → `RENAME` → перенос строк (`profile_id='default'`,
  `is_default=1`, допись `profile_id` в JSON) одной транзакцией;
  `save_profile/load_profile` с `profile_id` (первый профиль → default автоматически);
  `list_profiles/get_default/set_default`; `exists()` — семантика прежняя.
- `storage/store.py`: зеркала `users/<id>/profiles/<pid>.json`; `profile.json`
  остаётся зеркалом default; `profiles_dir/profile_path/list_profiles/
  set_default_profile`; fallback чтения без БД — по каталогу profiles/ → profile.json.

### Фаза B. Память и роутер
- `memory/base.py`: `MemoryContext(user_id, task="", session_id="", profile_id="")` —
  аддитивный параметр; `as_dict()` включает `profile_id`.
- `memory/profile.py`: read/write активного профиля (`ctx.profile_id or None`);
  merge-инвариант сохранён; `as_prompt_block`: «Профиль: <name> (<profile_id>)»
  первой строкой + прежние строки + «Пайплайн скиллов:» (нумерованные инструкции)
  + «Домен: <domain>».
- `core/profile_router.py` (новый): `ProfileRouter.route()` (+2 за триггер,
  +1 за домен, регистронезависимо; победитель >0; ничья/ноль → None) и `explain()`;
  лог «[Роутер] …»; детерминированный, без LLM.

### Фаза C. Агент и CLI
- `core/agent.py`: `active_profile=None`/`auto_route=False`/`router` в `__init__`
  (роутер — только если у store есть profile_repo); `switch_profile()` (лог
  «[Агент] активный профиль: <id>», False если профиля нет); `build_context`
  передаёт `profile_id`; `respond()` при `auto_route` вызывает роутер ДО сборки промта.
- `Kod.py`: `/profile list|show|use|new|route|auto` (голое `/profile` — как раньше);
  `/profile new` — мини-интервью (name/domain/triggers/style/constraints/context);
  флаг `--profile <id>` (несуществующий → предупреждение и default); `/help` дополнен.

### Фаза D. Тесты, документация, приёмка
- `dev/tests_debug/unit/test_person.py` (новый, 9 тестов): мультипрофильный roundtrip,
  миграция, обратная совместимость, роутер (триггеры/ноль/ничья/explain), различие
  блоков и ответов для двух профилей, switch_profile, auto_route до сборки промта.
- `dev/tests_debug/scenario.py`: + `scenario_personalization` (6-й сценарий в main()).
- `README.md`: раздел «Персонализация» + команды/флаг/дерево/демонстрация/показатели.
- `dev/Проверка.md`: строки 20–22 (мультипрофиль; миграция и совместимость; роутер
  и авто-выбор), итог 22 из 22.

## Проверка
Каждая фаза — L1 (`py_compile`) + прежние тесты без правок + ручной скрипт в `.tmp/`:
- Фаза A: `test_storage` 7/7 без правок; `.tmp/check_phaseA.py` — roundtrip двух
  профилей независим, get/set_default, зеркала, миграция legacy-БД → default. OK.
- Фаза B: `test_memory` 6/6, `test_prompt` 4/4 без правок; `.tmp/check_phaseB.py` —
  блок профиля (имя+скиллы+домен), merge, роутер (триггер/ноль/ничья/explain/лог). OK.
- Фаза C: `test_agent` 4/4; L3 smoke OK; `.tmp/check_phaseC.py` — прогон `/profile …`
  в `--mock`: list/show/use/route/auto, `--profile` (валидный/невалидный), разные
  ответы для разных профилей, auto_route переключил профиль до сборки промта. OK.
- Фаза D (гейт, без живого ключа): L1 всей сборки OK; `unit_runner.py` → **40 OK,
  0 FAIL**; `smoke.py` → SMOKE OK; `scenario.py` → **SCENARIO OK (6 сценариев)**;
  `check_acceptance.sh` → **9 из 9, exit 0**. Временные файлы — только
  `dev/tests_debug/.tmp/`; `users/` пуст, `tokens.csv` — только заголовок;
  прежние 19 пунктов `Проверка.md` без регрессии.

Итераций отладки: 0 (контракты §3 не правились; единственная правка по ходу —
синтаксис строки print в Kod.py после замены, устранена сразу).

## Статус
✅ Этап E закрыт. Критерий готовности §5 метапромта выполнен полностью.
Живой смоук — по-прежнему ⏸ (не требуется: роутер и профили детерминированные).
