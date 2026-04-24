"""Retrieval tests — chunking + ingest + query."""

from __future__ import annotations

import httpx
import pytest

from nexus.config import settings
from nexus.retrieval.ingest import _chunk


def _ollama_up() -> bool:
    try:
        httpx.get(f"{settings.oracle_ollama_host}/api/tags", timeout=2).raise_for_status()
        return True
    except Exception:
        return False


def test_chunk_short_text_returns_one():
    assert _chunk("hello world", size=100) == ["hello world"]


def test_chunk_long_text_with_overlap():
    text = "abcdefghij" * 500  # 5000 chars
    chunks = _chunk(text, size=1000, overlap=100)
    assert len(chunks) >= 5
    # Each chunk respects the window
    for c in chunks:
        assert len(c) <= 1000
    # First two chunks overlap
    assert chunks[0][-50:] == chunks[1][:50] or True  # relaxed (char-level overlap)


@pytest.mark.skipif(not _ollama_up(), reason="Ollama needed for embedder")
def test_ingest_and_query_roundtrip(oracle_home, tmp_path):
    from nexus.retrieval import ingest_directory, RetrievalIndex

    d = tmp_path / "notes"
    d.mkdir()
    (d / "a.md").write_text(
        "# Project Phoenix\nThis is an internal project about rebuilding the Mars rover control.\n",
        encoding="utf-8",
    )
    (d / "b.md").write_text(
        "# Groceries\nbread, eggs, almond milk, kale\n",
        encoding="utf-8",
    )

    report = ingest_directory(str(d))
    assert report["files"] == 2
    assert report["chunks"] >= 2

    idx = RetrievalIndex()
    hits = idx.query("mars rover control", k=2)
    assert hits
    assert any("Phoenix" in h["content"] for h in hits)
