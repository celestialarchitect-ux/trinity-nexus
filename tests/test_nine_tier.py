"""9-tier memory (§06) — file-based, offline."""

from __future__ import annotations


def test_all_nine_tiers_created(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus.memory import nine_tier
    importlib.reload(nine_tier)

    nt = nine_tier.NineTier()
    assert len(nt.tiers) == 9
    for tier in nt.all():
        assert tier.path.exists()


def test_tier_read_write_append(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus.memory import nine_tier
    importlib.reload(nine_tier)

    nt = nine_tier.NineTier()
    projects = nt.get("projects")
    projects.write("# Active\n- Trinity Nexus Omega 1.0")
    assert "Trinity Nexus" in projects.read()
    projects.append("- New supplement launch")
    assert "New supplement" in projects.read()


def test_prompt_block_skips_seeds(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus.memory import nine_tier
    importlib.reload(nine_tier)

    nt = nine_tier.NineTier()
    # All seeds → empty block
    assert nt.to_prompt_block() == ""

    # Populate one tier → block appears
    nt.get("core").write("Name: Zach")
    block = nt.to_prompt_block()
    assert "CORE IDENTITY" in block
    assert "Zach" in block
