"""Rewrite text in plain, direct language."""

from oracle.skills.base import Skill, SkillContext, llm_complete


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
            "Rewrite for clarity. Rules: active voice. Short sentences. "
            "Kill jargon unless it is required. No hedging ('kind of', 'sort of'). "
            "Keep the original facts."
        )
        prompt = (
            f"Audience: {audience}\n\nOriginal:\n{text}\n\n"
            "Return:\nREWRITTEN:\n<text>\n\nCHANGES:\n- <change>\n- <change>"
        )
        raw = llm_complete(ctx, system=system, prompt=prompt, max_tokens=len(text) + 400)
        rewritten = raw
        changes: list[str] = []
        if "REWRITTEN:" in raw:
            rest = raw.split("REWRITTEN:", 1)[1]
            if "CHANGES:" in rest:
                rewritten, changes_block = rest.split("CHANGES:", 1)
                changes = [
                    ln.lstrip("- ").strip()
                    for ln in changes_block.splitlines()
                    if ln.lstrip().startswith("-")
                ]
            else:
                rewritten = rest
        return {"rewritten": rewritten.strip(), "changes": changes}
