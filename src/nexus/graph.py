"""Graph memory — GraphRAG-style personal knowledge graph.

Extracts (entity, relation, entity) triples from session turns + archival
memory, stores in SQLite, serves BFS queries. Sits alongside the vector
archival so we get BOTH "similar to X" (vector) and "connected to X"
(graph).

Storage: <ORACLE_HOME>/memory/graph.sqlite
  entities  (id TEXT PK, name TEXT, type TEXT)
  edges     (src TEXT, dst TEXT, kind TEXT, weight REAL, source TEXT, ts REAL)

Commands:
  nexus graph ingest [thread_id]   extract triples from one or all threads
  nexus graph query <entity>        BFS from an entity
  /graph <entity>                   same, inside the REPL

Tool exposed to the agent:
  retrieve_graph(entity, depth=2)   returns connected entities + source turns
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from collections import deque
from pathlib import Path

from langchain_core.tools import tool

from nexus.config import settings


EXTRACTION_SYSTEM = """\
You extract knowledge-graph triples from a conversation turn.
Return STRICT JSON:
{"triples": [{"s": "subject", "r": "relation", "o": "object"}, ...]}

Rules:
- Each entity is a short noun phrase (3-5 words max).
- Relations are verbs or short verb phrases ("founded", "uses", "owns",
  "built with", "lives in").
- Only include triples strongly supported by the text. 0-5 triples.
- No meta-triples ("user said X"). Extract facts about the world.
- If no meaningful triples, return {"triples": []}.
- Return JSON only, no prose.
"""


def _db_path() -> Path:
    p = settings.oracle_home / "memory" / "graph.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(_db_path()))
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT
        );
        CREATE TABLE IF NOT EXISTS edges (
            src TEXT NOT NULL,
            dst TEXT NOT NULL,
            kind TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            source TEXT,
            ts REAL
        );
        CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
        CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);
        CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
    """)
    return c


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")[:80]


def _extract(text: str, model: str | None = None) -> list[dict]:
    """Call the fast model to extract triples. Returns [] on any failure."""
    try:
        import ollama as _ollama

        client = _ollama.Client(host=settings.oracle_ollama_host)
        kw: dict = dict(
            model=model or settings.oracle_fast_model,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM},
                {"role": "user", "content": f"TURN:\n{text[:2000]}\n\nReturn JSON only."},
            ],
            options={"temperature": 0.1, "num_predict": 600, "num_ctx": 2048},
        )
        try:
            r = client.chat(**kw, think=False)
        except TypeError:
            r = client.chat(**kw)
        raw = (r["message"]["content"] or "").strip()
        s = raw.find("{")
        e = raw.rfind("}")
        if s < 0 or e <= s:
            return []
        obj = json.loads(raw[s:e + 1])
        return [
            t for t in obj.get("triples", [])
            if isinstance(t, dict) and t.get("s") and t.get("r") and t.get("o")
        ]
    except Exception:
        return []


def _store_triples(triples: list[dict], *, source: str) -> int:
    if not triples:
        return 0
    now = time.time()
    with _conn() as c:
        for t in triples:
            s_name = str(t["s"]).strip()[:120]
            o_name = str(t["o"]).strip()[:120]
            r_kind = str(t["r"]).strip()[:60].lower()
            if not (s_name and o_name and r_kind):
                continue
            s_id = _slug(s_name)
            o_id = _slug(o_name)
            if not (s_id and o_id):
                continue
            c.execute(
                "INSERT OR IGNORE INTO entities(id, name, type) VALUES (?, ?, ?)",
                (s_id, s_name, ""),
            )
            c.execute(
                "INSERT OR IGNORE INTO entities(id, name, type) VALUES (?, ?, ?)",
                (o_id, o_name, ""),
            )
            c.execute(
                "INSERT INTO edges(src, dst, kind, weight, source, ts) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (s_id, o_id, r_kind, 1.0, source, now),
            )
    return len(triples)


def ingest_thread(thread_id: str, *, limit: int = 200) -> dict:
    """Extract triples from every user + assistant turn in a thread."""
    from nexus.sessions import read_thread

    events = read_thread(thread_id, limit=limit)
    stored = 0
    considered = 0
    for e in events:
        kind = e.get("kind")
        if kind not in {"user", "assistant"}:
            continue
        text = str(e.get("content", ""))
        if len(text.strip()) < 40:
            continue
        considered += 1
        triples = _extract(text)
        stored += _store_triples(triples, source=f"thread:{thread_id}:ts={e.get('ts')}")
    return {"thread_id": thread_id, "events_considered": considered, "triples_stored": stored}


def ingest_all() -> dict:
    """Ingest every recorded thread. Best-effort; slow."""
    from nexus.sessions import list_threads

    out = {"threads": 0, "triples_stored": 0}
    for tid in list_threads():
        r = ingest_thread(tid)
        out["threads"] += 1
        out["triples_stored"] += r["triples_stored"]
    return out


def query(entity: str, depth: int = 2, *, limit: int = 40) -> dict:
    """BFS from `entity` up to `depth` hops. Returns neighbors + edges."""
    eid = _slug(entity)
    if not eid:
        return {"entity": entity, "matches": 0, "edges": [], "neighbors": []}

    with _conn() as c:
        # Fuzzy match the entity if exact slug misses
        row = c.execute("SELECT id, name FROM entities WHERE id = ?", (eid,)).fetchone()
        if not row:
            hit = c.execute(
                "SELECT id, name FROM entities WHERE name LIKE ? LIMIT 1",
                (f"%{entity}%",),
            ).fetchone()
            if hit:
                eid = hit["id"]
                entity = hit["name"]
            else:
                return {"entity": entity, "matches": 0, "edges": [], "neighbors": []}

        visited: set[str] = {eid}
        edges: list[dict] = []
        frontier = deque([(eid, 0)])
        while frontier and len(edges) < limit:
            node, d = frontier.popleft()
            if d >= depth:
                continue
            out = c.execute(
                "SELECT src, dst, kind, source, ts FROM edges WHERE src = ? OR dst = ?",
                (node, node),
            ).fetchall()
            for row in out:
                other = row["dst"] if row["src"] == node else row["src"]
                edges.append({
                    "from": row["src"],
                    "to": row["dst"],
                    "kind": row["kind"],
                    "source": row["source"],
                    "ts": row["ts"],
                })
                if other not in visited:
                    visited.add(other)
                    frontier.append((other, d + 1))
                if len(edges) >= limit:
                    break

        # Resolve names for display
        if visited:
            placeholder = ",".join("?" for _ in visited)
            names = {
                row["id"]: row["name"]
                for row in c.execute(
                    f"SELECT id, name FROM entities WHERE id IN ({placeholder})",
                    tuple(visited),
                ).fetchall()
            }
        else:
            names = {}

    return {
        "entity": entity,
        "matches": 1,
        "neighbors": sorted(names.values()),
        "edges": [
            {
                "from": names.get(e["from"], e["from"]),
                "to": names.get(e["to"], e["to"]),
                "kind": e["kind"],
                "source": e["source"],
            }
            for e in edges
        ],
    }


def stats() -> dict:
    with _conn() as c:
        ent = c.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        edg = c.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    return {"entities": int(ent), "edges": int(edg)}


# ---------- agent-callable tool ----------


@tool
def retrieve_graph(entity: str, depth: int = 2) -> dict:
    """Query Trinity Nexus's personal knowledge graph.

    Returns entities connected to `entity` within `depth` hops + the edges
    (with their relation label and source turn). Complements `retrieve_notes`
    (vector similarity) by answering "what connects A to B" style questions.

    The graph is built from past conversations via nightly or on-demand
    ingestion (`nexus graph ingest`).
    """
    return query(entity, depth=max(1, min(int(depth), 4)), limit=30)
