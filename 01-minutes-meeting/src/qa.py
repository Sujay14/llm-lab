"""Transcript-grounded question answering using the configured local Ollama model."""
from __future__ import annotations
from .summarize import _chat, split_text, OllamaUnavailable
from . import config


def answer_question(question: str, transcript: str, *, model: str = config.OLLAMA_MODEL,
                    host: str = config.OLLAMA_HOST, max_chunks: int = 4) -> str:
    question = (question or "").strip()
    transcript = (transcript or "").strip()
    if not question:
        raise ValueError("Enter a question first.")
    if not transcript:
        raise ValueError("There is no transcript to search.")
    chunks = split_text(transcript)
    # Keep retrieval simple and deterministic: rank chunks by query-term overlap.
    terms = {w.lower().strip(".,!?():;\"'") for w in question.split() if len(w) > 2}
    ranked = sorted(chunks, key=lambda c: sum(c.lower().count(t) for t in terms), reverse=True)
    context = "\n\n---\n\n".join(ranked[:max_chunks])
    system = ("Answer questions using only the supplied meeting transcript. "
              "If the transcript does not contain the answer, say so clearly. "
              "Do not invent speaker names, decisions, dates or commitments. "
              "Cite timestamps or speaker labels when present.")
    return _chat(host, model, system, f"TRANSCRIPT EXCERPTS:\n{context}\n\nQUESTION: {question}")
