"""User hooks — shell-script lifecycle events. Offline."""

from __future__ import annotations

import os
import sys


def test_no_hooks_dir_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_HOOKS", "")
    # Point HOME at a clean tmp so ~/.nexus/hooks doesn't exist
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "h"))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus import hooks
    importlib.reload(hooks)

    # Should not raise when the dir doesn't exist
    hooks.run("pre_prompt", {"prompt": "hello"})


def test_hooks_off_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("NEXUS_HOOKS", "off")
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus import hooks
    importlib.reload(hooks)

    # Even if scripts existed, NEXUS_HOOKS=off means no execution.
    hdir = tmp_path / ".nexus" / "hooks"
    hdir.mkdir(parents=True)
    script = hdir / "pre_prompt.bat" if sys.platform == "win32" else hdir / "pre_prompt.sh"
    script.write_text("echo ran", encoding="utf-8")
    if sys.platform != "win32":
        os.chmod(script, 0o755)

    # Should not raise and should not execute (hook log stays empty of event)
    hooks.run("pre_prompt", {"x": 1})
    log = tmp_path / "logs" / "hooks.log"
    # If the killswitch worked, the log shouldn't have a pre_prompt entry
    if log.exists():
        assert "pre_prompt" not in log.read_text(encoding="utf-8")
