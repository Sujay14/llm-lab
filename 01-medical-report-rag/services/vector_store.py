"""ChromaDB wrapper. One in-memory collection per uploaded report (temporary storage)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

import chromadb

from services.text_chunker import Chunk
from utils.errors import VectorStoreError

log = logging.getLogger(__name__)
_ADD_BATCH = 128


@dataclass
class Retrieved:
    text: str
    pdf_page: int
    printed_label: str | None
    chunk_index: int
    distance: float  # cosine distance: lower = more similar


class ReportStore:
    """Holds ONE report. Every instance has its own collection name and document id, and every
    query is filtered by that id, so a session cannot retrieve text from another upload.
    Data lives in memory only and disappears when the app restarts."""

    def __init__(self) -> None:
        self.doc_id = uuid.uuid4().hex
        self._name = f"report_{self.doc_id}"
        try:
            self._client = chromadb.EphemeralClient()
            self._collection = self._client.create_collection(
                name=self._name, configuration={"hnsw": {"space": "cosine"}}
            )
        except Exception as exc:  # noqa: BLE001
            log.error("ChromaDB init failed (%s): %s", type(exc).__name__, exc)
            raise VectorStoreError("The local search database could not be started.") from exc

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise VectorStoreError("Internal error: chunk and embedding counts differ.")
        try:
            for i in range(0, len(chunks), _ADD_BATCH):
                part = chunks[i : i + _ADD_BATCH]
                self._collection.add(
                    ids=[f"{self.doc_id}-{c.index}" for c in part],
                    documents=[c.text for c in part],
                    embeddings=embeddings[i : i + _ADD_BATCH],
                    metadatas=[
                        {
                            "doc_id": self.doc_id,
                            "pdf_page": c.pdf_page,
                            "printed_label": c.printed_label or "",
                            "chunk_index": c.index,
                        }
                        for c in part
                    ],
                )
        except Exception as exc:  # noqa: BLE001
            log.error("ChromaDB add failed (%s): %s", type(exc).__name__, exc)
            raise VectorStoreError("Could not save the report in the local search database.") from exc

    def count(self) -> int:
        return self._collection.count()

    def query(self, query_embedding: list[float], k: int) -> list[Retrieved]:
        try:
            n = min(k, self._collection.count())
            if n == 0:
                return []
            res = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=n,
                where={"doc_id": self.doc_id},
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:  # noqa: BLE001
            log.error("ChromaDB query failed (%s): %s", type(exc).__name__, exc)
            raise VectorStoreError("Searching the report failed. Please try again.") from exc
        return [
            Retrieved(doc, int(meta["pdf_page"]), meta["printed_label"] or None, int(meta["chunk_index"]), float(dist))
            for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
        ]

    def close(self) -> None:
        """Delete this report's data (used by 'upload another report')."""
        try:
            self._client.delete_collection(self._name)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not delete collection (%s)", type(exc).__name__)
