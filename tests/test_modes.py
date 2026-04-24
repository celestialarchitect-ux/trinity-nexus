"""Operating modes (§13) + overlay injection — offline."""

from __future__ import annotations

import pytest


def test_modes_registry_has_all_twelve():
    from nexus.modes import MODES
    assert len(MODES) == 12
    for key in ("architect", "builder", "strategist", "codex", "critic",
                "executor", "mirror", "research", "memory", "evolution",
                "governor", "orchestrator"):
        assert key in MODES


def test_set_get_clear_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus import modes
    importlib.reload(modes)

    assert modes.get_active() is None
    modes.set_active("builder")
    assert modes.get_active().key == "builder"
    assert "BUILDER MODE" in modes.overlay()

    modes.set_active("off")
    assert modes.get_active() is None
    assert modes.overlay() == ""


def test_invalid_mode_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus import modes
    importlib.reload(modes)

    assert modes.set_active("definitely-not-a-mode") is None
