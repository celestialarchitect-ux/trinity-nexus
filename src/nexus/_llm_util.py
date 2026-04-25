"""Small shared helpers for raw ollama.Client.chat() call sites.

Extracted here because 8+ files were hand-rolling the same <think>-tag
stripping after their own client.chat calls, and one place (reflect.py)
had a pre-existing bug where qwen3's chain-of-thought leaked into the
output parser. One helper, one behaviour.

Handles two reasoning-preamble formats:

  - qwen3 / deepseek-r1: `<think>...</think>` blocks
  - gpt-oss (harmony): `<|channel|>analysis<|message|>...<|end|>` segments
    where only the `<|channel|>final<|message|>...` payload should survive.

Both are best-effort — if neither marker is present, the original string
is returned trimmed.
"""

from __future__ import annotations

import re


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)

# gpt-oss harmony format: keep only the content of the final channel.
# Examples seen in the wild:
#   <|channel|>analysis<|message|>...<|end|><|start|>assistant<|channel|>final<|message|>ANSWER
#   <|channel|>final<|message|>ANSWER<|end|>
_HARMONY_FINAL = re.compile(
    r"<\|channel\|>\s*final\s*<\|message\|>(.*?)(?:<\|end\|>|<\|return\|>|$)",
    re.DOTALL,
)
_HARMONY_ANY_TAG = re.compile(r"<\|[^|>]*\|>")


def _strip_harmony(s: str) -> str:
    """If the string contains gpt-oss harmony tags, return the `final` channel.

    If no `final` channel is found but harmony tags exist, fall back to
    stripping all `<|...|>` markers (worst case: analysis + final concatenated
    without delimiters).
    """
    if "<|channel|>" not in s and "<|message|>" not in s:
        return s
    m = _HARMONY_FINAL.search(s)
    if m:
        return m.group(1).strip()
    # Last-ditch: drop all harmony tags, keep whatever text remains.
    return _HARMONY_ANY_TAG.sub("", s).strip()


def strip_think(content: str | None) -> str:
    """Strip reasoning preamble from a model response.

    Handles:
      - balanced `<think>...</think>` blocks (removed entirely)
      - unclosed `<think>` with matching `</think>` later (split on close)
      - bare opening `<think>` with no close (drop everything after it)
      - gpt-oss harmony tags (`<|channel|>analysis`, `<|channel|>final`) —
        return only the `final` channel when present.

    Returns a stripped, trimmed string. Never raises.
    """
    if not content:
        return ""
    s = _strip_harmony(content)
    s = _THINK_BLOCK.sub("", s)
    if "<think>" in s:
        if "</think>" in s:
            s = s.split("</think>", 1)[1]
        else:
            s = s.split("<think>", 1)[0]
    return s.strip()
