"""Ingest a directory into the retrieval index.

Walks the dir, reads text-like files, chunks them, and upserts into LanceDB.
Skips binaries, hidden files, and oversized files. No PDF handling in v0.1 —
convert PDFs to txt first with `pdftotext`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Iterable

from oracle.retrieval.index import RetrievalIndex

logger = logging.getLogger(__name__)

TEXT_EXTS = {".md", ".txt", ".py", ".json", ".yaml", ".yml", ".toml", ".rst"}
SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
}
SKIP_DIR_SUFFIXES = (".egg-info",)
MAX_FILE_BYTES = 1_500_000  # ~1.5MB


def _chunk(text: str, *, size: int = 1200, overlap: int = 150) -> list[str]:
    """Character-based chunking with overlap. Good enough for v0.1.

    Future: token-aware chunking with the tokenizer that matches the embed model.
    """
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


def _walk(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if any(part.endswith(SKIP_DIR_SUFFIXES) for part in p.parts):
            continue
        if p.name.startswith("."):
            continue
        if p.suffix.lower() not in TEXT_EXTS:
            continue
        try:
            if p.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield p


def ingest_directory(
    directory: str | Path,
    *,
    index: RetrievalIndex | None = None,
    progress: Callable[[int, int, Path], None] | None = None,
) -> dict:
    """Ingest a directory. Returns {files, chunks, bytes}."""
    root = Path(directory).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(root)
    idx = index or RetrievalIndex()

    files = list(_walk(root))
    total_chunks = 0
    total_bytes = 0
    for i, p in enumerate(files, 1):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.warning("read fail %s: %s", p, e)
            continue
        total_bytes += len(text.encode("utf-8", errors="ignore"))
        chunks = _chunk(text)
        try:
            n = idx.upsert(source=str(p), chunks=chunks)
            total_chunks += n
        except Exception as e:
            logger.warning("upsert fail %s: %s", p, e)
            continue
        if progress:
            progress(i, len(files), p)

    return {
        "files": len(files),
        "chunks": total_chunks,
        "bytes": total_bytes,
        "index_total": idx.count(),
    }
