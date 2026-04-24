"""Reflection — periodic self-review loop.

Reads the last N turns from recall memory, summarizes themes, and proposes
edits to core memory (the always-injected facts block). Everything is logged;
edits are only applied when the caller confirms (`oracle reflect --apply`).

Rationale: the user explicitly wants Oracle to *learn between sessions*. Core
memory drift is the mechanism. Reflection is how it happens deliberately
rather than at every turn.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import ollama

from oracle.config import settings
from oracle.memory import MemoryTiers


@dataclass
class ReflectionReport:
    ts: float
    turns_reviewed: int
    themes: list[str] = field(default_factory=list)
    facts_to_remember: list[str] = field(default_factory=list)
    core_edits: str = ""  # proposed replacement for core memory (markdown)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


REFLECT_SYSTEM = """You are the reflective layer of Oracle. Your job is to
review recent user + assistant turns and surface stable, reusable signal
worth remembering long-term.

Output STRICT JSON with these keys:
{
  "themes": ["short phrase", ...],           // 0-5 recurring topics the user is working on
  "facts_to_remember": ["fact", ...],        // 0-8 durable facts worth storing in archival memory
  "core_edits": "<markdown>",                // revised core memory content, or "" if no change
  "notes": ["note", ...]                     // 0-3 honest observations (low-effort turns, confusion, style hints)
}

Rules:
- NEVER invent facts not present in the turns
- Only propose core edits when something genuinely stable has shifted
- Keep everything terse. No filler.
- Return ONLY the JSON object, no prose outside it.
"""


def _client() -> ollama.Client:
    return ollama.Client(host=settings.oracle_ollama_host)


def _chat(client: ollama.Client, *, system: str, prompt: str, max_tokens: int = 1500) -> str:
    kw: dict = dict(
        model=settings.oracle_primary_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        options={
            "temperature": 0.2,
            "num_predict": max_tokens,
            "num_ctx": settings.oracle_num_ctx,
        },
    )
    try:
        r = client.chat(**kw, think=False)
    except TypeError:
        r = client.chat(**kw)
    return r["message"]["content"] or ""


def _parse(raw: str) -> dict:
    """qwen3 often rambles before emitting JSON — find the largest balanced
    JSON object anywhere in the response."""
    import re

    raw = raw.strip()
    if not raw:
        return {"themes": [], "facts_to_remember": [], "core_edits": "", "notes": ["empty response"]}

    # Collect candidate { ... } substrings, try each from longest to shortest.
    candidates: list[str] = []
    starts = [i for i, ch in enumerate(raw) if ch == "{"]
    ends = [i for i, ch in enumerate(raw) if ch == "}"]
    for s in starts:
        for e in reversed(ends):
            if e > s:
                candidates.append(raw[s : e + 1])
                break
    for c in sorted(set(candidates), key=len, reverse=True):
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return {
        "themes": [],
        "facts_to_remember": [],
        "core_edits": "",
        "notes": [f"unparseable: {raw[:300]}"],
    }


def reflect(
    *,
    n_turns: int = 40,
    apply: bool = False,
    remember_facts: bool = True,
) -> ReflectionReport:
    """Run one reflection cycle.

    If `apply=True` and `core_edits` is non-empty, core memory is replaced.
    If `remember_facts=True`, facts_to_remember are stored to archival memory.
    """
    tiers = MemoryTiers()
    recent = tiers.recall.recent(n=n_turns)
    if not recent:
        return ReflectionReport(
            ts=time.time(), turns_reviewed=0, notes=["no turns to reflect on"]
        )

    # Oldest first for coherent context
    turns_text = "\n".join(
        f"[{r['role']}] {r['content'][:400]}" for r in reversed(recent)
    )
    current_core = tiers.core.read()

    prompt = (
        f"CURRENT CORE MEMORY:\n{current_core}\n\n"
        f"RECENT TURNS (oldest → newest):\n{turns_text}\n\n"
        "Reflect. Return JSON only."
    )
    raw = _chat(_client(), system=REFLECT_SYSTEM, prompt=prompt, max_tokens=3000)
    obj = _parse(raw)

    rep = ReflectionReport(
        ts=time.time(),
        turns_reviewed=len(recent),
        themes=list(obj.get("themes") or [])[:5],
        facts_to_remember=list(obj.get("facts_to_remember") or [])[:8],
        core_edits=str(obj.get("core_edits") or "").strip(),
        notes=list(obj.get("notes") or [])[:3],
    )

    if remember_facts:
        for fact in rep.facts_to_remember:
            try:
                tiers.remember(fact, tags=["reflection"], source="reflect")
            except Exception as e:
                rep.notes.append(f"archival store fail: {e}")

    if apply and rep.core_edits and rep.core_edits != current_core:
        backup = settings.oracle_home / "memory" / f"core.md.bak.{int(rep.ts)}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(current_core, encoding="utf-8")
        tiers.core.write(rep.core_edits)
        rep.notes.append(f"core memory replaced (backup → {backup.name})")

    # Persist the reflection for later audit
    log_path = settings.oracle_home / "reflect" / f"reflect_{int(rep.ts)}.json"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(rep.to_dict(), indent=2), encoding="utf-8")

    return rep
