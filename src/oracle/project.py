"""ORACLE.md — per-project and global instruction files.

Analogue of Claude Code's CLAUDE.md. At agent-startup we look for:
  1. <cwd>/ORACLE.md, walking upward until a repo root or HOME
  2. ~/.oracle/ORACLE.md (global personal instructions)

Both are concatenated into the system prompt. This is the main way users
customize Oracle's behavior per project and per user.
"""

from __future__ import annotations

from pathlib import Path

MAX_INSTRUCTION_CHARS = 20_000


def _find_project_oracle_md(start: Path | None = None) -> Path | None:
    """Walk up from `start` (default cwd) looking for an ORACLE.md. Stops at HOME or the root."""
    here = (start or Path.cwd()).resolve()
    home = Path.home().resolve()
    stop_markers = {".git", ".hg", "pyproject.toml", "package.json"}

    seen_stop = False
    p = here
    while True:
        candidate = p / "ORACLE.md"
        if candidate.is_file():
            return candidate
        # Stop one level ABOVE the first repo-root-ish marker we see
        if seen_stop:
            break
        if any((p / m).exists() for m in stop_markers):
            seen_stop = True
        if p == home or p.parent == p:
            break
        p = p.parent
    return None


def _global_oracle_md() -> Path:
    return Path.home() / ".oracle" / "ORACLE.md"


def load_instructions(start: Path | None = None) -> str:
    """Return concatenated ORACLE.md contents (project + global), empty string if none."""
    parts: list[str] = []

    project = _find_project_oracle_md(start)
    if project:
        try:
            text = project.read_text(encoding="utf-8", errors="replace")
            parts.append(f"# Project instructions ({project})\n\n{text.strip()}")
        except Exception:
            pass

    global_md = _global_oracle_md()
    if global_md.is_file():
        try:
            text = global_md.read_text(encoding="utf-8", errors="replace")
            parts.append(f"# Personal instructions ({global_md})\n\n{text.strip()}")
        except Exception:
            pass

    joined = "\n\n---\n\n".join(parts)
    if len(joined) > MAX_INSTRUCTION_CHARS:
        joined = joined[:MAX_INSTRUCTION_CHARS] + "\n\n…[truncated]"
    return joined
