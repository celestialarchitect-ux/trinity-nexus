"""Retrieval layer — ingest notes/docs into LanceDB, query semantically."""

from nexus.retrieval.index import RetrievalIndex
from nexus.retrieval.ingest import ingest_directory

__all__ = ["RetrievalIndex", "ingest_directory"]
