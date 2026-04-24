"""Real eval harness for distillation + skill evolution.

Three gates, all scored by a local judge model (qwen3:4b by default):

  1. Regression  — held-out (prompt, expected-substring) pairs that the
                   previous deployed Oracle answered well. New candidate must
                   not fall below the baseline pass rate.
  2. Diversity   — varied prompts across Zach's domains (trading, business,
                   code, memory recall). Judge scores 0-1. Average must stay
                   above threshold.
  3. Improvement — prompts the candidate is *trained to fix*. Judge compares
                   candidate vs baseline head-to-head; improvement = win rate
                   minus loss rate.

Scores are real. Stubs are gone.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import ollama

from nexus.config import settings

logger = logging.getLogger(__name__)


@dataclass
class EvalCase:
    prompt: str
    expected: str = ""          # substring that MUST appear (regression)
    topic: str = "general"      # for grouping diversity results
    note: str = ""


@dataclass
class JudgedScore:
    prompt: str
    answer: str
    score: float
    reason: str


@dataclass
class CompareResult:
    prompt: str
    candidate: str
    baseline: str
    winner: str  # "candidate" | "baseline" | "tie"
    margin: float


@dataclass
class EvalReport:
    regression_pass_rate: float
    diversity_score: float
    improvement_rate: float
    regression_cases: int
    diversity_cases: int
    improvement_cases: int
    duration_sec: float
    details_path: str

    def to_dict(self) -> dict:
        return asdict(self)


# ---------- Default eval sets — edit these as Oracle grows ----------

DEFAULT_REGRESSION: list[EvalCase] = [
    EvalCase(
        prompt="What is 2 + 2? Answer with only the number.",
        expected="4",
        topic="arithmetic",
    ),
    EvalCase(
        prompt="What does RAG stand for in AI? One line.",
        expected="retrieval",
        topic="ml",
    ),
    EvalCase(
        prompt="Name the city that is Hawaii's state capital.",
        expected="Honolulu",
        topic="geography",
    ),
    EvalCase(
        prompt="What HTTP status code is 'Not Found'?",
        expected="404",
        topic="web",
    ),
    EvalCase(
        prompt="In Python, what keyword defines a function? One word.",
        expected="def",
        topic="code",
    ),
]

DEFAULT_DIVERSITY: list[EvalCase] = [
    EvalCase(prompt="Summarize what a limit order is in one sentence.", topic="trading"),
    EvalCase(prompt="Explain LoRA adapters for LLMs in two sentences.", topic="ml"),
    EvalCase(prompt="How would you structure a product launch announcement email? Bullet the components.", topic="marketing"),
    EvalCase(prompt="What are the tradeoffs between SQLite and LanceDB for local AI memory?", topic="systems"),
    EvalCase(prompt="Write a 3-sentence cold open for an AI newsletter post.", topic="writing"),
    EvalCase(prompt="Given a 24GB GPU, how do you fit a 30B MoE model plus a 1GB embedder?", topic="infra"),
]


# ---------- Eval primitives ----------


def _client() -> ollama.Client:
    return ollama.Client(host=settings.oracle_ollama_host)


def _chat(
    client: ollama.Client,
    *,
    model: str,
    system: str,
    prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 512,
    think: bool = False,
) -> str:
    kw: dict = dict(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        options={"temperature": temperature, "num_predict": max_tokens},
    )
    try:
        r = client.chat(**kw, think=think)
    except TypeError:
        r = client.chat(**kw)
    from nexus._llm_util import strip_think
    return strip_think(r["message"]["content"])


def regression_pass_rate(
    *, answer_fn: Callable[[str], str], cases: list[EvalCase]
) -> tuple[float, list[dict]]:
    passes = 0
    details: list[dict] = []
    for c in cases:
        ans = answer_fn(c.prompt)
        hit = c.expected.lower() in (ans or "").lower()
        passes += int(hit)
        details.append(
            {"prompt": c.prompt, "expected": c.expected, "answer": ans[:400], "pass": hit}
        )
    return passes / max(1, len(cases)), details


def diversity_score(
    *,
    answer_fn: Callable[[str], str],
    cases: list[EvalCase],
    judge_model: str | None = None,
) -> tuple[float, list[JudgedScore]]:
    judge_model = judge_model or settings.oracle_fast_model
    client = _client()
    scores: list[JudgedScore] = []

    judge_system = (
        "You are a strict evaluator. Score the candidate's answer to a prompt "
        "on a 0.0-1.0 scale based on correctness, relevance, conciseness, and "
        "usefulness. Return ONLY this JSON: "
        '{"score": <float>, "reason": "<1 sentence>"}'
    )

    for c in cases:
        ans = answer_fn(c.prompt)
        jp = f"PROMPT:\n{c.prompt}\n\nANSWER:\n{ans}\n\nReturn JSON only."
        raw = _chat(
            client,
            model=judge_model,
            system=judge_system,
            prompt=jp,
            temperature=0.0,
            max_tokens=200,
        )
        score, reason = _parse_judge(raw)
        scores.append(JudgedScore(prompt=c.prompt, answer=ans, score=score, reason=reason))

    avg = sum(s.score for s in scores) / max(1, len(scores))
    return avg, scores


def head_to_head(
    *,
    candidate_fn: Callable[[str], str],
    baseline_fn: Callable[[str], str],
    cases: list[EvalCase],
    judge_model: str | None = None,
) -> tuple[float, list[CompareResult]]:
    """Return (improvement_rate, details).

    improvement_rate = (#candidate_wins - #baseline_wins) / total
    """
    judge_model = judge_model or settings.oracle_fast_model
    client = _client()
    results: list[CompareResult] = []

    judge_system = (
        "You are a strict evaluator comparing two answers. Choose which is "
        "better on correctness + usefulness + concision. Return ONLY this JSON: "
        '{"winner": "A"|"B"|"T", "margin": <0.0-1.0>, "reason": "<1 sentence>"}'
    )

    for c in cases:
        a = candidate_fn(c.prompt)
        b = baseline_fn(c.prompt)
        jp = (
            f"PROMPT:\n{c.prompt}\n\nA (candidate):\n{a}\n\nB (baseline):\n{b}\n\n"
            "Return JSON only."
        )
        raw = _chat(
            client,
            model=judge_model,
            system=judge_system,
            prompt=jp,
            temperature=0.0,
            max_tokens=200,
        )
        winner_letter, margin, _ = _parse_compare(raw)
        winner = {"A": "candidate", "B": "baseline", "T": "tie"}.get(winner_letter, "tie")
        results.append(
            CompareResult(
                prompt=c.prompt, candidate=a, baseline=b, winner=winner, margin=margin
            )
        )

    wins = sum(1 for r in results if r.winner == "candidate")
    losses = sum(1 for r in results if r.winner == "baseline")
    rate = (wins - losses) / max(1, len(results))
    return rate, results


# ---------- Parsers (lenient — judges don't always stay in JSON) ----------


def _parse_judge(raw: str) -> tuple[float, str]:
    """Lenient parser — tries JSON, then `score: 0.7` pattern, then bare float."""
    import re

    raw = raw.strip()
    # 1. Try strict JSON object first
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        obj = json.loads(raw[start:end])
        if "score" in obj:
            return float(obj["score"]), str(obj.get("reason", ""))[:200]
    except Exception:
        pass
    # 2. Look for `"score": <float>` or `score: <float>`
    m = re.search(r'"?score"?\s*[:=]\s*([01]?\.\d+|[01])', raw)
    if m:
        return float(m.group(1)), raw[:200]
    # 3. Fallback — first float in [0,1] that isn't preceded by a range "-"
    for tok in raw.replace(",", " ").replace(":", " ").split():
        try:
            f = float(tok)
            if 0.0 <= f <= 1.0:
                return f, raw[:200]
        except ValueError:
            continue
    return 0.0, raw[:200]


def _parse_compare(raw: str) -> tuple[str, float, str]:
    raw = raw.strip()
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        obj = json.loads(raw[start:end])
        w = str(obj.get("winner", "T")).upper()[:1]
        if w not in {"A", "B", "T"}:
            w = "T"
        return w, float(obj.get("margin", 0.0)), str(obj.get("reason", ""))[:200]
    except Exception:
        u = raw.upper()
        if "A" in u and "B" not in u:
            return "A", 0.5, raw[:200]
        if "B" in u and "A" not in u:
            return "B", 0.5, raw[:200]
        return "T", 0.0, raw[:200]


# ---------- Orchestration entry point ----------


def run_full_eval(
    *,
    candidate_fn: Callable[[str], str],
    baseline_fn: Callable[[str], str],
    regression: list[EvalCase] | None = None,
    diversity: list[EvalCase] | None = None,
    improvement: list[EvalCase] | None = None,
    judge_model: str | None = None,
    details_dir: Path | None = None,
) -> EvalReport:
    """Run all three gates; returns a structured report and writes details to disk."""
    t0 = time.time()
    reg = regression or DEFAULT_REGRESSION
    div = diversity or DEFAULT_DIVERSITY
    imp = improvement or []  # caller supplies task-specific prompts

    reg_rate, reg_detail = regression_pass_rate(answer_fn=candidate_fn, cases=reg)
    div_rate, div_detail = diversity_score(
        answer_fn=candidate_fn, cases=div, judge_model=judge_model
    )
    imp_rate: float
    imp_detail: list[CompareResult]
    if imp:
        imp_rate, imp_detail = head_to_head(
            candidate_fn=candidate_fn,
            baseline_fn=baseline_fn,
            cases=imp,
            judge_model=judge_model,
        )
    else:
        imp_rate, imp_detail = 0.0, []

    out_dir = details_dir or (settings.oracle_home / "eval")
    out_dir.mkdir(parents=True, exist_ok=True)
    details_path = out_dir / f"eval_{int(time.time())}.json"
    details_path.write_text(
        json.dumps(
            {
                "regression": reg_detail,
                "diversity": [asdict(s) for s in div_detail],
                "improvement": [asdict(r) for r in imp_detail],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return EvalReport(
        regression_pass_rate=round(reg_rate, 4),
        diversity_score=round(div_rate, 4),
        improvement_rate=round(imp_rate, 4),
        regression_cases=len(reg),
        diversity_cases=len(div),
        improvement_cases=len(imp),
        duration_sec=round(time.time() - t0, 2),
        details_path=str(details_path),
    )
