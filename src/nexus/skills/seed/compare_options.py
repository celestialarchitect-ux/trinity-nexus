"""Evaluate 2-N options across dimensions, produce a recommendation."""

from nexus.skills.base import Skill, SkillContext, llm_json


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
            "You make sharp decisions. For each option, score every dimension 1-10. "
            "Pick one option. The pick must be defensible in one sentence."
        )
        schema = (
            'Output JSON: {"scores":[{"option":"...","per_dim":{"dim":score,...},"total":int}, ...],'
            '"pick":"the chosen option","why":"one-sentence rationale"}'
        )
        prompt = (
            "Options:\n" + "\n".join(f"- {o}" for o in options)
            + f"\n\nDimensions to score (1-10 each): {', '.join(dims)}\n"
            + (f"Context: {context}\n" if context else "")
            + "\nScore every option on every dimension, then pick one."
        )
        data = llm_json(
            ctx, system=system, prompt=prompt, schema_hint=schema,
            temperature=0.2, max_tokens=900,
            default={"scores": [], "pick": "", "why": ""},
        )

        # Build a human-readable table from the scored options.
        table_lines = ["| Option | " + " | ".join(dims) + " | Total |"]
        table_lines.append("| --- | " + " | ".join(["---"] * len(dims)) + " | --- |")
        for row in (data.get("scores") or []):
            if not isinstance(row, dict):
                continue
            name = str(row.get("option", ""))
            per = row.get("per_dim") or {}
            cells = [str(per.get(d, "-")) for d in dims]
            total = str(row.get("total", sum(
                int(per.get(d, 0)) for d in dims if isinstance(per.get(d), (int, float))
            )))
            table_lines.append(f"| {name} | " + " | ".join(cells) + f" | {total} |")

        return {
            "table": "\n".join(table_lines),
            "pick": str(data.get("pick", "")).strip(),
            "why": str(data.get("why", "")).strip(),
        }
