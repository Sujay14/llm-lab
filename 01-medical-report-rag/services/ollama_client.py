"""Shared Ollama connection, health check and friendly error translation."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import ollama

import config
from utils.errors import ModelMissingError, OllamaNotRunningError, UserFacingError

log = logging.getLogger(__name__)


def get_client() -> ollama.Client:
    return ollama.Client(host=config.OLLAMA_HOST) if config.OLLAMA_HOST else ollama.Client()


def translate_error(exc: Exception, model: str, fallback: type[UserFacingError]) -> UserFacingError:
    """Turn an Ollama/network exception into a friendly error (details go to the log only)."""
    log.error("Ollama call failed (%s): %s", type(exc).__name__, exc)
    if isinstance(exc, ConnectionError):
        return OllamaNotRunningError(
            "Cannot reach Ollama. Install it from https://ollama.com/download/windows, "
            "start it (open the Ollama app) and try again."
        )
    if isinstance(exc, ollama.ResponseError) and exc.status_code == 404:
        return ModelMissingError(
            f"The model '{model}' is not installed. In PowerShell run:  ollama pull {model}"
        )
    return fallback(f"The request to the '{model}' model failed. See the terminal window for details.")


@dataclass
class OllamaStatus:
    running: bool
    missing_models: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.running and not self.missing_models


def _installed(name: str, installed: list[str]) -> bool:
    return any(n == name or n.startswith(name + ":") for n in installed)


def check_ollama() -> OllamaStatus:
    """Is Ollama reachable, and are both required models downloaded?"""
    try:
        listing = get_client().list()  # typed ListResponse; each item has .model
    except Exception as exc:
        log.error("Ollama health check failed (%s)", type(exc).__name__)
        return OllamaStatus(running=False)
    names = [m.model for m in listing.models if m.model]
    missing = [m for m in (config.LLM_MODEL, config.EMBED_MODEL) if not _installed(m, names)]
    return OllamaStatus(running=True, missing_models=missing)
