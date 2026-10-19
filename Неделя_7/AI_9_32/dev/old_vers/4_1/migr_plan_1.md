# migr_plan_1.md — рабочий план этапа M1 (Ядро планировщика фоновых задач)

> Рабочий план-алгоритм **одного этапа** миграции `den_18` (Ревизия 4). Подчинён
> плану-эталону `dev/migr_plan.md` §4 «Этап M1» (задание 1). Один этап = один рабочий
> план = один автоматический гейт. Результат — в `dev/migr_log.md`.
> `migr_plan.md` перечитан перед созданием этого файла (правило §1.1).

---

## 0. Цель и границы

**Цель** — фоновый планировщик (24/7) с JSON-хранилищем и агрегацией — фундамент
задания 1, **независимый от LLM**. Планировщик — **внешний heartbeat**: фон
обеспечивает worker (поток stdlib), а не LLM.

**Границы**: только stdlib (`threading`, `datetime`, `json`); MCP SDK сюда НЕ
проникает; хранение — только через фасад `Store`; временные файлы тестов — в `.tmp/`.

---

## 1. Артефакты

| Файл | Назначение |
|---|---|
| `integrations/scheduler/__init__.py` | пакет |
| `integrations/scheduler/models.py` | `Job`, `Observation`, `Summary`, `JobState` |
| `integrations/scheduler/store.py` | `SchedulerStore` поверх фасада `Store` (jobs/observations/summaries JSON) |
| `integrations/scheduler/runner.py` | `Scheduler` (worker по расписанию, `run_once`, `start/stop`) |
| `integrations/scheduler/aggregator.py` | `aggregate(...)` → `Summary` (count/min/max/avg/last) |
| `storage/store.py` | + методы путей планировщика (фасад) |

---

## 2. Шаги

1. **`models.py`** — контракты без MCP SDK:
   - `JobState` (`scheduled/running/done/failed/paused`);
   - `Job` (job_id, kind, interval_seconds, at, payload, enabled, state, created_at,
     last_run_at, next_run_at, run_count, last_result);
   - `Observation` (timestamp, source, payload);
   - `Summary` (window, metrics, text, created_at).
2. **`storage/store.py`** — методы фасада:
   `scheduler_dir`, `scheduler_path(user_id, name)`,
   `read_scheduler(user_id, name, default)`, `write_scheduler(user_id, name, data)`
   (каталог `users/<id>/integrations/mcp/scheduler/`).
3. **`store.py` (планировщик)** — `SchedulerStore(store, user_id)`:
   `load_jobs/save_jobs`, `append_observation/list_observations`, `save_summary/latest_summary`.
   Битый/отсутствующий JSON → дефолт (не падает).
4. **`runner.py`** — `Scheduler(store, log)`:
   - `add_job(kind, interval_seconds=0, at=None, payload=None)` → `Job` (job_id, next_run_at);
   - `due_jobs(now)` → созревшие (`next_run_at <= now`), идемпотентность (state=running);
   - `run_once(now=None)` → выполнить созревшие: `record` → наблюдение в JSON; `summary`
     → агрегат; пересчитать `next_run_at`; вернуть агрегированный результат;
   - `start()/stop()` — фоновый поток с тиком; `run_once()` — детерминированный тик без ожидания.
5. **`aggregator.py`** — `aggregate(observations, window)` → `Summary`:
   метрики `count/min/max/avg/last` по числовым полям `payload`; текст сводки.
6. **Детерминированные проверки** (в `.tmp/`): тик с интервалом 0.05 c → наблюдения в
   JSON; агрегатор считает фактические показатели; битый JSON → дефолт; чистая остановка.

---

## 3. Гейт M1→M2 (критерии)

- [ ] планировщик работает по расписанию (укороченный интервал);
- [ ] данные сохраняются в JSON (через `Store`);
- [ ] агрегат возвращается (count/min/max/avg/last);
- [ ] worker стартует и останавливается чисто;
- [ ] L1 без регрессии; SDK не протёк в `integrations/scheduler/` (grep);
- [ ] L2/L3/L4/гейт без регрессии.