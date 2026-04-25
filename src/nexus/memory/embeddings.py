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
        # 4s, not 30s: every turn embeds the user prompt + retrieval queries.
        # Healthy bge-m3 returns in <1s. When Ollama is stuck loading the
        # embedder (seen on this Windows + RTX 4090 + co-resident gpt-oss:20b
        # at 16K), the request never completes — we'd rather give up fast
        # and use the zero-vector fallback than block the user.
        self._client = httpx.Client(timeout=4.0)
        self._dim: int | None = None  # learned on first success
        self._consecutive_failures = 0
        self._tripped = False  # circuit-breaker: skip calls once we've given up

    def _call(self, text: str, *, keep_alive: str) -> tuple[float, ...] | None:
        try:
            r = self._client.post(
                f"{self.host}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text,
                    "keep_alive": keep_alive,
                    # Pin to bge-m3's training context. Ollama otherwise
                    # silently applies a global default num_ctx (observed:
                    # 32768) to the embedder load, which triggers
                    # "requested context size too large for model" and
                    # makes the load process hang waiting for an oversized
                    # KV cache that never materializes. 8192 = bge-m3's
                    # actual n_ctx_train.
                    "options": {"num_ctx": 8192},
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
        # Circuit breaker: once tripped, return zero vectors for the rest of
        # the session without calling Ollama. Avoids a full retry-storm on
        # every turn when the embedder is wedged. Process restart resets it.
        if self._tripped:
            return tuple([0.0] * (self._dim or _DIM_FALLBACK))

        # First try with the configured keep_alive.
        vec = self._call(text, keep_alive=settings.oracle_embed_keepalive)
        if vec:
            self._consecutive_failures = 0
            return vec

        # First failure: trip the breaker immediately and return zero
        # vector. Skipping the previous retry-with-keep_alive=0s because
        # when Ollama is stuck loading bge-m3 (the failure mode this
        # circuit breaker exists for), the retry just costs another full
        # timeout window without improving anything. Process restart
        # resets the breaker — a recovered Ollama gets re-tested cleanly
        # next session.
        self._consecutive_failures += 1
        if not self._tripped:
            logger.error(
                "embedder %s unavailable; tripped circuit breaker. Returning "
                "zero vectors for the rest of this session — retrieval is "
                "degraded but the agent will continue. Restart `nexus` once "
                "Ollama recovers to retry.",
                self.model,
            )
            self._tripped = True
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
