"""Graph memory layer — GraphRAG / cognee style. SCAFFOLD.

Status: not yet implemented. This module reserves the namespace and
documents the design so the next-session build lands cleanly.

Plan (next build burst):
  1. Nightly extraction pass (hook: post_session or `nexus reflect --graph`)
     - feed each session's archival turn into a small extraction prompt
     - emit (entity, relation, entity) triples with source_ts + thread_id
  2. Store in SQLite + in-memory networkx for traversal
     - tables: entities(id, name, type), relations(src, dst, kind, weight, ts)
  3. New tool `retrieve_graph(entity, depth=2)` sitting next to retrieve_notes
     - returns the subgraph + the sentences that produced each edge
  4. Agent system-prompt addition: graph results go in a new memory tier
  5. Periodic community detection to surface clusters (who/what/when)

Key dependencies: networkx is lightweight and already common.
Model choice for extraction: the FAST model, low temp, JSON-mode output.

Until implemented, `retrieve_graph` raises a helpful error pointing here.
"""

from __future__ import annotations


def retrieve_graph(entity: str, depth: int = 2) -> dict:
    raise NotImplementedError(
        "graph memory is scaffolded for the next session build. "
        "Until then: use retrieve_notes (vector) + archival recall. "
        "Design doc: src/nexus/graph.py"
    )
