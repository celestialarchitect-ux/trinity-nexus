"""Archival memory — LanceDB vector store for long-term semantic recall.

Embeddings via bge-m3 (Ollama). Store anything that's worth remembering across
conversations: facts about the user, project notes, decisions, lessons learned.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

import lancedb
import numpy as np
import pyarrow as pa

from oracle.config import settings
from oracle.memory.embeddings import Embedder, get_embedder


class ArchivalMemory:
    """LanceDB-backed long-term vector memory."""

    TABLE = "archival"

    def __init__(
        self,
        path: Path | None = None,
        embedder: Embedder | None = None,
    ):
        self.path = path or (settings.oracle_home / "memory" / "archival.lance")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder or get_embedder()
        self.db = lancedb.connect(str(self.path))
        self._ensure_table()

    def _ensure_table(self) -> None:
        # Probe dimension once with a short embed
        probe = self.embedder.embed("dimension probe")
        dim = int(probe.shape[0])
        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("ts", pa.float64()),
                pa.field("content", pa.string()),
                pa.field("tags", pa.string()),  # comma-separated
                pa.field("source", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), dim)),
            ]
        )
        try:
            self._table = self.db.open_table(self.TABLE)
        except Exception:
            self._table = self.db.create_table(self.TABLE, schema=schema)

    def store(
        self,
        content: str,
        *,
        tags: list[str] | None = None,
        source: str = "user",
    ) -> str:
        vec = self.embedder.embed(content)
        mid = str(uuid.uuid4())
        self._table.add(
            [
                {
                    "id": mid,
                    "ts": time.time(),
                    "content": content,
                    "tags": ",".join(tags or []),
                    "source": source,
                    "vector": vec.tolist(),
                }
            ]
        )
        return mid

    def query(self, text: str, k: int = 5) -> list[dict[str, Any]]:
        if self._table.count_rows() == 0:
            return []
        q = self.embedder.embed(text).tolist()
        results = (
            self._table.search(q)
            .limit(k)
            .to_list()
        )
        # Drop the raw vector from the result payload for readability
        for r in results:
            r.pop("vector", None)
        return results

    def count(self) -> int:
        return int(self._table.count_rows())

    def all(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._table.to_pandas().head(limit).to_dict(orient="records")
        for r in rows:
            r.pop("vector", None)
        return rows

    def delete(self, memory_id: str) -> None:
        self._table.delete(f"id = '{memory_id}'")
