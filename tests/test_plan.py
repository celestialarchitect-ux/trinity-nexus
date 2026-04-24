"""Plan mode — serialization + parsers. Offline (no model calls)."""

from __future__ import annotations


def test_plan_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus import plan
    importlib.reload(plan)

    p = plan.Plan(
        id="p1",
        intent="build something",
        created_ts=0.0,
        tasks=[
            plan.PlanTask(id="t1", description="step one"),
            plan.PlanTask(id="t2", description="step two", status="done", result="ok"),
        ],
    )
    plan.save(p, "thread-x")
    loaded = plan.load("thread-x")
    assert loaded is not None
    assert loaded.intent == "build something"
    assert len(loaded.tasks) == 2
    assert loaded.tasks[0].description == "step one"
    assert loaded.tasks[1].status == "done"


def test_next_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus import plan
    importlib.reload(plan)

    p = plan.Plan(
        id="p2", intent="x", created_ts=0.0,
        tasks=[
            plan.PlanTask(id="a", description="a", status="done"),
            plan.PlanTask(id="b", description="b"),
            plan.PlanTask(id="c", description="c"),
        ],
    )
    n = plan.next_pending(p)
    assert n.id == "b"


def test_json_extractor_recovers_on_rambling_model():
    from nexus.plan import _extract_json

    raw = (
        "Okay, let me think. Here is the plan:\n"
        '{"tasks":[{"description":"ingest docs"},{"description":"run eval"}]}\n'
        "Let me know if you need changes."
    )
    obj = _extract_json(raw)
    assert isinstance(obj, dict)
    assert len(obj["tasks"]) == 2


def test_mark_updates_and_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus import plan
    importlib.reload(plan)

    p = plan.Plan(
        id="p3", intent="z", created_ts=0.0,
        tasks=[plan.PlanTask(id="only", description="only")],
    )
    plan.save(p, "t-mark")
    plan.mark(p, "only", status="done", result="✓", thread_id="t-mark")
    loaded = plan.load("t-mark")
    assert loaded.tasks[0].status == "done"
    assert loaded.tasks[0].result == "✓"
