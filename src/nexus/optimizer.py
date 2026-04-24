"""Prompt optimizer — evolutionary, DSPy-inspired.

We don't pull DSPy as a hard dep (heavy). Instead we run a small
evolutionary loop using the tools we already have:

  1. Score the current constitution against the 3-gate eval harness.
  2. Ask the PRIMARY model to propose N variations of a TARGET SECTION
     (not the whole constitution — keep identity-critical sections frozen).
  3. For each variation: plug it in, re-score, keep the best.
  4. Optionally: commit the new section with a scorecard if it wins.

Default frozen sections (never mutated): §01 (Core Activation),
§10 (Truth Engine), §11 (Autonomy), §29 (Security), §33 (Prime Directive).
Default mutable: §14 (Response Style), §15 (Depth Control), §16
(Prompt Engineering guidance).

Use:  nexus optimize-prompt --iterations 3 --section 14
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from nexus.config import settings


FROZEN_SECTIONS = {1, 2, 3, 10, 11, 22, 23, 29, 32, 33}


@dataclass
class Proposal:
    section: int
    original: str
    candidate: str
    score_reg: float
    score_div: float
    score_imp: float

    @property
    def overall(self) -> float:
        # Weighted average — tuneable
        return 0.4 * self.score_reg + 0.3 * self.score_div + 0.3 * (0.5 + self.score_imp / 2)


def _read_constitution() -> str:
    from nexus import prompts as _p
    return _p.TRINITY_NEXUS_CONSTITUTION


def _split_sections(text: str) -> list[tuple[int, str]]:
    """Return [(section_number, section_body_including_header), ...]."""
    pattern = re.compile(r"(SECTION\s+(\d{1,2})[^\n]*\n.*?)(?=SECTION\s+\d{1,2}|$)", re.DOTALL)
    return [(int(m.group(2)), m.group(1)) for m in pattern.finditer(text)]


def _assemble(sections: list[tuple[int, str]], preamble: str) -> str:
    return preamble + "\n" + "".join(body for _, body in sections)


def _propose_variations(section_body: str, *, n: int, model: str | None = None) -> list[str]:
    """Ask the model for N crisper variations that preserve intent."""
    import ollama as _ollama

    client = _ollama.Client(host=settings.oracle_ollama_host)
    system = (
        "You rewrite operating-prompt sections for Trinity Nexus. "
        "Preserve every directive, constraint, and named field. Make the text "
        "crisper and more operationally reliable. Do NOT invent new rules. "
        f"Return STRICT JSON: {{\"variations\": [\"...\", \"...\"]}} — exactly {n} items. "
        "Each variation keeps the same 'SECTION NN - TITLE' header format."
    )
    kw: dict = dict(
        model=model or settings.oracle_primary_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"ORIGINAL:\n{section_body}\n\nReturn JSON only."},
        ],
        options={"temperature": 0.5, "num_predict": 3000, "num_ctx": settings.oracle_num_ctx},
        format="json",
    )
    try:
        r = client.chat(**kw, think=False)
    except TypeError:
        r = client.chat(**kw)
    from nexus._llm_util import strip_think
    raw = strip_think(r["message"]["content"])
    s = raw.find("{")
    e = raw.rfind("}")
    if s < 0 or e <= s:
        return []
    try:
        obj = json.loads(raw[s:e + 1])
        return [v for v in obj.get("variations", []) if isinstance(v, str) and v.strip()][:n]
    except Exception:
        return []


def _score_with_constitution(constitution: str) -> tuple[float, float, float]:
    """Run the 3-gate eval against a candidate system prompt."""
    from nexus.distillation.eval import run_full_eval
    import ollama as _ollama

    client = _ollama.Client(host=settings.oracle_ollama_host)
    model = settings.oracle_primary_model

    def _ask(prompt: str) -> str:
        kw: dict = dict(
            model=model,
            messages=[
                {"role": "system", "content": constitution[:8000]},
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.2, "num_predict": 400, "num_ctx": settings.oracle_num_ctx},
        )
        try:
            r = client.chat(**kw, think=False)
        except TypeError:
            r = client.chat(**kw)
        from nexus._llm_util import strip_think
        return strip_think(r["message"]["content"])

    # Baseline == candidate for h2h (we're not comparing two prompts here; we
    # just need a stable baseline_fn signature). Improvement score will be ~0.
    report = run_full_eval(candidate_fn=_ask, baseline_fn=_ask, improvement=[])
    return report.regression_pass_rate, report.diversity_score, report.improvement_rate


def optimize(
    *,
    section_num: int = 14,
    iterations: int = 3,
    variations_per_iter: int = 3,
    apply: bool = False,
    output_dir: Path | None = None,
) -> dict:
    """Run the optimizer. Writes every scored proposal to disk."""
    if section_num in FROZEN_SECTIONS:
        return {
            "ok": False,
            "reason": f"section {section_num} is frozen (identity-critical). Choose a different one.",
        }

    base = _read_constitution()
    preamble = base.split("SECTION 01", 1)[0]
    sections = _split_sections(base)
    target_idx = None
    for i, (n, _) in enumerate(sections):
        if n == section_num:
            target_idx = i
            break
    if target_idx is None:
        return {"ok": False, "reason": f"no section {section_num} found"}

    original_body = sections[target_idx][1]
    reg0, div0, imp0 = _score_with_constitution(base)
    best = Proposal(
        section=section_num,
        original=original_body,
        candidate=original_body,
        score_reg=reg0, score_div=div0, score_imp=imp0,
    )

    out_dir = output_dir or (settings.oracle_home / "optimizer")
    out_dir.mkdir(parents=True, exist_ok=True)

    history: list[dict] = [{
        "iteration": 0, "score": best.overall,
        "reg": reg0, "div": div0, "imp": imp0, "is_original": True,
    }]

    for it in range(1, iterations + 1):
        variations = _propose_variations(original_body, n=variations_per_iter)
        for v in variations:
            trial_sections = list(sections)
            trial_sections[target_idx] = (section_num, v.rstrip() + "\n\n")
            candidate_cst = _assemble(trial_sections, preamble)
            try:
                r, d, i = _score_with_constitution(candidate_cst)
            except Exception:
                continue
            p = Proposal(
                section=section_num, original=original_body, candidate=v,
                score_reg=r, score_div=d, score_imp=i,
            )
            history.append({
                "iteration": it, "score": p.overall,
                "reg": r, "div": d, "imp": i, "is_original": False,
            })
            if p.overall > best.overall:
                best = p

    # Persist scorecard
    ts = int(time.time())
    (out_dir / f"opt_{section_num}_{ts}.json").write_text(
        json.dumps({
            "section": section_num,
            "iterations": iterations,
            "best_score": best.overall,
            "best_scores": {"reg": best.score_reg, "div": best.score_div, "imp": best.score_imp},
            "history": history,
            "best_candidate": best.candidate[:4000],
        }, indent=2),
        encoding="utf-8",
    )

    if apply and best.candidate != original_body:
        # Rewrite src/nexus/prompts.py — replace the section in
        # TRINITY_NEXUS_CONSTITUTION. Risky operation: require that the
        # file can be re-imported cleanly afterward; if not, roll back.
        from nexus import prompts as _p
        prompts_path = Path(_p.__file__)
        src = prompts_path.read_text(encoding="utf-8")
        if original_body in src:
            backup = prompts_path.with_suffix(".py.bak")
            backup.write_text(src, encoding="utf-8")
            prompts_path.write_text(src.replace(original_body, best.candidate, 1), encoding="utf-8")
            try:
                import importlib
                importlib.reload(_p)
                applied = True
            except Exception:
                prompts_path.write_text(src, encoding="utf-8")
                applied = False
        else:
            applied = False
    else:
        applied = False

    return {
        "ok": True,
        "section": section_num,
        "baseline_score": history[0]["score"],
        "best_score": best.overall,
        "improved": best.overall > history[0]["score"],
        "applied": applied,
        "scorecard_path": str(out_dir / f"opt_{section_num}_{ts}.json"),
    }
