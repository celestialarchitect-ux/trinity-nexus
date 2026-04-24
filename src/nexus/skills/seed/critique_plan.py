"""Find holes in a plan — adversarial review."""

from nexus.skills.base import Skill, SkillContext, llm_json


class CritiquePlan(Skill):
    id = "critique_plan"
    name = "Critique Plan"
    description = "Adversarially review a plan; find holes, risks, unpriced assumptions, order-of-effect mistakes."
    tags = ["critique", "review", "adversarial", "risk", "planning", "audit"]
    inputs = {"plan": "str", "focus": "str (optional)"}
    outputs = {"critique": "str", "risks": "list[str]"}
    model_preference = "reasoning"

    def execute(self, ctx: SkillContext, inputs: dict) -> dict:
        plan = inputs["plan"]
        focus = inputs.get("focus", "")
        system = (
            "You are an adversarial reviewer. Your only job is to find what's "
            "wrong. No cheerleading. Only specific risks, unpriced assumptions, "
            "physics violations, mis-sequenced dependencies. Be specific."
        )
        schema = (
            'Output JSON: {"critique":"one paragraph - the single biggest flaw",'
            '"risks":["specific risk 1","specific risk 2", ...]}'
        )
        prompt = (
            f"Plan:\n{plan}\n\n"
            + (f"Focus the critique on: {focus}\n\n" if focus else "")
            + "Attack this plan."
        )
        data = llm_json(
            ctx, system=system, prompt=prompt, schema_hint=schema,
            temperature=0.3, max_tokens=900,
            default={"critique": "", "risks": []},
        )
        risks = [str(r).strip() for r in (data.get("risks") or []) if str(r).strip()]
        return {
            "critique": str(data.get("critique", "")).strip(),
            "risks": risks,
        }
