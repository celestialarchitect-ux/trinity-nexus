"""Cost ledger — offline."""

from __future__ import annotations


def test_price_lookup_exact_and_prefix():
    from nexus.cost import _price_for

    assert _price_for("anthropic/claude-opus-4-7") == (15.00, 75.00)
    assert _price_for("anthropic/claude-opus-4-7:beta") == (15.00, 75.00)
    assert _price_for("qwen3:4b") == (0.0, 0.0)
    assert _price_for("unknown-model-xyz") == (0.0, 0.0)


def test_record_and_totals(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLE_HOME", str(tmp_path))
    import importlib
    from nexus import config as cfg
    importlib.reload(cfg)
    from nexus import cost
    importlib.reload(cost)

    row = cost.record(
        backend="openai_compat",
        model="anthropic/claude-opus-4-7",
        prompt_tokens=1000,
        completion_tokens=500,
        thread_id="t1",
    )
    # $15/1M in, $75/1M out → 1000*15/1M + 500*75/1M = 0.015 + 0.0375 = 0.0525
    assert row["usd"] == 0.0525

    cost.record(
        backend="ollama", model="qwen3:4b",
        prompt_tokens=4000, completion_tokens=200, thread_id="t1",
    )

    day = cost.daily_total()
    assert day["calls"] == 2
    assert day["prompt_tokens"] == 5000
    assert day["completion_tokens"] == 700
    assert round(day["usd"], 4) == 0.0525

    sess = cost.session_total("t1")
    assert sess["calls"] == 2
