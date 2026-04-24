"""Graph memory tests — offline (no model calls)."""

from __future__ import annotations


def test_schema_creates_and_stats(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus import graph
    importlib.reload(graph)

    s = graph.stats()
    assert s["entities"] == 0
    assert s["edges"] == 0


def test_store_triples_and_query(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus import graph
    importlib.reload(graph)

    triples = [
        {"s": "Trinity Nexus", "r": "owned_by", "o": "Zach"},
        {"s": "Trinity Nexus", "r": "runs_on", "o": "Ollama"},
        {"s": "Ollama", "r": "hosts", "o": "qwen3:4b"},
        {"s": "Zach", "r": "uses", "o": "RTX 4090"},
    ]
    n = graph._store_triples(triples, source="test")
    assert n == 4

    q = graph.query("Trinity Nexus", depth=1)
    assert q["matches"] == 1
    # Direct neighbors at depth=1: Trinity Nexus connects to Zach + Ollama
    names = set(q["neighbors"])
    assert "Zach" in names
    assert "Ollama" in names
    assert len(q["edges"]) >= 2


def test_query_bfs_depth(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus import graph
    importlib.reload(graph)

    # chain A -> B -> C -> D
    graph._store_triples([
        {"s": "A", "r": "to", "o": "B"},
        {"s": "B", "r": "to", "o": "C"},
        {"s": "C", "r": "to", "o": "D"},
    ], source="chain")

    shallow = graph.query("A", depth=1)
    names_shallow = set(shallow["neighbors"])
    assert "B" in names_shallow
    assert "D" not in names_shallow

    deep = graph.query("A", depth=3)
    names_deep = set(deep["neighbors"])
    assert "D" in names_deep


def test_query_miss_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus import graph
    importlib.reload(graph)

    r = graph.query("never-mentioned", depth=2)
    assert r["matches"] == 0


def test_fuzzy_name_match(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus import graph
    importlib.reload(graph)

    graph._store_triples([{"s": "Trinity Intelligence Network", "r": "makes", "o": "Nexus"}],
                         source="t")
    r = graph.query("trinity", depth=1)
    assert r["matches"] == 1
    assert "Nexus" in r["neighbors"]
