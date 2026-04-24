"""Decompose a goal into an ordered task list."""

import re

from oracle.skills.base import Skill, SkillContext, llm_complete


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
            "You turn goals into concrete task lists. Each task must be small "
            "enough to complete in one sitting. Identify dependencies explicitly."
        )
        prompt = (
            f"Goal: {goal}\n"
            + (f"Context: {context}\n" if context else "")
            + "\nDecompose. For EACH task, output:\n"
            "N) TASK: <task>\n   DEPS: <none | task #s>\n   EFFORT: <S|M|L>"
        )
        raw = llm_complete(ctx, system=system, prompt=prompt, max_tokens=900)
        tasks: list[dict] = []
        blocks = re.split(r"\n(?=\d+\))", raw)
        for b in blocks:
            m = re.search(r"(\d+)\)\s*TASK:\s*(.+?)(?:\n|$)", b)
            if not m:
                continue
            deps_m = re.search(r"DEPS:\s*(.+)", b)
            eff_m = re.search(r"EFFORT:\s*([SML])", b)
            tasks.append(
                {
                    "n": int(m.group(1)),
                    "task": m.group(2).strip(),
                    "deps": deps_m.group(1).strip() if deps_m else "none",
                    "effort": eff_m.group(1) if eff_m else "M",
                }
            )
        return {"tasks": tasks}
