"""Find holes in a plan — adversarial review."""

from oracle.skills.base import Skill, SkillContext, llm_complete


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
            "You are an adversarial reviewer. Your only job is to find what's wrong. "
            "No cheerleading. No 'overall strong plan'. Only: specific risks, "
            "unpriced assumptions, physics violations, mis-sequenced dependencies. "
            "Be specific. Cite the line of the plan you're attacking."
        )
        prompt = (
            f"Plan:\n{plan}\n\n"
            + (f"Focus the critique on: {focus}\n\n" if focus else "")
            + "Return:\n"
            "CRITIQUE: <one paragraph — the single most important flaw>\n\n"
            "RISKS:\n- <risk 1>\n- <risk 2>\n- ..."
        )
        raw = llm_complete(
            ctx, system=system, prompt=prompt, max_tokens=900, temperature=0.3
        )
        critique = ""
        risks: list[str] = []
        if "CRITIQUE:" in raw:
            critique = raw.split("CRITIQUE:", 1)[1].split("RISKS:")[0].strip()
        if "RISKS:" in raw:
            risks_block = raw.split("RISKS:", 1)[1]
            risks = [
                ln.lstrip("- ").strip()
                for ln in risks_block.splitlines()
                if ln.lstrip().startswith("-")
            ]
        return {"critique": critique or raw, "risks": risks}
