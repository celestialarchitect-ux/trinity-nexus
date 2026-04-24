"""Evaluate 2-N options across dimensions, produce a recommendation."""

import re

from nexus.skills.base import Skill, SkillContext, llm_complete


class CompareOptions(Skill):
    id = "compare_options"
    name = "Compare Options"
    description = "Evaluate 2-N options across user-specified dimensions; pick one with rationale."
    tags = ["decision", "comparison", "evaluation", "tradeoff"]
    inputs = {
        "options": "list[str]",
        "dimensions": "list[str] (default: cost, speed, risk, leverage)",
        "context": "str (optional)",
    }
    outputs = {"table": "str", "pick": "str", "why": "str"}
    model_preference = "reasoning"

    def execute(self, ctx: SkillContext, inputs: dict) -> dict:
        options = inputs["options"]
        dims = inputs.get("dimensions") or ["cost", "speed", "risk", "leverage"]
        context = inputs.get("context", "")
        system = (
            "You make sharp recommendations. Score each option 1-10 per dimension. "
            "Then pick one. Your pick must be defensible in one sentence."
        )
        prompt = (
            f"Options:\n"
            + "\n".join(f"- {o}" for o in options)
            + f"\n\nDimensions: {', '.join(dims)}\n"
            + (f"Context: {context}\n" if context else "")
            + "\nFormat:\n"
            "TABLE:\n| Option | "
            + " | ".join(dims)
            + " | Total |\n"
            + "| --- | "
            + " | ".join(["---"] * len(dims))
            + " | --- |\n"
            + "...\n\nPICK: <option>\nWHY: <one sentence>"
        )
        raw = llm_complete(
            ctx, system=system, prompt=prompt, max_tokens=700, temperature=0.2
        )
        pick_m = re.search(r"PICK:\s*(.+)", raw)
        why_m = re.search(r"WHY:\s*(.+)", raw)
        table = raw.split("PICK:", 1)[0].replace("TABLE:", "").strip()
        return {
            "table": table,
            "pick": pick_m.group(1).strip() if pick_m else "",
            "why": why_m.group(1).strip() if why_m else "",
        }
