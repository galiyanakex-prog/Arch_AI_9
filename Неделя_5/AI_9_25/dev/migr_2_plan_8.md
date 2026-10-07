# migr_2_plan_8.md — Этап 8. Конфигурация: `.gitignore` (Г1)

> Рабочий план **одного этапа** на основе `dev/migr_2_plan.md` (Ревизия 7.1, §4 «Этап 8»).
> Контур: **Г (конфигурация)**. Метка цели: **Г1**. Зависимости: **этап 0**.
> Порядок: **пошагово с оператором**. **Коммиты — только за оператором** (ШАГ 8.4).

## Цель этапа

**Решение оператора №5.** Закрыть `dev/old_vers/` в `.gitignore`, чтобы архивы не засоряли
`git status` (в отличие от `dev/tests_debug/.tmp/`, который уже закрыт).

> **Факт (Ш12):** `git check-ignore dev/old_vers/` → пусто (не закрыт);
> `dev/tests_debug/.tmp/` — закрыт.

## Предусловия

- `.gitignore` содержит `.tmp` (стр. 13) и `rag/.tmp/` (стр. 26).
- `dev/old_vers/` — архивы прошлых ревизий (не должны попадать в коммит).

## Границы этапа

- **Не** удаляем `dev/old_vers/` — только закрываем `.gitignore`.
- **Не** трогаем git-историю (пункты 2, 6).
- **Не** меняем `requirements.txt`.

---

## Шаги

### ШАГ 8.1 — Красная проверка (агент)

```bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
git check-ignore dev/old_vers/; echo "exit=$?"
git status --short | grep -c "old_vers"
```

Ожидаемо: `check-ignore` — пусто (exit 1); `git status` показывает архивы `old_vers`.

### ШАГ 8.2 — Правка `.gitignore` (агент)

```bash
grep -n "old_vers\|\.tmp" .gitignore
```

Добавить `dev/old_vers/` (рядом с `.tmp`).

### ШАГ 8.3 — Зелёная проверка (агент)

```bash
git check-ignore dev/old_vers/; echo "exit=$?"
git status --short | grep -c "old_vers"
```

Ожидаемо: `check-ignore` → путь (exit 0); `git status` больше не показывает архивы.

### ШАГ 8.4 — Запись в журнал + коммит (оператор)

Запись «Ревизия 7.1 — Этап 8» в `dev/migr_log.md`. **Предлагаемый коммит:**

```
chore(git): закрыть dev/old_vers/ в .gitignore (Ревизия 7.1, этап 8)

Причина: решение оператора №5 — архивы прошлых ревизий не должны засорять git status.
```

---

## Выход этапа

- `.gitignore` — `dev/old_vers/` закрыт;
- `git status` не содержит архивов `old_vers`;
- запись «Этап 8» в `dev/migr_log.md`.

## Гейт 8→9 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `git check-ignore dev/old_vers/` | путь (exit 0) |
| 2 | `git status --short \| grep -c old_vers` | 0 |
| 3 | `dev/tests_debug/.tmp/` по-прежнему закрыт | ✅ |
| 4 | `git diff --stat requirements.txt` | пусто |
| 5 | запись «Этап 8» + перечитывание `migr_2_plan.md` | ✅ |

## Откат

`git checkout -- .gitignore`; запись ❌.

## Что передаём дальше

- **Этапу 9 (Ф):** `git status` чище (архивы скрыты); финальный гейт и чистка `.tmp`.
