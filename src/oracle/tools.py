"""Built-in tools for the Oracle agent.

Week 1 scope: a small, trustworthy toolset so the agent loop works end-to-end.
Week 2 scope: skill library (ToolUniverse + ToolAlpaca + self-rewritten skills)
will replace this with ~2K retrievable skills.
"""

from __future__ import annotations

import datetime as _dt
import platform
import subprocess
from typing import Any

from langchain_core.tools import tool


@tool
def get_time(timezone: str = "local") -> str:
    """Return the current date and time. `timezone` accepts 'local' or 'utc'."""
    now = _dt.datetime.now(_dt.UTC) if timezone == "utc" else _dt.datetime.now()
    return now.isoformat(timespec="seconds")


@tool
def system_info() -> dict[str, str]:
    """Return host machine information: OS, CPU, Python version."""
    return {
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "node": platform.node(),
    }


@tool
def run_command(command: str, timeout_sec: int = 30) -> dict[str, Any]:
    """Execute a shell command on the host machine. Returns stdout, stderr, returncode.

    SAFETY: in Week 1 this runs unsandboxed (your own machine). In Week 2 it
    moves to a Docker/E2B sandbox for any LLM-generated code.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        return {
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-2000:],
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "timeout", "returncode": -1}
    except Exception as e:
        return {"stdout": "", "stderr": f"{type(e).__name__}: {e}", "returncode": -2}


@tool
def remember(fact: str, tags: str = "") -> str:
    """Store an important fact in Oracle's long-term archival memory.

    Args:
        fact: the fact to remember.
        tags: comma-separated tags, e.g. "decision,project:oracle".
    """
    from oracle.memory import MemoryTiers

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    mid = MemoryTiers().remember(fact, tags=tag_list, source="agent")
    return f"remembered: id={mid} {fact[:80]}"


# Registry used by the agent — order doesn't matter for retrieval but does for
# context-window cost. Keep this list tight (~5-20 tools in the hot set).
BUILTIN_TOOLS = [get_time, system_info, run_command, remember]
