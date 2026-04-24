"""Token + cost ledger.

Every call to the runtime goes through `record()`. Usage is appended to a
daily JSONL at `<ORACLE_HOME>/costs/<YYYY-MM-DD>.jsonl`. The `/cost` REPL
command reads the current day + session totals.

Local inference is $0 but token counts still drive ctx-budget warnings,
so we record them either way.
"""

from __future__ import annotations

import datetime as _dt
import json
import time
from pathlib import Path

from nexus.config import settings


# USD per 1M tokens — updated 2026-04. Local = $0, frontier = varies.
# Keep a small, conservative table; OpenRouter returns real pricing per
# call via the `usage` block on hit response and we prefer that when present.
PRICE_TABLE: dict[str, tuple[float, float]] = {
    # model_id_prefix: (prompt $/1M, completion $/1M)
    "anthropic/claude-opus-4-7":    (15.00, 75.00),
    "anthropic/claude-sonnet-4-6":  (3.00, 15.00),
    "anthropic/claude-haiku-4-5":   (0.80, 4.00),
    "openai/gpt-5":                 (5.00, 40.00),
    "openai/o3":                    (2.00, 8.00),
    "openai/o4-mini":               (0.30, 1.20),
    "google/gemini-2.5-pro":        (1.25, 10.00),
    "google/gemini-2.5-flash":      (0.30, 2.50),
    "x-ai/grok-4":                  (3.00, 15.00),
    "deepseek/deepseek-chat":       (0.14, 0.28),
    "deepseek/deepseek-reasoner":   (0.55, 2.19),
    "meta-llama/llama-3.3-70b":     (0.35, 0.40),
    # Groq free tier — effectively $0 but rate-limited
    "llama-3.3-70b-versatile":      (0.00, 0.00),
    "llama-3.1-8b-instant":         (0.00, 0.00),
    # Ollama / local
    "qwen3:4b":                     (0.00, 0.00),
    "qwen3:30b":                    (0.00, 0.00),
    "bge-m3":                       (0.00, 0.00),
}


def _price_for(model: str) -> tuple[float, float]:
    if model in PRICE_TABLE:
        return PRICE_TABLE[model]
    # Prefix match (OpenRouter IDs like "anthropic/claude-opus-4-7:beta")
    for k, v in PRICE_TABLE.items():
        if model.startswith(k):
            return v
    return (0.0, 0.0)


def _log_path(day: str | None = None) -> Path:
    d = day or _dt.date.today().isoformat()
    p = settings.oracle_home / "costs" / f"{d}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def record(
    *,
    backend: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    thread_id: str = "",
    purpose: str = "chat",
) -> dict:
    """Append one usage row. Returns the row dict (with computed cost)."""
    pin, pout = _price_for(model)
    usd = (prompt_tokens / 1_000_000.0) * pin + (completion_tokens / 1_000_000.0) * pout
    row = {
        "ts": time.time(),
        "backend": backend,
        "model": model,
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "usd": round(usd, 6),
        "thread_id": thread_id,
        "purpose": purpose,
    }
    try:
        with _log_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass
    return row


def daily_total(day: str | None = None) -> dict:
    """Read the day's ledger and return totals."""
    p = _log_path(day)
    if not p.exists():
        return {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "usd": 0.0, "by_model": {}}
    calls = 0
    pt = 0
    ct = 0
    usd = 0.0
    by_model: dict[str, dict] = {}
    with p.open(encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except Exception:
                continue
            calls += 1
            pt += row.get("prompt_tokens", 0)
            ct += row.get("completion_tokens", 0)
            usd += row.get("usd", 0.0)
            m = row.get("model", "?")
            bm = by_model.setdefault(m, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "usd": 0.0})
            bm["calls"] += 1
            bm["prompt_tokens"] += row.get("prompt_tokens", 0)
            bm["completion_tokens"] += row.get("completion_tokens", 0)
            bm["usd"] += row.get("usd", 0.0)
    return {
        "calls": calls,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "usd": round(usd, 6),
        "by_model": by_model,
    }


def session_total(thread_id: str, day: str | None = None) -> dict:
    p = _log_path(day)
    if not p.exists():
        return {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "usd": 0.0}
    calls = 0
    pt = 0
    ct = 0
    usd = 0.0
    with p.open(encoding="utf-8") as f:
        for line in f:
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("thread_id") != thread_id:
                continue
            calls += 1
            pt += row.get("prompt_tokens", 0)
            ct += row.get("completion_tokens", 0)
            usd += row.get("usd", 0.0)
    return {"calls": calls, "prompt_tokens": pt, "completion_tokens": ct, "usd": round(usd, 6)}
