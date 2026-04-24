from nexus.skills.base import Skill, SkillContext, llm_complete


class TextShorten(Skill):
    id = "text_shorten"
    name = "Shorten Text"
    description = "Rewrites text to be shorter while preserving meaning"
    tags = ["text_shortening", "concise_writing"]
    inputs = {"text": "The text to shorten"}
    outputs = {"shortened_text": "The shortened text"}
    origin = "self_written"

    def execute(self, ctx: SkillContext, inputs: dict) -> dict:
        text = inputs.get("text", "")
        system = "You are a text shortening assistant. Rewrite the following text to be shorter while preserving its meaning. Do not add or remove information. Output only the shortened text."
        prompt = f"Rewrite the following text to be shorter while preserving meaning: {text}"
        result = llm_complete(ctx, system=system, prompt=prompt, max_tokens=200)
        return {"shortened_text": result}