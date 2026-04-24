"""Skill self-evolution — DGM-inspired.

Loop:
  1. Identify a gap: a user intent that routed to 0 skills or to skills with
     low confidence.
  2. Propose: ask the LLM to write a new Skill subclass targeting that gap.
  3. Syntactic validation: AST-parse + import-in-sandbox.
  4. Semantic validation: judge-score the skill's output on a held-out prompt.
  5. Promote: write to `skills/evolved/`, bumped origin="self_written".
  6. Archive rejects with reasons for future analysis.

Research: DGM (arXiv 2505.22954) shows self-modification with proper guardrails
outperforms static agents. The critical invariants: sandbox, eval gate, rollback.
"""

from __future__ import annotations

import ast
import json
import logging
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import ollama

from oracle.config import settings
from oracle.distillation.eval import _chat, _parse_judge
from oracle.sandbox import DockerSandbox
from oracle.skills.base import Skill, SkillContext, llm_complete
from oracle.skills.registry import SkillRegistry
from oracle.skills.router import SkillRouter

logger = logging.getLogger(__name__)


EVOLVED_DIR = Path(__file__).parent / "evolved"
EVOLVED_DIR.mkdir(parents=True, exist_ok=True)
# Ensure the evolved dir is a proper package for importlib
_init = EVOLVED_DIR / "__init__.py"
if not _init.exists():
    _init.write_text("# Evolved skills — written by Oracle itself.\n", encoding="utf-8")


@dataclass
class EvolutionResult:
    ok: bool
    skill_id: str | None
    skill_file: str | None
    score: float
    rejection_reasons: list[str] = field(default_factory=list)
    proposal_raw: str = ""
    elapsed_sec: float = 0.0

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "skill_id": self.skill_id,
            "skill_file": self.skill_file,
            "score": self.score,
            "rejection_reasons": self.rejection_reasons,
            "elapsed_sec": self.elapsed_sec,
        }


PROPOSAL_SYSTEM = """You write new Python Skill classes for Oracle's skill library.

Invariants (if ANY is broken the skill will be rejected):
- Exactly ONE class, subclassing `Skill`
- Fields: `id` (snake_case), `name`, `description`, `tags: list[str]`, `inputs: dict[str,str]`, `outputs: dict[str,str]`
- Set `origin = "self_written"`
- Method: `def execute(self, ctx: SkillContext, inputs: dict) -> dict:`
- Use `llm_complete(ctx, system=..., prompt=..., max_tokens=...)` for any LLM call
- No filesystem writes, no subprocess, no network except `llm_complete`
- Import only: `from oracle.skills.base import Skill, SkillContext, llm_complete`
- Handle missing inputs gracefully (use .get with defaults)
- Output a dict matching `outputs`; never raise on normal inputs

Output ONLY the Python code in a triple-backtick python block. No commentary.
"""


PROPOSAL_TEMPLATE = """A user asked:
  "{intent}"

The current skill router returned low-confidence matches, so Oracle is gap-filling.

Write a new Skill that would answer this intent well. The skill should be
generalizable (not hard-coded to this one prompt) but clearly relevant to the
pattern.

Remember the invariants. Return ONLY the Python class in a ```python block.
"""


def _propose_skill(intent: str, *, ctx: SkillContext) -> str:
    raw = llm_complete(
        ctx,
        system=PROPOSAL_SYSTEM,
        prompt=PROPOSAL_TEMPLATE.format(intent=intent),
        temperature=0.2,
        max_tokens=3000,
        think=False,
    )
    return raw


def _extract_code(raw: str) -> str | None:
    """Pull the first syntactically-valid ``` ... ``` block that looks like a Skill.

    qwen3 often emits multiple code fences interleaved with commentary; picking
    the *longest* block sometimes catches a truncated one at the end, so we
    instead scan in order and keep the first that parses + defines a class.
    """
    import ast
    import re

    blocks: list[str] = []
    for m in re.finditer(r"```(?:python)?\s*([\s\S]*?)```", raw):
        body = m.group(1).strip()
        if body:
            blocks.append(body)

    def _looks_like_skill(code: str) -> bool:
        if "class " not in code or "Skill" not in code:
            return False
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == "Skill":
                        return True
                    if isinstance(base, ast.Attribute) and base.attr == "Skill":
                        return True
        return False

    for b in blocks:
        if _looks_like_skill(b):
            return b
    # Last resort — any syntactically valid block
    for b in blocks:
        try:
            ast.parse(b)
            return b
        except SyntaxError:
            continue
    # No fences — accept naked code if it looks skill-shaped and parses
    stripped = raw.strip()
    if "class " in stripped and "Skill" in stripped:
        try:
            ast.parse(stripped)
            return stripped
        except SyntaxError:
            pass
    return None


def _syntactic_check(code: str) -> list[str]:
    reasons: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"syntax error: {e}"]

    # Forbidden imports / calls
    bad_imports = {"os", "sys", "subprocess", "socket", "urllib", "requests", "shutil"}
    bad_calls = {"exec", "eval", "compile", "__import__", "open"}
    classes = 0
    has_execute = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name.split(".")[0] in bad_imports:
                    reasons.append(f"forbidden import: {n.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            if mod in bad_imports:
                reasons.append(f"forbidden import-from: {node.module}")
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in bad_calls:
                reasons.append(f"forbidden call: {f.id}")
        elif isinstance(node, ast.ClassDef):
            classes += 1
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "execute":
                    has_execute = True

    if classes != 1:
        reasons.append(f"must define exactly 1 class, found {classes}")
    if not has_execute:
        reasons.append("missing execute() method")
    return reasons


def _load_and_run(code: str, *, ctx: SkillContext, test_input: dict) -> tuple[Skill | None, dict | None, str | None]:
    """Write code to a temp module OUTSIDE the skills package, import, run.

    The temp module must not live under `skills/evolved/` or the registry
    will pick it up at doctor time as a duplicate skill id.
    """
    import tempfile

    mod_name = f"oracle_evolved_probe_{uuid.uuid4().hex[:10]}"
    tmp_dir = Path(tempfile.mkdtemp(prefix="oracle_evolve_"))
    tmp_path = tmp_dir / f"{mod_name}.py"
    tmp_path.write_text(code, encoding="utf-8")

    try:
        import importlib.util
        import sys as _sys

        spec = importlib.util.spec_from_file_location(mod_name, tmp_path)
        if not spec or not spec.loader:
            return None, None, "cannot build module spec"
        module = importlib.util.module_from_spec(spec)
        _sys.modules[mod_name] = module
        spec.loader.exec_module(module)

        skill_cls = None
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, Skill) and obj is not Skill:
                skill_cls = obj
                break
        if skill_cls is None:
            return None, None, "no Skill subclass found"
        instance = skill_cls()
        if not instance.id:
            return None, None, "skill has no id"

        out = instance.execute(ctx, test_input)
        if not isinstance(out, dict):
            return instance, None, f"execute returned {type(out).__name__}, not dict"
        return instance, out, None
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"
    finally:
        import shutil as _sh
        try:
            _sh.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


def _judge_output(
    *, intent: str, output: dict, judge_model: str | None = None
) -> tuple[float, str]:
    """Two-step judge: brief rationale, then a single score number on its own line.

    qwen3 ignores "no preamble" instructions so we give it room to ramble, then
    demand a final structured line, and parse the last score we find.
    """
    judge_model = judge_model or settings.oracle_fast_model
    client = ollama.Client(host=settings.oracle_ollama_host)
    system = (
        "You rate how well a skill's output serves the user's intent on a "
        "0.0 - 1.0 scale. Output format (exactly):\n"
        "REASON: <one sentence>\n"
        "SCORE: <number between 0 and 1>"
    )
    prompt = (
        f"INTENT:\n{intent}\n\n"
        f"OUTPUT:\n{json.dumps(output, indent=2, default=str)[:1200]}\n\n"
        "Reply with REASON line then SCORE line. Nothing else."
    )
    raw = _chat(
        client,
        model=judge_model,
        system=system,
        prompt=prompt,
        temperature=0.0,
        max_tokens=800,
        think=False,
    )
    # Pull SCORE: <num> first, then fall back to the generic parser.
    import re

    # Find the LAST SCORE: line (preamble may contain false positives earlier)
    score_matches = list(re.finditer(r"SCORE\s*:\s*([01]?\.\d+|[01](?:\.0+)?)", raw))
    if score_matches:
        score = float(score_matches[-1].group(1))
        r_match = re.search(r"REASON\s*:\s*(.+?)(?:\n|$)", raw)
        reason = r_match.group(1).strip() if r_match else raw[:200]
        return score, reason[:200]
    return _parse_judge(raw)


def evolve_skill(
    *,
    intent: str,
    min_score: float = 0.55,
    ctx: SkillContext | None = None,
) -> EvolutionResult:
    """Propose → validate → (promote | archive) a new skill for the given intent."""
    t0 = time.time()
    ctx = ctx or SkillContext(
        llm=ollama.Client(host=settings.oracle_ollama_host),
        model=settings.oracle_primary_model,
    )

    raw = _propose_skill(intent, ctx=ctx)
    code = _extract_code(raw)
    if not code:
        return EvolutionResult(
            ok=False,
            skill_id=None,
            skill_file=None,
            score=0.0,
            rejection_reasons=["no code block returned by proposer"],
            proposal_raw=raw[:500],
            elapsed_sec=round(time.time() - t0, 2),
        )

    syn_reasons = _syntactic_check(code)
    if syn_reasons:
        archive = EVOLVED_DIR.parent / "evolved_archive"
        archive.mkdir(parents=True, exist_ok=True)
        (archive / f"rejected_{int(time.time())}.py").write_text(code, encoding="utf-8")
        return EvolutionResult(
            ok=False,
            skill_id=None,
            skill_file=None,
            score=0.0,
            rejection_reasons=syn_reasons,
            proposal_raw=raw[:500],
            elapsed_sec=round(time.time() - t0, 2),
        )

    # Smoke-run the skill with a reasonable default input
    test_input = _guess_inputs(code, intent=intent)
    instance, output, err = _load_and_run(code, ctx=ctx, test_input=test_input)
    if err or output is None or instance is None:
        return EvolutionResult(
            ok=False,
            skill_id=getattr(instance, "id", None),
            skill_file=None,
            score=0.0,
            rejection_reasons=[f"runtime: {err}"],
            proposal_raw=raw[:500],
            elapsed_sec=round(time.time() - t0, 2),
        )

    score, reason = _judge_output(intent=intent, output=output)
    if score < min_score:
        return EvolutionResult(
            ok=False,
            skill_id=instance.id,
            skill_file=None,
            score=score,
            rejection_reasons=[f"score {score:.2f} < {min_score:.2f}: {reason}"],
            proposal_raw=raw[:500],
            elapsed_sec=round(time.time() - t0, 2),
        )

    # Promote: save alongside seed skills under evolved/
    promoted = EVOLVED_DIR / f"{instance.id}.py"
    promoted.write_text(code, encoding="utf-8")

    return EvolutionResult(
        ok=True,
        skill_id=instance.id,
        skill_file=str(promoted),
        score=score,
        rejection_reasons=[],
        proposal_raw=raw[:500],
        elapsed_sec=round(time.time() - t0, 2),
    )


def _guess_inputs(code: str, *, intent: str) -> dict[str, Any]:
    """Heuristic: pull `inputs = {...}` from the skill, build a sensible test payload."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"text": intent, "query": intent}

    inputs_keys: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "inputs":
                    if isinstance(node.value, ast.Dict):
                        for k in node.value.keys:
                            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                inputs_keys.append(k.value)

    test: dict[str, Any] = {}
    for k in inputs_keys:
        # Best-guess defaults by name
        if k in {"text", "content", "passage", "body", "article"}:
            test[k] = intent
        elif k in {"query", "question", "q", "prompt"}:
            test[k] = intent
        elif k in {"n", "k", "count", "limit", "max_items"}:
            test[k] = 3
        elif "max" in k and "word" in k:
            test[k] = 80
        else:
            test[k] = intent
    if not test:
        test = {"text": intent, "query": intent}
    return test


def evolve_from_router_gap(
    *,
    intent: str,
    sim_threshold: float = 0.4,
    min_score: float = 0.55,
) -> EvolutionResult | None:
    """Only evolve if the existing router has no good match for this intent."""
    reg = SkillRegistry()
    reg.load_all()
    router = SkillRouter(reg)
    router.build_index()
    top = router.route(intent, top_k=1, min_similarity=0.0)
    if top and top[0][1] >= sim_threshold:
        return None  # existing skill covers it
    return evolve_skill(intent=intent, min_score=min_score)
