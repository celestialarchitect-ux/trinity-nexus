"""File editing tools — apply_diff (SEARCH/REPLACE) + edit_file drift-tolerance. Offline."""

from __future__ import annotations


def test_apply_diff_exact_match(tmp_path):
    from nexus.tools import apply_diff

    f = tmp_path / "a.py"
    f.write_text("def greet():\n    return 'hello'\n", encoding="utf-8")

    r = apply_diff.invoke({
        "path": str(f),
        "search": "    return 'hello'",
        "replace": "    return 'hi'",
    })
    assert "applied diff" in r
    assert f.read_text(encoding="utf-8") == "def greet():\n    return 'hi'\n"


def test_apply_diff_missing_match(tmp_path):
    from nexus.tools import apply_diff

    f = tmp_path / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")
    r = apply_diff.invoke({
        "path": str(f),
        "search": "not present",
        "replace": "whatever",
    })
    assert "not found" in r.lower()


def test_apply_diff_multiple_matches_rejects(tmp_path):
    from nexus.tools import apply_diff

    f = tmp_path / "a.py"
    f.write_text("x = 1\nx = 1\n", encoding="utf-8")
    r = apply_diff.invoke({"path": str(f), "search": "x = 1", "replace": "x = 2"})
    assert "appears 2 times" in r


def test_edit_file_exact_match(tmp_path):
    from nexus.tools import edit_file

    f = tmp_path / "a.py"
    original = "def foo():\n    return 1\n"
    f.write_text(original, encoding="utf-8")
    r = edit_file.invoke({
        "path": str(f),
        "old_string": "    return 1",
        "new_string": "    return 42",
    })
    assert "edited" in r
    assert "return 42" in f.read_text(encoding="utf-8")


def test_edit_file_ambiguous_match_rejected(tmp_path):
    from nexus.tools import edit_file

    f = tmp_path / "a.py"
    f.write_text("x = 1\nx = 1\n", encoding="utf-8")
    r = edit_file.invoke({
        "path": str(f),
        "old_string": "x = 1",
        "new_string": "x = 2",
    })
    assert "appears 2 times" in r


def test_dangerous_patterns_blocked(tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_ALLOW_DANGEROUS", raising=False)
    from nexus.tools import run_command

    r = run_command.invoke({"command": "rm -rf /", "timeout_sec": 5})
    assert r["returncode"] == -3
    assert "blocked" in r["stderr"]


def test_dangerous_unlock(monkeypatch):
    monkeypatch.setenv("NEXUS_ALLOW_DANGEROUS", "1")
    from nexus.tools import _is_dangerous

    assert _is_dangerous("rm -rf /") is None  # unlocked → not flagged
