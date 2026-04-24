"""Plan mode (§09 + §13 orchestrator).

Generates an ordered task list from a user intent without calling tools.
Persists to `<ORACLE_HOME>/plans/<thread_id>.json`. `execute_next()` runs
one task through the normal agent loop.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from nexus.config import settings
from nexus.prompts import TRINITY_NEXUS_CONSTITUTION


@dataclass
class PlanTask:
    id: str
    description: str
    status: str = "pending"          # pending | done | failed | skipped
    result: str = ""
    started_ts: float = 0.0
    finished_ts: float = 0.0


@dataclass
class Plan:
    id: str
    intent: str
    created_ts: float
    tasks: list[PlanTask] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "intent": self.intent,
            "created_ts": self.created_ts,
            "tasks": [t.__dict__ for t in self.tasks],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Plan":
        return cls(
            id=d["id"],
            intent=d["intent"],
            created_ts=d["created_ts"],
            tasks=[PlanTask(**t) for t in d.get("tasks", [])],
        )


def _path(thread_id: str) -> Path:
    p = settings.oracle_home / "plans" / f"{thread_id}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def save(plan: Plan, thread_id: str) -> Path:
    p = _path(thread_id)
    p.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
    return p


def load(thread_id: str) -> Plan | None:
    p = _path(thread_id)
    if not p.exists():
        return None
    try:
        return Plan.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return None


PLANNER_SYSTEM = (
    "You are the PLANNER stage of Trinity Nexus (§09, §13 orchestrator mode). "
    "Given the user's intent, produce an ordered list of concrete, atomic tasks "
    "that a capable agent (with file/web/shell/memory tools) can execute in "
    "sequence. Each task must be small enough that ONE tool-use round resolves it.\n\n"
    "Output strictly this JSON:\n"
    '{\n'
    '  "tasks": [\n'
    '    {"description": "<one verb-first step>"},\n'
    '    ...\n'
    '  ]\n'
    "}\n\n"
    "Rules: 2-10 tasks. No prose. No explanations. Do not call tools. "
    "If the intent is trivial (single turn), return one task."
)


def _extract_json(raw: str) -> dict:
    import re

    raw = raw.strip()
    try:
        s = raw.index("{")
        e = raw.rindex("}") + 1
        return json.loads(raw[s:e])
    except Exception:
        return {"tasks": [{"description": raw[:200]}]}


def draft(intent: str, thread_id: str) -> Plan:
    """Ask the primary model to draft a plan for `intent`."""
    import ollama

    client = ollama.Client(host=settings.oracle_ollama_host)
    kw: dict = dict(
        model=settings.oracle_primary_model,
        messages=[
            {"role": "system", "content": PLANNER_SYSTEM},
            {"role": "user", "content": f"INTENT: {intent}\n\nReturn JSON only."},
        ],
        options={
            "temperature": 0.2,
            "num_ctx": settings.oracle_num_ctx,
            "num_predict": 1200,
        },
        format="json",
    )
    try:
        r = client.chat(**kw, think=False)
    except TypeError:
        r = client.chat(**kw)
    from nexus._llm_util import strip_think
    raw = strip_think(r["message"]["content"])
    obj = _extract_json(raw)
    tasks = [
        PlanTask(id=str(uuid.uuid4())[:8], description=str(t.get("description", "")).strip())
        for t in obj.get("tasks") or []
        if str(t.get("description", "")).strip()
    ]
    if not tasks:
        tasks = [PlanTask(id=str(uuid.uuid4())[:8], description=intent)]

    plan = Plan(
        id=str(uuid.uuid4())[:10],
        intent=intent,
        created_ts=time.time(),
        tasks=tasks,
    )
    save(plan, thread_id)
    return plan


def next_pending(plan: Plan) -> PlanTask | None:
    for t in plan.tasks:
        if t.status == "pending":
            return t
    return None


def mark(plan: Plan, task_id: str, *, status: str, result: str, thread_id: str) -> None:
    for t in plan.tasks:
        if t.id == task_id:
            t.status = status
            t.result = result[:2000]
            if t.started_ts == 0:
                t.started_ts = time.time()
            t.finished_ts = time.time()
            break
    save(plan, thread_id)
