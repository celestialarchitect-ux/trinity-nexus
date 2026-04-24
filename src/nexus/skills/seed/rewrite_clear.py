"""Rewrite text in plain, direct language."""

from nexus.skills.base import Skill, SkillContext, llm_json


class RewriteClear(Skill):
    id = "rewrite_clear"
    name = "Rewrite Clear"
    description = "Rewrite text in plain, direct language; kill jargon, passive voice, hedging."
    tags = ["writing", "editing", "clarity", "simplify", "rewrite"]
    inputs = {"text": "str", "audience": "str (optional)"}
    outputs = {"rewritten": "str", "changes": "list[str]"}
    model_preference = "primary"

    def execute(self, ctx: SkillContext, inputs: dict) -> dict:
        text = inputs["text"]
        audience = inputs.get("audience", "a smart generalist")
        system = (
            "Rewrite for clarity. Rules: active voice. Short sentences. Kill "
            "jargon unless required. No hedging ('kind of', 'sort of'). Keep "
            "the original facts."
        )
        schema = (
            'Output JSON: {"rewritten":"the rewritten text",'
            '"changes":["what you changed and why", ...]}'
        )
        prompt = f"Audience: {audience}\n\nOriginal:\n{text}"
        data = llm_json(
            ctx, system=system, prompt=prompt, schema_hint=schema,
            temperature=0.3, max_tokens=len(text) + 500,
            default={"rewritten": "", "changes": []},
        )
        changes = [str(c).strip() for c in (data.get("changes") or []) if str(c).strip()]
        return {
            "rewritten": str(data.get("rewritten", "")).strip(),
            "changes": changes,
        }
