"""Decompose a goal into an ordered task list."""

import json
import re

from nexus.skills.base import Skill, SkillContext, llm_complete


class DecomposeTask(Skill):
    id = "decompose_task"
    name = "Decompose Task"
    description = "Break a goal into an ordered list of concrete tasks with dependencies."
    tags = ["planning", "decomposition", "project", "tasks", "breakdown"]
    inputs = {"goal": "str", "context": "str (optional)"}
    outputs = {"tasks": "list[dict]"}
    model_preference = "primary"

    def execute(self, ctx: SkillContext, inputs: dict) -> dict:
        goal = inputs["goal"]
        context = inputs.get("context", "")
        system = (
            "You decompose goals into ordered task lists. Each task must be small "
            "enough to finish in one sitting. Output ONLY valid JSON matching the "
            "schema — no prose, no markdown fences, no keys outside the schema."
        )
        prompt = (
            f"Goal: {goal}\n"
            + (f"Context: {context}\n" if context else "")
            + "\nOutput a JSON object with one key `tasks`, an array of objects, "
            "each with these fields:\n"
            '  "n": int (1-indexed step number)\n'
            '  "task": string (the concrete task)\n'
            '  "deps": string (comma-separated task #s this depends on, or "none")\n'
            '  "effort": one of "S" | "M" | "L"\n'
            "Produce 3-8 tasks."
        )
        raw = llm_complete(
            ctx, system=system, prompt=prompt, max_tokens=900, format="json"
        )
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
        m = re.search(r"\{[\s\S]*\}", raw)
        tasks: list[dict] = []
        if m:
            try:
                data = json.loads(m.group(0))
                for i, t in enumerate(data.get("tasks", []) or [], 1):
                    if not isinstance(t, dict):
                        continue
                    tasks.append(
                        {
                            "n": int(t.get("n", i)),
                            "task": str(t.get("task", "")).strip(),
                            "deps": str(t.get("deps", "none")).strip() or "none",
                            "effort": str(t.get("effort", "M")).strip().upper()[:1] or "M",
                        }
                    )
            except Exception:
                pass
        return {"tasks": tasks}
