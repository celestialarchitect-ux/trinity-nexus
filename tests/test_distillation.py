"""Distillation tests — collector + validator (no training)."""

from __future__ import annotations

from pathlib import Path

from nexus.distillation.collector import Interaction, InteractionCollector
from nexus.distillation.validator import AdapterValidator


def test_collector_round_trip(oracle_home, tmp_path):
    path = tmp_path / "ix.jsonl"
    c = InteractionCollector(path=path)
    assert c.count() == 0

    c.log_turn(intent="hello", response="hi", thread_id="t", confidence=0.8)
    c.log_turn(
        intent="what is 2+2",
        response="4",
        thread_id="t",
        confidence=0.9,
        tools_used=["calc"],
    )
    assert c.count() == 2

    rows = c.read_since(0)
    assert len(rows) == 2
    assert isinstance(rows[0], Interaction)
    assert rows[0].intent == "hello"
    assert rows[1].tools_used == ["calc"]


def test_validator_accepts_passing(tmp_path: Path):
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    v = AdapterValidator()
    r = v.validate(
        adapter_path=adapter,
        regression_scores=[0.97, 0.98],
        diversity_scores=[0.85],
        improvement_scores=[0.05],
    )
    assert r.accepted
    assert r.rejection_reasons == []


def test_validator_rejects_regression(tmp_path: Path):
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    v = AdapterValidator(regression_threshold=0.95)
    r = v.validate(
        adapter_path=adapter,
        regression_scores=[0.80],  # fails
        diversity_scores=[0.85],
        improvement_scores=[0.05],
    )
    assert not r.accepted
    assert any("regression" in reason for reason in r.rejection_reasons)


def test_validator_rejects_no_improvement(tmp_path: Path):
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    v = AdapterValidator()
    r = v.validate(
        adapter_path=adapter,
        regression_scores=[0.97],
        diversity_scores=[0.85],
        improvement_scores=[0.0],  # no net improvement
    )
    assert not r.accepted
    assert any("improvement" in reason for reason in r.rejection_reasons)
