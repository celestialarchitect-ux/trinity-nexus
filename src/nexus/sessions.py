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
    """Append a single event. Never raises. Secrets auto-redacted."""
    if not _enabled():
        return
    try:
        from nexus.security import redact

        # Strip secrets from any string-valued fields before persisting
        safe_data = {k: (redact(v) if isinstance(v, str) else v) for k, v in data.items()}
        record = {"ts": time.time(), "kind": kind, **safe_data}
        with _path(thread_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception:
        pass


def get_title(thread_id: str) -> str | None:
    """Return a cached short title for a thread, or None if not titled yet."""
    for ev in read_thread(thread_id, limit=200):
        if ev.get("kind") == "title":
            return str(ev.get("text", ""))[:60] or None
    return None


def set_title(thread_id: str, title: str) -> None:
    """Persist a short title event."""
    log(thread_id, "title", text=title[:60])


def ensure_title(thread_id: str, first_user_message: str, model: str) -> str | None:
    """If the thread has no title yet, generate one from the first message.

    Non-blocking and best-effort: 3-6 words, no quotes, no period.
    Called after the first user turn completes.
    """
    if get_title(thread_id):
        return None
    try:
        import ollama as _ollama
        from nexus.config import settings

        client = _ollama.Client(host=settings.oracle_ollama_host)
        system = (
            "You generate 3-6 word titles for conversations. No quotes, no "
            "period. Return ONLY the title. Title the user's first message "
            "below so it reads naturally in a list of sessions."
        )
        kw: dict = dict(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": first_user_message[:400]},
            ],
            options={"temperature": 0.2, "num_predict": 40, "num_ctx": 2048},
        )
        try:
            r = client.chat(**kw, think=False)
        except TypeError:
            r = client.chat(**kw)
        title = (r["message"]["content"] or "").strip().strip('"').strip("'").rstrip(".")
        title = title.splitlines()[0][:60] if title else ""
        if title:
            set_title(thread_id, title)
            return title
    except Exception:
        pass
    return None


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
