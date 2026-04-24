"""Core memory — a small set of facts always injected into the system prompt.

This is the user's identity + operating preferences + current goals. The LLM
sees it on every turn. Keep it tight (< 2000 chars).

Letta calls this the "persona + human" block. We keep it as a single markdown
file the user can edit directly.
"""

from __future__ import annotations

from pathlib import Path

from nexus.config import settings

DEFAULT_CORE = """\
# user
name: {user}
device: {device}

# preferences
- respond directly; no filler, no trailing summaries
- when uncertain, say so with a confidence level
- use tools when they help; do not narrate unless asked

# goals (update as they change)
- (none yet — add via `oracle memory core add "…"`)

# dont
- do not apologize reflexively
- do not ask permission for reversible local actions
"""


class CoreMemory:
    """Markdown facts file. Always included at the top of the system prompt."""

    def __init__(self, path: Path | None = None):
        self.path = path or (settings.oracle_home / "memory" / "core.md")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(
                DEFAULT_CORE.format(
                    user=settings.oracle_user,
                    device=settings.oracle_device_name,
                ),
                encoding="utf-8",
            )

    def read(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def write(self, content: str) -> None:
        self.path.write_text(content.strip() + "\n", encoding="utf-8")

    def append(self, line: str) -> None:
        text = self.read().rstrip()
        self.path.write_text(text + "\n" + line.strip() + "\n", encoding="utf-8")

    def size(self) -> int:
        return len(self.read())
