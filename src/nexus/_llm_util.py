"""Small shared helpers for raw ollama.Client.chat() call sites.

Extracted here because 8+ files were hand-rolling the same <think>-tag
stripping after their own client.chat calls, and one place (reflect.py)
had a pre-existing bug where qwen3's chain-of-thought leaked into the
output parser. One helper, one behaviour.
"""

from __future__ import annotations

import re


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_think(content: str | None) -> str:
    """Strip qwen3's `<think>...</think>` blocks from a model response.

    Handles:
      - balanced blocks (removed entirely)
      - unclosed `<think>` with matching `</think>` later (split on close)
      - bare opening `<think>` with no close (drop everything after it)

    Returns a stripped, trimmed string. Never raises.
    """
    if not content:
        return ""
    s = _THINK_BLOCK.sub("", content)
    if "<think>" in s:
        if "</think>" in s:
            s = s.split("</think>", 1)[1]
        else:
            s = s.split("<think>", 1)[0]
    return s.strip()
