"""Generate N distinct ideas on a topic."""

from nexus.skills.base import Skill, SkillContext, llm_json


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
            "different from the others — not variants. Rate each 1-10 for leverage "
            "(higher = bigger payoff per unit effort)."
        )
        schema = (
            'Output JSON: {"ideas":[{"idea":"one-line idea","why":"one-line rationale",'
            '"leverage":1-10}, ...]}\n'
            "Exactly one key `ideas` at the top level. No prose."
        )
        prompt = (
            f"Topic: {topic}\n"
            + (f"Constraints: {constraints}\n" if constraints else "")
            + f"\nGenerate {n} ideas as described."
        )
        data = llm_json(
            ctx, system=system, prompt=prompt, schema_hint=schema,
            temperature=0.8, max_tokens=n * 120,
            default={"ideas": []},
        )
        ideas: list[dict] = []
        for item in (data.get("ideas") or []):
            if not isinstance(item, dict):
                continue
            idea = str(item.get("idea", "")).strip()
            if not idea:
                continue
            try:
                lev = int(item.get("leverage", 5))
            except (TypeError, ValueError):
                lev = 5
            ideas.append({
                "idea": idea,
                "why": str(item.get("why", "")).strip(),
                "leverage": max(1, min(10, lev)),
            })
        ideas.sort(key=lambda x: -x["leverage"])
        return {"ideas": ideas[:n]}
