"""Context compaction — when the thread gets long, squash old turns.

Inspired by MemGPT/letta and Claude Code's `/compact`. We read the most
recent N turns from the session transcript, ask the fast model to
summarize everything older than the last K, and write a single compact
"prior context" block back to the session's 'threads' tier of memory.

Does NOT touch LangGraph state directly — that's SqliteSaver's domain.
The compaction output lands in the `threads` tier (§06.8) so it flows
back into the agent via the 9-tier memory injection on the next turn.
"""

from __future__ import annotations

import json

from nexus.config import settings
from nexus.memory.nine_tier import NineTier
from nexus.sessions import read_thread


COMPACT_SYSTEM = (
    "You are the COMPACTION stage. You receive a long conversation "
    "transcript and produce a compressed summary that preserves:\n"
    "- the user's goals and open questions\n"
    "- key decisions made\n"
    "- facts established\n"
    "- tool-call outcomes that matter for future turns\n"
    "- unresolved threads to pick up\n\n"
    "Output: one terse markdown block, ~300-500 words, under ## headings. "
    "No filler, no apology. Return ONLY the markdown."
)


def compact(thread_id: str, *, keep_recent: int = 10) -> dict:
    """Summarize everything older than the last `keep_recent` events.

    Writes the summary into the `threads` tier of 9-tier memory so it gets
    auto-injected next turn. Returns a report dict.
    """
    import ollama

    events = read_thread(thread_id, limit=500)
    if len(events) <= keep_recent:
        return {"ok": False, "reason": f"only {len(events)} events — nothing to compact"}

    to_summarize = events[:-keep_recent]
    kept = events[-keep_recent:]

    transcript_lines: list[str] = []
    for e in to_summarize:
        kind = e.get("kind", "?")
        if kind == "user":
            transcript_lines.append(f"[user] {str(e.get('content',''))[:400]}")
        elif kind == "assistant":
            transcript_lines.append(f"[assistant] {str(e.get('content',''))[:400]}")
        elif kind == "tool_call":
            transcript_lines.append(
                f"[tool] {e.get('name','?')}({json.dumps(e.get('args',{}), default=str)[:200]})"
            )
        elif kind == "tool_result":
            transcript_lines.append(f"[result] {str(e.get('content',''))[:200]}")

    transcript = "\n".join(transcript_lines)
    if not transcript.strip():
        return {"ok": False, "reason": "no substantive prior turns"}

    client = ollama.Client(host=settings.oracle_ollama_host)
    kw: dict = dict(
        model=settings.oracle_fast_model,
        messages=[
            {"role": "system", "content": COMPACT_SYSTEM},
            {"role": "user", "content": f"TRANSCRIPT:\n{transcript}\n\nProduce the compressed summary now."},
        ],
        options={
            "temperature": 0.2,
            "num_ctx": settings.oracle_num_ctx,
            "num_predict": 1500,
        },
    )
    try:
        r = client.chat(**kw, think=False)
    except TypeError:
        r = client.chat(**kw)
    from nexus._llm_util import strip_think
    summary = strip_think(r["message"]["content"])
    if not summary:
        return {"ok": False, "reason": "empty summary"}

    # Write to the 'threads' tier so it gets injected on future turns
    nine = NineTier()
    threads_tier = nine.get("threads")
    if threads_tier:
        current = threads_tier.read()
        header = f"\n\n## Compacted context (thread {thread_id})\n"
        threads_tier.write((current.strip() + header + summary).strip())

    return {
        "ok": True,
        "thread_id": thread_id,
        "compacted_events": len(to_summarize),
        "kept_events": len(kept),
        "summary_chars": len(summary),
    }
