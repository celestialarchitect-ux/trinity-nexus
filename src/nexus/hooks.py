"""User-defined hooks — shell scripts invoked on lifecycle events.

Directory: ~/.nexus/hooks/
Scripts (chmod +x on unix; .bat / .ps1 also accepted):
    pre_prompt         before the agent receives the user turn
    post_response      after the agent emits its final message
    pre_tool           before a tool call fires (args: tool name, json args)
    post_tool          after a tool call returns (args: tool name, json result)
    pre_exit           before the REPL exits

Each hook receives structured JSON on stdin (one line) and its stdout is
captured (first 4 KB) as a diagnostic note only — the hook cannot alter
the pipeline. Hooks are non-fatal: errors get logged to `logs/hooks.log`
and execution continues.

Set NEXUS_HOOKS=off to disable entirely.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from nexus.config import settings


HOOKS_DIR = Path.home() / ".nexus" / "hooks"


def _log_path() -> Path:
    p = settings.oracle_log_dir / "hooks.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _candidates(event: str) -> list[Path]:
    if not HOOKS_DIR.exists():
        return []
    found: list[Path] = []
    for ext in ("", ".sh", ".bat", ".ps1"):
        p = HOOKS_DIR / f"{event}{ext}"
        if p.exists() and p.is_file():
            found.append(p)
    return found


def run(event: str, payload: dict | None = None, *, timeout_sec: float = 10.0) -> None:
    """Fire all hooks registered for `event`. Never raises."""
    if os.environ.get("NEXUS_HOOKS", "").lower() == "off":
        return
    scripts = _candidates(event)
    if not scripts:
        return
    body = json.dumps(payload or {}, default=str)
    log = _log_path()
    for script in scripts:
        cmd: list[str]
        if script.suffix == ".ps1":
            if not shutil.which("powershell"):
                continue
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        elif script.suffix == ".bat":
            cmd = [str(script)]
        else:
            cmd = [str(script)] if os.name != "nt" else ["bash", str(script)]
        try:
            proc = subprocess.run(
                cmd,
                input=body,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            with log.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": time.time(),
                            "event": event,
                            "script": str(script),
                            "rc": proc.returncode,
                            "stdout": (proc.stdout or "")[:4000],
                            "stderr": (proc.stderr or "")[:2000],
                        }
                    )
                    + "\n"
                )
        except Exception as e:
            with log.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {"ts": time.time(), "event": event, "script": str(script), "error": f"{type(e).__name__}: {e}"}
                    )
                    + "\n"
                )
