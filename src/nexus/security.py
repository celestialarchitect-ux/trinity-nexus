"""Security governor (§29) — runtime guardrails.

Three layers:
  1. Safe mode (NEXUS_SAFE=1)
       - blocks run_command entirely
       - blocks write_file / edit_file / apply_diff outside NEXUS_WRITE_ALLOW
       - blocks spawn_agent
  2. Untrusted-tool taint
       - any content returned from web_fetch / web_search / frontier_ask
         is wrapped with a "[UNTRUSTED]" marker so the agent sees it
         and refuses to treat it as instructions (§10 Truth Engine)
  3. Destructive-op gate (already in tools.py) with /dangerous override

Nothing in here is a substitute for OS-level permissions. The goal is to
stop the agent from being tricked by prompt injection in a fetched page
or a malicious frontier response into destroying local state.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path


def is_safe_mode() -> bool:
    return os.environ.get("NEXUS_SAFE", "0") == "1"


def write_allowed(path: str) -> bool:
    """Under safe mode, only paths matching NEXUS_WRITE_ALLOW (colon-sep
    globs) can be written. Otherwise everything is allowed."""
    if not is_safe_mode():
        return True
    patterns = os.environ.get("NEXUS_WRITE_ALLOW", "")
    if not patterns:
        return False
    abs_path = str(Path(path).expanduser().resolve())
    for pat in patterns.split(os.pathsep):
        if fnmatch.fnmatch(abs_path, pat.strip()):
            return True
    return False


def taint(text: str, *, source: str) -> str:
    """Wrap an untrusted string with a prompt-injection guard.

    Models instructed via the constitution (§10 + §20) to treat anything
    inside UNTRUSTED blocks as data — never as instructions.
    """
    if not text:
        return ""
    head = f"<UNTRUSTED source={source}>"
    tail = "</UNTRUSTED>"
    return head + "\n" + text + "\n" + tail


# Heuristics — cheap first-pass detection of injection attempts in fetched
# web content or tool output before we pipe it to the model. These are not
# a substitute for the taint marker; they log a warning for audit.
_INJECTION_PATTERNS = [
    r"ignore (?:all|previous|prior) (?:instructions|prompts)",
    r"disregard (?:all|previous|prior)",
    r"new instructions",
    r"system prompt",
    r"you are now",
    r"(?:please )?run (?:the )?command",
    r"execute(?: the)? code",
    r"curl .+? \| (?:bash|sh)",
    r"rm -rf",
    r"NEXUS_ALLOW_DANGEROUS",
]


def scan_for_injection(text: str) -> list[str]:
    """Return any injection-pattern matches. Empty list = clean."""
    import re
    if not text:
        return []
    hits: list[str] = []
    for pat in _INJECTION_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            hits.append(pat)
    return hits
