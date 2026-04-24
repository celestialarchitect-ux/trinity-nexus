"""Skill engine tests — registry, router, stats."""

from __future__ import annotations

import httpx
import pytest

from oracle.config import settings
from oracle.skills import SkillRegistry, SkillRouter


def _ollama_up() -> bool:
    try:
        httpx.get(f"{settings.oracle_ollama_host}/api/tags", timeout=2).raise_for_status()
        return True
    except Exception:
        return False


def test_registry_loads_seed_skills():
    reg = SkillRegistry()
    n = reg.load_all()
    assert n >= 10
    for sid in [
        "summarize_text",
        "draft_email",
        "decompose_task",
        "critique_plan",
        "compare_options",
        "recall_memory",
    ]:
        assert reg.get(sid) is not None, f"missing expected skill: {sid}"


def test_skill_confidence_bumps_correctly():
    reg = SkillRegistry()
    reg.load_all()
    s = reg.get("summarize_text")
    assert s is not None
    before = s.confidence
    s._bump_confidence(True)
    assert s.confidence > before
    s._bump_confidence(False)
    s._bump_confidence(False)
    s._bump_confidence(False)
    assert s.confidence < before + 0.1


@pytest.mark.skipif(not _ollama_up(), reason="Ollama needed for embedder")
def test_router_ranks_obvious_intents():
    reg = SkillRegistry()
    reg.load_all()
    router = SkillRouter(reg)
    router.build_index()

    cases = [
        ("write a cold email to a vc", "draft_email"),
        ("break this goal into concrete tasks", "decompose_task"),
        ("summarize this long document", "summarize_text"),
        ("rip apart my plan", "critique_plan"),
    ]
    for intent, expected in cases:
        hits = router.route(intent, top_k=3)
        ids = [s.id for s, _ in hits]
        assert expected in ids, f"for intent {intent!r} expected {expected} in top 3, got {ids}"
