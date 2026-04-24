"""MemoryTiers — unified facade over core/recall/archival.

Every agent turn passes through this:

    tiers.log_turn(role, content)
    context_block = tiers.build_context(intent)

The context block is appended to the system prompt: core (always) + top-k
relevant archival memories + optional recent recall snippets.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from oracle.memory.archival import ArchivalMemory
from oracle.memory.core import CoreMemory
from oracle.memory.recall import RecallMemory


@dataclass
class MemoryContext:
    core: str
    archival_hits: list[dict]
    recall_recent: list[dict]

    def to_prompt_block(self) -> str:
        parts: list[str] = ["## core memory", self.core.strip()]

        if self.archival_hits:
            parts.append("\n## relevant long-term memory")
            for i, hit in enumerate(self.archival_hits, 1):
                tags = hit.get("tags", "")
                parts.append(
                    f"[{i}] {hit['content'].strip()}"
                    + (f"  _(tags: {tags})_" if tags else "")
                )

        if self.recall_recent:
            parts.append("\n## recent conversation context")
            for r in self.recall_recent[-6:]:  # last 6 turns max
                parts.append(f"- **{r['role']}**: {r['content'][:200]}")

        return "\n".join(parts)


class MemoryTiers:
    """Three-tier memory facade."""

    def __init__(self, base_path: Path | None = None):
        self.core = CoreMemory(
            path=base_path / "core.md" if base_path else None
        )
        self.recall = RecallMemory(
            path=base_path / "recall.sqlite" if base_path else None
        )
        self.archival = ArchivalMemory(
            path=base_path / "archival.lance" if base_path else None
        )

    def log_turn(
        self,
        *,
        role: str,
        content: str,
        thread_id: str = "default",
        meta: dict | None = None,
    ) -> int:
        return self.recall.log(
            role=role, content=content, thread_id=thread_id, meta=meta
        )

    def remember(
        self, fact: str, tags: list[str] | None = None, source: str = "agent"
    ) -> str:
        """Store a long-term fact into archival memory."""
        return self.archival.store(fact, tags=tags, source=source)

    def build_context(
        self,
        intent: str,
        *,
        thread_id: str = "default",
        archival_k: int = 4,
        recall_n: int = 6,
    ) -> MemoryContext:
        return MemoryContext(
            core=self.core.read(),
            archival_hits=self.archival.query(intent, k=archival_k),
            recall_recent=list(reversed(self.recall.recent(recall_n, thread_id))),
        )

    def stats(self) -> dict[str, int | str]:
        return {
            "core_chars": self.core.size(),
            "recall_turns": self.recall.count(),
            "archival_memories": self.archival.count(),
        }

    def close(self) -> None:
        self.recall.close()
