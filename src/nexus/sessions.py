"""Session transcript recording.

Appends every turn (user + assistant + tool calls + tool results) as
JSONL under `<ORACLE_HOME>/sessions/<thread_id>.jsonl`. One record per
event. Fuels reflection, distillation, and replay.

Disable entirely with `NEXUS_RECORD=0`.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from nexus.config import settings


def _enabled() -> bool:
    return os.environ.get("NEXUS_RECORD", "1") != "0"


def _path(thread_id: str) -> Path:
    # Strict sanitiser: alphanum + '-' + '_' only. Dots are stripped to block
    # path-traversal attempts like "../etc".
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in (thread_id or "default"))
    safe = safe.strip("_") or "default"
    p = settings.oracle_home / "sessions" / f"{safe}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def log(thread_id: str, kind: str, **data: Any) -> None:
    """Append a single event. Never raises."""
    if not _enabled():
        return
    try:
        record = {"ts": time.time(), "kind": kind, **data}
        with _path(thread_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception:
        pass


def list_threads() -> list[str]:
    base = settings.oracle_home / "sessions"
    if not base.exists():
        return []
    return sorted(p.stem for p in base.glob("*.jsonl"))


def read_thread(thread_id: str, *, limit: int = 200) -> list[dict]:
    p = _path(thread_id)
    if not p.exists():
        return []
    out: list[dict] = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out[-limit:]
