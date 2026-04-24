"""Session transcript recording — offline."""

from __future__ import annotations


def test_disabled_when_env_off(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_RECORD", "0")
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus import sessions
    importlib.reload(sessions)

    sessions.log("t1", "user", content="hello")
    assert sessions.list_threads() == []
    assert sessions.read_thread("t1") == []


def test_log_read_list(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_RECORD", "1")
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus import sessions
    importlib.reload(sessions)

    sessions.log("alpha", "user", content="first message")
    sessions.log("alpha", "assistant", content="reply")
    sessions.log("alpha", "tool_call", name="read_file", args={"path": "x"})
    sessions.log("beta", "user", content="another thread")

    threads = sessions.list_threads()
    assert "alpha" in threads
    assert "beta" in threads

    events = sessions.read_thread("alpha")
    assert len(events) == 3
    assert events[0]["kind"] == "user"
    assert events[1]["kind"] == "assistant"
    assert events[2]["kind"] == "tool_call"


def test_title_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_RECORD", "1")
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus import sessions
    importlib.reload(sessions)

    assert sessions.get_title("new-thread") is None
    sessions.set_title("new-thread", "first-title")
    assert sessions.get_title("new-thread") == "first-title"
    # Adding later events doesn't break retrieval
    sessions.log("new-thread", "user", content="hi")
    assert sessions.get_title("new-thread") == "first-title"


def test_thread_id_sanitised(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    monkeypatch.setenv("NEXUS_RECORD", "1")
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus import sessions
    importlib.reload(sessions)

    # Path traversal attempt — must be sanitised
    sessions.log("../../etc", "user", content="nope")
    path = sessions._path("../../etc")
    assert ".." not in path.name
    assert path.exists()
