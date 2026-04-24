"""Trinity Nexus operating modes (§13 of the constitution).

12 modes. Switching a mode appends a short overlay to the system prompt
so the agent takes on the posture the user named. The constitution tells
the model what each mode means; this module tracks which one is active
and produces the overlay.

Active mode is persisted to `<ORACLE_HOME>/mode.json` so it survives
REPL restarts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from nexus.config import settings


@dataclass(frozen=True)
class Mode:
    key: str
    name: str
    one_line: str
    directive: str
    # Optional model override. Consulted at agent-init time; overridden by
    # env var NEXUS_MODEL_<MODE_KEY> (e.g. NEXUS_MODEL_ARCHITECT=...).
    preferred_model: str = ""


MODES: dict[str, Mode] = {
    "architect": Mode(
        key="architect",
        name="ARCHITECT",
        one_line="Design systems, codebases, agents, ecosystems, brand architecture.",
        directive=(
            "You are in ARCHITECT MODE. Design the system before writing any "
            "code. Return: structure diagrams (text), component responsibilities, "
            "data flow, failure modes, and the smallest viable implementation "
            "path. Prefer composable layers over monoliths."
        ),
    ),
    "builder": Mode(
        key="builder",
        name="BUILDER",
        one_line="Write real code, prompts, scripts, docs, APIs, automations.",
        directive=(
            "You are in BUILDER MODE. Produce working artifacts. Read the repo "
            "before editing (§17). Make minimal safe changes. Explain what "
            "changed in one line. Provide verification steps."
        ),
    ),
    "strategist": Mode(
        key="strategist",
        name="STRATEGIST",
        one_line="Market, offers, launches, monetization, growth, risk, leverage.",
        directive=(
            "You are in STRATEGIST MODE. Evaluate market position, offer "
            "structure, timing, leverage, and risk. Quantify where possible. "
            "End with a concrete next action and a measurable signal."
        ),
    ),
    "codex": Mode(
        key="codex",
        name="CODEX",
        one_line="Philosophical, symbolic, narrative, high-concept material.",
        directive=(
            "You are in CODEX MODE. Produce material with elevated structure "
            "and meaning. Use symbolic precision, not decoration. Every line "
            "must carry weight. Honor the user's existing mythology."
        ),
    ),
    "critic": Mode(
        key="critic",
        name="CRITIC",
        one_line="Find flaws, risks, contradictions, weak assumptions, exposure.",
        directive=(
            "You are in CRITIC MODE. Your job is to find what is wrong. Be "
            "specific: cite the assumption, explain why it breaks, propose "
            "the stronger alternative. Do not soften. §25 Strategic Honesty."
        ),
    ),
    "executor": Mode(
        key="executor",
        name="EXECUTOR",
        one_line="Direct deliverables. Minimal explanation.",
        directive=(
            "You are in EXECUTOR MODE. Ship the artifact. No preamble, no "
            "recap of the request, no trailing summary. If tools are needed, "
            "call them. If the request is ambiguous, make the best "
            "reasonable assumption and state it in one line."
        ),
    ),
    "mirror": Mode(
        key="mirror",
        name="MIRROR",
        one_line="Reflect the user's thinking back with structure and pattern.",
        directive=(
            "You are in MIRROR MODE. Restate what the user is actually "
            "building, the deeper pattern underneath, and the structure "
            "they have not articulated yet. Do not add new material. Reveal."
        ),
    ),
    "research": Mode(
        key="research",
        name="RESEARCH",
        one_line="Verify, compare sources, cite, distinguish fact from memory.",
        directive=(
            "You are in RESEARCH MODE. Use web_fetch / web_search / retrieve "
            "_notes. Separate known fact / tool-confirmed / reasoned "
            "inference / speculation (§10). Cite what you used. Flag what is "
            "stale."
        ),
    ),
    "memory": Mode(
        key="memory",
        name="MEMORY",
        one_line="Summarize, classify, compress, preserve important context.",
        directive=(
            "You are in MEMORY MODE. Identify what is worth saving and "
            "classify it into Mind / Soul / Body (§07). Propose compression "
            "of stale threads. Never save noise."
        ),
    ),
    "evolution": Mode(
        key="evolution",
        name="EVOLUTION",
        one_line="Improve previous outputs, prompts, systems, strategies, names.",
        directive=(
            "You are in EVOLUTION MODE. Take the most recent artifact and "
            "produce a strictly stronger version. Keep what works. Upgrade "
            "what is weak. Document what changed and why."
        ),
    ),
    "governor": Mode(
        key="governor",
        name="GOVERNOR",
        one_line="Detect and prevent destructive, false, illegal, unsafe actions.",
        directive=(
            "You are in GOVERNOR MODE. Audit the plan before execution. "
            "Flag: destructive filesystem ops, credential exposure, "
            "irreversible deploys, legal/financial risk, silent failure "
            "modes. Require confirmation for anything irreversible."
        ),
    ),
    "orchestrator": Mode(
        key="orchestrator",
        name="ORCHESTRATOR",
        one_line="Coordinate agents, tools, files, memory, task queues.",
        directive=(
            "You are in ORCHESTRATOR MODE. Decompose the work into ordered "
            "steps. For each step decide: which tool, which sub-agent "
            "(spawn_agent), which memory tier to read, which to write. "
            "Produce a plan first; execute second."
        ),
    ),
}


def _state_path() -> Path:
    p = settings.oracle_home / "mode.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_active() -> Mode | None:
    p = _state_path()
    if not p.exists():
        return None
    try:
        key = json.loads(p.read_text(encoding="utf-8")).get("mode")
    except Exception:
        return None
    return MODES.get(key or "")


def set_active(key: str) -> Mode | None:
    key = key.lower().strip()
    if key in {"none", "off", "clear", "default"}:
        _state_path().unlink(missing_ok=True)
        return None
    mode = MODES.get(key)
    if not mode:
        return None
    _state_path().write_text(json.dumps({"mode": key}), encoding="utf-8")
    return mode


def overlay() -> str:
    """Block to append to the system prompt. Empty when no mode is active."""
    m = get_active()
    if not m:
        return ""
    return (
        f"## ACTIVE OPERATING MODE — {m.name}\n"
        f"{m.directive}\n"
    )


def preferred_model_for_active() -> str:
    """Return the model for the active mode, if any.

    Precedence: env NEXUS_MODEL_<KEY> > Mode.preferred_model > "".
    Agent caller falls back to settings.oracle_primary_model on "".
    """
    import os as _os
    m = get_active()
    if not m:
        return ""
    env_key = f"NEXUS_MODEL_{m.key.upper()}"
    env_val = _os.environ.get(env_key, "")
    if env_val:
        return env_val
    return m.preferred_model or ""


def describe_all() -> list[tuple[str, str]]:
    return [(m.key, m.one_line) for m in MODES.values()]
