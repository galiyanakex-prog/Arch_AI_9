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
from core.model_registry import ModelRegistry
from core.prompt_builder import PromptBuilder, DELIVERABLE
from core.agent import Agent, StubExecutor
from core.state_machine import TaskStage, ALLOWED_TRANSITIONS
from core.invariants import Invariant, ConstraintSet

# 2. Окружение и ключ --------------------------------------------------------
load_dotenv()
api_key = os.getenv("API_KEY")

# Кодировки stdin/stdout: errors="replace" — битые байты заменяются заглушкой,
# а не роняют программу (урок дня 10). Под pytest stdin/stdout подменяются
# объектами без reconfigure — проверяем наличие метода.
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stdout, "reconfigure"):
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
parser.add_argument("--model", type=str, default=None, metavar="ID",
                    help="Модель/сервис для сессии из models.json (по умолчанию облако).")
parser.add_argument("--model-list", action="store_true",
                    help="One-shot: напечатать реестр моделей и выйти.")
parser.add_argument("--model-profile", type=str, default=None, metavar="NAME",
                    help="Профиль параметров модели (default / rag-strict / fast).")
parser.add_argument("--oneshot", type=str, default=None, metavar="ЗАДАЧА",
                    help="One-shot: один обмен → ответ → выход (субагенты, фасад).")
parser.add_argument("--subagent-run", type=str, default=None, metavar="ЗАДАЧА",
                    help="One-shot: запустить субагента на локальной LLM и выйти.")
parser.add_argument("--subagent-service", type=str, default="lmstudio",
                    choices=("lmstudio", "ollama"),
                    help="Сервис для субагента (по умолчанию lmstudio).")
parser.add_argument("--local-only", action="store_true",
                    help="Запрет облачных моделей в этой сессии (и для субагентов).")
parser.add_argument("--local-gen", action="store_true",
                    help="RAG: переключить модель агента на локальную "
                         "(=> генератор RAG локальный; секции generation нет).")
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
parser.add_argument("--rag-gen-compare", action="store_true",
                    help="One-shot: сравнить локальную и облачную генерацию RAG (этап 6).")
parser.add_argument("--gen-modes", type=str, default="cloud,local",
                    help="Генераторы для --rag-gen-compare (cloud,local).")
parser.add_argument("--repeat", type=int, default=1,
                    help="Повторов на вопрос для --rag-gen-compare (ось стабильности).")
parser.add_argument("--gen-questions", type=int, default=10,
                    help="Число контрольных вопросов для --rag-gen-compare (этап 8).")
parser.add_argument("--gen-resources", action="store_true",
                    help="С --rag-gen-compare: снимать ресурсы (RSS/CPU/RAM) вокруг "
                         "прогона каждого локального генератора (этап 8).")
parser.add_argument("--gen-report", type=str, default=None, metavar="FILE",
                    help="Путь отчёта --rag-gen-compare (по умолчанию stages/rag_local_compare.md).")
parser.add_argument("--gen-profile", type=str, default=None, metavar="NAME",
                    help="Профиль параметров генератора RAG (default/rag-strict/fast) "
                         "для --rag-gen-compare (этап 7).")
parser.add_argument("--local-template", action="store_true",
                    help="С --rag-gen-compare: строгий prompt-шаблон [rag] для "
                         "локального генератора (часть 4, этап 7).")
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
parser.add_argument("--embed-provider", type=str, default=None,
                    choices=("ollama", "lmstudio", "hashing", "fake"),
                    help="Провайдер эмбеддингов RAG (роль «эмбеддинг»; не захардкожен).")
parser.add_argument("--embed-model", type=str, default=None, metavar="NAME",
                    help="Модель эмбеддингов (напр. bge-m3). Смена dim требует ребилда индекса.")
parser.add_argument("--embed-url", type=str, default=None, metavar="URL",
                    help="URL сервиса эмбеддингов (только localhost).")
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
# Реестр моделей (Ревизия 8): секретов не содержит, лежит рядом с кодом.
MODELS_PATH = os.path.join(BASE_DIR, "models.json")

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
def append_token_log(exchange, prompt_tokens, cost_rubles, model=None):
    """Дозаписывает строку обмена в CSV. Ошибка записи не роняет чат.

    Колонка `model` (Ревизия 8, этап 3) — видимость модели в журнале. Старые
    строки не переписываем: если файл уже существует без колонки, дописываем
    строку с прежним набором полей (совместимость).
    """
    try:
        is_new = not os.path.exists(TOKEN_LOG)
        with open(TOKEN_LOG, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow(["exchange", "timestamp", "prompt_tokens",
                                 "cost_rubles", "cost_total_rubles", "model"])
            row = [exchange, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   prompt_tokens, f"{cost_rubles:.6f}", f"{cost_rubles * exchange:.6f}"]
            if model is not None:
                row.append(model)
            writer.writerow(row)
    except OSError:
        pass


# 8. Композиция объектов (DI) ---------------------------------------------------
def build_agent(user_id=None, mock=False, mcp_enabled=False, scheduler_enabled=False,
                scheduler_interval=60.0, rag_enabled=False, rag_config=None,
                model_id=None):
    """Собирает Store + профиль-репозиторий + слои + LLM-клиент в Agent.

    MCP-слой опционален (mcp_enabled=False по умолчанию — поведение = den_15):
    gateway → provider → ToolRegistry; каталог сохраняется через Store.
    Планировщик (День 18, scheduler_enabled) — фоновый worker 24/7, независимый
    от LLM; по умолчанию не поднимается.
    RAG-слой (День 21, rag_enabled) — фасад RagService; по умолчанию выключен.
    Модель (Ревизия 8, model_id) — выбор через ModelRegistry; без него поведение
    прежних ревизий (облако / MockClient) не меняется.
    """
    store = Store(MEMORY_ROOT, log=log_line)
    repo = ProfileRepository(os.path.join(MEMORY_ROOT, "profiles.db"), log=log_line)
    store.profile_repo = repo

    memory = MemoryManager(default_layers(store, log=log_line), log=log_line)
    builder = PromptBuilder(SYSTEM_PROMPT)

    # Реестр моделей (Ревизия 8): единая точка выбора клиента. Без model_id и без
    # --mock поведение прежних ревизий сохраняется (облако / MockClient).
    registry = ModelRegistry(MODELS_PATH, log=log_line)
    if user_id:
        registry.load_state(store.user_dir(user_id))
    if model_id:
        registry.use(model_id, user_dir=store.user_dir(user_id) if user_id else None)

    if mock or api_key is None or api_key == "test-key":
        client = MockClient(name="Mock")
        # В тестовом режиме план/шаги детерминированы (без сети): StubExecutor.
        executor = StubExecutor()
        model_label = "mock/Mock"
    else:
        spec = registry.current()
        client = registry.build(spec)
        executor = None  # Agent построит LLMExecutor по умолчанию
        model_label = spec.display()

    agent = Agent(client, memory, builder, store, user_id=user_id,
                  default_task="Основная_задача", log=log_line, executor=executor)
    agent.set_model(client, label=model_label)
    agent.model_registry = registry
    # Шаблон блока [rag] по локальности модели (часть 4, этап 7): для облака — None.
    _apply_local_rag_template(agent)

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
            # Генератор RAG = текущая модель агента (уточнение куратора 2026-10-12):
            # отдельной секции generation нет, поэтому генератор — тот же client.
            service = _make_rag_service(cfg, llm=client.complete)
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
    # Эмбеддер (роль «эмбеддинг», уточнение куратора 2026-10-12): провайдер/модель
    # переключаемы, не захардкожены. Приоритет: флаги CLI > config.json > env.
    emb_patch = {}
    if getattr(cli_args, "embed_provider", None):
        emb_patch["provider"] = cli_args.embed_provider
    if getattr(cli_args, "embed_model", None):
        emb_patch["model"] = cli_args.embed_model
    if getattr(cli_args, "embed_url", None):
        emb_patch["url"] = cli_args.embed_url
    if emb_patch:
        patch["embedding"] = dataclasses.replace(cfg.embedding, **emb_patch)
    # Генератора в конфиге нет (уточнение куратора 2026-10-12): генератор RAG =
    # текущая модель агента (реестр + /model). `--local-gen` переключает модель.
    if patch:
        cfg = dataclasses.replace(cfg, **patch)

    # Относительные пути конфига — от BASE_DIR (индекс и corpus.list).
    cfg = dataclasses.replace(
        cfg,
        index_dir=_abs_path(cfg.index_dir),
        corpus=dataclasses.replace(cfg.corpus, list_file=_abs_path(cfg.corpus.list_file)),
    )
    return cfg.validate()


def _make_rag_service(cfg, llm=None):
    """Фасад RagService поверх конфига (единственная точка входа ядра в rag/).

    `llm` — callable(messages)->str (генератор RAG, этап 5); None → заглушка.
    """
    from rag.service import RagService
    return RagService(cfg, log=log_line, llm=llm)


def _local_rag_renderer():
    """callable(hits, query)->str — строгий шаблон блока [rag] для локальных моделей.

    Часть 4 (этап 7): шаблон живёт в core/prompt_builder.py; в rag/ уходит как DI
    (граница §5 — rag/ не импортирует core/). Возвращает None, если шаблон
    недоступен (деградация к общему блоку).
    """
    try:
        from core.prompt_builder import render_local_rag_template
    except Exception:
        return None
    return lambda hits, query="": render_local_rag_template(hits, query=query)


def _apply_local_rag_template(agent: Agent) -> None:
    """Включить строгий шаблон [rag] ТОЛЬКО для локальной модели (часть 4, этап 7).

    Облачный промпт остаётся байт-в-байт прежним: для облака renderer = None.
    Вызывается после каждого переключения модели (старт, /model use, /gen, флаги).
    """
    registry = getattr(agent, "model_registry", None)
    if registry is None:
        agent.rag_block_renderer = None
        return
    try:
        is_local = registry.current().local
    except Exception:
        is_local = False
    agent.rag_block_renderer = _local_rag_renderer() if is_local else None


def _build_gen_client(mock=False, model_id=None, profile=None):
    """LLMClient-генератор RAG = текущая модель агента (уточнение куратора 2026-10-12).

    Отдельного «RAG-генератора» нет: RAG — две роли (эмбеддинг + генератор), и
    генератор — это модель агента (`models.json → current` + `/model`). Возвращает
    (client, label) либо (None, None) (облако без ключа — заглушка). `model_id` /
    `profile` — разовое переопределение (для сравнения генераторов, `--model`).
    """
    if mock:
        from core.llm_client import MockClient
        return MockClient(), "mock"
    registry = ModelRegistry(MODELS_PATH, log=log_line)
    if model_id:
        spec = registry.get(model_id)
    else:
        spec = registry.current()
    if profile:
        spec = dataclasses.replace(spec, profile=profile)
    if spec.service == "cloud":
        api_key = os.getenv("API_KEY")
        if not api_key or api_key == "test-key":
            return None, None
    return registry.build(spec), spec.display()


def _build_gen_llm(mock=False, model_id=None, profile=None):
    """callable(messages)->str для RagService (обёртка над _build_gen_client)."""
    client, _ = _build_gen_client(mock=mock, model_id=model_id, profile=profile)
    return client.complete if client is not None else None


def _default_model_id(service: str):
    """Первый chat-спек сервиса из реестра (для сравнения генераторов: cloud/local)."""
    registry = ModelRegistry(MODELS_PATH, log=log_line)
    spec = next((s for s in registry.list(role="chat") if s.service == service), None)
    return spec.id if spec is not None else None


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
    """LLM для one-shot ответа RAG = текущая модель агента (уточнение куратора).

    Отдельной секции `generation` нет: генератор RAG — это модель агента
    (`models.json → current` + `/model`). `--model <id>` разово переопределяет её
    для one-shot. --mock → MockClient; cloud без ключа → None (заглушка).
    """
    try:
        return _build_gen_llm(mock=getattr(cli_args, "mock", False),
                              model_id=getattr(cli_args, "model", None))
    except Exception as error:
        print(f"[RAG] генератор не собран ({type(error).__name__}: {error}) — заглушка",
              file=sys.stderr)
        return None


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


def run_rag_gen_compare(cli_args) -> int:
    """One-shot: сравнить локальную и облачную генерацию RAG (этап 6, G2).

    Один датасет, один retrieval, различается только генератор. Клиентов строит
    Kod.py (граница §5: rag/ не импортирует core/). Отчёт — три оси + вердикт.
    """
    from rag.compare import compare_generators, render_generator_report

    cfg = _build_rag_config(cli_args)
    service = _make_rag_service(cfg)
    if not service.stats().get("n_chunks"):
        print("[RAG] Индекс пуст — сначала: python Kod.py --rag-ingest", file=sys.stderr)
        return 1
    modes = [m.strip() for m in cli_args.gen_modes.split(",") if m.strip()]
    # Профиль параметров генератора (этап 7): --gen-profile переопределяет профиль
    # модели (None → профиль самой модели из реестра).
    gen_profile = getattr(cli_args, "gen_profile", None)
    registry = ModelRegistry(MODELS_PATH, log=log_line)
    generators = {}
    for mode in modes:
        if mode == "cloud":
            client, _ = _build_gen_client(mock=cli_args.mock,
                                          model_id=_default_model_id("cloud"),
                                          profile=gen_profile)
        elif mode == "local":
            client, _ = _build_gen_client(mock=cli_args.mock,
                                          model_id=_default_model_id("lmstudio"),
                                          profile=gen_profile)
        elif mode in registry.models:
            # Ось модели (этап 8): генератор задан id модели из реестра.
            client, _ = _build_gen_client(mock=cli_args.mock, model_id=mode,
                                          profile=gen_profile)
        else:
            print(f"[RAG] Неизвестный генератор «{mode}» (cloud|local|id модели).",
                  file=sys.stderr)
            return 2
        if client is None:
            print(f"[RAG] Генератор «{mode}» недоступен (нет ключа/сервиса) — пропуск.",
                  file=sys.stderr)
            continue
        generators[mode] = client.complete
    if not generators:
        print("[RAG] Ни один генератор не собран — сравнение невозможно.", file=sys.stderr)
        return 1
    # Строгий шаблон [rag] для локальных генераторов (часть 4, этап 7).
    block_renderers = {}
    if getattr(cli_args, "local_template", False):
        renderer = _local_rag_renderer()
        if renderer is not None:
            for name in generators:
                if name == "cloud":
                    continue
                block_renderers[name] = renderer
    dataset = os.path.join(BASE_DIR, "rag", "datasets", "queries.jsonl")
    n_questions = getattr(cli_args, "gen_questions", 10) or 10
    queries = [q for q in _load_queries(dataset)
               if q.get("id", "").startswith("c")][:n_questions]
    print(f"[RAG] Сравнение генераторов {list(generators)} на {len(queries)} вопросах, "
          f"повторов={cli_args.repeat}. Локальная генерация на CPU — это долго.")
    if block_renderers:
        print(f"[RAG] Строгий шаблон [rag] применён к: {list(block_renderers)}.")
    # Снятие ресурсов вокруг прогона каждого локального генератора (этап 8).
    resource_hooks = {}
    if getattr(cli_args, "gen_resources", False):
        from core.resources import ResourceSampler
        for name in generators:
            if name == "cloud":
                continue
            hint = ""
            if name in registry.models:
                hint = registry.get(name).model.split("/")[-1].split(":")[0]
            sampler = ResourceSampler(interval=5.0, model_hint=hint)

            def _stop(s=sampler):
                s.stop()
                return s.summary()

            resource_hooks[name] = {"start": sampler.start, "stop": _stop}
        if resource_hooks:
            print(f"[RAG] Снятие ресурсов включено для: {list(resource_hooks)}.")
    result = compare_generators(cfg, queries, generators, k=cfg.retrieval.final_k,
                                repeat=cli_args.repeat, block_renderers=block_renderers,
                                resource_hooks=resource_hooks)
    # Заголовок отчёта: этап 7/8 (оптимизация) — если задан профиль/строгий шаблон.
    if gen_profile or block_renderers:
        title = ("# Оптимизация генерации RAG: замер «до/после» (этап 7/8, P1/P2)\n\n"
                 f"Профиль: `{gen_profile or 'default'}` · локальный шаблон [rag]: "
                 f"{'да' if block_renderers else 'нет'}")
    else:
        title = None
    text = render_generator_report(result, title=title)
    report_path = cli_args.gen_report or os.path.join(
        BASE_DIR, "dev", "logs_reports", "stages", "rag_local_compare.md")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(text)
    print(f"\n[RAG] Отчёт записан: {report_path}")
    return 0


def _ensure_rag_service(agent: Agent):
    """Собрать RagService в рантайме (RAG включили в чате без флага --rag).

    Генератор RAG = текущая модель агента (уточнение куратора 2026-10-12):
    берём `agent.llm.complete`. Граница §5: rag/ не импортирует core/.
    """
    cfg = _build_rag_config(args)
    agent.rag_service = _make_rag_service(cfg, llm=agent.llm.complete)
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


# 9.0 One-shot обмен (Ревизия 8, этап 4): один запрос → ответ → выход ------------
def run_oneshot(agent: Agent, user_id: str, task: str) -> int:
    """Один обмен без REPL: используется субагентами и фасадом (этап 9).

    Новый пользователь инициализируется без интервью (неинтерактивно). Ответ
    печатается с подписью модели; код выхода 0 — ответ получен, 1 — нет.
    """
    profile_repo = agent.store.profile_repo
    if not profile_repo.exists(user_id):
        agent.initialize_user(user_id, name=user_id, answers={})
    else:
        agent.load_state(user_id)
    print(model_banner(agent))
    answer = agent.respond(task)
    if answer is None:
        print("[API] Ответ не получен.")
        return 1
    print(f"[{agent.model_label()}] Агент: {answer}")
    return 0


# 9.1 Модель/сервис (Ревизия 8, этап 3): отображение и команда /model ------------
def model_banner(agent: Agent) -> str:
    """Баннер сессии: единая подпись модели (сервис/модель, локальность, квант)."""
    registry = getattr(agent, "model_registry", None)
    if registry is None:
        return f"[Сессия] модель: {agent.model_label()}"
    spec = registry.current()
    where = "локально" if spec.local else "облако"
    quant = f", {spec.quant}" if spec.quant else ""
    return (f"[Сессия] модель: {spec.display()} "
            f"({where}{quant}, ctx {spec.context_window}, профиль {spec.profile})")


def print_model_list(agent: Agent):
    """Печать реестра моделей с отметкой текущей (токенов LLM не тратит)."""
    registry = getattr(agent, "model_registry", None)
    if registry is None:
        print("[Модель] Реестр недоступен.\n")
        return
    current = registry.current_id
    print(f"[Модели] Всего: {len(registry.list())}; текущая: {current}")
    for spec in registry.list():
        marker = "*" if spec.id == current else " "
        where = "local" if spec.local else "cloud"
        role = "" if spec.role == "chat" else f" [{spec.role}]"
        print(f"  {marker} {spec.id}  ({where}{role})")
    print()


def handle_model_command(agent: Agent, user_input: str):
    """Диспетчер /model: current | list | use <id> | status | profile <name>."""
    registry = getattr(agent, "model_registry", None)
    if registry is None:
        print("[Модель] Реестр недоступен.\n")
        return
    parts = user_input.split()
    sub = parts[1] if len(parts) > 1 else "current"

    if sub in ("current", ""):
        info = registry.describe(registry.current_id)
        print(f"[Модель] {info['label']}")
        print(f"  сервис: {info['service']} | {'локальная' if info['local'] else 'облачная'}"
              f" | роль: {info['role']}")
        if info["quant"]:
            print(f"  квант: {info['quant']} | окно: {info['context_window']}")
        print(f"  профиль: {info['profile']} | параметры: {info['params']}\n")
        return

    if sub == "list":
        print_model_list(agent)
        return

    if sub == "use":
        if len(parts) < 3:
            print("[Модель] Укажите id: /model use <id> (см. /model list)\n")
            return
        model_id = parts[2]
        try:
            spec = registry.get(model_id)
        except KeyError as error:
            print(f"[Модель] ⚠ {error}\n")
            return
        # Проверка доступности сервиса (кроме mock/cloud) — не переключаемся вслепую.
        if spec.service in ("lmstudio", "ollama"):
            probe = registry.probe(model_id)
            if not probe.get("ok"):
                print(f"[Модель] ⚠ Сервис «{spec.service}» недоступен "
                      f"({probe.get('error', 'нет ответа')}) — прежняя модель сохранена.\n")
                return
        client = registry.build(spec)
        registry.use(model_id, user_dir=agent.store.user_dir(agent.user_id)
                     if agent.user_id else None)
        agent.set_model(client, label=spec.display())
        _apply_local_rag_template(agent)
        print(f"[Модель] Переключено: {spec.display()}")
        print(model_banner(agent) + "\n")
        return

    if sub == "status":
        for spec in registry.list():
            if spec.service in ("lmstudio", "ollama"):
                probe = registry.probe(spec.id)
                state = "доступна" if probe.get("ok") else "НЕдоступна"
                print(f"  {spec.id}: {state} ({probe.get('latency_ms', '?')} мс, "
                      f"{probe.get('version', '')})")
        print()
        return

    if sub == "profile":
        if len(parts) < 3:
            print(f"[Модель] Профили: {', '.join(registry.profiles)}\n")
            return
        name = parts[2]
        if name not in registry.profiles:
            print(f"[Модель] ⚠ Профиль «{name}» не найден. "
                  f"Доступны: {', '.join(registry.profiles)}\n")
            return
        spec = registry.current()
        spec.profile = name
        client = registry.build(spec)
        agent.set_model(client, label=spec.display())
        _apply_local_rag_template(agent)
        print(f"[Модель] Профиль «{name}» применён к {spec.display()}\n")
        return

    print(f"[Модель] Неизвестная подкоманда: {sub}. "
          f"См. /model [current|list|use|status|profile]\n")


# 9.2 Субагенты (Ревизия 8, этап 4): дочерние CLI-сессии на локальной LLM --------
def _get_subagent_runner(agent: Agent):
    """Ленивая сборка SubagentRunner (реестр берётся из агента)."""
    from core.subagents import SubagentRunner
    runner = getattr(agent, "subagent_runner", None)
    if runner is None:
        registry = getattr(agent, "model_registry", None)
        runner = SubagentRunner(BASE_DIR, registry=registry, log=log_line)
        agent.subagent_runner = runner
    return runner


def run_subagent(agent: Agent, task: str, service: str = "lmstudio",
                 model: str = None, wait: bool = True):
    """Запускает субагента и печатает сводку. Не трогает TaskStage основной задачи."""
    from core.subagents import SubagentError
    runner = _get_subagent_runner(agent)
    try:
        result = runner.run(task, service=service, model=model, wait=wait)
    except SubagentError as error:
        print(f"[Субагент] ⚠ {error}\n")
        return None
    print(f"[Субагент] id={result['id']}, сервис={result['service']}, "
          f"модель={result['model']}, pid={result['pid']}")
    if wait:
        print(f"[Субагент] статус={result['status']} ({result['duration']} с), "
              f"лог: {result['log']}")
        if result["output"].strip():
            print(result["output"].strip())
    else:
        print(f"[Субагент] запущен в фоне; лог: {result['log']}")
    print()
    return result


def handle_subagent_command(agent: Agent, user_input: str):
    """Диспетчер /subagent: run <задача> [--service …] [--model …] | list | log <id>."""
    parts = user_input.split()
    sub = parts[1] if len(parts) > 1 else "list"

    if sub == "list":
        runner = _get_subagent_runner(agent)
        active = runner.list_active()
        print(f"[Субагенты] Активных: {len(active)}; завершённых: {len(runner.history)}")
        for item in active:
            print(f"  * {item['id']} (pid {item['pid']})")
        for item in runner.history[-5:]:
            print(f"    {item['id']} | {item['status']} | {item['model']} | {item['log']}")
        print()
        return

    if sub == "log":
        if len(parts) < 3:
            print("[Субагент] Укажите id: /subagent log <id>\n")
            return
        runner = _get_subagent_runner(agent)
        target = next((h for h in runner.history if h["id"] == parts[2]), None)
        if target is None:
            print(f"[Субагент] id «{parts[2]}» не найден.\n")
            return
        try:
            with open(target["log"], "r", encoding="utf-8") as handle:
                print(handle.read())
        except OSError as error:
            print(f"[Субагент] ⚠ Не удалось прочитать лог: {error}\n")
        return

    if sub == "run":
        rest = user_input.split(maxsplit=2)
        if len(rest) < 3 or not rest[2].strip():
            print("[Субагент] Укажите задачу: /subagent run <задача> "
                  "[--service ollama|lmstudio] [--model <id>] [--async]\n")
            return
        tail = rest[2].strip()
        service = "lmstudio"
        model = None
        wait = True
        tokens = tail.split()
        task_words = []
        i = 0
        while i < len(tokens):
            if tokens[i] == "--service" and i + 1 < len(tokens):
                service = tokens[i + 1]
                i += 2
            elif tokens[i] == "--model" and i + 1 < len(tokens):
                model = tokens[i + 1]
                i += 2
            elif tokens[i] == "--async":
                wait = False
                i += 1
            elif tokens[i] == "--wait":
                wait = True
                i += 1
            else:
                task_words.append(tokens[i])
                i += 1
        task = " ".join(task_words).strip()
        if not task:
            print("[Субагент] Пустая задача.\n")
            return
        run_subagent(agent, task, service=service, model=model, wait=wait)
        return

    print(f"[Субагент] Неизвестная подкоманда: {sub}. "
          f"См. /subagent [run|list|log]\n")


# 9.3 Генератор RAG (Ревизия 8, этап 5; уточнение куратора 2026-10-12) ---------
# Генератор RAG = текущая модель агента. `/gen local|cloud` — удобный алиас над
# `/model use` (переключает модель агента => и RAG-генератор). Отдельного выбора
# генератора и секции `generation` в конфиге нет.
def handle_gen_command(agent: Agent, user_input: str):
    """Диспетчер /gen: status | local | cloud — кто генерирует ответ RAG."""
    parts = user_input.split()
    sub = parts[1] if len(parts) > 1 else "status"

    if sub == "status":
        registry = getattr(agent, "model_registry", None)
        label = agent.model_label()
        print(f"[Генератор] RAG отвечает моделью агента: {label}")
        if registry is not None:
            info = registry.describe(registry.current_id)
            print(f"  сервис: {info['service']} | "
                  f"{'локальная' if info['local'] else 'облачная'} | "
                  f"профиль: {info['profile']}")
        service = agent.rag_service
        state = "есть" if (service is not None and service.llm is not None) else "нет (заглушка)"
        print(f"  LLM-инжект в RAG: {state}\n")
        return

    if sub in ("local", "cloud"):
        registry = getattr(agent, "model_registry", None)
        if registry is None:
            registry = ModelRegistry(MODELS_PATH, log=log_line)
            agent.model_registry = registry
        # Выбираем подходящий спек: cloud — облако; local — первая локальная chat-модель.
        if sub == "cloud":
            spec = next((s for s in registry.list(role="chat") if not s.local), None)
        else:
            spec = next((s for s in registry.list(role="chat") if s.local), None)
        if spec is None:
            print(f"[Генератор] ⚠ Нет chat-модели для «{sub}» в реестре.\n")
            return
        if spec.service in ("lmstudio", "ollama"):
            probe = registry.probe(spec.id)
            if not probe.get("ok"):
                print(f"[Генератор] ⚠ Сервис «{spec.service}» недоступен "
                      f"({probe.get('error', 'нет ответа')}) — прежняя модель сохранена.\n")
                return
        client = registry.build(spec)
        registry.use(spec.id, user_dir=agent.store.user_dir(agent.user_id)
                     if agent.user_id else None)
        # Одна точка (agent.set_model): и agent.llm, и rag_service.llm — без расхождений.
        agent.set_model(client, label=spec.display())
        _apply_local_rag_template(agent)
        print(f"[Генератор] RAG переключён на «{spec.display()}» "
              f"({'локально' if spec.local else 'облако'}).\n")
        return

    print(f"[Генератор] Неизвестная подкоманда: {sub}. См. /gen [status|local|cloud]\n")


# 9.4 Эмбеддер RAG (уточнение куратора 2026-10-12): /embed status|use -----------------
# Роль «эмбеддинг» не захардкожена: провайдер/модель переключаемы. Смена модели
# или размерности (dim) НЕсовместима с текущим индексом → нужен ребилд
# (`python Kod.py --rag-ingest`) — команда об этом предупреждает.
_EMBED_PROVIDERS = {
    "ollama": {"url": "http://127.0.0.1:11434", "model": "bge-m3", "dim": 1024},
    "lmstudio": {"url": "http://127.0.0.1:1234",
                 "model": "text-embedding-nomic-embed-text-v1.5", "dim": 768},
    "hashing": {"url": "http://127.0.0.1", "model": "hashing", "dim": 256},
}


def handle_embed_command(agent: Agent, user_input: str):
    """Диспетчер /embed: status | use <provider>[:<model>] — эмбеддер RAG."""
    parts = user_input.split()
    sub = parts[1] if len(parts) > 1 else "status"

    def _current():
        # Живой сервис приоритетнее файла: /embed use меняет эмбеддер в рантайме.
        svc = getattr(agent, "rag_service", None)
        svc_cfg = getattr(svc, "cfg", None) if svc is not None else None
        if svc_cfg is not None:
            return svc_cfg.embedding, svc_cfg
        cfg = _build_rag_config(args)
        return cfg.embedding, cfg

    if sub == "status":
        emb, _ = _current()
        index = getattr(agent, "rag_service", None)
        index_dim = index.stats().get("dim") if index is not None else None
        index_model = index.stats().get("model_id") if index is not None else None
        print(f"[Эмбеддер] Провайдер: {emb.provider} | модель: {emb.model} | "
              f"dim: {emb.dim} | url: {emb.url}")
        if index_dim is not None:
            # index.model_id вида "ollama:bge-m3" — сравниваем по имени модели.
            index_name = (index_model or "").split(":", 1)[-1]
            mismatch = (index_dim != emb.dim) or (index_name and index_name != emb.model)
            note = " ⚠ индекс несовместим — нужен ребилд (--rag-ingest)" if mismatch else " ✓"
            print(f"  Индекс: dim={index_dim}, модель={index_model or '—'}{note}")
        print()
        return

    if sub == "use":
        if len(parts) < 3:
            print("[Эмбеддер] Укажите провайдера: /embed use <provider>[:<model>] "
                  f"(доступно: {', '.join(_EMBED_PROVIDERS)})\n")
            return
        token = parts[2]
        provider, _, model = token.partition(":")
        defaults = _EMBED_PROVIDERS.get(provider)
        if defaults is None:
            print(f"[Эмбеддер] ⚠ Неизвестный провайдер «{provider}». "
                  f"Доступно: {', '.join(_EMBED_PROVIDERS)}\n")
            return
        url = defaults["url"]
        dim = defaults["dim"]
        # Реестр моделей знает embedding-спеки — берём dim/url оттуда, если есть.
        registry = getattr(agent, "model_registry", None)
        if registry is not None:
            spec = next((s for s in registry.list(role="embedding")
                         if s.service == provider), None)
            if spec is not None and not model:
                model = spec.model.split(":")[0]
                url = spec.base_url or url
        model = model or defaults["model"]
        if len(parts) > 3:
            model = parts[3]
        # Проба: живой сервис проверяем до переключения (кроме hashing/fake).
        if provider in ("ollama", "lmstudio"):
            ok, detail = _probe_embed_provider(provider, url, model)
            if not ok:
                print(f"[Эмбеддер] ⚠ Сервис «{provider}» недоступен ({detail}) — "
                      "прежний эмбеддер сохранён.\n")
                return
        _rebuild_service_with_embedding(agent, provider, model, url, dim)
        print(f"[Эмбеддер] Переключено: {provider}:{model} (dim={dim}).")
        print("  Внимание: индекс построен под прежнюю модель — для поиска по новой "
              "модели пересоберите индекс: python Kod.py --rag-ingest\n")
        return

    print(f"[Эмбеддер] Неизвестная подкоманда: {sub}. См. /embed [status|use]\n")


def _probe_embed_provider(provider: str, url: str, model: str):
    """Доступность embedding-сервиса (только localhost). → (ok, detail)."""
    import json
    import urllib.error
    import urllib.request
    try:
        if provider == "ollama":
            with urllib.request.urlopen(f"{url.rstrip('/')}/api/tags", timeout=3) as resp:
                json.load(resp)
            return True, "ok"
        # lmstudio (OpenAI-совместимо): пробуем реальный эмбеддинг.
        data = json.dumps({"model": model, "input": ["ping"]}).encode("utf-8")
        request = urllib.request.Request(
            f"{url.rstrip('/')}/v1/embeddings", data=data,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as resp:
            json.load(resp)
        return True, "ok"
    except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
        return False, f"{type(error).__name__}: {error}"


def _rebuild_service_with_embedding(agent: Agent, provider: str, model: str,
                                    url: str, dim: int):
    """Пересобрать RagService с новым эмбеддером (индекс грузится лениво)."""
    cfg = _build_rag_config(args)
    emb = dataclasses.replace(cfg.embedding, provider=provider, model=model,
                              url=url, dim=dim)
    cfg = dataclasses.replace(cfg, embedding=emb)
    # Эмбеддер сменился → сбрасываем кэш эмбеддера/ретривера у активного сервиса.
    llm = agent.llm.complete if agent.llm is not None else None
    agent.rag_service = _make_rag_service(cfg, llm=llm)
    agent.rag_top_k = cfg.retrieval.final_k
    agent.rag_mode = cfg.retrieval.mode


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
    print("  /model               — текущая модель/сервис (профиль, параметры, окно)")
    print("  /model list          — все модели реестра + отметка текущей")
    print("  /model use <id>      — переключить модель/сервис в сессии")
    print("  /model status        — живой health-check сервисов (latency, версия)")
    print("  /model profile <name> — применить профиль параметров (default/rag-strict/fast)")
    print("  /subagent run <задача> [--service ollama|lmstudio] [--model <id>] [--async]")
    print("                       — поднять вспомогательную CLI-сессию на локальной LLM")
    print("  /subagent list       — активные/завершённые субагенты и их логи")
    print("  /subagent log <id>   — показать лог субагента (с его подписью модели)")
    print("  /gen [status]        — кто генерирует ответ RAG (= текущая модель агента)")
    print("  /gen local|cloud     — алиас: переключить модель агента (=> генератор RAG)")
    print("  /embed [status]      — провайдер/модель эмбеддингов RAG (роль «эмбеддинг»)")
    print("  /embed use <p>[:<m>] — переключить эмбеддер (ollama|lmstudio|hashing)")
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

    # One-shot: печать реестра моделей и выход (токенов LLM не тратит).
    if args.model_list:
        registry = ModelRegistry(MODELS_PATH, log=log_line)
        print(f"[Модели] Всего: {len(registry.list())}; текущая: {registry.current_id}")
        for spec in registry.list():
            marker = "*" if spec.id == registry.current_id else " "
            where = "local" if spec.local else "cloud"
            role = "" if spec.role == "chat" else f" [{spec.role}]"
            print(f"  {marker} {spec.id}  ({where}{role})")
        sys.exit(0)

    # One-shot: запустить субагента на локальной LLM и выйти (Ревизия 8, этап 4).
    if args.subagent_run is not None:
        from core.subagents import SubagentRunner, SubagentError
        registry = ModelRegistry(MODELS_PATH, log=log_line)
        runner = SubagentRunner(BASE_DIR, registry=registry, log=log_line)
        try:
            result = runner.run(args.subagent_run, service=args.subagent_service)
        except SubagentError as error:
            print(f"[Субагент] ⚠ {error}")
            sys.exit(2)
        print(f"[Субагент] id={result['id']} сервис={result['service']} "
              f"модель={result['model']} pid={result['pid']}")
        print(f"[Субагент] статус={result['status']} ({result['duration']} с), "
              f"лог: {result['log']}")
        print(result["output"].strip())
        sys.exit(0 if result["status"] == "ok" else 1)

    # One-shot прогоны RAG (День 21): индексация / поиск / метрики / сравнение.
    # REPL не запускается, LLM не тратится. Заданные прогоны идут по порядку
    # (индексация раньше метрик), код выхода — худший из кодов прогонов.
    rag_runs = [(args.rag_ingest, run_rag_ingest),
                (args.rag_search is not None, run_rag_search),
                (args.rag_ask is not None, run_rag_ask),
                (args.rag_verify, run_rag_verify),
                (args.rag_eval, run_rag_eval),
                (args.rag_compare, run_rag_compare),
                (args.rag_gen_compare, run_rag_gen_compare)]
    if any(flag for flag, _ in rag_runs):
        sys.exit(max((run(args) for flag, run in rag_runs if flag), default=0))

    # Идентификация: --user либо интерактивный ввод ДО загрузки памяти.
    user_id = args.user
    rag_cfg = _build_rag_config(args) if args.rag else None
    agent = build_agent(user_id=user_id, mock=args.mock, mcp_enabled=args.mcp,
                        scheduler_enabled=args.scheduler,
                        scheduler_interval=args.scheduler_interval,
                        rag_enabled=args.rag, rag_config=rag_cfg,
                        model_id=args.model)

    # Флаг --local-only (Ревизия 8, этап 4): запрет облачных моделей в сессии.
    # Если текущая модель облачная — переключаемся на локальную (lmstudio).
    if args.local_only:
        registry = getattr(agent, "model_registry", None)
        if registry is not None and not registry.current().local:
            local_spec = next((s for s in registry.list(role="chat") if s.local), None)
            if local_spec is not None:
                agent.set_model(registry.build(local_spec), label=local_spec.display())
                registry.current_id = local_spec.id
                _apply_local_rag_template(agent)
                print(f"[Модель] --local-only: переключено на {local_spec.display()}")
            else:
                print("[Модель] ⚠ --local-only: локальных chat-моделей нет в реестре.")

    # Флаг --local-gen (уточнение куратора 2026-10-12): RAG-генератор = модель
    # агента, поэтому «локальная генерация» = переключить модель агента на локальную.
    # `agent.set_model` синхронизирует и agent.llm, и rag_service.llm (одна точка).
    if args.local_gen:
        registry = getattr(agent, "model_registry", None)
        if registry is not None:
            local_spec = next((s for s in registry.list(role="chat") if s.local), None)
            if local_spec is not None:
                agent.set_model(registry.build(local_spec), label=local_spec.display())
                registry.current_id = local_spec.id
                _apply_local_rag_template(agent)
                print(f"[Генератор] --local-gen: RAG генерирует {local_spec.display()}")
            else:
                print("[Генератор] ⚠ --local-gen: локальных chat-моделей нет в реестре.")

    # Накопительный трекер токенов сессии (локальная оценка).
    exchange_tracker = {"n": 0, "tokens": 0, "cost": 0.0}

    # One-shot обмен (Ревизия 8, этап 4): один запрос → ответ → выход. REPL и
    # интервью не запускаются; используется субагентами и фасадом (этап 9).
    if args.oneshot is not None:
        sys.exit(run_oneshot(agent, user_id or "oneshot", args.oneshot))

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

    # Флаг --model-profile (Ревизия 8): профиль параметров модели на старте.
    if args.model_profile:
        registry = getattr(agent, "model_registry", None)
        if registry is not None and args.model_profile in registry.profiles:
            spec = registry.current()
            spec.profile = args.model_profile
            agent.set_model(registry.build(spec), label=spec.display())
            _apply_local_rag_template(agent)
            print(f"[Модель] Профиль «{args.model_profile}» применён.")
        else:
            print(f"[Модель] ⚠ Профиль «{args.model_profile}» не найден — использую default.")

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

    # Баннер модели (Ревизия 8, этап 3): во всех CLI-сессиях видно, что подключено.
    print(model_banner(agent))

    print("Команды: /memory /profile [list|show|use|new|route|auto] /tasks /task [retry] "
          "/plan /approve /goto /transitions /step /run /pause /resume /deliver /compare "
          "/summary /state /tokens /cost /mcp summary|jobs|pipeline|route "
          "/rag status|on|off|ingest|find|stats|eval|check /model [list|use|status|profile] "
          "/help /exit\n")

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
                if command == "/model":
                    handle_model_command(agent, user_input)
                    continue
                if command == "/subagent":
                    handle_subagent_command(agent, user_input)
                    continue
                if command == "/gen":
                    handle_gen_command(agent, user_input)
                    continue
                if command == "/embed":
                    handle_embed_command(agent, user_input)
                    continue
                if command == "/exit":
                    stop_scheduler(agent)
                    agent.save_state()
                    print("[Выход] Состояние сохранено. До встречи!")
                    break
                print(f"[Команда] Неизвестная команда: {command}. См. /help\n")
                continue

            # Триггер-фраза «сделай локально в <service>: <задача>» (этап 4):
            # детерминированный анализатор → подтверждение → субагент.
            from core.subagents import detect_local_subagent_request
            detected = detect_local_subagent_request(user_input)
            if detected is not None:
                service, task = detected
                confirm = input(f"[Субагент] Запустить локально в «{service}»: "
                                f"«{task}»? [y/N]: ").strip().lower()
                if confirm in ("y", "yes", "д", "да"):
                    run_subagent(agent, task, service=service)
                else:
                    print("[Субагент] Отменено.\n")
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
            append_token_log(exchange_tracker["n"], prompt_tokens, exchange_cost,
                             model=agent.model_label())

            # Префикс реплики (Ревизия 8, этап 3): видно, какая модель ответила.
            print(f"[{agent.model_label()}] Агент: {answer}\n")

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