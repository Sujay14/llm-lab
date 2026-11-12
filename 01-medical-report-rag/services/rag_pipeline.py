"""The RAG steps used by app.py: ingest a report, then retrieve context for a question."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable

import config
from services.embedding_service import embed_documents, embed_query
from services.pdf_processor import extract_pages
from services.text_chunker import chunk_pages
from services.vector_store import ReportStore, Retrieved
from utils.errors import PDFError

log = logging.getLogger(__name__)

_BROAD = re.compile(
    r"summar|overview|overall|whole report|entire report|all (?:the )?(?:results|tests)|"
    r"outside|abnormal|out of range|flagged|which (?:results|tests)|every",
    re.IGNORECASE,
)
_FOLLOWUP = re.compile(
    r"\b(?:that|it|this|these|those|them|previous|above|earlier|again|simpler|simply|simplify|more)\b",
    re.IGNORECASE,
)


@dataclass
class IngestResult:
    store: ReportStore
    page_count: int
    pages_with_text: int
    chunk_count: int
    pages_without_text: list[int]


@dataclass
class Retrieval:
    items: list[Retrieved]
    weak: bool  # True when even the best match is far from the question


def ingest_report(pdf_bytes: bytes, status: Callable[[str, float], None] | None = None) -> IngestResult:
    """PDF bytes -> pages -> chunks -> embeddings -> ChromaDB. `status(message, fraction)` reports progress."""
    say = status or (lambda msg, frac: None)
    say("Reading the PDF…", 0.05)
    extraction = extract_pages(pdf_bytes)

    say("Splitting the text into searchable pieces…", 0.15)
    chunks = chunk_pages(extraction.pages)
    if not chunks:
        raise PDFError("No usable text could be prepared from this PDF.")

    store = ReportStore()
    try:
        vectors = embed_documents(
            [c.text for c in chunks],
            progress=lambda done, total: say(f"Creating embeddings ({done}/{total})…", 0.15 + 0.75 * done / total),
        )
        say("Saving to the local search database…", 0.95)
        store.add(chunks, vectors)
    except Exception:
        store.close()  # never leave a half-indexed report behind
        raise
    say("Done", 1.0)
    return IngestResult(store, extraction.page_count, len(extraction.pages), len(chunks), extraction.pages_without_text)


def is_followup(question: str) -> bool:
    return len(question.split()) <= 12 and bool(_FOLLOWUP.search(question))


def retrieve(store: ReportStore, question: str, previous_question: str | None = None) -> Retrieval:
    """Embed the question and fetch the most similar chunks (more of them for broad questions)."""
    query = f"{previous_question} {question}" if previous_question and is_followup(question) else question
    k = config.BROAD_TOP_K if _BROAD.search(question) else config.TOP_K
    items = store.query(embed_query(query), k)
    weak = not items or min(r.distance for r in items) > config.MAX_DISTANCE
    return Retrieval(items, weak)
