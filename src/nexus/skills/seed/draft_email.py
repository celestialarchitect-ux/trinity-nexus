"""Draft an email from a brief."""

from nexus.skills.base import Skill, SkillContext, llm_json


class DraftEmail(Skill):
    id = "draft_email"
    name = "Draft Email"
    description = "Compose an email from a one-line brief. Output subject + body."
    tags = ["email", "writing", "outreach", "communication"]
    inputs = {
        "brief": "str",
        "to": "str (optional)",
        "tone": "str (warm|direct|formal|curt, default: direct)",
        "length": "str (short|medium|long, default: short)",
    }
    outputs = {"subject": "str", "body": "str"}
    model_preference = "primary"

    def execute(self, ctx: SkillContext, inputs: dict) -> dict:
        brief = inputs["brief"]
        to = inputs.get("to", "")
        tone = inputs.get("tone", "direct")
        length = inputs.get("length", "short")
        system = (
            "You draft emails for a busy founder. One clear ask per email. "
            "No filler, no 'I hope this finds you well'. Match the requested tone."
        )
        schema = (
            'Output JSON: {"subject":"email subject line","body":"email body text"}'
        )
        prompt = (
            f"Draft an email. Recipient: {to or '(not specified)'}. "
            f"Tone: {tone}. Length: {length}.\n\nBrief: {brief}"
        )
        data = llm_json(
            ctx, system=system, prompt=prompt, schema_hint=schema,
            temperature=0.4, max_tokens=700,
            default={"subject": "", "body": ""},
        )
        return {
            "subject": str(data.get("subject", "")).strip(),
            "body": str(data.get("body", "")).strip(),
        }
