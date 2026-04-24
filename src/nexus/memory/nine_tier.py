"""Constitution §06 — 9-tier memory.

Each tier is a plain markdown file under `<ORACLE_HOME>/memory/`. Users
(or Nexus itself) edit them directly. They are injected into the system
prompt per turn in a compact form (header + first N chars) so they
influence behavior without blowing the ctx budget.

Tiers:
  1. CORE IDENTITY                core.md
  2. ACTIVE PROJECTS              projects.md
  3. STRATEGIC CONTEXT            strategic.md
  4. CREATIVE WORLD               creative.md
  5. TECHNICAL CONTEXT            technical.md
  6. PERSONAL OPERATING SYSTEM    personal_os.md
  7. PROTECTED NOTES              protected.md
  8. SESSION THREADS              threads.md
  9. ARTIFACT INDEX               artifacts.md
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nexus.config import settings


TIER_FILES: dict[str, str] = {
    "core":        "core.md",
    "projects":    "projects.md",
    "strategic":   "strategic.md",
    "creative":    "creative.md",
    "technical":   "technical.md",
    "personal":    "personal_os.md",
    "protected":   "protected.md",
    "threads":     "threads.md",
    "artifacts":   "artifacts.md",
}

TIER_LABELS: dict[str, str] = {
    "core":      "§1 CORE IDENTITY",
    "projects":  "§2 ACTIVE PROJECTS",
    "strategic": "§3 STRATEGIC CONTEXT",
    "creative":  "§4 CREATIVE WORLD",
    "technical": "§5 TECHNICAL CONTEXT",
    "personal":  "§6 PERSONAL OS",
    "protected": "§7 PROTECTED NOTES",
    "threads":   "§8 SESSION THREADS",
    "artifacts": "§9 ARTIFACT INDEX",
}

TIER_SEEDS: dict[str, str] = {
    "core":       "# Core Identity\n(name, long-term goals, mission, orientation, tone.)\n",
    "projects":   "# Active Projects\n(businesses, books, apps, offers, launches, current priorities.)\n",
    "strategic":  "# Strategic Context\n(market, differentiators, competitors, risks, timelines, leverage.)\n",
    "creative":   "# Creative World\n(language, symbols, brand voice, aesthetics, mythology.)\n",
    "technical":  "# Technical Context\n(stacks, APIs, repos, deployment, infrastructure decisions.)\n",
    "personal":   "# Personal Operating System\n(habits, routines, energy patterns, decision style.)\n",
    "protected":  "# Protected Notes\n(sensitive: legal, financial, medical, relational. Handle with care.)\n",
    "threads":    "# Session Threads\n(open loops, unresolved questions, pending decisions.)\n",
    "artifacts":  "# Artifact Index\n(documents, prompts, code files, decks, generated assets.)\n",
}


@dataclass
class Tier:
    key: str
    label: str
    path: Path

    def read(self) -> str:
        try:
            return self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def write(self, content: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(content.strip() + "\n", encoding="utf-8")

    def append(self, line: str) -> None:
        current = self.read().rstrip()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(current + "\n" + line.strip() + "\n", encoding="utf-8")

    def size(self) -> int:
        return len(self.read())


class NineTier:
    """Facade over the nine markdown-tier memory files."""

    def __init__(self, base: Path | None = None):
        self.base = base or (settings.oracle_home / "memory")
        self.base.mkdir(parents=True, exist_ok=True)
        self.tiers: dict[str, Tier] = {}
        for key, fname in TIER_FILES.items():
            path = self.base / fname
            if not path.exists():
                path.write_text(TIER_SEEDS[key], encoding="utf-8")
            self.tiers[key] = Tier(key=key, label=TIER_LABELS[key], path=path)

    def get(self, key: str) -> Tier | None:
        return self.tiers.get(key)

    def all(self) -> list[Tier]:
        return list(self.tiers.values())

    def stats(self) -> dict[str, int]:
        return {t.key: t.size() for t in self.all()}

    def to_prompt_block(self, *, max_chars_each: int = 800) -> str:
        """Compact serialization for injection into the system prompt.

        Each tier contributes at most `max_chars_each` chars; empty seeds and
        whitespace-only tiers are skipped so we don't waste context.
        """
        parts: list[str] = ["## PERSISTENT MEMORY (9-tier · §06)"]
        for t in self.all():
            raw = t.read().strip()
            if not raw or raw == TIER_SEEDS[t.key].strip():
                continue
            block = raw[:max_chars_each]
            if len(raw) > max_chars_each:
                block += "\n…[truncated]"
            parts.append(f"\n### {t.label}\n{block}")
        if len(parts) == 1:
            return ""  # all seeds → nothing meaningful to inject
        return "\n".join(parts)
