"""Embeddings via Ollama bge-m3. Cached so identical strings don't re-embed."""

from __future__ import annotations

import functools
import hashlib

import httpx
import numpy as np

from nexus.config import settings


class Embedder:
    """Thin wrapper over Ollama /api/embeddings. Synchronous, cached in-memory."""

    def __init__(self, model: str | None = None, host: str | None = None):
        self.model = model or settings.oracle_embed_model
        self.host = host or settings.oracle_ollama_host
        self._client = httpx.Client(timeout=30.0)

    @functools.lru_cache(maxsize=4096)
    def _embed_cached(self, text_hash: str, text: str) -> tuple[float, ...]:
        r = self._client.post(
            f"{self.host}/api/embeddings",
            json={
                "model": self.model,
                "prompt": text,
                "keep_alive": settings.oracle_embed_keepalive,
            },
        )
        r.raise_for_status()
        return tuple(r.json()["embedding"])

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
