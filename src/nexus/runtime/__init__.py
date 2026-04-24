"""Nexus runtime — pluggable inference backends.

Selected via `NEXUS_BACKEND` env var (or legacy `ORACLE_BACKEND`):
  - `ollama` (default) — wraps the existing ollama.Client
  - `llama_cpp`       — direct llama-cpp-python (parallel, KV-cache reuse)
  - `openai`          — any OpenAI-compatible HTTP endpoint  (TODO)
  - `vllm`            — Linux + serious GPU                  (TODO)
"""

from __future__ import annotations

import os

from nexus.runtime.backends.base import Backend
from nexus.runtime.backends.ollama import OllamaBackend
from nexus.runtime.types import (
    ChatRequest,
    ChatResponse,
    Message,
    StreamEvent,
    StreamIter,
    ToolSpec,
)


_BACKENDS: dict[str, Backend] = {}


def _select() -> str:
    return (
        os.environ.get("NEXUS_BACKEND")
        or os.environ.get("ORACLE_BACKEND")
        or "ollama"
    ).lower()


def get_backend(name: str | None = None) -> Backend:
    """Return a singleton backend by name (defaults to env selection)."""
    key = (name or _select()).lower()
    if key in _BACKENDS:
        return _BACKENDS[key]
    if key == "ollama":
        _BACKENDS[key] = OllamaBackend()
    elif key == "llama_cpp":
        from nexus.runtime.backends.llama_cpp import LlamaCppBackend

        _BACKENDS[key] = LlamaCppBackend()
    else:
        raise ValueError(
            f"unknown backend {key!r} — valid: ollama, llama_cpp "
            "(openai / vllm coming)"
        )
    return _BACKENDS[key]


def available_backends() -> dict[str, bool]:
    """Return {name: is_installed} so CLI can show what's reachable."""
    out = {"ollama": OllamaBackend().is_available()}
    try:
        from nexus.runtime.backends.llama_cpp import LlamaCppBackend

        out["llama_cpp"] = LlamaCppBackend().is_available()
    except Exception:
        out["llama_cpp"] = False
    return out


__all__ = [
    "Backend",
    "ChatRequest",
    "ChatResponse",
    "Message",
    "StreamEvent",
    "StreamIter",
    "ToolSpec",
    "get_backend",
    "available_backends",
]
