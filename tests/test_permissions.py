"""Permissions (§29) — offline."""

from __future__ import annotations


def test_default_denies_mutation_allows_read(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    import importlib
    from nexus import permissions as p
    importlib.reload(p)

    assert p.check("read", "/etc/hosts").ok
    assert p.check("glob", "**/*.py").ok
    assert not p.check("bash", "echo hi").ok
    assert not p.check("write", "/tmp/x").ok


def test_allow_deny_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    import importlib
    from nexus import permissions as p
    importlib.reload(p)

    p.allow("bash", "git *")
    assert p.check("bash", "git status").ok
    assert not p.check("bash", "rm -rf /").ok  # no matching allow, default deny

    p.deny("bash", "git push --force")
    assert not p.check("bash", "git push --force").ok  # deny wins

    p.remove("bash", "git push --force")
    assert p.check("bash", "git push --force").ok  # allow pattern catches it now
