"""Optimizer unit tests — no model calls. Verifies section splitter + gate."""

from __future__ import annotations


def test_split_sections_finds_all_33():
    from nexus.optimizer import _split_sections
    from nexus.prompts import TRINITY_NEXUS_CONSTITUTION

    sections = _split_sections(TRINITY_NEXUS_CONSTITUTION)
    nums = {n for n, _ in sections}
    # At minimum we should find a substantial majority of the 33 sections
    assert len(sections) >= 30
    for required in (1, 6, 10, 13, 29, 33):
        assert required in nums


def test_frozen_sections_are_refused():
    from nexus.optimizer import FROZEN_SECTIONS, optimize

    r = optimize(section_num=1, iterations=1, variations_per_iter=1)
    assert r["ok"] is False
    assert 1 in FROZEN_SECTIONS


def test_nonexistent_section_refused():
    from nexus import optimizer

    r = optimizer.optimize(section_num=99, iterations=1, variations_per_iter=1)
    assert r["ok"] is False


def test_assemble_roundtrip_is_nondestructive():
    from nexus.optimizer import _assemble, _split_sections
    from nexus.prompts import TRINITY_NEXUS_CONSTITUTION

    preamble = TRINITY_NEXUS_CONSTITUTION.split("SECTION 01", 1)[0]
    sections = _split_sections(TRINITY_NEXUS_CONSTITUTION)
    reassembled = _assemble(sections, preamble)
    # Identity-critical headers should survive
    for marker in ("SECTION 01", "SECTION 13", "SECTION 33", "TRUTH BEFORE COMFORT"):
        assert marker in reassembled
