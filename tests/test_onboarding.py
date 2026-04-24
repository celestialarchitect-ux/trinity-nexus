"""USER MAP (§24) + onboarding state — offline."""

from __future__ import annotations


def test_user_map_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus import onboarding
    importlib.reload(onboarding)

    assert not onboarding.is_onboarded()
    assert onboarding.load_user_map() == ""
    assert onboarding.to_prompt_block() == ""

    um = onboarding.UserMap(
        preferred_name="Zach",
        primary_mission="build Trinity Nexus",
        operating_role="all of the above",
        mind="systems thinker, ships fast",
        current_priority="complete Omega Foundation",
    )
    path = onboarding.save_user_map(um)
    assert path.exists()

    body = onboarding.load_user_map()
    assert "Zach" in body
    assert "Trinity Nexus" in body

    block = onboarding.to_prompt_block()
    assert "USER MAP" in block
    assert "Zach" in block


def test_orientation_questions_shape():
    from nexus.onboarding import ORIENTATION_QUESTIONS, OPENING_LINE

    assert len(ORIENTATION_QUESTIONS) == 4
    assert all(len(q) == 2 for q in ORIENTATION_QUESTIONS)
    assert "I am Trinity Nexus" in OPENING_LINE
