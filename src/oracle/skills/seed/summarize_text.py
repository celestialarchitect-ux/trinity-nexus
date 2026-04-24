"""Summarize a long piece of text into a terse briefing."""

from oracle.skills.base import Skill, SkillContext, llm_complete


class SummarizeText(Skill):
    id = "summarize_text"
    name = "Summarize Text"
    description = "Compress long text into a tight briefing with key points and actions."
    tags = ["writing", "summary", "compression", "briefing", "tldr"]
    inputs = {"text": "str", "max_words": "int (optional, default 150)"}
    outputs = {"summary": "str", "bullets": "list[str]"}
    model_preference = "primary"

    def execute(self, ctx: SkillContext, inputs: dict) -> dict:
        text = inputs["text"]
        max_words = int(inputs.get("max_words", 150))
        system = (
            "You compress text into terse briefings. Lead with the single most "
            "important fact. Then 3-7 bullet points of substance. No filler."
        )
        prompt = (
            f"Compress this into <= {max_words} words. Return format:\n\n"
            "LEAD: <one sentence>\n\nBULLETS:\n- <point>\n- <point>\n\n"
            f"TEXT:\n{text}"
        )
        raw = llm_complete(ctx, system=system, prompt=prompt, max_tokens=max_words * 3)
        bullets = [
            ln.lstrip("- ").strip()
            for ln in raw.splitlines()
            if ln.lstrip().startswith("-")
        ]
        return {"summary": raw.strip(), "bullets": bullets}
