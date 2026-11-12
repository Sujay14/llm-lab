"""Embeddings via Ollama (`nomic-embed-text`). The same model embeds chunks and questions."""
from __future__ import annotations

import logging
from typing import Callable, Sequence

import config
from services.ollama_client import get_client, translate_error
from utils.errors import EmbeddingError

log = logging.getLogger(__name__)

# nomic-embed-text is trained with task prefixes; they improve retrieval quality.
DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


def _embed(texts: Sequence[str]) -> list[list[float]]:
    try:
        response = get_client().embed(model=config.EMBED_MODEL, input=list(texts))
        vectors = [list(v) for v in response.embeddings]  # typed EmbedResponse -> .embeddings
    except Exception as exc:  # noqa: BLE001
        raise translate_error(exc, config.EMBED_MODEL, EmbeddingError) from exc
    if len(vectors) != len(texts):
        log.error("Embedding count mismatch: sent %d, got %d", len(texts), len(vectors))
        raise EmbeddingError("The embedding model returned an unexpected result. Please try again.")
    return vectors


def embed_documents(
    texts: Sequence[str], progress: Callable[[int, int], None] | None = None
) -> list[list[float]]:
    """Embed chunk texts in small batches. `progress(done, total)` is called after each batch."""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), config.EMBED_BATCH_SIZE):
        batch = [DOC_PREFIX + t for t in texts[start : start + config.EMBED_BATCH_SIZE]]
        vectors.extend(_embed(batch))
        if progress:
            progress(len(vectors), len(texts))
    return vectors


def embed_query(text: str) -> list[float]:
    return _embed([QUERY_PREFIX + text])[0]
