"""Tests for the shared `<think>` stripping helper."""

from __future__ import annotations

from nexus._llm_util import strip_think


def test_strip_balanced_block():
    assert strip_think("<think>reasoning</think>answer") == "answer"
    assert strip_think("pre<think>r</think>post") == "prepost"


def test_strip_multiple_blocks():
    got = strip_think("a<think>r1</think>b<think>r2</think>c")
    assert got == "abc"


def test_strip_multiline_block():
    content = "before\n<think>\nlong\nreasoning\nhere\n</think>\nafter"
    assert strip_think(content).strip() == "before\n\nafter".strip()


def test_unclosed_open_with_no_close_drops_tail():
    """Bare `<think>` with no close: drop everything from there."""
    assert strip_think("prefix<think>runaway reasoning no close").strip() == "prefix"


def test_bare_close_is_passed_through():
    """A stray `</think>` with no opening tag is ambiguous — leave the content
    alone rather than guess where thinking ends. (Real qwen3 emits paired
    tags or bare opens, not bare closes.)"""
    assert strip_think("</think>answer") == "</think>answer"


def test_unclosed_then_close_after_content():
    """<think>reasoning (unclosed by re.sub since no closing) — but we still
    have </think> later. The split-on-</think> branch kicks in, leaving the tail."""
    content = "<think>reasoning here</think>final answer"
    # balanced; caught by the sub
    assert strip_think(content) == "final answer"


def test_none_and_empty():
    assert strip_think(None) == ""
    assert strip_think("") == ""
    assert strip_think("   \n  ") == ""


def test_whitespace_trimmed():
    assert strip_think("  hello  ") == "hello"


def test_no_think_tags_untouched():
    assert strip_think("plain answer") == "plain answer"
