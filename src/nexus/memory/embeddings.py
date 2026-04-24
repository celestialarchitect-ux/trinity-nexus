"""Embeddings via Ollama bge-m3. Cached in-memory, resilient to VRAM pressure.

Ollama returns HTTP 500 with "memory allocation failed" when a big primary
model leaves insufficient VRAM for the embedder. We retry once with
keep_alive=0s (forces any cached embedder to unload and reload cleanly),
and fall back to a zero-vector if it still fails — that lets the agent
continue instead of crashing the turn.
"""

from __future__ import annotations

import functools
import hashlib
import logging
import time

import httpx
import numpy as np

from nexus.config import settings

logger = logging.getLogger(__name__)

_DIM_FALLBACK = 1024  # bge-m3 dimension; only used if every call fails


class Embedder:
    """Thin wrapper over Ollama /api/embeddings. Synchronous, cached in-memory."""

    def __init__(self, model: str | None = None, host: str | None = None):
        self.model = model or settings.oracle_embed_model
        self.host = host or settings.oracle_ollama_host
        self._client = httpx.Client(timeout=30.0)
        self._dim: int | None = None  # learned on first success

    def _call(self, text: str, *, keep_alive: str) -> tuple[float, ...] | None:
        try:
            r = self._client.post(
                f"{self.host}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text,
                    "keep_alive": keep_alive,
                },
            )
            if r.status_code >= 400:
                return None
            vec = tuple(r.json().get("embedding") or ())
            if vec:
                self._dim = len(vec)
            return vec or None
        except Exception:
            return None

    @functools.lru_cache(maxsize=4096)
    def _embed_cached(self, text_hash: str, text: str) -> tuple[float, ...]:
        # First try with the configured keep_alive.
        vec = self._call(text, keep_alive=settings.oracle_embed_keepalive)
        if vec:
            return vec

        # Retry once with keep_alive=0s — forces Ollama to unload and reload
        # the embedder cleanly, which recovers from VRAM-allocation failures.
        logger.warning(
            "embedder %s returned error; retrying with keep_alive=0s", self.model
        )
        time.sleep(0.3)
        vec = self._call(text, keep_alive="0s")
        if vec:
            return vec

        # Both failed. Return a zero-vector so the agent can continue —
        # archival queries degrade to "no hits" instead of crashing the turn.
        logger.error(
            "embedder %s unavailable after retry; returning zero vector", self.model
        )
        dim = self._dim or _DIM_FALLBACK
        return tuple([0.0] * dim)

    def embed(self, text: str) -> np.ndarray:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        vec = self._embed_cached(h, text)
        return np.array(vec, dtype=np.float32)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        return np.stack([self.embed(t) for t in texts])

    def close(self):
        self._client.close()


# Module-level singleton
_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder
