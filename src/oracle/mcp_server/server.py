"""MCP server implementation using the official mcp SDK.

Exposes:
  Tools:
    - oracle_ask            run a full agentic turn on the local Oracle
    - oracle_retrieve       semantic search over the user's ingested corpus
    - oracle_recall         semantic search over archival memory
    - oracle_remember       store a fact in archival memory
    - oracle_skill_list     enumerate the skill library
    - oracle_skill_run      run a specific skill by id
  Resources:
    - oracle://core-memory  the core memory markdown block
    - oracle://skills       a JSON listing of all skills
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from oracle import __version__
from oracle.config import settings


def build_server() -> FastMCP:
    mcp = FastMCP("oracle")

    # ----------------------------- Tools -----------------------------

    @mcp.tool()
    def oracle_ask(prompt: str, thread_id: str = "mcp-default") -> str:
        """Ask Oracle a question via its full agentic loop (memory + tools)."""
        from oracle.agent import Oracle

        oracle = Oracle(thread_id=thread_id)
        try:
            return oracle.ask(prompt)
        finally:
            oracle.close()

    @mcp.tool()
    def oracle_retrieve(query: str, k: int = 5) -> list[dict]:
        """Semantic search over the user's ingested documents."""
        from oracle.retrieval import RetrievalIndex

        idx = RetrievalIndex()
        hits = idx.query(query, k=k)
        return [
            {"source": h["source"], "chunk": h["chunk_idx"], "content": h["content"]}
            for h in hits
        ]

    @mcp.tool()
    def oracle_recall(query: str, k: int = 5) -> list[dict]:
        """Semantic search over Oracle's long-term archival memory."""
        from oracle.memory import MemoryTiers

        t = MemoryTiers()
        return t.archival.query(query, k=k)

    @mcp.tool()
    def oracle_remember(fact: str, tags: list[str] | None = None) -> dict:
        """Store an important fact in Oracle's long-term archival memory."""
        from oracle.memory import MemoryTiers

        t = MemoryTiers()
        mid = t.remember(fact, tags=tags or [], source="mcp")
        return {"memory_id": mid, "ok": True}

    @mcp.tool()
    def oracle_skill_list() -> list[dict]:
        """List every skill in Oracle's library with confidence + usage stats."""
        from oracle.skills import SkillRegistry

        reg = SkillRegistry()
        reg.load_all()
        return [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "tags": s.tags,
                "origin": s.origin,
                "confidence": round(s.confidence, 3),
                "usage_count": s.usage_count,
            }
            for s in sorted(reg.all(), key=lambda x: x.id)
        ]

    @mcp.tool()
    def oracle_skill_run(skill_id: str, inputs_json: str) -> dict:
        """Execute a specific Oracle skill by id.

        Args:
            skill_id: one of the ids from oracle_skill_list
            inputs_json: JSON string matching the skill's inputs schema
        """
        import ollama

        from oracle.memory import MemoryTiers
        from oracle.skills import SkillContext, SkillRegistry

        try:
            inputs: dict[str, Any] = json.loads(inputs_json)
        except Exception as e:
            return {"ok": False, "error": f"inputs_json not valid JSON: {e}"}

        reg = SkillRegistry()
        reg.load_all()
        skill = reg.get(skill_id)
        if not skill:
            return {"ok": False, "error": f"unknown skill: {skill_id}"}

        tiers = MemoryTiers()
        client = ollama.Client(host=settings.oracle_ollama_host)
        ctx = SkillContext(
            llm=client,
            model=settings.oracle_primary_model,
            memory=tiers,
            user=settings.oracle_user,
            thread_id="mcp",
        )
        result = skill.run(ctx, inputs)
        reg.save_stats()
        return {
            "ok": result.ok,
            "output": result.output,
            "elapsed_ms": round(result.elapsed_ms, 1),
            "error": result.error,
        }

    # ----------------------------- Resources -----------------------------

    @mcp.resource("oracle://core-memory")
    def core_memory() -> str:
        """Oracle's core memory — facts always injected into the system prompt."""
        from oracle.memory import MemoryTiers

        return MemoryTiers().core.read()

    @mcp.resource("oracle://skills")
    def skills_json() -> str:
        """JSON listing of every skill in Oracle's library."""
        from oracle.skills import SkillRegistry

        reg = SkillRegistry()
        reg.load_all()
        return json.dumps(
            [
                {
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "tags": s.tags,
                    "confidence": round(s.confidence, 3),
                }
                for s in sorted(reg.all(), key=lambda x: x.id)
            ],
            indent=2,
        )

    return mcp


def run_stdio() -> None:
    """Run the MCP server over stdio. For use by Claude Desktop / Cursor."""
    server = build_server()
    server.run(transport="stdio")


if __name__ == "__main__":
    run_stdio()
