"""Eval harness — parser tests + regression gate (no Ollama needed)."""

from __future__ import annotations

from oracle.distillation.eval import (
    EvalCase,
    _parse_compare,
    _parse_judge,
    regression_pass_rate,
)


def test_parse_judge_json():
    s, r = _parse_judge('here: {"score": 0.72, "reason": "clear"}')
    assert s == 0.72
    assert "clear" in r


def test_parse_judge_fallback_float():
    s, r = _parse_judge("the score is 0.4 because...")
    assert s == 0.4


def test_parse_compare_json():
    w, m, _ = _parse_compare('{"winner":"A","margin":0.3,"reason":"tighter"}')
    assert w == "A" and m == 0.3


def test_parse_compare_fallback_letter():
    w, _, _ = _parse_compare("I prefer A")
    assert w == "A"


def test_regression_pass_rate_counts_substring_hits():
    cases = [
        EvalCase(prompt="what is 2+2?", expected="4"),
        EvalCase(prompt="capital of Japan?", expected="Tokyo"),
        EvalCase(prompt="http not found?", expected="404"),
    ]

    def answer(p: str) -> str:
        if "2+2" in p: return "The answer is 4."
        if "Japan" in p: return "Tokyo is the capital."
        if "not found" in p: return "code 400, probably"
        return ""

    rate, details = regression_pass_rate(answer_fn=answer, cases=cases)
    assert round(rate, 2) == 0.67
    assert sum(1 for d in details if d["pass"]) == 2
