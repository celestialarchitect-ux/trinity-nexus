"""LangChain tool wrapper so the agent can query the retrieval index."""

from langchain_core.tools import tool

from nexus.retrieval.index import RetrievalIndex


@tool
def retrieve_notes(query: str, k: int = 4) -> list[dict]:
    """Semantic search over the user's ingested notes/docs. Returns top-k chunks.

    Args:
        query: what to look up in the user's notes.
        k: how many results to return (default 4, max 10).
    """
    idx = RetrievalIndex()
    k = max(1, min(int(k), 10))
    hits = idx.query(query, k=k)
    return [
        {
            "source": h["source"],
            "chunk": h["chunk_idx"],
            "content": h["content"][:800],
        }
        for h in hits
    ]
