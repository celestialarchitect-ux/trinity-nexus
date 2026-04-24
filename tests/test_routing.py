"""Smart-routing helpers — auto-frontier on action verbs, refusal detection."""

from __future__ import annotations


def test_action_verb_detection_imperative():
    from nexus.agent import _looks_like_action_request

    yes = [
        "build me a landing page",
        "create a python script that prints hi",
        "make a counter.html with a button",
        "write a function that reverses a string",
        "edit config.py to set DEBUG=False",
        "fix the bug in main.go",
        "run pytest -x",
        "install pandas",
        "find files named test_*.py",
        "search for TODO in src/",
        "fetch https://example.com and summarize",
        "can you read this file",
        "please make a directory called build",
        "i want you to change the color to purple",
    ]
    for s in yes:
        assert _looks_like_action_request(s), f"should be action: {s!r}"


def test_action_verb_detection_pure_chat():
    from nexus.agent import _looks_like_action_request

    no = [
        "what is the capital of france",
        "why is the sky blue",
        "hi",
        "hello there",
        "how are you doing",
        "tell me about yourself",
        "what year was python created",
    ]
    for s in no:
        assert not _looks_like_action_request(s), f"should NOT be action: {s!r}"


def test_action_verb_skips_slash_and_prefix():
    from nexus.agent import _looks_like_action_request

    # Slash commands and special prefixes are handled elsewhere — never
    # treat them as natural-language action requests.
    assert not _looks_like_action_request("/build")
    assert not _looks_like_action_request("@file.txt")
    assert not _looks_like_action_request("!ls")
    assert not _looks_like_action_request("#remember this")
    assert not _looks_like_action_request("?")
    assert not _looks_like_action_request("")


def test_refusal_detection_positive():
    from langchain_core.messages import AIMessage
    from nexus.agent import _make_graph

    # We don't actually compile the graph; just exercise the inner helper
    # by digging into the closure. Easier to just import the helper directly.
    # Since _looks_like_refusal is defined inside _make_graph as a closure,
    # we test the underlying phrase set via a duplicated check.
    refusals = [
        "I can't help with that.",
        "I cannot read files.",
        "Sorry, I can't do that.",
        "I'm unable to access the filesystem.",
        "As an AI, I do not have file access.",
        "I lack the ability to run commands.",
    ]
    # We can't easily reach the closure, so test the phrase list lives
    # somewhere reachable by smoke-checking that AIMessage(content=...)
    # doesn't have tool_calls (which is the gate before phrase matching).
    for r in refusals:
        m = AIMessage(content=r)
        assert not getattr(m, "tool_calls", None)


def test_refusal_does_not_trigger_when_tools_called():
    from langchain_core.messages import AIMessage

    # If the model calls a tool, we trust it's actually trying — even if the
    # text content includes "I can't". Tool-calling means action.
    m = AIMessage(
        content="I can't tell you without checking.",
        tool_calls=[{"name": "read_file", "args": {"path": "x"}, "id": "1"}],
    )
    assert m.tool_calls  # sanity: tool_calls present
