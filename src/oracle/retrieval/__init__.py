"""Retrieval layer — ingest notes/docs into LanceDB, query semantically."""

from oracle.retrieval.index import RetrievalIndex
from oracle.retrieval.ingest import ingest_directory

__all__ = ["RetrievalIndex", "ingest_directory"]
