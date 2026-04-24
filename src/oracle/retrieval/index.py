"""LanceDB-backed retrieval index. Separate table from archival memory."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa

from oracle.config import settings
from oracle.memory.embeddings import Embedder, get_embedder


class RetrievalIndex:
    """Document chunks + embeddings. Used for grounded Q&A over user's corpus."""

    TABLE = "docs"

    def __init__(
        self,
        path: Path | None = None,
        embedder: Embedder | None = None,
    ):
        self.path = path or (settings.oracle_home / "retrieval" / "index.lance")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder or get_embedder()
        self.db = lancedb.connect(str(self.path))
        self._ensure_table()

    def _ensure_table(self) -> None:
        probe = self.embedder.embed("dimension probe")
        dim = int(probe.shape[0])
        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("ts", pa.float64()),
                pa.field("source", pa.string()),
                pa.field("chunk_idx", pa.int32()),
                pa.field("content", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), dim)),
            ]
        )
        try:
            self._table = self.db.open_table(self.TABLE)
        except Exception:
            self._table = self.db.create_table(self.TABLE, schema=schema)

    def upsert(self, *, source: str, chunks: list[str]) -> int:
        """Delete existing chunks for `source` then insert new."""
        self._table.delete(f"source = '{source}'")
        rows = []
        for i, chunk in enumerate(chunks):
            vec = self.embedder.embed(chunk).tolist()
            rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "ts": time.time(),
                    "source": source,
                    "chunk_idx": i,
                    "content": chunk,
                    "vector": vec,
                }
            )
        if rows:
            self._table.add(rows)
        return len(rows)

    def query(self, text: str, k: int = 5) -> list[dict[str, Any]]:
        if self._table.count_rows() == 0:
            return []
        q = self.embedder.embed(text).tolist()
        results = self._table.search(q).limit(k).to_list()
        for r in results:
            r.pop("vector", None)
        return results

    def count(self) -> int:
        return int(self._table.count_rows())

    def sources(self) -> list[str]:
        df = self._table.to_pandas()
        return sorted(df["source"].unique().tolist()) if len(df) > 0 else []

    def delete_source(self, source: str) -> None:
        self._table.delete(f"source = '{source}'")
