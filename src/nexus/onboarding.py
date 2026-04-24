"""Constitution §04 / §23 / §24 — onboarding + USER MAP.

First-run detection, opening prompt, and a structured USER MAP persisted
at `<ORACLE_HOME>/memory/user_map.md`. The USER MAP is injected into the
system prompt on every turn once it exists.

The orientation questions (§04) are asked by the REPL once, not by the
agent every turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path

from nexus.config import settings


OPENING_LINE = (
    "I am Trinity Nexus. I learn through use, but I begin by orienting to "
    "you. Tell me what you are building, what you want me to become for you, "
    "and whether you want speed, depth, precision, creativity, execution, "
    "or blunt truth as the default."
)


ORIENTATION_QUESTIONS = [
    ("mission",  "What are you building or trying to improve?"),
    ("role",     "What role should I play? (strategist / coder / researcher / operator / creative partner / critic / executor / all)"),
    ("mental",   "What should I always understand about how you think?"),
    ("priority", "Should I prioritize speed, depth, precision, creativity, execution, or blunt truth as default?"),
]


@dataclass
class UserMap:
    """§24 structure — serialized as markdown for user editability."""

    preferred_name: str = ""
    primary_mission: str = ""
    operating_role: str = ""
    mind: str = ""
    soul: str = ""
    body: str = ""
    current_priority: str = ""
    risks: str = ""
    next_best_action: str = ""
    memory_candidates: str = ""

    def to_markdown(self) -> str:
        return (
            "# USER MAP\n\n"
            f"**Preferred Name:** {self.preferred_name or '_unset_'}\n\n"
            f"**Primary Mission:** {self.primary_mission or '_unset_'}\n\n"
            f"**Operating Role:** {self.operating_role or '_unset_'}\n\n"
            "## Mind\n" + (self.mind or "_unset_") + "\n\n"
            "## Soul\n" + (self.soul or "_unset_") + "\n\n"
            "## Body\n" + (self.body or "_unset_") + "\n\n"
            f"**Current Priority:** {self.current_priority or '_unset_'}\n\n"
            f"**Risks:** {self.risks or '_unset_'}\n\n"
            f"**Next Best Action:** {self.next_best_action or '_unset_'}\n\n"
            f"**Memory Candidates:** {self.memory_candidates or '_unset_'}\n"
        )


def _map_path() -> Path:
    p = settings.oracle_home / "memory" / "user_map.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def is_onboarded() -> bool:
    p = _map_path()
    if not p.exists():
        return False
    body = p.read_text(encoding="utf-8")
    # Heuristic: at least one real field populated (not _unset_)
    return "_unset_" not in body.replace("_unset_", "", 1) or body.count("_unset_") < 5


def load_user_map() -> str:
    p = _map_path()
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def save_user_map(um: UserMap) -> Path:
    p = _map_path()
    p.write_text(um.to_markdown(), encoding="utf-8")
    return p


def to_prompt_block() -> str:
    """Inject the USER MAP into the system prompt if it exists."""
    body = load_user_map().strip()
    if not body:
        return ""
    return "## USER MAP (§24)\n" + body
