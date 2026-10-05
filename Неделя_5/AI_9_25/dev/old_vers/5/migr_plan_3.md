# migr_plan_3.md — рабочий план этапа M3 (Пайплайн из MCP-инструментов)

> Рабочий план-алгоритм одного этапа миграции `den_18` (Ревизия 4). Подчинён
> плану-эталону `dev/migr_plan.md` §4 «Этап M3» (задание 2). Один этап = один план =
> один гейт. Результат — в `dev/migr_log.md`.
> `migr_plan.md` перечитан перед созданием файла (правило §1.1).

---

## 0. Цель и границы

**Цель** — пайплайн `search → summarize → saveToFile`: первый получает данные,
второй обрабатывает, третий сохраняет; **автовыполнение цепочки** и **корректная
передача данных** между инструментами.

**Границы**: пайплайн поверх `ToolRegistry`/`ToolExecutor`; **не трогает
`StateMachine`** (инструмент ≠ переход); данные между шагами передаются явно
(результат N → аргумент N+1); SDK — только в `integrations/mcp/`.

---

## 1. Артефакты

| Файл | Назначение |
|---|---|
| `integrations/mcp/pipeline_server.py` | MCP-сервер: `search`, `summarize`, `saveToFile` (+ `readFile` для проверки) |
| `core/tool_pipeline.py` | автоцепочка `PipelineStep`/`Pipeline` поверх `ToolExecutor` |
| `integrations/mcp/config.py` | сервер `pipeline` в `DEFAULT_SERVERS` (env `PIPELINE_MCP_URL`) |

---

## 2. Шаги

1. `pipeline_server.py` на `MCPServer`: `search(query)` — детерминированный набор
   фактов; `summarize(text)` — сжатие; `saveToFile(name, content)` — сохранение в
   область пайплайна через фасад `Store`; `readFile(name)` — чтение для проверки.
2. `core/tool_pipeline.py`: `PipelineStep(tool, arg_map, source_key)` +
   `Pipeline([...])` + `run(pipeline, executor, ...)`: разрешение имён в каталоге,
   передача результата шага N в аргумент шага N+1, аудит каждого вызова (существующий
   `ToolExecutor`). `StateMachine` не трогается.
3. `config.py` — сервер `pipeline` (`transport="http"`, env `PIPELINE_MCP_URL`).
4. Детерминированная проверка (`FakeMCPTransport`): цепочка исполняется
   автоматически; результат `search` попадает в `summarize`, результат `summarize` —
   в `saveToFile`; файл сохранён; аудит — три записи `succeeded`.
5. Живой прогон (не гейт): `/mcp pipeline <запрос>` (появится в M5) → три тула по
   порядку, результат сохранён.

---

## 3. Гейт M3→M4 (критерии)

- [ ] цепочка исполняется автоматически;
- [ ] данные корректно передаются между инструментами (fake + вживую);
- [ ] файл сохранён; аудит — три записи `succeeded`;
- [ ] `TaskStage` не меняется (инструмент ≠ переход);
- [ ] L1 без регрессии; SDK только в `integrations/mcp/`;
- [ ] L2/L3/L4/гейт без регрессии.