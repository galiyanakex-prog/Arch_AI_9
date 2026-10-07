# migr_plan_0.md — Этап 0. Базовая линия Ревизии 6 + каркас `rag/` (О0)

> Рабочий план **одного этапа** на основе `dev/migr_plan.md` (Ревизия 6, §4 «Этап 0»).
> Контур: **О (оснащение)**. Метка цели: **О0**. Зависимости: **нет** (первый этап).
> Порядок выполнения: **пошагово с оператором** — агент даёт команду/файл, оператор
> подтверждает, агент выполняет и фиксирует вывод; затем следующий шаг.
> **Коммиты — только за оператором** (текст предложен в ШАГЕ 0.9).

## Цель этапа

Зафиксировать **«как есть»** (живая базовая линия тестового контура) и создать
**скелет модуля** `rag/` — конфигурацию и контракты данных, — чтобы этапы 3–10
вставляли логику **не меняя структуры**. Никакой рабочей логики RAG на этом этапе
нет и быть не должно: заглушки обязаны громко падать с `NotImplementedError`.

## Предусловия (выполнено)

- `dev/migr_plan.md` — мастер-план Ревизии 6 (проверено: 730 строк).
- `dev/migr_log.md` — обнулён до шапки Ревизии 6, запись «Подготовка» внесена.
- Снимок Ревизии 5 — в `dev/old_vers/6/` (включая прежние `migr_plan.md`, `migr_log.md`).
- `rag/` — пустой каталог; `requirements.txt` — без изменений; `ollama` в системе нет.

## Границы этапа

- **Не** ставим Ollama и модель (этап 1), **не** собираем корпус (этап 2).
- **Не** трогаем `Kod.py`, `core/`, `storage/`, `memory/`, `integrations/` — правок
  продукта на этом этапе нет вообще.
- **Не** добавляем зависимостей: `requirements.txt` остаётся как есть.
- **Не** создаём юнит-модулей `test_rag_*.py` (первый — на этапе 3); проверки этапа —
  командами гейта (см. примечание к ШАГУ 0.8).

---

## Шаги

### ШАГ 0.1 — Базовая линия «до» (то, что должно остаться зелёным)

Все четыре контура прогоняются **до** появления `rag/` и **после** (ШАГ 0.7) — счётчики
в журнале должны совпасть.

```bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
PY="$PWD/.venv/bin/python"; TST="$PWD/dev/tests_debug"

ls "$TST"/unit/test_*.py | wc -l                          # ожидаем 18 модулей
API_KEY=test-key "$PY" "$TST/unit_runner.py" | tail -3     # L2: «Итого: N OK, 0 FAIL»
API_KEY=test-key "$PY" "$TST/smoke.py" | tail -3           # L3
API_KEY=test-key "$PY" "$TST/scenario.py" | tail -3        # L4
API_KEY=test-key bash "$TST/check_acceptance.sh" | tail -3 # гейт: 25 из 25
```

**Записать в `migr_log.md`:** точные числа (модулей / тестов OK / сценариев / проверок).
**Красный флаг:** если базовая линия **не** зелёная — этап 0 не начинаем, сначала
чиним наследие (иначе дальше не отличим свой регресс от чужого).

### ШАГ 0.2 — Красные проверки (воспроизведение «функции нет»)

```bash
# К1: модуля нет
"$PY" -c "import rag" ; echo "exit=$?"
# К2: флага CLI нет
API_KEY=test-key "$PY" Kod.py --rag ; echo "exit=$?"
# К3: артефактов индекса нет
ls rag/ ; echo "exit=$?"
```

**Ожидаемо (красное):** К1 `ModuleNotFoundError`, exit 1; К2 `error: unrecognized
arguments: --rag`, exit 2; К3 — пустой вывод. Три вывода дословно — в журнал.
> К2 **останется красным до этапа 8** — это плановое состояние, а не провал гейта 0→1.

### ШАГ 0.3 — `rag/types.py` (контракты данных)

Создать `rag/types.py`. Это **контракты всего модуля**: этапы 3–10 не имеют права
менять поля без записи в `migr_log.md`.

```python
# -*- coding: utf-8 -*-
"""Контракты данных RAG-модуля (этап 0).

Три правила, которые здесь закреплены:
1. все объекты неизменяемы (frozen) — найденный чанк не «дописывается» по дороге;
2. у каждого объекта есть to_dict() — любой артефакт (индекс, отчёт, журнал) пишется
   из них без ручного конструирования словарей;
3. метаданные чанка (source/title/section/chunk_id) обязательны — это требование
   Задание_d21.txt, а не опция.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass(frozen=True)
class Chunk:
    """Кусочек документа — единица индексирования."""
    chunk_id: str                 # "<doc_id>#<номер>" — обязателен, уникален в индексе
    doc_id: str                   # sha1 пути документа
    source: str                   # путь к файлу (относительный от корня проекта)
    title: str                    # H1 документа или имя файла
    section: str                  # путь заголовков: "A > B > C" ("" — начало файла)
    text: str                     # собственно текст чанка
    strategy: str                 # "fixed" | "structural" | "semantic"
    content_type: str = "text"    # "text" | "code" | "table"
    start_line: int = 0
    end_line: int = 0
    tokens: int = 0               # оценка (эвристика), не гарантированный счёт BPE
    sha1: str = ""                # sha1 текста — ключ кэша эмбеддингов
    parent_id: str = ""           # parent-child: id блока, который отдаём в контекст

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DocMeta:
    """След документа в индексе — по нему считается инкрементальная дельта."""
    doc_id: str
    source: str
    sha1: str
    mtime: float
    n_chunks: int
    content_type: str = "text"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Hit:
    """Результат поиска. scores обязателен: выдача должна быть объяснима."""
    chunk_id: str
    doc_id: str
    source: str
    title: str
    section: str
    text: str
    score: float
    scores: dict = field(default_factory=dict)   # {bm25_rank, dense_rank, rrf, rerank}
    source_query: str = ""                       # какая переформулировка нашла (multi-query)
    parent_text: str = ""                        # если есть — отдаём в промпт его

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IngestReport:
    """Итог индексации: сколько и почему пересчитано."""
    added: int = 0
    updated: int = 0
    removed: int = 0
    skipped: int = 0                # совпал sha1 — не переэмбедили
    chunks: int = 0
    seconds: float = 0.0
    embed_calls: int = 0            # сколько раз реально обратились к эмбеддеру
    errors: tuple = ()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvalReport:
    """Метрики качества retrieval на golden-датасете."""
    k: int = 5
    metrics: dict = field(default_factory=dict)      # recall@k, precision@k, hit_rate@k, mrr, ndcg@k
    latency_ms: dict = field(default_factory=dict)   # p50, p95
    per_query: tuple = ()
    dataset: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CompareReport:
    """Сравнение стратегий чанкинга — прямой результат Задание_d21.txt."""
    rows: tuple = ()                # ({strategy, mode, **metrics}, ...)
    best: str = ""                  # "<strategy>/<mode>"
    verdict: str = ""               # человекочитаемое обоснование выбора
    divergences: tuple = ()         # разборы запросов, где стратегии разошлись
    k: int = 5
    model_id: str = ""              # сравнение осмысленно только при одном model_id

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GroundingReport:
    """Проверка «ответ опирается на найденное» (решение пользователя №4)."""
    verdict: str = "unchecked"      # ok | partial | hallucination | unchecked
    sentences: tuple = ()           # ({text, status, best_chunk_id, coverage, numbers_missing})
    citations_ok: bool = False
    regenerated: bool = False
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
```

### ШАГ 0.4 — `rag/config.py` (конфигурация)

Создать `rag/config.py`. Ключевые свойства, которые проверяет гейт: **битый/отсутствующий
файл не роняет** (дефолтизация, как в `Store.read_*`), **неизвестные ключи игнорируются
с предупреждением**, **`load("rag/config.json") == DEFAULTS`**, **embedding-URL обязан
быть localhost**.

```python
# -*- coding: utf-8 -*-
"""Конфигурация RAG-модуля.

Приоритет (низкий → высокий): DEFAULTS → rag/config.json → env
(AI9_RAG_*, OLLAMA_EMBED_URL, OLLAMA_EMBED_MODEL).

Секретов здесь нет и быть не может: эмбеддинги ходят только на localhost и
ключей не требуют (решение пользователя №5).
"""
from __future__ import annotations

import dataclasses
import json
import os
from dataclasses import dataclass, field

DEFAULT_CONFIG_PATH = "rag/config.json"
_ALLOWED_URL_PREFIXES = ("http://127.0.0.1", "http://localhost")


class RagConfigError(ValueError):
    """Конфигурация противоречит границам модуля (например, внешний embedding-URL)."""


@dataclass(frozen=True)
class CorpusConfig:
    list_file: str = "rag/datasets/corpus.list"
    max_docs: int = 2000
    max_chunks: int = 50000
    deny: tuple = (".env", ".ssh", "users", ".venv", "__pycache__", "rag/index")


@dataclass(frozen=True)
class ChunkingConfig:
    strategy: str = "structural"        # "fixed" | "structural"
    size_tokens: int = 400
    overlap_ratio: float = 0.15
    parent_max_tokens: int = 1200
    keep_code_whole: bool = True
    fixed_size_tokens: int = 300        # стратегия S1
    fixed_overlap_tokens: int = 60


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str = "ollama"            # "ollama" | "hashing" | "fake"
    model: str = "bge-m3"
    dim: int = 1024
    url: str = "http://127.0.0.1:11434"
    batch_size: int = 32
    timeout_seconds: int = 30
    retries: int = 2
    keep_alive: str = "10m"
    fallback_provider: str = "hashing"  # деградация, не падение
    hashing_dim: int = 256


@dataclass(frozen=True)
class Bm25Config:
    k1: float = 1.2
    b: float = 0.75


@dataclass(frozen=True)
class RetrievalConfig:
    mode: str = "hybrid"                # "bm25" | "dense" | "hybrid"
    candidate_k: int = 50
    final_k: int = 5
    rrf_k: int = 60
    mmr_lambda: float = 0.7
    max_chunks_per_doc: int = 2
    multi_query: bool = False
    bm25: Bm25Config = field(default_factory=Bm25Config)


@dataclass(frozen=True)
class RerankConfig:
    provider: str = "lexical"
    enabled: bool = True
    candidates: int = 20


@dataclass(frozen=True)
class CacheConfig:
    enabled: bool = True
    max_entries: int = 256
    ttl_seconds: int = 900


@dataclass(frozen=True)
class GroundingConfig:
    mode: str = "strict"                # off | warn | strict
    coverage_min: float = 0.45
    numbers_strict: bool = True
    max_regenerations: int = 1


@dataclass(frozen=True)
class BudgetConfig:
    max_rag_tokens: int = 1400          # блок [rag] усекается первым


@dataclass(frozen=True)
class RagConfig:
    corpus: CorpusConfig = field(default_factory=CorpusConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    rerank: RerankConfig = field(default_factory=RerankConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    grounding: GroundingConfig = field(default_factory=GroundingConfig)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    index_dir: str = "rag/index"
    enabled: bool = False               # RAG выключен по умолчанию

    @classmethod
    def default(cls) -> "RagConfig":
        return cls()

    @classmethod
    def from_dict(cls, data: dict) -> "RagConfig":
        if not isinstance(data, dict):
            print("[RAG] конфиг: файл не-объект, используем значения по умолчанию")
            return cls()
        return _build(cls, data)

    @classmethod
    def load(cls, path: str = DEFAULT_CONFIG_PATH) -> "RagConfig":
        """Битый или отсутствующий файл → DEFAULTS (по образцу Store.read_*)."""
        try:
            with open(path, "r", encoding="utf-8") as handle:
                cfg = cls.from_dict(json.load(handle))
        except FileNotFoundError:
            print(f"[RAG] конфиг {path} не найден — значения по умолчанию")
            cfg = cls()
        except (json.JSONDecodeError, OSError) as error:
            print(f"[RAG] конфиг {path} повреждён ({error}) — значения по умолчанию")
            cfg = cls()
        return cfg.from_env().validate()

    def from_env(self) -> "RagConfig":
        """Переопределение из окружения (значения по умолчанию не мутируются)."""
        patch = {}
        emb = {}
        if os.getenv("AI9_RAG_ENABLED"):
            patch["enabled"] = os.environ["AI9_RAG_ENABLED"].strip().lower() in ("1", "true", "yes")
        if os.getenv("AI9_RAG_MODE"):
            patch["retrieval"] = dataclasses.replace(self.retrieval, mode=os.environ["AI9_RAG_MODE"])
        if os.getenv("AI9_RAG_STRATEGY"):
            patch["chunking"] = dataclasses.replace(self.chunking, strategy=os.environ["AI9_RAG_STRATEGY"])
        if os.getenv("AI9_RAG_TOP_K"):
            patch["retrieval"] = dataclasses.replace(
                patch.get("retrieval", self.retrieval), final_k=int(os.environ["AI9_RAG_TOP_K"]))
        if os.getenv("AI9_RAG_GROUNDING"):
            patch["grounding"] = dataclasses.replace(self.grounding, mode=os.environ["AI9_RAG_GROUNDING"])
        if os.getenv("OLLAMA_EMBED_URL"):
            emb["url"] = os.environ["OLLAMA_EMBED_URL"]
        if os.getenv("OLLAMA_EMBED_MODEL"):
            emb["model"] = os.environ["OLLAMA_EMBED_MODEL"]
        if emb:
            patch["embedding"] = dataclasses.replace(self.embedding, **emb)
        return dataclasses.replace(self, **patch) if patch else self

    # ---------- инварианты ----------
    def validate(self) -> "RagConfig":
        """Границы модуля (мастер-план §5): embedding — только localhost."""
        url = (self.embedding.url or "").lower()
        if not url.startswith(_ALLOWED_URL_PREFIXES):
            raise RagConfigError(
                f"embedding.url обязан быть локальным {_ALLOWED_URL_PREFIXES}, получено: {self.embedding.url}. "
                "RAG сознательно не ходит во внешнюю сеть (решение пользователя №5).")
        if self.chunking.strategy not in ("fixed", "structural"):
            raise RagConfigError(f"неизвестная стратегия чанкинга: {self.chunking.strategy}")
        if self.retrieval.mode not in ("bm25", "dense", "hybrid"):
            raise RagConfigError(f"неизвестный режим ретривера: {self.retrieval.mode}")
        if self.grounding.mode not in ("off", "warn", "strict"):
            raise RagConfigError(f"неизвестный режим grounding: {self.grounding.mode}")
        return self

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# Поля, чьи значения — вложенные секции-конфиги. JSON отдаёт словари, и без
# рекурсивной сборки cfg.embedding остался бы dict: любое cfg.embedding.url упало бы
# с AttributeError, а load("rag/config.json") == DEFAULTS не сошлось бы. Это ловит гейт №2.
# deny (list->tuple) обрабатывается внутри рекурсии: поле живёт в CorpusConfig, а не наверху.
SECTION_CLASSES = {
    "corpus": CorpusConfig,
    "chunking": ChunkingConfig,
    "embedding": EmbeddingConfig,
    "retrieval": RetrievalConfig,
    "rerank": RerankConfig,
    "cache": CacheConfig,
    "grounding": GroundingConfig,
    "budget": BudgetConfig,
    "bm25": Bm25Config,
}


def _build(cls, data):
    """Рекурсивная сборка dataclass из dict: неизвестные ключи — предупреждение, не падение."""
    if not isinstance(data, dict):
        return cls()
    names = {f.name for f in dataclasses.fields(cls)}
    unknown = sorted(set(data) - names - {"_comment"})
    if unknown:
        print(f"[RAG] конфиг {cls.__name__}: неизвестные ключи игнорируются: {unknown}")
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        value = data[f.name]
        section = SECTION_CLASSES.get(f.name)
        if section is not None:
            value = _build(section, value)
        elif f.name == "deny" and isinstance(value, list):
            value = tuple(value)
        kwargs[f.name] = value
    return cls(**kwargs)


DEFAULTS = RagConfig.default()


def load_config(path: str = DEFAULT_CONFIG_PATH) -> RagConfig:
    """Точка входа для Kod.py (этап 8)."""
    return RagConfig.load(path)
```

> **Почему `validate()` бросает исключение, а не чинит молча:** внешний embedding-URL —
> это нарушение заявленной границы («только localhost»), а не опечатка в пути. Молча
> подменить адрес = соврать пользователю о приватности.

### ШАГ 0.5 — `rag/config.json` (редактируемый конфиг)

Создать **генерацией из `DEFAULTS`**, а не руками — иначе гейт «`load() == DEFAULTS`»
падает на первой же опечатке.

```bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
"$PY" - <<'EOF'
import json, sys
sys.path.insert(0, ".")
from rag.config import DEFAULTS
data = {"_comment": "Конфигурация RAG-модуля AI_9. Секреты здесь запрещены; "
                    "embedding.url — только 127.0.0.1/localhost."}
data.update(DEFAULTS.to_dict())
with open("rag/config.json", "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)
    fh.write("\n")
print("rag/config.json записан")
EOF
```

**Проверка:** `head -20 rag/config.json` → виден `_comment`, `corpus.deny`, `chunking.strategy`.

### ШАГ 0.6 — Модули-заглушки (контур без логики)

Создать 12 файлов по единому шаблону: docstring с указанием этапа реализации +
публичные имена, бросающие `NotImplementedError`. **Никаких «временных рабочих»
реализаций** — заглушка, возвращающая пустой список, позже выдаст зелёный гейт
вместо реального результата.

Шаблон (`rag/<модуль>.py`):

```python
# -*- coding: utf-8 -*-
"""<назначение> — реализация на этапе <N> (мастер-план §4).

На этапе 0 модуль объявлен как контракт. Вызов бросает NotImplementedError,
чтобы ни один потребитель не получил «тихую» заглушку вместо результата.
"""
from __future__ import annotations

STAGE = <N>


def _todo(what: str):
    raise NotImplementedError(
        f"rag: {what} ещё не реализован (этап {STAGE} плана dev/migr_plan.md)")
```

Что объявить в каждом модуле (сигнатуры — контракт, тела — `_todo(...)`):

| Модуль | Этап | Публичные имена |
|---|---|---|
| `text.py` | 3 | `normalize(text)`, `tokenize(text)`, `stem(word)`, `split_sentences(text)`, `est_tokens(text)` |
| `chunking.py` | 3 | `STRATEGIES = ("fixed", "structural")`, `chunk_document(doc, cfg, strategy)` |
| `corpus.py` | 5 | `discover(paths, cfg)`, `delta(docs, known_docs)` |
| `embedding.py` | 4 | `Embedder` (протокол: `dim`, `model_id`, `embed(texts)`), `HashingEmbedder`, `OllamaEmbedder`, `FakeEmbedder`, `make_embedder(cfg)` |
| `index.py` | 5 | `RagIndex`: `build`, `save`, `load`, `search_bm25`, `search_dense`, `stats` |
| `retrieval.py` | 6 | `Retriever`: `search(query, k, mode, filters)` |
| `rerank.py` | 6 (интерфейс — 10) | `Reranker` (протокол), `LexicalReranker` |
| `cache.py` | 10 | `SearchCache`: `get`, `put`, `invalidate`, `stats` |
| `grounding.py` | 9 | `ground(answer, hits, cfg)` |
| `eval.py` | 7 | `evaluate(index, dataset, k)`, `main()` |
| `compare.py` | 7 | `compare(cfg, strategies, modes, queries, k)`, `main()` |
| `service.py` | 8 | `RagService`: `ingest`, `search`, `context_block`, `stats`, `compare`, `evaluate`, `ground` |

> **Почему `rerank.py` начинается на этапе 6, а не 10:** гибридный режим (этап 6)
> по мастер-плану включает lexical-реранк в цепочку `RRF → rerank → MMR`; оставлять
> «гибрид без реранка» значило бы сравнивать на этапе 7 не то, что интегрируем.
> На этапе 10 добавляется только интерфейс и задел под cross-encoder.

### ШАГ 0.7 — `rag/__init__.py` (публичный API)

```python
# -*- coding: utf-8 -*-
"""RAG-модуль AI_9: индексация и поиск по документам (Задание_d21.txt).

Конвейер: corpus → chunking (fixed | structural) → embedding (Ollama | hashing)
→ index (BM25 + dense) → retrieval (RRF + MMR) → context_block со ссылками
→ grounding (ответ обязан опираться на найденное).

Границы модуля (мастер-план §5): только stdlib; сеть — исключительно
127.0.0.1:11434 (Ollama); rag/ не импортирует core/; индекс глобальный (rag/index/).
На этапе 0 реализованы только конфигурация и контракты данных.
"""
from rag.config import (DEFAULTS, DEFAULT_CONFIG_PATH, RagConfig, RagConfigError,
                        load_config)
from rag.types import (Chunk, CompareReport, DocMeta, EvalReport, GroundingReport,
                       Hit, IngestReport)
from rag.service import RagService

__all__ = [
    "RagConfig", "RagConfigError", "load_config", "DEFAULTS", "DEFAULT_CONFIG_PATH",
    "Chunk", "DocMeta", "Hit", "IngestReport", "EvalReport", "CompareReport",
    "GroundingReport", "RagService",
]
```

### ШАГ 0.8 — `.gitignore` и проверка изоляции

```bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
cat >> .gitignore <<'EOF'

# RAG: артефакты индекса (восстанавливаются командой --rag-ingest)
rag/index/
rag/.tmp/
EOF
```

Проверки изоляции (должны быть **пустыми**):

```bash
grep -rn "^from core\|^import core\|from core\." rag/ ; echo "core-импортов нет: exit=$?"
grep -rn "http://\|https://" rag/ | grep -v "127.0.0.1\|localhost" ; echo "внешних URL нет: exit=$?"
git diff --stat requirements.txt            # пусто = зависимостей не добавили
```

> **Про тесты.** Отдельный `test_rag_config.py` на этом этапе **не** создаём:
> мастер-план §0.5 отводит под RAG шесть юнит-модулей, первый из них — `test_rag_text.py`
> (этап 3). Равенство конфига дефолтам проверяется командами гейта ниже; постоянный
> тест round-trip добавим в `test_rag_index.py` (этап 5). Если захотите тест сейчас —
> это расширение §0.5, его надо отдельно записать в `migr_log.md`.

### ШАГ 0.9 — Базовая линия «после» + запись в журнал

```bash
API_KEY=test-key "$PY" -c "import rag; print('rag OK:', ', '.join(rag.__all__))"
API_KEY=test-key "$PY" "$TST/unit_runner.py" | tail -3
API_KEY=test-key "$PY" "$TST/smoke.py" | tail -3
API_KEY=test-key "$PY" "$TST/scenario.py" | tail -3
API_KEY=test-key bash "$TST/check_acceptance.sh" | tail -3
git status --porcelain
```

Внести в `dev/migr_log.md` запись «Этап 0» по шаблону §7.3 мастер-плана: было
(3 красных вывода ШАГА 0.2 + счётчики ШАГА 0.1) → стало (счётчики ШАГА 0.9,
`import rag` OK) → артефакты → гейт.

**Предлагаемый текст коммита** (выполняет **только** оператор):

```
feat(rag): каркас модуля RAG — конфигурация и контракты данных (этап 0, Ревизия 6)

Причина: этапы 3–10 должны наращивать логику в неизменной структуре, иначе
каждый следующий план меняет контракты предыдущего. Поэтому конфигурация
(RagConfig c дефолтизацией битого файла и запретом внешних embedding-URL)
и контракты данных (Chunk/Hit/CompareReport/GroundingReport) фиксируются сейчас.

Заглушки бросают NotImplementedError намеренно: пустая реализация позже дала бы
зелёный гейт вместо реального результата. Тестовый контур не изменился.
```

---

## Выход этапа

- `rag/` содержит: `__init__.py`, `config.py`, `types.py`, `config.json` + 12 заглушек;
- `rag/index/` **не** создан (появится на этапе 5) и уже в `.gitignore`;
- `requirements.txt`, `Kod.py`, `core/`, `storage/` — **не изменены**;
- запись «Этап 0» в `dev/migr_log.md`.

## Гейт 0→1 (все пункты зелёные)

| № | Проверка | Ожидаемо |
|---|---|---|
| 1 | `"$PY" -c "import rag"` | exit 0, `__all__` печатается |
| 2 | `"$PY" -c "from rag import RagConfig; c=RagConfig.load('rag/config.json'); assert c==RagConfig.default(), c; assert c.embedding.url.startswith('http://127.0.0.1'), c.embedding"` | exit 0 (конфиг == дефолты **и** вложенные секции — dataclass, а не dict) |
| 3 | граница «только localhost» — скриптом через heredoc (в `python -c` перевод строки не работает, это проверено): готовый текст под таблицей | exit 0 (внешний `embedding.url` отвергнут) |
| 4 | `"$PY" -c "import rag, json; json.dumps([rag.Chunk('a','b','c','d','e','t','fixed').to_dict()])"` | exit 0 (контракты сериализуемы) |
| 5 | заглушка падает громко: `"$PY" -c "from rag.service import RagService; RagService(RagConfig.default()).search('x')"` | `NotImplementedError` (не пустой результат) |
| 6 | `grep -rnE "^\s*(from\|import)\s+core\b" rag/*.py` | пусто (направление зависимостей не нарушено; `grep "core"` даёт ложные срабатывания на `score`/`scores` и упоминание `core/` в docstring) |
| 7 | `grep -rn "http" rag/*.py rag/config.json \| grep -v 127.0.0.1 \| grep -v localhost` | пусто |
| 8 | `git diff --stat requirements.txt` | пусто (новых зависимостей нет) |
| 9 | `unit_runner.py` / `smoke.py` / `scenario.py` | счётчики **совпадают** с ШАГОМ 0.1 |
| 10 | `check_acceptance.sh` | **25 из 25** (столько же, сколько до этапа) |
| 11 | `Kod.py --rag` | **красный по плану** (аргумент появится на этапе 8) — фиксируется в журнале, не считается провалом |
| 12 | запись «Этап 0» в `migr_log.md` + перечитывание `migr_plan.md` | ✅ |

> **Готовый текст проверки №3.** Многострочные проверки через `python -c` здесь
> не работают: интерпретатор получает литеральный `\n` внутри одной строки и падает с
> `SyntaxError` (проверено на `.venv/bin/python` 3.13.5). Поэтому — heredoc:
>
> ```bash
> "$PY" - <<'EOF'
> import dataclasses, sys
> sys.path.insert(0, ".")
> from rag.config import RagConfig, RagConfigError
> base = RagConfig.default()
> bad = dataclasses.replace(base, embedding=dataclasses.replace(base.embedding, url="http://8.8.8.8"))
> try:
>     bad.validate()
> except RagConfigError as error:
>     print("OK, внешний URL отвергнут:", error)
> else:
>     raise SystemExit("КРАСНЫЙ: внешний embedding-URL пропущен валидацией")
> EOF
> ```
>
> Тем же способом (heredoc) выполняются проверки №4 и №5, если их тело не укладывается
> в одну строку.

Красный хотя бы один из 1–10 → карточка в `dev/logs_reports/errors/error_<ts>.md`,
этап 0 остаётся открытым.

## Откат

```bash
cd /home/u/Документы/111111/Обучение_Курсы/Основной_репозиторий/AI_9
rm -rf rag/                       # каталог был пуст, рабочих данных в нём нет
git checkout -- .gitignore        # вернуть файл в прежнее состояние
```
Код продукта не менялся, поэтому откат не затрагивает поведение агента; запись в
`migr_log.md` помечается ❌ с причиной.

## Что передаём дальше

- **Этапу 1 (O1):** `rag/config.json → embedding.{url, model, dim}` уже заданы
  (`127.0.0.1:11434`, `bge-m3`, `1024`) — установка Ollama должна им соответствовать;
  при выборе `nomic-embed-text` правятся только `model` и `dim`, код не трогается.
- **Этапу 2 (О2):** `corpus.list_file` и `corpus.deny` — контракт, который должен
  удовлетворить список корпуса; `deny` уже содержит `.env`, `.ssh`, `users`, `.venv`.
- **Этапу 3 (R1):** `Chunk` и `ChunkingConfig` заморожены; новые поля — только
  через запись в `migr_log.md`.