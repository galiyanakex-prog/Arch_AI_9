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
                        RagDependencyError, load_config)
from rag.types import (Chunk, CompareReport, DocMeta, EvalReport, GroundingReport,
                       Hit, IngestReport)
from rag.service import RagService

__all__ = [
    "RagConfig", "RagConfigError", "RagDependencyError", "load_config", "DEFAULTS",
    "DEFAULT_CONFIG_PATH",
    "Chunk", "DocMeta", "Hit", "IngestReport", "EvalReport", "CompareReport",
    "GroundingReport", "RagService",
]
