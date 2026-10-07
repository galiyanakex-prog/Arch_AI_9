# -*- coding: utf-8 -*-
# ============================================================================
# Kod.py — точка входа агента с явной моделью памяти
#
# КЛЮЧЕВАЯ ИДЕЯ:
# Переход от «одного снимка состояния» к ЯВНОЙ модели памяти. Информация
# разделяется на типы (краткосрочная / рабочая / долговременная + профиль),
# хранится физически раздельно, ЯВНО маршрутизируется при сохранении
# (memory.remember(layer, ...)) и ДОЗИРОВАННО подмешивается в промт
# (deliver: set[str]). Агент — stateful: идентификация на старте,
# интервью-инициализация для нового ID, resume «с того же места».
#
# Уроки дня 10 (п.16 §7): try: import readline; sys.stdin/stdout.reconfigure
# (errors="replace"); BASE_DIR; retry 429 (в LLM-клиенте); токен-учёт + CSV.
#
# Запуск:
#   python Kod.py                # интерактивный REPL (спросит user_id)
#   python Kod.py --user alice   # сразу идентификация alice
#   python Kod.py --mock         # тестовый режим на MockClient (без ключа)
#   python Kod.py --mcp          # REPL с включённым MCP-слоем (/mcp …)
#   python Kod.py --mcp-probe    # one-shot: подключиться к MCP и вывести
#                                # список доступных инструментов (День 16)
#   python Kod.py --rag          # REPL с RAG-слоем: поиск + блок [rag] в промте
#   python Kod.py --rag-ingest   # one-shot: проиндексировать корпус и выйти
#   python Kod.py --rag-search "текст"  # one-shot: поиск по индексу и выйти
#   python Kod.py --rag-eval     # one-shot: метрики retrieval и выйти
#   python Kod.py --rag-compare  # one-shot: стратегии чанкинга × режимы поиска
#
# Внутри чата: /memory /profile [list|show|use|new|route|auto] /tasks
# /task <имя> /deliver /compare /summary /state /tokens /cost
# /mcp [status|servers|tools|refresh|connect|disconnect]
# /rag [status|on|off|ingest|find|stats|eval] /help /exit
# ============================================================================

# 1. Импорты ----------------------------------------------------------------
import os
import sys
import csv
import json

# readline — редактирование ввода (стрелки); без него input() вставляет
# escape-последовательности в текст. Обёрнуто в try: на Windows не падаем.
try:
    import readline
except ImportError:
    pass

import argparse
import dataclasses
from datetime import datetime

# Путь к модулям дня: добавляем каталог скрипта в sys.path, чтобы импорты
# core.* и memory.* работали независимо от того, откуда запущен скрипт.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv

# Импортируем слои дня из модулей (абстракции, фасады, менеджер).
from storage.store import Store, safe_name
from storage.db import ProfileRepository
from memory.base import MemoryContext
from memory.manager import MemoryManager, default_layers
from core.llm_client import (RouterAIClient, MockClient, MODEL_CONTEXT_LIMIT,
                             PRICE_IN_PER_M, PRICE_OUT_PER_M)
from core.prompt_builder import PromptBuilder, DELIVERABLE
from core.agent import Agent, StubExecutor
from core.state_machine import TaskStage, ALLOWED_TRANSITIONS
from core.invariants import Invariant, ConstraintSet

# 2. Окружение и ключ --------------------------------------------------------
load_dotenv()
api_key = os.getenv("API_KEY")

# Кодировки stdin/stdout: errors="replace" — битые байты заменяются заглушкой,
# а не роняют программу (урок дня 10).
sys.stdin.reconfigure(encoding="utf-8", errors="replace")
sys.stdout.reconfigure(errors="replace")

# 3. Флаги --------------------------------------------------------------------
parser = argparse.ArgumentParser(
    description="Чат-бот: агент с явной моделью памяти (memory layers)."
)
parser.add_argument("--user", type=str, default=None,
                    help="Идентификатор пользователя (без него — спросит на старте).")
parser.add_argument("--profile", type=str, default=None,
                    help="Активный профиль на старте (несуществующий → предупреждение и default).")
parser.add_argument("--deliver", type=str, default="profile,invariants,long_term,working,short_term",
                    help="Набор слоёв для доставки в промт (через запятую).")
parser.add_argument("--mock", action="store_true",
                    help="Режим MockClient: ответы от заглушки, ключ не нужен.")
parser.add_argument("--fresh", action="store_true",
                    help="Не восстанавливать прошлое состояние (новая сессия).")
parser.add_argument("--log", type=str, default="Den_log.md",
                    help="Имя лог-файла.")
parser.add_argument("--token-log", type=str, default="tokens.csv",
                    help="CSV-журнал токенов и стоимости (по умолчанию tokens.csv).")
parser.add_argument("--max-tokens", type=int, default=None,
                    help="Лимит длины ответа модели.")
parser.add_argument("--budget", type=int, default=None,
                    help="Лимит входящих токенов промта: необязательные блоки "
                         "опускаются (роль и текущий запрос — всегда). Ориентир для "
                         "ручного значения — MODEL_CONTEXT_LIMIT (%d) минус резерв "
                         "под ответ. По умолчанию выключен." % MODEL_CONTEXT_LIMIT)
parser.add_argument("--price-in", type=float, default=PRICE_IN_PER_M,
                    help="Цена 1M входящих токенов в рублях (по умолчанию 11).")
parser.add_argument("--price-out", type=float, default=PRICE_OUT_PER_M,
                    help="Цена 1M исходящих токенов в рублях (по умолчанию 33).")
parser.add_argument("--memory-dir", type=str, default=None,
                    help="Каталог хранилища памяти (по умолчанию users/ рядом с кодом).")
parser.add_argument("--mcp", action="store_true",
                    help="Включить MCP-слой (подключение к серверам из servers.json).")
parser.add_argument("--mcp-probe", action="store_true",
                    help="One-shot: подключиться к MCP, вывести список инструментов "
                         "и выйти (результат задания Дня 16).")
parser.add_argument("--mcp-probe-server", type=str, default=None,
                    help="С --mcp-probe: строгая проверка одного сервера по id "
                         "(например time).")
parser.add_argument("--no-tools-block", action="store_true",
                    help="С --mcp: не добавлять слой tools в промт (диагностика D2).")
# --- RAG-модуль (День 21, Ревизия 6): выключен по умолчанию ----------------------
parser.add_argument("--rag", action="store_true",
                    help="Включить RAG-слой: поиск по корпусу и блок [rag] в промте.")
parser.add_argument("--no-rag-block", action="store_true",
                    help="С --rag: искать, но не добавлять слой rag в промт (диагностика).")
parser.add_argument("--rag-ingest", action="store_true",
                    help="One-shot: проиндексировать корпус (по умолчанию corpus.list) и выйти.")
parser.add_argument("--rag-path", action="append", default=None, metavar="ПУТЬ",
                    help="С --rag-ingest: конкретный файл/каталог вместо corpus.list "
                         "(можно повторять).")
parser.add_argument("--rag-search", type=str, default=None, metavar="ЗАПРОС",
                    help="One-shot: поиск по индексу, вывести топ-k источников и выйти.")
parser.add_argument("--rag-ask", type=str, default=None, metavar="ВОПРОС",
                    help="One-shot: ответ с RAG (ответ + источники + цитаты) и выйти.")
parser.add_argument("--rag-verify", action="store_true",
                    help="One-shot: проверка источников/цитат на 10 вопросах и выйти.")
parser.add_argument("--rag-threshold", type=float, default=None, metavar="F",
                    help="Порог отсечения нерелевантных результатов (часть 2).")
parser.add_argument("--rag-unknown", type=str, default=None, choices=("off", "on"),
                    help="Режим «не знаю» при слабом контексте (часть 3).")
parser.add_argument("--rag-reranker", type=str, default=None, choices=("off", "lexical"),
                    help="Второй этап ранжирования: реранкер (часть 2).")
parser.add_argument("--rag-rewrite", type=str, default=None,
                    choices=("off", "llm", "heuristic"),
                    help="Query rewrite перед поиском (часть 2).")
parser.add_argument("--rag-eval", action="store_true",
                    help="One-shot: метрики качества retrieval на golden-датасете и выйти.")
parser.add_argument("--rag-compare", action="store_true",
                    help="One-shot: сравнить стратегии чанкинга × режимы ретривера и выйти.")
parser.add_argument("--rag-mode", type=str, default=None,
                    choices=("bm25", "dense", "hybrid"),
                    help="Режим ретривера (по умолчанию из rag/config.json: hybrid).")
parser.add_argument("--rag-strategy", type=str, default=None,
                    choices=("fixed", "structural"),
                    help="Стратегия чанкинга для индексации/сравнения.")
parser.add_argument("--rag-top-k", type=int, default=None,
                    help="Число источников в блоке [rag] (по умолчанию final_k=5).")
parser.add_argument("--rag-config", type=str, default=None, metavar="FILE",
                    help="Путь к JSON-конфигу RAG (по умолчанию rag/config.json).")
parser.add_argument("--rag-grounding", type=str, default=None,
                    choices=("off", "warn", "strict"),
                    help="Режим проверки опоры на источники (полноценно — этап 9).")
parser.add_argument("--rag-multi-query", action="store_true",
                    help="Расширение запроса несколькими формулировками (этап 10).")
parser.add_argument("--scheduler", action="store_true",
                    help="Поднять фоновый планировщик (24/7): периодический сбор данных "
                         "и регулярная сводка в JSON (задание Дня 18).")
parser.add_argument("--scheduler-interval", type=float, default=60.0,
                    help="Интервал планировщика в секундах (по умолчанию 60).")
args = parser.parse_args()

# Корень хранилища памяти: users/ рядом со скриптом (BASE_DIR), если не задано.
MEMORY_ROOT = args.memory_dir if args.memory_dir else os.path.join(BASE_DIR, "users")
LOG_FILE = os.path.join(BASE_DIR, args.log) if not os.path.isabs(args.log) else args.log
TOKEN_LOG = os.path.join(BASE_DIR, args.token_log) if not os.path.isabs(args.token_log) else args.token_log

# 4. Роль агента ---------------------------------------------------------------
SYSTEM_PROMPT = (
    "Ты полезный ассистент с явной моделью памяти. Отвечай кратко на русском языке, "
    "учитывая переданные блоки памяти. Если блок памяти отсутствует — отвечай без него. "
    "Работай в рамках текущего этапа задачи, не перепрыгивай этапы; переходы "
    "контролирует код."
)

# 5. Локальная оценка токенов (для /tokens, /cost, CSV; авторитет — usage живого API) ---
def estimate_tokens(text: str) -> int:
    """Грубая локальная оценка: ~1 токен на 4 символа (без внешних зависимостей)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages) -> int:
    """Оценка списка сообщений API (роль + служебные ~4 токена на сообщение)."""
    return sum(estimate_tokens(m.get("content", "")) + 4 for m in messages)


# 6. Лог маршрутизации памяти ---------------------------------------------------
def log_line(line: str):
    """Пишет строку в лог-файл (журнал «что куда легло»)."""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {line}\n")
    except OSError:
        pass


# 7. CSV-журнал токенов (п.16) ---------------------------------------------------
def append_token_log(exchange, prompt_tokens, cost_rubles):
    """Дозаписывает строку обмена в CSV. Ошибка записи не роняет чат."""
    try:
        is_new = not os.path.exists(TOKEN_LOG)
        with open(TOKEN_LOG, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow(["exchange", "timestamp", "prompt_tokens",
                                 "cost_rubles", "cost_total_rubles"])
            writer.writerow([exchange, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                             prompt_tokens, f"{cost_rubles:.6f}",
                             f"{cost_rubles * exchange:.6f}"])
    except OSError:
        pass


# 8. Композиция объектов (DI) ---------------------------------------------------
def build_agent(user_id=None, mock=False, mcp_enabled=False, scheduler_enabled=False,
                scheduler_interval=60.0, rag_enabled=False, rag_config=None):
    """Собирает Store + профиль-репозиторий + слои + LLM-клиент в Agent.

    MCP-слой опционален (mcp_enabled=False по умолчанию — поведение = den_15):
    gateway → provider → ToolRegistry; каталог сохраняется через Store.
    Планировщик (День 18, scheduler_enabled) — фоновый worker 24/7, независимый
    от LLM; по умолчанию не поднимается.
    RAG-слой (День 21, rag_enabled) — фасад RagService; по умолчанию выключен.
    """
    store = Store(MEMORY_ROOT, log=log_line)
    repo = ProfileRepository(os.path.join(MEMORY_ROOT, "profiles.db"), log=log_line)
    store.profile_repo = repo

    memory = MemoryManager(default_layers(store, log=log_line), log=log_line)
    builder = PromptBuilder(SYSTEM_PROMPT)

    if mock or api_key is None or api_key == "test-key":
        client = MockClient(name="Mock")
        # В тестовом режиме план/шаги детерминированы (без сети): StubExecutor.
        executor = StubExecutor()
    else:
        client = RouterAIClient(api_key=api_key, max_tokens=args.max_tokens)
        executor = None  # Agent построит LLMExecutor по умолчанию

    agent = Agent(client, memory, builder, store, user_id=user_id,
                  default_task="Основная_задача", log=log_line, executor=executor)

    # MCP-слой (День 16): только при явном включении; MCP off по умолчанию.
    if mcp_enabled:
        from integrations.mcp.config import load_servers_config
        from integrations.mcp.gateway import MCPGatewaySync
        from integrations.mcp.provider import MCPToolProvider
        from core.tool_registry import ToolRegistry
        from core.tool_policy import ToolPolicy
        from core.tool_executor import ToolExecutor

        servers_path = store.mcp_servers_path(user_id) if user_id else None
        servers = load_servers_config(servers_path)
        gateway = MCPGatewaySync(servers)
        registry = ToolRegistry()
        registry.add_provider(MCPToolProvider(gateway))
        # Полный tool-use: policy + исполнитель + блок [tools] в промте.
        policy = ToolPolicy()
        executor = ToolExecutor(registry, policy, gateway, store=store,
                                checker=agent.checker, log=log_line)
        agent.mcp_gateway = gateway
        agent.tool_registry = registry
        agent.tool_policy = policy
        agent.tool_executor = executor
        agent.deliver.add("tools")
        # Каталог готовим сразу (реальное discovery); недоступность — деградация.
        try:
            gateway.start()
            snap = registry.refresh()
            # Персистентность каталога (переживает перезапуск) — как в /mcp refresh.
            if user_id:
                store.save_tool_catalog(user_id, {
                    "schema_version": 1, "version": snap.version,
                    "tools": [{
                        "name": t.name, "description": t.description,
                        "input_schema": t.input_schema, "source": t.source,
                        "provider": t.provider, "original_name": t.original_name,
                        "risk_level": t.risk_level,
                        "allowed_stages": sorted(t.allowed_stages),
                        "requires_confirmation": t.requires_confirmation,
                        "enabled": t.enabled,
                    } for t in snap.tools],
                    "created_at": snap.created_at})
        except Exception as error:
            log_line(f"[MCP] стартовое discovery не удалось: {error}")

    # RAG-слой (День 21): только при явном включении; RAG off по умолчанию.
    # Индекс/эмбеддер грузятся лениво (внутри RagService) — старт не платит за
    # загрузку; ошибка сборки слоя не роняет агента (деградация без блока [rag]).
    if rag_enabled:
        try:
            cfg = rag_config or _build_rag_config(args)
            service = _make_rag_service(cfg)
            agent.rag_service = service
            agent.rag_enabled = True
            agent.rag_top_k = cfg.retrieval.final_k
            agent.rag_mode = cfg.retrieval.mode
        except Exception as error:
            log_line(f"[RAG] слой не собран: {type(error).__name__}: {error}")

    # Планировщик фоновых задач (День 18): внешний worker (не LLM). Собирается
    # только при явном включении; привязка к user_id — после идентификации
    # (setup_scheduler в main), т.к. user_id может задаваться интерактивно.
    agent._scheduler_enabled = bool(scheduler_enabled)
    agent._scheduler_interval = scheduler_interval
    return agent


def setup_scheduler(agent: Agent, user_id: str, interval: float = 60.0):
    """Поднять фоновый планировщик 24/7 (внешний worker, не LLM).

    Дефолтное расписание: периодический сбор данных + регулярная сводка.
    Останавливается при /exit / EOF / Ctrl+C (stop_scheduler).
    """
    from integrations.scheduler.store import SchedulerStore
    from integrations.scheduler.runner import Scheduler

    sched_store = SchedulerStore(agent.store, user_id or "scheduler")
    scheduler = Scheduler(sched_store, log=log_line)
    scheduler.add_job("collect", interval_seconds=interval,
                      payload={"source": "heartbeat", "ticks": 1})
    scheduler.add_job("summary", interval_seconds=interval)
    agent.scheduler = scheduler
    scheduler.start()
    print(f"[Планировщик] Фоновый worker запущен (24/7), интервал {interval:g} c. "
          f"Данные: users/{user_id}/integrations/mcp/scheduler/")
    return scheduler


def stop_scheduler(agent: Agent):
    """Остановить фоновый worker чисто (идемпотентно)."""
    if getattr(agent, "scheduler", None) is not None:
        agent.scheduler.stop()
        agent.scheduler = None


# 8.1 One-shot результат задания Дня 16: --mcp-probe ------------------------------
def run_mcp_probe(only_server: str | None = None) -> int:
    """Подключиться к MCP → вывести список инструментов → корректно закрыться.

    Не входит в REPL. D1 (Ревизия 5): успех = **≥1 READY-сервер и непустой
    список инструментов** (а не `overall == "ready"`). Частичная готовность
    (`degraded`) больше не блокирует приёмку: сервер задания может быть жив,
    пока другие недоступны. `only_server` — строгая проверка одного сервера.
    """
    from integrations.mcp.config import load_servers_config
    from integrations.mcp.gateway import MCPGatewaySync

    servers = load_servers_config(None)
    if only_server is not None:
        servers = [s for s in servers if s.server_id == only_server]
        if not servers:
            print(f"[MCP] Сервер «{only_server}» не найден в конфиге.",
                  file=sys.stderr)
            return 1
    gateway = MCPGatewaySync(servers)
    print(f"[MCP] Подключение к серверам: "
          f"{', '.join(s.server_id for s in servers)}")
    try:
        gateway.start()
    except Exception as error:
        print(f"[MCP] Ошибка подключения: {error}", file=sys.stderr)
        return 1

    status = gateway.status()
    ready = [sid for sid, state in status["servers"].items() if state == "ready"]
    if not ready:
        print(f"[MCP] Ни один сервер не подключён (overall: {status['overall']})",
              file=sys.stderr)
        gateway.stop()
        return 1

    print(f"[MCP] Соединение установлено (READY: {', '.join(ready)}; "
          f"overall: {status['overall']}). Список доступных инструментов:")
    tools = gateway.discover()
    if not tools:
        print("[MCP] Инструменты не обнаружены — приёмка не пройдена.",
              file=sys.stderr)
        gateway.stop()
        return 1
    for tool in tools:
        print(f"\n  {tool.name}")
        print(f"    description: {tool.description or '—'}")
        print(f"    input_schema: {json.dumps(tool.input_schema, ensure_ascii=False)}")
    print(f"\n[MCP] Всего инструментов: {len(tools)}")
    gateway.stop()
    print("[MCP] Соединение закрыто (DISCONNECTED).")
    return 0


# 8.2 Семейство команд /mcp (День 16 → День 18) -------------------------------------
def _scheduler_store(agent):
    """Хранилище планировщика текущего пользователя (или None)."""
    from integrations.scheduler.store import SchedulerStore
    user_id = agent.user_id or "scheduler"
    return SchedulerStore(agent.store, user_id)


def handle_mcp_command(agent: Agent, user_input: str):
    """Разбирает /mcp status|servers|tools|refresh|connect|call|disconnect|summary|jobs|pipeline|route."""
    parts = user_input.split()
    sub = parts[1] if len(parts) > 1 else ""

    # Команды планировщика (День 18) доступны и без --mcp (фон — отдельная опция).
    if sub == "summary":
        window = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        sched_store = _scheduler_store(agent)
        summary = sched_store.latest_summary()
        if summary is not None and window == 0:
            # Уже сохранённая сводка — без нового запроса к модели (канон).
            print(f"[Планировщик] Последняя сохранённая сводка "
                  f"({summary.created_at}):\n{summary.text}\n")
            return
        from integrations.scheduler.aggregator import aggregate
        fresh = aggregate(sched_store.list_observations(), window=window)
        sched_store.save_summary(fresh)
        print(f"[Планировщик] Сводка (окно {window or 'все'}):\n{fresh.text}\n")
        return

    if sub == "jobs":
        sched_store = _scheduler_store(agent)
        jobs = sched_store.load_jobs()
        if not jobs:
            print("[Планировщик] Задач нет (запустите с флагом --scheduler).\n")
            return
        print(f"[Планировщик] Задачи ({len(jobs)}):")
        for job in jobs:
            print(f"  {job.job_id} [{job.kind}] state={job.state} "
                  f"interval={job.interval_seconds}s next={job.next_run_at} "
                  f"runs={job.run_count}")
        print()
        return

    if sub == "pipeline":
        # /mcp pipeline <запрос> — автоцепочка search → summarize → saveToFile.
        if len(parts) < 3:
            print("[Пайплайн] Использование: /mcp pipeline <запрос>\n")
            return
        if agent.tool_executor is None:
            print("[Пайплайн] Исполнитель инструментов не собран (нужен --mcp).\n")
            return
        from core.tool_pipeline import Pipeline, PipelineStep, run_pipeline
        query = user_input.split(None, 2)[2]
        pipeline = Pipeline("report", [
            PipelineStep("mcp.pipeline.search", {"query": query}),
            PipelineStep("mcp.pipeline.summarize", input_key="text"),
            PipelineStep("mcp.pipeline.saveToFile", {"name": "report"}, input_key="content"),
        ])
        run = run_pipeline(pipeline, agent.tool_executor, user_id=agent.user_id,
                           task=agent.task,
                           task_stage=(agent.task_state.stage.value if agent.task_state else ""),
                           constraints=agent.constraints)
        print(f"[Пайплайн] {run.name}: {'OK' if run.ok else 'FAIL'}")
        for step in run.steps:
            print(f"  {step['tool']}: {step['status']}")
        print(f"[Пайплайн] Результат: {run.output[:200]}\n")
        return

    if sub == "route":
        # /mcp route <текст> — объяснить выбор инструмента/сервера (без вызова).
        if len(parts) < 3:
            print("[Маршрут] Использование: /mcp route <текст запроса>\n")
            return
        if agent.tool_registry is None:
            print("[Маршрут] Реестр не собран (нужен --mcp).\n")
            return
        from core.tool_routing import rank_tools
        query = user_input.split(None, 2)[2]
        snap = agent.tool_registry.snapshot()
        print(f"[Маршрут] Запрос: «{query}»; каталог v{snap.version}, "
              f"тулов: {len(snap.tools)}")
        matches = rank_tools(query, snap.tools)
        if not matches:
            print("[Маршрут] Совпадений нет — уточните запрос "
                  "(доступно: /mcp tools).\n")
            return
        best = matches[0]
        print(f"[Маршрут] Кандидат: {best.name} [{best.provider}] "
              f"(оценка {best.score:g})")
        print(f"          обоснование: {', '.join(best.reasons) or '—'}")
        for alt in matches[1:]:
            print(f"          альтернатива: {alt.name} [{alt.provider}] "
                  f"(оценка {alt.score:g})")
        print()
        return

    if agent.mcp_gateway is None:
        print("[MCP] MCP-слой выключен (запустите с флагом --mcp).\n")
        return

    gateway = agent.mcp_gateway
    registry = agent.tool_registry

    if sub == "status":
        status = gateway.status()
        print(f"[MCP] Общее состояние: {status['overall']}")
        for sid, state in status["servers"].items():
            print(f"  {sid}: {state}")
        if registry is not None:
            snap = registry.snapshot()
            print(f"  Каталог инструментов: версия {snap.version}, "
                  f"тулов: {len(snap.tools)}")
        print()
        return

    if sub == "servers":
        servers = gateway.gateway._servers
        print("[MCP] Сконфигурированные серверы:")
        for s in servers:
            print(f"  {s.server_id}: transport={s.transport}, enabled={s.enabled}, "
                  f"trust={s.trust_level}, allowed={sorted(s.allowed_tools) or 'все'}, "
                  f"denied={sorted(s.denied_tools) or '—'}")
        print()
        return

    if sub == "tools":
        if registry is None:
            print("[MCP] Реестр не собран.\n")
            return
        snap = registry.snapshot()
        if not snap.tools:
            print("[MCP] Каталог пуст (выполните: /mcp refresh)\n")
            return
        print(f"[MCP] Доступные инструменты (каталог v{snap.version}):")
        for tool in snap.tools:
            print(f"  {tool.name} — {tool.description or '—'}")
            print(f"    input_schema: {json.dumps(tool.input_schema, ensure_ascii=False)}")
        print()
        return

    if sub == "refresh":
        if registry is None:
            print("[MCP] Реестр не собран.\n")
            return
        try:
            gateway.start()
        except Exception as error:
            print(f"[MCP] Подключение не удалось: {error} "
                  f"(память, профили и автомат продолжают работать)\n")
            return
        snap = registry.refresh()
        # Каталог переживает перезапуск — сохранение через Store.
        data = {
            "schema_version": 1,
            "version": snap.version,
            "tools": [{
                "name": t.name, "description": t.description,
                "input_schema": t.input_schema, "source": t.source,
                "provider": t.provider, "original_name": t.original_name,
                "risk_level": t.risk_level,
                "allowed_stages": sorted(t.allowed_stages),
                "requires_confirmation": t.requires_confirmation,
                "enabled": t.enabled,
            } for t in snap.tools],
            "created_at": snap.created_at,
        }
        agent.store.save_tool_catalog(agent.user_id, data)
        ready = [sid for sid, st in gateway.status()["servers"].items() if st == "ready"]
        print(f"[MCP] Каталог обновлён: {len(snap.tools)} тулов "
              f"(версия {snap.version}); серверы READY: {ready or '—'}; "
              f"снимок сохранён (catalog.json)\n")
        return

    if sub == "connect":
        target = parts[2] if len(parts) > 2 else None
        servers = gateway.gateway._servers
        if target is not None:
            found = [s for s in servers if s.server_id == target]
            if not found:
                known = ", ".join(s.server_id for s in servers) or "—"
                print(f"[MCP] Сервер «{target}» не найден. Сконфигурированы: {known}\n")
                return
        try:
            # D6: с id — подключаем ТОЛЬКО целевой сервер (не весь каталог).
            gateway.start(only_server=target)
            if target is not None:
                state = gateway.status().get("servers", {}).get(target, "?")
                print(f"[MCP] Сервер «{target}»: {str(state).upper()}\n")
            else:
                print(f"[MCP] Подключение установлено: "
                      f"{gateway.status()['overall'].upper()}\n")
        except Exception as error:
            print(f"[MCP] Подключение не удалось: {error} "
                  f"(память, профили и автомат продолжают работать)\n")
        return

    if sub == "disconnect":
        gateway.stop()
        print("[MCP] Соединения закрыты (DISCONNECTED).\n")
        return

    if sub == "call":
        # /mcp call <qualified_tool> [{json}]
        if len(parts) < 3:
            print("[MCP] Использование: /mcp call <tool> [{\"arg\": \"value\"}]\n")
            return
        if agent.tool_executor is None:
            print("[MCP] Исполнитель инструментов не собран.\n")
            return
        tool_name = parts[2]
        raw_args = user_input.split(None, 3)[3] if len(parts) > 3 else "{}"
        try:
            arguments = json.loads(raw_args) if raw_args.strip() else {}
        except json.JSONDecodeError as error:
            print(f"[MCP] Аргументы должны быть JSON: {error}\n")
            return
        from core.tools import ToolCallRequest
        result = agent.tool_executor.execute(
            ToolCallRequest(name=tool_name, arguments=arguments),
            user_id=agent.user_id, task=agent.task,
            task_stage=(agent.task_state.stage.value if agent.task_state else ""),
            constraints=agent.constraints)
        print(f"[MCP] Вызов {tool_name}: {result.status}")
        if result.summary:
            print(f"  результат: {result.summary[:500]}")
        print()
        return

    print(f"[MCP] Неизвестная подкоманда: {sub or '(пусто)'}. "
          "Доступно: status | servers | tools | refresh | connect <id> | "
          "call <tool> [json] | disconnect | summary [N] | jobs | "
          "pipeline <запрос> | route <текст>\n")


# 8.3 RAG-модуль (День 21, Ревизия 6): конфиг, one-shot прогоны, /rag -----------------
# Все импорты rag/ — ЛЕНИВЫЕ и только внутри этих функций: без явного включения
# (флаг --rag или /rag …) модуль rag/ не импортируется вообще (инвариант §5).

def _abs_path(path: str) -> str:
    """Относительный путь — от BASE_DIR (запуск из любого каталога)."""
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)


def _build_rag_config(cli_args):
    """RagConfig: rag/config.json → env → флаги CLI (флаги — высший приоритет)."""
    from rag.config import RagConfig

    cfg_path = _abs_path(cli_args.rag_config) if cli_args.rag_config else \
        os.path.join(BASE_DIR, "rag", "config.json")
    cfg = RagConfig.load(cfg_path)

    patch = {}
    if cli_args.rag_mode:
        patch["retrieval"] = dataclasses.replace(cfg.retrieval, mode=cli_args.rag_mode)
    if cli_args.rag_strategy:
        patch["chunking"] = dataclasses.replace(cfg.chunking, strategy=cli_args.rag_strategy)
    if cli_args.rag_top_k:
        patch["retrieval"] = dataclasses.replace(
            patch.get("retrieval", cfg.retrieval), final_k=cli_args.rag_top_k)
    if cli_args.rag_threshold is not None:
        patch["retrieval"] = dataclasses.replace(
            patch.get("retrieval", cfg.retrieval), threshold=cli_args.rag_threshold)
    if cli_args.rag_grounding:
        patch["grounding"] = dataclasses.replace(cfg.grounding, mode=cli_args.rag_grounding)
    if cli_args.rag_unknown:
        patch["unknown"] = dataclasses.replace(
            cfg.unknown, enabled=(cli_args.rag_unknown == "on"))
    if cli_args.rag_reranker:
        patch["rerank"] = dataclasses.replace(
            cfg.rerank, enabled=(cli_args.rag_reranker == "lexical"))
    if cli_args.rag_rewrite and cli_args.rag_rewrite != "off":
        # Режим rewrite сохраняем в retrieval.multi_query (heuristic → выкл. LLM-вариант).
        patch["retrieval"] = dataclasses.replace(
            patch.get("retrieval", cfg.retrieval),
            multi_query=(cli_args.rag_rewrite == "llm"))
        # Флаг имеет приоритет над конфигом: фиксируем режим в rewrite-секции.
        patch["rewrite"] = dataclasses.replace(
            cfg.rewrite, enabled=True, mode=cli_args.rag_rewrite)
    if cli_args.rag_multi_query:
        patch["retrieval"] = dataclasses.replace(
            patch.get("retrieval", cfg.retrieval), multi_query=True)
    if patch:
        cfg = dataclasses.replace(cfg, **patch)

    # Относительные пути конфига — от BASE_DIR (индекс и corpus.list).
    cfg = dataclasses.replace(
        cfg,
        index_dir=_abs_path(cfg.index_dir),
        corpus=dataclasses.replace(cfg.corpus, list_file=_abs_path(cfg.corpus.list_file)),
    )
    return cfg.validate()


def _make_rag_service(cfg):
    """Фасад RagService поверх конфига (единственная точка входа ядра в rag/)."""
    from rag.service import RagService
    return RagService(cfg, log=log_line)


def _print_rag_hits(hits, header: str):
    """Печать выдачи поиска (one-shot и /rag find — без обращения к LLM)."""
    print(f"{header} Найдено источников: {len(hits)}")
    for num, hit in enumerate(hits, 1):
        section = f" · раздел: {hit.section}" if hit.section else ""
        print(f"\n  {num}. [{hit.doc_id}#{hit.chunk_id}] {hit.source}{section}"
              f" · score={hit.score:.4f}")
        text = " ".join((hit.text or "").split())
        print(f"     {text[:300]}{'…' if len(text) > 300 else ''}")
    print()


def _print_answer_sources(agent) -> None:
    """Печать источников/цитат последнего ответа агента (часть 3, этап 10).

    При активном RAG ответ обязан нести источники (source + section/chunk_id) и
    цитаты. Без RAG/источников — ничего не печатаем (поведение прежнее).
    """
    sources = getattr(agent, "last_answer_sources", None) or []
    if not sources:
        return
    verdict = getattr(agent, "last_answer_verdict", "unchecked")
    print(f"[RAG] Источники ответа ({len(sources)}), опора: {verdict}")
    for num, src in enumerate(sources, 1):
        section = f" · {src.section}" if getattr(src, "section", "") else ""
        print(f"  [{num}] {src.source}{section} · {src.chunk_id} · score={src.score}")
    quotes = getattr(agent, "last_answer_quotes", None) or []
    if quotes:
        print(f"[RAG] Цитаты ({len(quotes)}):")
        for num, quote in enumerate(quotes, 1):
            snippet = " ".join((quote.text or "").split())[:200]
            print(f"  [{num}] {quote.source} · {quote.chunk_id}\n      «{snippet}»")
    print()


def run_rag_ingest(cli_args) -> int:
    """One-shot: индексация корпуса (дельтой) → сохранить индекс → выйти."""
    cfg = _build_rag_config(cli_args)
    service = _make_rag_service(cfg)
    paths = [_abs_path(p) for p in cli_args.rag_path] if cli_args.rag_path else None
    try:
        report = service.ingest(paths)
    except Exception as error:
        print(f"[RAG] Индексация не удалась: {type(error).__name__}: {error}",
              file=sys.stderr)
        return 1
    print(f"[RAG] Индексация завершена: +{report.added} новых, ~{report.updated} "
          f"изменённых, -{report.removed} удалённых, ={report.skipped} без изменений")
    print(f"[RAG] Чанков в индексе: {report.chunks}; эмбеддингов запрошено: "
          f"{report.embed_calls}; время: {report.seconds}s")
    for err in list(report.errors)[:5]:
        print(f"[RAG] ⚠ {err}", file=sys.stderr)
    print(f"[RAG] Индекс сохранён: {cfg.index_dir}")
    return 0


def run_rag_search(cli_args) -> int:
    """One-shot: поиск по индексу, печать топ-k источников, выйти (LLM не тратит)."""
    cfg = _build_rag_config(cli_args)
    service = _make_rag_service(cfg)
    if not service.stats().get("n_chunks"):
        print("[RAG] Индекс пуст — сначала: python Kod.py --rag-ingest", file=sys.stderr)
        return 1
    hits = service.search(cli_args.rag_search, k=cli_args.rag_top_k, mode=cli_args.rag_mode)
    if not hits:
        print("[RAG] Ничего не найдено (запрос не зацепился за индекс).", file=sys.stderr)
        return 1
    _print_rag_hits(hits, f"[RAG] Запрос «{cli_args.rag_search}» "
                          f"(режим {cli_args.rag_mode or cfg.retrieval.mode}):")
    return 0


def run_rag_ask(cli_args) -> int:
    """One-shot: ответ с RAG (ответ + источники + цитаты) и выйти (тратит LLM)."""
    cfg = _build_rag_config(cli_args)
    service = _make_rag_service(cfg)
    if not service.stats().get("n_chunks"):
        print("[RAG] Индекс пуст — сначала: python Kod.py --rag-ingest", file=sys.stderr)
        return 1
    llm = _rag_llm_callable(cli_args)
    ans = service.answer(cli_args.rag_ask, use_rag=True, k=cli_args.rag_top_k, llm=llm)
    print(f"[RAG] Вопрос: {cli_args.rag_ask}")
    print(f"[RAG] Ответ (опора: {ans.verdict}, {ans.latency_ms} мс):")
    print(ans.text)
    print()
    if ans.sources:
        print(f"[RAG] Источники ({len(ans.sources)}):")
        for num, src in enumerate(ans.sources, 1):
            section = f" · {src.section}" if src.section else ""
            print(f"  [{num}] {src.source}{section} · {src.chunk_id} · score={src.score}")
    if ans.quotes:
        print(f"[RAG] Цитаты ({len(ans.quotes)}):")
        for num, quote in enumerate(ans.quotes, 1):
            snippet = " ".join(quote.text.split())[:200]
            print(f"  [{num}] {quote.source} · {quote.chunk_id}\n      «{snippet}»")
    return 0


def run_rag_verify(cli_args) -> int:
    """One-shot: проверка источников/цитат на 10 контрольных вопросах и выйти."""
    from rag.verify import verify_answers, render_report
    cfg = _build_rag_config(cli_args)
    service = _make_rag_service(cfg)
    if not service.stats().get("n_chunks"):
        print("[RAG] Индекс пуст — сначала: python Kod.py --rag-ingest", file=sys.stderr)
        return 1
    dataset = os.path.join(BASE_DIR, "rag", "datasets", "queries.jsonl")
    queries = [q for q in _load_queries(dataset) if q.get("id", "").startswith("c")][:10]
    llm = _rag_llm_callable(cli_args)
    result = verify_answers(cfg, queries, k=cfg.retrieval.final_k, llm=llm, limit=10)
    print(render_report(result))
    return 0


def _load_queries(path):
    import json
    return [json.loads(l) for l in open(path, encoding="utf-8").read().splitlines() if l.strip()]


def _rag_llm_callable(cli_args):
    """LLM для one-shot ответа: MockClient в --mock, иначе RouterAI. None — заглушка."""
    if getattr(cli_args, "mock", False):
        from core.llm_client import MockClient
        return MockClient().complete
    api_key = os.getenv("API_KEY")
    if not api_key or api_key == "test-key":
        return None
    from core.llm_client import RouterAIClient
    return RouterAIClient().complete


def run_rag_eval(cli_args) -> int:
    """One-shot: метрики retrieval на golden-датасете (LLM не тратит)."""

    cfg = _build_rag_config(cli_args)
    service = _make_rag_service(cfg)
    if not service.stats().get("n_chunks"):
        print("[RAG] Индекс пуст — сначала: python Kod.py --rag-ingest", file=sys.stderr)
        return 1
    dataset = os.path.join(BASE_DIR, "rag", "datasets", "queries.jsonl")
    report = service.evaluate(dataset=dataset, k=cfg.retrieval.final_k)
    print(f"[RAG] Оценка по {report.dataset} (k={report.k}, "
          f"режим {cli_args.rag_mode or cfg.retrieval.mode}):")
    for name, value in report.metrics.items():
        print(f"  {name}: {value:.4f}")
    lat = report.latency_ms
    if lat:
        print(f"  латентность: p50={lat.get('p50', 0):.0f} мс, "
              f"p95={lat.get('p95', 0):.0f} мс")
    return 0


def run_rag_compare(cli_args) -> int:
    """One-shot: стратегии чанкинга × режимы ретривера (тяжёлый: ребилд индексов)."""
    from rag.compare import render_report

    cfg = _build_rag_config(cli_args)
    service = _make_rag_service(cfg)
    strategies = [cli_args.rag_strategy] if cli_args.rag_strategy else ["fixed", "structural"]
    modes = [cli_args.rag_mode] if cli_args.rag_mode else ["bm25", "dense", "hybrid"]
    queries = os.path.join(BASE_DIR, "rag", "datasets", "queries.jsonl")
    print(f"[RAG] Сравнение: стратегии={strategies}, режимы={modes}, k={cfg.retrieval.final_k}. "
          "Перестройка индексов + эмбеддинги — это долго (минуты на CPU).")
    report = service.compare(strategies=strategies, modes=modes, queries=queries,
                             k=cfg.retrieval.final_k)
    print(render_report(report))
    return 0


def _ensure_rag_service(agent: Agent):
    """Собрать RagService в рантайме (RAG включили в чате без флага --rag)."""
    cfg = _build_rag_config(args)
    agent.rag_service = _make_rag_service(cfg)
    agent.rag_top_k = cfg.retrieval.final_k
    agent.rag_mode = cfg.retrieval.mode
    return agent.rag_service


def handle_rag_command(agent: Agent, user_input: str):
    """Разбирает /rag [status|on|off|ingest [путь]|find <запрос>|stats|eval|check].

    find/stats/eval НЕ обращаются к LLM (только поиск по индексу) — см. мастер-план §4.
    """
    parts = user_input.split()
    sub = parts[1] if len(parts) > 1 else ""

    if sub in ("", "status"):
        if agent.rag_service is None:
            print("[RAG] Слой выключен (запустите с флагом --rag или: /rag on).\n")
            return
        st = agent.rag_service.stats()
        state = "включён" if agent.rag_enabled else "выключен (/rag on)"
        print(f"[RAG] Состояние: {state}; блок в промте: "
              f"{'да' if agent.rag_block_enabled and 'rag' in agent.deliver else 'нет'}")
        print(f"  Индекс: {st['n_chunks']} чанков / {st['n_docs']} документов, "
              f"dim={st['dim']}, модель: {st['model_id'] or '—'}")
        print(f"  Режим: {st['mode']}; стратегия чанкинга индекса: "
              f"{st.get('strategy', '—')}; каталог: {st['index_dir']}")
        print(f"  Ollama ({st['ollama_url']}): "
              f"{'доступна' if st['ollama_ready'] else 'НЕдоступна — dense/hybrid деградируют'}")
        print()
        return

    if sub == "on":
        if agent.rag_service is None:
            try:
                _ensure_rag_service(agent)
            except Exception as error:
                print(f"[RAG] Не удалось собрать слой: {error}\n")
                return
        agent.rag_enabled = True
        if agent.rag_block_enabled:
            agent.deliver.add("rag")
        print("[RAG] Включён: следующий запрос обогатится блоком [rag].\n")
        return

    if sub == "off":
        agent.rag_enabled = False
        agent.deliver.discard("rag")
        print("[RAG] Выключён: блок [rag] больше не попадает в промт.\n")
        return

    if sub == "ingest":
        try:
            service = agent.rag_service or _ensure_rag_service(agent)
            paths = [_abs_path(p) for p in parts[2:]] or None
            report = service.ingest(paths)
        except Exception as error:
            print(f"[RAG] Индексация не удалась: {error}\n")
            return
        print(f"[RAG] Индексация: +{report.added} ~{report.updated} "
              f"-{report.removed} ={report.skipped}; чанков: {report.chunks}; "
              f"{report.seconds}s\n")
        return

    if sub == "find":
        if len(parts) < 3:
            print("[RAG] Использование: /rag find <запрос>\n")
            return
        service = agent.rag_service or _ensure_rag_service(agent)
        query = user_input.split(None, 2)[2]
        hits = service.search(query, k=agent.rag_top_k)
        if not hits:
            print("[RAG] Ничего не найдено (индекс пуст? /rag stats).\n")
            return
        # Ручной поиск тоже задаёт «последние найденные источники» — после него
        # доступен /rag check <ответ> без обращения к LLM.
        agent.last_rag_hits = hits
        _print_rag_hits(hits, f"[RAG] Запрос «{query}»:")
        return

    if sub == "stats":
        service = agent.rag_service or _ensure_rag_service(agent)
        st = service.stats()
        print(f"[RAG] Индекс: {st['n_chunks']} чанков / {st['n_docs']} документов; "
              f"dim={st['dim']}; модель: {st['model_id'] or '—'}; "
              f"размер: {st['size_bytes']} Б; RAM≈{st['ram_estimate_bytes']} Б")
        print(f"  Режим: {st['mode']}; стратегия: {st['strategy']}; "
              f"multi-query: {'вкл' if st['multi_query'] else 'выкл'}; "
              f"эмбеддер: {st['embedding_provider']} "
              f"({st['ollama_url']}, {'жив' if st['ollama_ready'] else 'недоступен'})")
        cache = st["cache"]
        lat = st["latency"]
        print(f"  Кэш: {'вкл' if cache['enabled'] else 'выкл'}, записей {cache['entries']}"
              f"/{cache['max_entries']}, TTL {cache['ttl_seconds']}с; "
              f"попаданий {cache['hits']}, промахов {cache['misses']}, "
              f"вытеснений {cache['evictions']}, инвалидаций {cache['invalidations']} "
              f"(hit-rate {cache['hit_rate']})")
        print(f"  Латентность поиска: p50={lat['p50']} мс, p95={lat['p95']} мс "
              f"(замеров {lat['n']})\n")
        return

    if sub == "eval":
        service = agent.rag_service or _ensure_rag_service(agent)
        dataset = os.path.join(BASE_DIR, "rag", "datasets", "queries.jsonl")
        try:
            report = service.evaluate(dataset=dataset)
        except Exception as error:
            print(f"[RAG] Оценка не удалась: {error}\n")
            return
        print(f"[RAG] Метрики (k={report.k}):")
        for name, value in report.metrics.items():
            print(f"  {name}: {value:.4f}")
        print()
        return

    if sub == "check":
        # /rag check <ответ> — grounding по ПОСЛЕДНИМ найденным чанкам (LLM не тратит).
        if len(parts) < 3:
            print("[RAG] Использование: /rag check <текст ответа>\n")
            return
        if not agent.last_rag_hits:
            print("[RAG] Нет последних найденных источников — сначала обычный "
                  "вопрос или /rag find <запрос>.\n")
            return
        answer = user_input.split(None, 2)[2]
        report = agent.check_grounding(answer)
        if report is None:
            print("[RAG] Grounding недоступен (слой не собран).\n")
            return
        print("[RAG] Проверка опоры на источники "
              f"(режим {agent.rag_service.cfg.grounding.mode}):")
        print(agent.rag_service.grounding_render(report))
        print()
        return

    if sub == "ask":
        # /rag ask <вопрос> — ответ с RAG (ответ + источники + цитаты).
        if len(parts) < 3:
            print("[RAG] Использование: /rag ask <вопрос>\n")
            return
        service = agent.rag_service or _ensure_rag_service(agent)
        question = user_input.split(None, 2)[2]
        llm = getattr(agent.llm, "complete", None)
        ans = service.answer(question, use_rag=True, k=agent.rag_top_k, llm=llm)
        print(f"[RAG] Ответ (опора: {ans.verdict}, {ans.latency_ms} мс):\n{ans.text}\n")
        if ans.sources:
            print(f"[RAG] Источники ({len(ans.sources)}):")
            for num, src in enumerate(ans.sources, 1):
                section = f" · {src.section}" if src.section else ""
                print(f"  [{num}] {src.source}{section} · {src.chunk_id} · score={src.score}")
        if ans.quotes:
            print(f"[RAG] Цитаты ({len(ans.quotes)}):")
            for num, quote in enumerate(ans.quotes, 1):
                snippet = " ".join(quote.text.split())[:200]
                print(f"  [{num}] {quote.source} · {quote.chunk_id}\n      «{snippet}»")
        print()
        return

    if sub in ("sources", "quotes"):
        # Источники/цитаты последнего ответа агента (заполняются в respond).
        sources = getattr(agent, "last_answer_sources", None) or []
        quotes = getattr(agent, "last_answer_quotes", None) or []
        if sub == "sources":
            if not sources:
                print("[RAG] Источников нет (RAG выключен или пустой индекс).\n")
                return
            print(f"[RAG] Источники последнего ответа ({len(sources)}, "
                  f"опора: {getattr(agent, 'last_answer_verdict', '—')}):")
            for num, src in enumerate(sources, 1):
                section = f" · {src.section}" if src.section else ""
                print(f"  [{num}] {src.source}{section} · {src.chunk_id} · score={src.score}")
        else:
            if not quotes:
                print("[RAG] Цитат нет (RAG выключен или пустой индекс).\n")
                return
            print(f"[RAG] Цитаты последнего ответа ({len(quotes)}):")
            for num, quote in enumerate(quotes, 1):
                snippet = " ".join(quote.text.split())[:200]
                print(f"  [{num}] {quote.source} · {quote.chunk_id}\n      «{snippet}»")
        print()
        return

    if sub == "verify":
        # /rag verify — проверка источников/цитат на 10 контрольных вопросах.
        from rag.verify import verify_answers, render_report
        service = agent.rag_service or _ensure_rag_service(agent)
        dataset = os.path.join(BASE_DIR, "rag", "datasets", "queries.jsonl")
        queries = [q for q in _load_queries(dataset) if q.get("id", "").startswith("c")][:10]
        llm = getattr(agent.llm, "complete", None)
        result = verify_answers(service.cfg, queries, k=service.cfg.retrieval.final_k,
                                llm=llm, limit=10)
        print(render_report(result))
        print()
        return

    print("[RAG] Подкоманды: status | on | off | ingest [путь] | find <запрос> | "
          "ask <вопрос> | sources | quotes | verify | stats | eval | check\n")


# 9. Интервью-инициализация ------------------------------------------------------
def run_interview(agent: Agent, user_id: str):
    """Проводит интервью (стиль/констрейнты/контекст) и создаёт дерево памяти."""
    print(f"[Инициализация] Новый пользователь «{user_id}» — проведу интервью.\n")
    name = input("Ваше имя: ").strip()
    answers = {}
    for key, question in agent.interview_questions():
        val = input(f"{question}\n> ").strip()
        answers[key] = val
    agent.initialize_user(user_id, name, answers)
    print(f"[Инициализация] Профиль и дерево users/{user_id}/ созданы.\n")


# 10. Печать справки ---------------------------------------------------------------
def print_help():
    print("[Справка] Доступные команды:")
    print("  /memory              — снимок «какие данные в каком типе памяти»")
    print("  /profile             — активный профиль (style/constraints/context)")
    print("  /profile list        — профили пользователя (* default, > активный)")
    print("  /profile show <id>   — полный JSON профиля")
    print("  /profile use <id>    — переключить активный профиль сессии")
    print("  /profile new <id>    — создать профиль (мини-интервью)")
    print("  /profile route <текст> — показать решение роутера, НЕ переключая")
    print("  /profile auto on|off — авто-роутинг профиля по каждому запросу")
    print("  /tasks               — список задач + активная задача")
    print("  /task <имя>          — переключить/создать задачу (с отметкой перехода)")
    print("  /task retry          — повтор задачи из состояния failed (→ planning)")
    print("  /plan <цель>         — новая задача: план строится и ожидает утверждения")
    print("  /approve             — утвердить план (planning → plan_approved)")
    print("  /goto <этап>         — попытка явного перехода (демо контроля переходов)")
    print("  /transitions         — карта переходов + журнал попыток и отказов")
    print("  /step                — один шаг автомата (снимок: этап/шаг/действие)")
    print("  /run                 — крутить автомат до done/failed (не обходит /approve)")
    print("  /pause               — пауза на любом рабочем этапе (состояние сохраняется)")
    print("  /resume              — продолжение с того же шага, без повторных объяснений")
    print("  /deliver <слои>      — набор включаемых слоёв (напр. profile,working)")
    print("  /compare             — сравнение ответа с/без слоя долговременной памяти")
    print("  /summary             — резюме сессий текущей задачи")
    print("  /state               — снимок задачи + task state machine (этапы, переходы)")
    print("  /invariants          — список инвариантов (id, category, severity, active)")
    print("  /invariant add <id> <category> <текст>  — добавить инвариант")
    print("  /invariant set <id> <текст> [--yes]     — изменить (нужно подтверждение)")
    print("  /invariant on|off <id>                  — включить/выключить инвариант")
    print("  /check <действие>    — прогнать действие через проверку инвариантов (демо)")
    print("  /tokens              — локальная оценка токенов последнего запроса")
    print("  /cost                — стоимость обменов (локальная оценка)")
    print("  /mcp status          — состояние MCP-подключения + версия каталога")
    print("  /mcp servers         — сконфигурированные MCP-серверы")
    print("  /mcp tools           — список доступных инструментов (результат Дня 16)")
    print("  /mcp refresh         — обновить каталог инструментов (discovery)")
    print("  /mcp connect <id>    — подключить MCP-сервер")
    print("  /mcp call <tool> [{json}] — вызвать инструмент вручную")
    print("  /mcp disconnect      — закрыть MCP-соединения")
    print("  /mcp summary [N]     — последняя сохранённая сводка планировщика")
    print("  /mcp jobs            — задачи планировщика (24/7)")
    print("  /mcp pipeline <запрос> — пайплайн search→summarize→saveToFile")
    print("  /mcp route <текст>   — объяснить выбор инструмента/сервера")
    print("  /rag [status]        — состояние RAG-слоя и индекса")
    print("  /rag on|off          — включить/выключить блок [rag] в промте")
    print("  /rag ingest [путь]   — проиндексировать корпус (по умолчанию corpus.list)")
    print("  /rag find <запрос>   — поиск по индексу (без обращения к LLM)")
    print("  /rag stats           — метрики индекса (чанки, документы, модель)")
    print("  /rag eval            — метрики retrieval на golden-датасете")
    print("  /rag check <ответ>   — проверка опоры ответа на последние источники")
    print("  /help                — эта справка")
    print("  /exit                — завершить и сохранить состояние")
    print()


# 10.1 Обработка семейства команд /profile (персонализация) -------------------------
def handle_profile_command(agent: Agent, user_input: str):
    """Разбирает /profile [list|show|use|new|route|auto]; голое /profile — как раньше."""
    parts = user_input.split()
    sub = parts[1] if len(parts) > 1 else ""

    # Голое /profile — активный профиль (обратная совместимость с днём 11).
    if not sub:
        ctx = MemoryContext(agent.user_id, profile_id=agent.active_profile or "")
        profile = agent.memory.layers["profile"].read(ctx)
        active = agent.active_profile or "(default)"
        print(f"[Профиль] активный: {active}\n{profile}\n")
        return

    if sub == "list":
        profiles = agent.store.list_profiles(agent.user_id)
        # Активный профиль: явный выбор сессии, иначе — default из хранилища.
        active = agent.active_profile
        if active is None and agent.store.profile_repo is not None:
            active = agent.store.profile_repo.get_default(agent.user_id)
        print("[Профили]")
        for pid, is_default in profiles:
            marks = ("*" if is_default else " ") + (">" if pid == active else " ")
            print(f"  {marks} {pid}")
        print("  (* — default, > — активный)\n")
        return

    if sub == "show":
        if len(parts) < 3:
            print("[Профиль] Укажите id: /profile show <id>\n")
            return
        profile = agent.store.load_profile(agent.user_id, parts[2])
        if profile is None:
            print(f"[Профиль] «{parts[2]}» не найден.\n")
            return
        print(f"[Профиль {parts[2]}]\n{json.dumps(profile, ensure_ascii=False, indent=2)}\n")
        return

    if sub == "use":
        if len(parts) < 3:
            print("[Профиль] Укажите id: /profile use <id>\n")
            return
        if agent.switch_profile(parts[2]):
            print(f"[Профиль] Активный профиль: {parts[2]}\n")
        else:
            print(f"[Профиль] «{parts[2]}» не существует (см. /profile list)\n")
        return

    if sub == "new":
        if len(parts) < 3:
            print("[Профиль] Укажите id: /profile new <id>\n")
            return
        run_profile_interview(agent, parts[2])
        return

    if sub == "route":
        text = user_input.split(maxsplit=2)
        if len(text) < 3:
            print("[Роутер] Укажите текст: /profile route <текст>\n")
            return
        if agent.router is None:
            print("[Роутер] Недоступен (нет репозитория профилей).\n")
            return
        print(agent.router.explain(agent.user_id, text[2]) + "\n")
        return

    if sub == "auto":
        mode = parts[2] if len(parts) > 2 else ""
        if mode == "on":
            agent.auto_route = True
            print("[Роутер] Авто-роутинг включён (профиль выбирается по каждому запросу).\n")
        elif mode == "off":
            agent.auto_route = False
            print("[Роутер] Авто-роутинг выключен.\n")
        else:
            print(f"[Роутер] Авто-роутинг: {'on' if agent.auto_route else 'off'} "
                  f"(управление: /profile auto on|off)\n")
        return

    print(f"[Профиль] Неизвестная подкоманда: {sub}. См. /help\n")


def run_profile_interview(agent: Agent, profile_id: str):
    """Мини-интервью создания профиля: name, domain, triggers, style, constraints, context."""
    print(f"[Профиль] Создание профиля «{profile_id}» (мини-интервью).")
    name = input("  Имя профиля: ").strip() or profile_id
    domain = input("  Домен (область запросов): ").strip()
    triggers = [t.strip() for t in input("  Триггеры (через запятую): ").split(",") if t.strip()]
    style = input("  Стиль ответов: ").strip()
    constraints = input("  Ограничения: ").strip()
    context = input("  Контекст: ").strip()
    profile = {
        "id": agent.user_id,
        "profile_id": profile_id,
        "name": name,
        "domain": domain,
        "triggers": triggers,
        "style": {"answers": style},
        "constraints": {"answers": constraints},
        "context": {"answers": context},
        "skills": [],
    }
    agent.store.save_profile(agent.user_id, profile, profile_id)
    agent.switch_profile(profile_id)
    print(f"[Профиль] Профиль «{profile_id}» создан и активирован.\n")


# 11. Демонстрация влияния памяти на ответы ----------------------------------------
def compare_demonstration(agent: Agent, exchange_tracker):
    """Сравнение ответа с/без долговременной памяти (демонстрация задания п.14)."""
    question = "Какой стек я предпочитаю и почему?"

    # Вариант 1: все слои.
    agent.deliver = {"profile", "long_term", "working", "short_term"}
    prompt_ctx_full = agent.build_context(question)
    messages_full = agent.prompts.build(prompt_ctx_full, agent.deliver)
    answer_full = agent.llm.complete(messages_full)

    # Вариант 2: без слоя долговременной памяти (урезанный режим).
    agent.deliver = {"profile", "working", "short_term"}
    prompt_ctx_cut = agent.build_context(question)
    messages_cut = agent.prompts.build(prompt_ctx_cut, agent.deliver)
    answer_cut = agent.llm.complete(messages_cut)

    # Учёт токенов демонстрации (локальная оценка).
    tokens_full = estimate_messages_tokens(messages_full)
    tokens_cut = estimate_messages_tokens(messages_cut)
    cost_full = (tokens_full * args.price_in) / 1_000_000
    cost_cut = (tokens_cut * args.price_in) / 1_000_000
    exchange_tracker["n"] += 2
    exchange_tracker["tokens"] += tokens_full + tokens_cut
    exchange_tracker["cost"] += cost_full + cost_cut

    print("\n[Сравнение] Влияние долговременной памяти на ответы:")
    print(f"  С long_term  (~{tokens_full} вх. токенов): {answer_full if answer_full else '(нет ответа)'}")
    print(f"  БЕЗ long_term (~{tokens_cut} вх. токенов): {answer_cut if answer_cut else '(нет ответа)'}")
    print("  (разница показывает, как слой долговременной памяти меняет ответ)\n")


# 12. Показать state machine -------------------------------------------------------
def show_state(agent: Agent):
    """Полный снимок TaskState + карта переходов + разрешённые из текущей + отказы."""
    st = agent.task_state
    if st is not None:
        steps = st.steps or []
        print("[Состояние задачи]")
        print(f"  Задача: {st.objective} (id: {st.task_id})")
        print(f"  Этап: {st.stage.value}")
        if steps:
            idx = min(st.current_step, len(steps) - 1)
            print(f"  Шаг: {st.current_step}/{len(steps)} — {steps[idx]}")
        else:
            print(f"  Шаг: {st.current_step}/0 (план ещё не построен)")
        if st.expected_action:
            print(f"  Ожидаемое действие: {st.expected_action}")
        if st.previous_stage:
            print(f"  Вернуться после паузы к: {st.previous_stage.value}")
        if st.error:
            print(f"  Ошибка: {st.error}")
        print(f"  Результатов собрано: {len(st.results)}")
        allowed = ALLOWED_TRANSITIONS.get(st.stage, set())
        names = ", ".join(t.value for t in sorted(allowed, key=lambda s: s.value)) or "—"
        print(f"  Разрешённые переходы из {st.stage.value}: {names}")
        refused = sum(1 for e in st.transition_log if not e.get("allowed"))
        print(f"  Отказов в журнале переходов: {refused}")
        print()
    else:
        print("[Состояние задачи] Нет активной задачи (создайте: /plan <цель>)\n")
    print("[State machine] Этапы и разрешённые переходы:")
    for stage in TaskStage:
        targets = ALLOWED_TRANSITIONS.get(stage, set())
        names = ", ".join(t.value for t in sorted(targets, key=lambda s: s.value)) or "—"
        print(f"  {stage.value} → {names}")
    print()



# 12.1 Печать снимка автомата после команд жизненного цикла ------------------------
def print_task_snapshot(agent: Agent, header: str):
    """Компактный снимок: этап, шаг N/M + текст шага, ожидаемое действие, последний результат."""
    st = agent.task_state
    print(f"[{header}]")
    if st is None:
        print("  Нет активной задачи (сначала /plan <цель>)\n")
        return
    steps = st.steps or []
    step_view = f"{st.current_step}/{len(steps)}"
    if steps:
        idx = min(st.current_step, len(steps) - 1)
        step_view += f" — {steps[idx]}"
    print(f"  Этап: {st.stage.value} | Шаг: {step_view}")
    if st.expected_action:
        print(f"  Ожидаемое действие: {st.expected_action}")
    if st.stage.value == "paused" and st.previous_stage:
        print(f"  Вернуться после паузы к: {st.previous_stage.value}")
    if st.error:
        print(f"  Ошибка: {st.error}")
    if st.results:
        last = str(st.results[-1])
        print(f"  Последний результат: {last[:120]}")
    print()


# 12.2 Инварианты: список/добавление/изменение/вкл-выкл + демонстрация проверки ---------
def handle_invariants_command(agent: Agent, user_input: str):
    """Разбирает /invariants и /invariant add|set|on|off (День 14).

    /invariants                       — список правил задачи;
    /invariant add <id> <cat> <текст> — добавить правило;
    /invariant set <id> <текст> [--yes] — изменить (без --yes требует подтверждения);
    /invariant on|off <id>            — включить/выключить.
    """
    parts = user_input.split()
    command = parts[0]

    # /invariants — список.
    if command == "/invariants":
        if not agent.constraints.invariants:
            print("[Инварианты] Набор пуст (все действия разрешены). "
                  "Добавить: /invariant add <id> <category> <текст>\n")
            return
        print(f"[Инварианты] Задача «{agent.task}»:")
        for inv in agent.constraints.invariants:
            flag = "on " if inv.active else "off"
            print(f"  [{flag}] {inv.id} | {inv.category} | {inv.severity} | {inv.description}")
        print()
        return

    # /invariant <sub> ...
    sub = parts[1] if len(parts) > 1 else ""

    if sub == "add":
        if len(parts) < 5:
            print("[Инварианты] Формат: /invariant add <id> <category> <текст>\n")
            return
        inv_id, category = parts[2], parts[3]
        text = user_input.split(maxsplit=4)[4].strip()
        agent.add_invariant(Invariant(id=inv_id, category=category, description=text))
        print(f"[Инварианты] Добавлен {inv_id} ({category}).\n")
        return

    if sub == "set":
        if len(parts) < 4:
            print("[Инварианты] Формат: /invariant set <id> <текст> [--yes]\n")
            return
        inv_id = parts[2]
        authorized = "--yes" in parts
        text = user_input.split(maxsplit=3)[3]
        if authorized:
            text = text.replace("--yes", "").strip()
        try:
            agent.update_invariant(inv_id, text, authorized=authorized)
            print(f"[Инварианты] Изменён {inv_id}.\n")
        except PermissionError as error:
            print(f"[Инварианты] {error} Повторите с --yes для подтверждения.\n")
        except KeyError as error:
            print(f"[Инварианты] {error}\n")
        return

    if sub in ("on", "off"):
        if len(parts) < 3:
            print(f"[Инварианты] Формат: /invariant {sub} <id>\n")
            return
        inv_id = parts[2]
        if agent.toggle_invariant(inv_id, sub == "on"):
            print(f"[Инварианты] {inv_id} → {sub}.\n")
        else:
            print(f"[Инварианты] Инвариант «{inv_id}» не найден.\n")
        return

    print("[Инварианты] Подкоманды: add | set | on | off (см. /help)\n")


def check_demonstration(agent: Agent, user_input: str):
    """ /check <действие> — прогнать ProposedAction через InvariantChecker (без исполнения)."""
    parts = user_input.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        print("[Проверка] Укажите действие: /check <описание действия>\n")
        return
    text = parts[1].strip()
    action = agent.propose_action(text)
    violations = agent.check_invariants(action)
    warnings = agent.invariant_warnings(action)
    print(f"[Проверка] Действие: {action.description}")
    print(f"  technology={action.technology} | language={action.language} | "
          f"adds_dependency={action.adds_dependency} | "
          f"changes_database_schema={action.changes_database_schema}")
    if violations:
        print("  Результат: ЗАПРЕЩЕНО. Нарушения:")
        for violation in violations:
            print(f"    - {violation}")
    else:
        print("  Результат: разрешено (блокирующих нарушений нет).")
    for warning in warnings:
        print(f"  ⚠ {warning}")
    print()


# 13. Главная программа ------------------------------------------------------------

def main():
    # One-shot результат задания Дня 16: подключиться → вывести список → выйти.
    if args.mcp_probe:
        sys.exit(run_mcp_probe(args.mcp_probe_server))

    # One-shot прогоны RAG (День 21): индексация / поиск / метрики / сравнение.
    # REPL не запускается, LLM не тратится. Заданные прогоны идут по порядку
    # (индексация раньше метрик), код выхода — худший из кодов прогонов.
    rag_runs = [(args.rag_ingest, run_rag_ingest),
                (args.rag_search is not None, run_rag_search),
                (args.rag_ask is not None, run_rag_ask),
                (args.rag_verify, run_rag_verify),
                (args.rag_eval, run_rag_eval),
                (args.rag_compare, run_rag_compare)]
    if any(flag for flag, _ in rag_runs):
        sys.exit(max((run(args) for flag, run in rag_runs if flag), default=0))

    # Идентификация: --user либо интерактивный ввод ДО загрузки памяти.
    user_id = args.user
    rag_cfg = _build_rag_config(args) if args.rag else None
    agent = build_agent(user_id=user_id, mock=args.mock, mcp_enabled=args.mcp,
                        scheduler_enabled=args.scheduler,
                        scheduler_interval=args.scheduler_interval,
                        rag_enabled=args.rag, rag_config=rag_cfg)

    # Накопительный трекер токенов сессии (локальная оценка).
    exchange_tracker = {"n": 0, "tokens": 0, "cost": 0.0}

    if user_id is None:
        user_id = input("Идентификатор пользователя (user_id): ").strip()
        if not user_id:
            user_id = "anonymous"
        agent.user_id = user_id

    # Загрузка памяти существующего пользователя либо интервью нового.
    profile_repo = agent.store.profile_repo
    if not args.fresh and profile_repo.exists(user_id):
        agent.load_state(user_id)
        print(f"[Память] Пользователь «{user_id}» найден, контекст загружен. Задача: {agent.task}")
    else:
        run_interview(agent, user_id)
        # --fresh: сохранённое состояние задачи игнорируется — старт с PLANNING.
        if args.fresh:
            agent.task_state = None
            # ...и сохранённый набор инвариантов не восстанавливается (arch_den_14 §2.12).
            agent.constraints = ConstraintSet()

    # Флаг --profile: активный профиль на старте (после идентификации).
    # Несуществующий профиль → предупреждение и default (active_profile=None).
    if args.profile:
        if agent.switch_profile(args.profile):
            print(f"[Профиль] Активный профиль на старте: {args.profile}")
        else:
            print(f"[Профиль] ⚠ Профиль «{args.profile}» не найден — использую default.")

    # Применяем --deliver (набор слоёв по умолчанию).
    deliver = {part.strip() for part in args.deliver.split(",") if part.strip()}
    agent.deliver = deliver & set(DELIVERABLE)
    # D2 (Ревизия 5): при --mcp слой `tools` не должен затираться дефолтным
    # --deliver — иначе каталог не доезжает до модели. `--no-tools-block` —
    # диагностический откат (проверить поведение без блока [tools]).
    if args.mcp and not args.no_tools_block:
        agent.deliver.add("tools")
    # RAG (День 21): слой rag включается только явным флагом — без --rag набор
    # delivery и промпт байт-в-байт прежние. --no-rag-block: ищем и логируем,
    # но в промпт не подмешиваем (диагностика влияния блока).
    agent.rag_block_enabled = not args.no_rag_block
    if args.rag and agent.rag_service is not None:
        if not args.no_rag_block:
            agent.deliver.add("rag")
    # Бюджет промта: None — обрезание выключено (поведение не меняется).
    agent.prompt_budget = args.budget
    print(f"[Режим] Доставка слоёв: {sorted(agent.deliver)}")
    if args.budget is not None:
        print(f"[Режим] Бюджет промта: {args.budget} токенов "
              f"(необязательные блоки опускаются)")
    if args.mock:
        print("[Режим] MockClient (заглушка) — живых запросов к API не будет.")
    if args.rag:
        if agent.rag_service is not None:
            st = agent.rag_service.stats()
            block = "в промпт подмешивается" if (agent.rag_block_enabled
                                                 and "rag" in agent.deliver) \
                else "в промпт НЕ подмешивается (--no-rag-block)"
            print(f"[Режим] RAG: включён ({st['mode']}, топ-{agent.rag_top_k}), {block}; "
                  f"индекс: {st['n_chunks']} чанков / {st['n_docs']} документов; "
                  f"Ollama: {'доступна' if st['ollama_ready'] else 'НЕдоступна'}; "
                  f"grounding: {agent.rag_service.cfg.grounding.mode}")
        else:
            print("[Режим] RAG: ⚠ слой не собран (см. лог) — агент работает без поиска.")

    # Планировщик 24/7 (День 18): поднимаем ПОСЛЕ идентификации пользователя.
    if args.scheduler:
        setup_scheduler(agent, user_id, args.scheduler_interval)
    else:
        print("[Планировщик] Фон выключен (запустите с флагом --scheduler для 24/7).")

    print("Команды: /memory /profile [list|show|use|new|route|auto] /tasks /task [retry] "
          "/plan /approve /goto /transitions /step /run /pause /resume /deliver /compare "
          "/summary /state /tokens /cost /mcp summary|jobs|pipeline|route "
          "/rag status|on|off|ingest|find|stats|eval|check /help /exit\n")

    # Главный цикл.
    while True:
        try:
            user_input = input(f"Вы [{agent.task}]: ").strip()

            if not user_input:
                continue

            if user_input.startswith("/"):
                command = user_input.split()[0]
                if command == "/help":
                    print_help()
                    continue
                if command == "/memory":
                    ctx = MemoryContext(agent.user_id, agent.task, agent.session_id)
                    print(f"[Память]\n{agent.memory.report(ctx)}\n")
                    continue
                if command == "/profile":
                    handle_profile_command(agent, user_input)
                    continue
                if command == "/tasks":
                    tasks = agent.store.list_tasks(agent.user_id)
                    active = agent.task
                    print(f"[Задачи] Всего: {len(tasks)}; активная: {active}")
                    for t in tasks:
                        marker = "*" if t == safe_name(active) else " "
                        print(f"  {marker} {t}")
                    print()
                    continue
                if command == "/task":
                    parts = user_input.split(maxsplit=1)
                    if len(parts) < 2:
                        print("[Задача] Укажите имя: /task <имя> | /task retry\n")
                        continue
                    arg = parts[1].strip()
                    if arg == "retry":
                        # Восстановление из failed → planning (единственный выход).
                        if agent.retry_task():
                            print("[Задача] Повтор: failed → planning, шаги и результаты очищены.\n")
                        else:
                            print("[Задача] /task retry: задача не в состоянии failed.\n")
                        continue
                    agent.switch_task(arg)
                    print(f"[Задача] Переключился на «{arg}»\n")
                    continue
                if command == "/plan":
                    parts = user_input.split(maxsplit=1)
                    if len(parts) < 2 or not parts[1].strip():
                        print("[План] Укажите цель: /plan <цель задачи>\n")
                        continue
                    objective = parts[1].strip()
                    agent.start_task(objective)
                    # Первый проход: new → planning (план построен, ожидает /approve).
                    agent.step_task()
                    print_task_snapshot(agent, "План")
                    continue
                if command == "/approve":
                    print(agent.approve_plan() + "\n")
                    continue
                if command == "/goto":
                    parts = user_input.split(maxsplit=1)
                    if len(parts) < 2 or not parts[1].strip():
                        stages = ", ".join(s.value for s in TaskStage)
                        print(f"[Переход] Укажите стадию: /goto <этап>. Стадии: {stages}\n")
                        continue
                    print(agent.attempt_transition(parts[1].strip()) + "\n")
                    continue
                if command == "/transitions":
                    print(agent.transitions_report() + "\n")
                    continue
                if command == "/step":
                    if agent.task_state is None:
                        print("[Шаг] Нет активной задачи (сначала /plan <цель>)\n")
                        continue
                    agent.step_task()
                    print_task_snapshot(agent, "Шаг")
                    continue
                if command == "/run":
                    if agent.task_state is None:
                        print("[Прогон] Нет активной задачи (сначала /plan <цель>)\n")
                        continue
                    agent.run_to_end()
                    print_task_snapshot(agent, "Прогон")
                    continue
                if command == "/pause":
                    if agent.pause():
                        print_task_snapshot(agent, "Пауза")
                    continue
                if command == "/resume":
                    if agent.resume():
                        print_task_snapshot(agent, "Продолжение")
                    continue
                if command == "/deliver":
                    parts = user_input.split(maxsplit=1)
                    if len(parts) < 2:
                        print("[Доставка] Укажите слои: /deliver profile,working\n")
                        continue
                    chosen = {p.strip() for p in parts[1].split(",") if p.strip()}
                    agent.deliver = chosen & set(DELIVERABLE)
                    print(f"[Доставка] Теперь: {sorted(agent.deliver)}\n")
                    continue
                if command == "/compare":
                    compare_demonstration(agent, exchange_tracker)
                    continue
                if command == "/summary":
                    text = agent.store.read_sessions_resume(agent.user_id, agent.task)
                    print(f"[Саммари]\n{text or '(пусто)'}\n")
                    continue
                if command == "/state":
                    show_state(agent)
                    continue
                if command == "/invariants":
                    handle_invariants_command(agent, user_input)
                    continue
                if command == "/invariant":
                    handle_invariants_command(agent, user_input)
                    continue
                if command == "/check":
                    check_demonstration(agent, user_input)
                    continue
                if command == "/tokens":
                    print(f"[Токены] Обменов: {exchange_tracker['n']} | "
                          f"Всего вх. оценка: {exchange_tracker['tokens']} | "
                          f"Последний запрос: см. CSV {os.path.basename(TOKEN_LOG)}\n")
                    continue
                if command == "/cost":
                    print(f"[Стоимость] Оценка сессии (вход): {exchange_tracker['cost']:.6f} ₽ "
                          f"(вход {args.price_in} ₽/1M, выход {args.price_out} ₽/1M)\n")
                    continue
                if command == "/mcp":
                    handle_mcp_command(agent, user_input)
                    continue
                if command == "/rag":
                    handle_rag_command(agent, user_input)
                    continue
                if command == "/exit":
                    stop_scheduler(agent)
                    agent.save_state()
                    print("[Выход] Состояние сохранено. До встречи!")
                    break
                print(f"[Команда] Неизвестная команда: {command}. См. /help\n")
                continue

            # Обычное сообщение → полный цикл агента.
            answer = agent.respond(user_input)
            if answer is None:
                print("[API] Ответ не получен.\n")
                continue

            # Токен-учёт: локальная оценка собранного запроса последнего обмена.
            last_ctx = agent.build_context(user_input)
            last_messages = agent.prompts.build(last_ctx, agent.deliver)
            prompt_tokens = estimate_messages_tokens(last_messages)
            # Grounding (этап 9): авто-перегенерация — дополнительный обмен, его
            # оценка добавляется к сессии (multi-query на этапе 10 — так же).
            prompt_tokens += getattr(agent, "last_grounding_extra_tokens", 0)
            exchange_tracker["n"] += 1
            exchange_tracker["tokens"] += prompt_tokens
            exchange_cost = (prompt_tokens * args.price_in) / 1_000_000
            exchange_tracker["cost"] += exchange_cost
            append_token_log(exchange_tracker["n"], prompt_tokens, exchange_cost)

            print(f"Агент: {answer}\n")

            # Источники/цитаты ответа (часть 3, этап 10): при активном RAG ответ
            # обязан нести источники (source + section/chunk_id) и цитаты.
            _print_answer_sources(agent)

        except EOFError:
            stop_scheduler(agent)
            agent.save_state()
            print("\n[Выход] Ввод завершён (EOF)")
            break
        except KeyboardInterrupt:
            stop_scheduler(agent)
            agent.save_state()
            print("\n[Выход] Прервано пользователем")
            break
        except Exception as error:
            log_line(f"[Ошибка] {type(error).__name__}: {error}")
            print(f"[Ошибка] {error}\n")


if __name__ == "__main__":
    main()