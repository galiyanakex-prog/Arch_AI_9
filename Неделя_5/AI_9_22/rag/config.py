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


class RagDependencyError(RuntimeError):
    """Выбран провайдер, требующий не установленной зависимости (sentence-transformers)."""


@dataclass(frozen=True)
class CorpusConfig:
    list_file: str = "rag/datasets/corpus.list"
    max_docs: int = 2000
    max_chunks: int = 50000
    deny: tuple = (".env", ".ssh", "users", ".venv", "__pycache__", "rag/index", "*.db")


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
    # bge-m3 на CPU даёт ~2.4 с на чанк 400 токенов (замер: 8×400 = 19 с, 32×400 = 76 с).
    # Батч 8 укладывается в таймаут с запасом; больший батч не ускоряет (CPU-bound),
    # но рискует упереться в таймаут на холодной модели.
    batch_size: int = 8
    timeout_seconds: int = 60
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
    # Веса RRF по надёжности ретриверов (этап 7). Dense (bi-encoder, bge-m3) —
    # основной ретривер по модели куратора (N5_audio: «bi-encoder Top-20»), BM25 —
    # вспомогательный лексический сигнал. На golden-датасете BM25 слабее (0.75 vs
    # 0.875), поэтому его вклад понижен. Подобрано экспериментально, как требует
    # лекция («тут очень много экспериментального»), а не подогнано под датасет.
    # 0.1 — максимум, при котором гибрид не хуже ОБЕИХ компонент на ОБЕИХ
    # стратегиях чанкинга (fixed и structural); при 0.3 гибрид на fixed проигрывал
    # dense (0.875 < 0.9167). Проверено живым прогоном на bge-m3.
    rrf_weight_bm25: float = 0.1
    rrf_weight_dense: float = 1.0
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
