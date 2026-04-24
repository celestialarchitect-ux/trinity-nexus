"""Collects interactions from live agent turns into a training log."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from nexus.config import settings


@dataclass
class Interaction:
    ts: float
    thread_id: str
    intent: str
    local_response: str
    local_confidence: float = 0.5
    user_correction: str | None = None
    outcome: str = "unknown"  # success | partial | failure | unknown
    feedback_score: float = 0.5
    tools_used: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


class InteractionCollector:
    """Append-only JSONL log of every turn.

    The orchestrator samples from this log nightly to generate teacher gold.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or (
            settings.oracle_home / "distillation" / "interactions.jsonl"
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, ix: Interaction) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(ix)) + "\n")

    def log_turn(
        self,
        *,
        intent: str,
        response: str,
        thread_id: str = "default",
        confidence: float = 0.5,
        tools_used: list[str] | None = None,
        meta: dict | None = None,
    ) -> None:
        ix = Interaction(
            ts=time.time(),
            thread_id=thread_id,
            intent=intent,
            local_response=response,
            local_confidence=confidence,
            tools_used=tools_used or [],
            meta=meta or {},
        )
        self.log(ix)

    def read_since(self, since_ts: float) -> list[Interaction]:
        if not self.path.exists():
            return []
        out: list[Interaction] = []
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    if row.get("ts", 0) >= since_ts:
                        out.append(Interaction(**row))
                except Exception:
                    continue
        return out

    def count(self) -> int:
        if not self.path.exists():
            return 0
        n = 0
        with self.path.open(encoding="utf-8") as f:
            for _ in f:
                n += 1
        return n
