
from __future__ import annotations

import logging
from typing import Iterator

import config
from services.ollama_client import get_client, translate_error
from services.vector_store import Retrieved
from utils.errors import LLMError
from utils.prompt_templates import SYSTEM_PROMPT, USER_TEMPLATE, WEAK_CONTEXT_NOTE, format_excerpts

log = logging.getLogger(__name__)


def build_messages(
    question: str, retrieved: list[Retrieved], history: list[dict], weak: bool = False
) -> list[dict]:
    """System rules + recent chat turns (so 'explain that more simply' works) + excerpts and question."""
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history[-2 * config.HISTORY_TURNS :])
    messages.append(
        {
            "role": "user",
            "content": USER_TEMPLATE.format(
                excerpts=format_excerpts(retrieved),
                weak_note=WEAK_CONTEXT_NOTE if weak else "",
                question=question,
            ),
        }
    )
    return messages


def stream_answer(messages: list[dict]) -> Iterator[str]:
    """Yield the answer piece by piece. Raises a friendly LLMError-family error on failure."""
    try:
        stream = get_client().chat(
            model=config.LLM_MODEL,
            messages=messages,
            stream=True,
            options={"num_ctx": config.NUM_CTX, "temperature": config.TEMPERATURE},
        )
        for part in stream:  # typed ChatResponse objects -> .message.content
            piece = part.message.content
            if piece:
                yield piece
    except Exception as exc:  
        raise translate_error(exc, config.LLM_MODEL, LLMError) from exc
