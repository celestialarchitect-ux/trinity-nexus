"""Generate N distinct ideas on a topic."""

import re

from nexus.skills.base import Skill, SkillContext, llm_complete


class BrainstormIdeas(Skill):
    id = "brainstorm_ideas"
    name = "Brainstorm Ideas"
    description = "Generate N distinct, non-redundant ideas on a topic with one-line rationale each."
    tags = ["brainstorm", "ideation", "creative", "strategy", "divergent"]
    inputs = {"topic": "str", "n": "int (default 7)", "constraints": "str (optional)"}
    outputs = {"ideas": "list[dict]"}
    model_preference = "primary"

    def execute(self, ctx: SkillContext, inputs: dict) -> dict:
        topic = inputs["topic"]
        n = int(inputs.get("n", 7))
        constraints = inputs.get("constraints", "")
        system = (
            "You generate distinct, non-redundant ideas. Each must be materially "
            "different from the others — not variants. Rate each 1-10 for leverage."
        )
        prompt = (
            f"Topic: {topic}\n"
            + (f"Constraints: {constraints}\n" if constraints else "")
            + f"\nGenerate {n} ideas. Format EACH as:\n"
            "IDEA: <one-line idea>\nWHY: <one-line rationale>\nLEVERAGE: <1-10>\n---"
        )
        raw = llm_complete(
            ctx, system=system, prompt=prompt, max_tokens=n * 100, temperature=0.8
        )
        ideas: list[dict] = []
        for block in raw.split("---"):
            idea_m = re.search(r"IDEA:\s*(.+)", block)
            why_m = re.search(r"WHY:\s*(.+)", block)
            lev_m = re.search(r"LEVERAGE:\s*(\d+)", block)
            if idea_m:
                ideas.append(
                    {
                        "idea": idea_m.group(1).strip(),
                        "why": why_m.group(1).strip() if why_m else "",
                        "leverage": int(lev_m.group(1)) if lev_m else 5,
                    }
                )
        ideas.sort(key=lambda x: -x["leverage"])
        return {"ideas": ideas[:n]}
