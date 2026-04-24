"""Draft an email from a brief."""

from oracle.skills.base import Skill, SkillContext, llm_complete


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
        prompt = (
            f"Draft an email. Recipient: {to or '(not specified)'}. "
            f"Tone: {tone}. Length: {length}.\n\n"
            f"Brief: {brief}\n\n"
            "Return format exactly:\n"
            "SUBJECT: <line>\n\nBODY:\n<body>"
        )
        raw = llm_complete(ctx, system=system, prompt=prompt, max_tokens=600)
        subject, body = "", raw.strip()
        for line in raw.splitlines():
            if line.lower().startswith("subject:"):
                subject = line.split(":", 1)[1].strip()
                break
        if "BODY:" in raw:
            body = raw.split("BODY:", 1)[1].strip()
        return {"subject": subject, "body": body}
