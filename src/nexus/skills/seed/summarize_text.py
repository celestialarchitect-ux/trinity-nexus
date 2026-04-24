"""Summarize a long piece of text into a terse briefing."""

from nexus.skills.base import Skill, SkillContext, llm_complete


class SummarizeText(Skill):
    id = "summarize_text"
    name = "Summarize Text"
    description = "Compress long text into a tight briefing with key points and actions."
    tags = ["writing", "summary", "compression", "briefing", "tldr"]
    inputs = {"text": "str", "max_words": "int (optional, default 150)"}
    outputs = {"summary": "str", "bullets": "list[str]"}
    model_preference = "primary"

    def execute(self, ctx: SkillContext, inputs: dict) -> dict:
        import json
        import re

        text = inputs["text"]
        max_words = int(inputs.get("max_words", 150))
        system = (
            "You compress text into terse briefings. Output ONLY a valid JSON "
            "object matching the schema described. Never echo the schema, never "
            "include keys other than the two specified, never add commentary."
        )
        prompt = (
            f"Summarize the text below in <= {max_words} words, then output a "
            "JSON object with these two keys:\n"
            '  "summary": a single declarative sentence — the most important fact.\n'
            '  "bullets": an array of 3-7 short strings, each a concrete point.\n\n'
            "Output ONLY the JSON object. No markdown fences, no prose.\n\n"
            "TEXT:\n" + text
        )
        raw = llm_complete(
            ctx, system=system, prompt=prompt, max_tokens=max_words * 3,
            temperature=0.2, format="json",
        )

        # Strip markdown code fences if the model added any.
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)

        # Extract the first {...} block (qwen3 sometimes adds a preface line).
        def _is_meta(s: str) -> bool:
            """True if `s` looks like qwen3 meta-reasoning instead of a real summary."""
            low = s.strip().lower()
            if not low:
                return True
            for stem in (
                "we are given", "we are asked", "the user wants", "the user is asking",
                "let me", "first, i", "i need to", "i should", "i'll", "i will",
                "the task is", "here is a summary", "here is the summary",
                "to summarize", "summary of the text",
            ):
                if low.startswith(stem):
                    return True
            # Summary that just echoes the instruction ("one sentence that captures...")
            if "one sentence" in low and "captures" in low:
                return True
            return False

        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                data = json.loads(m.group(0))
                summary = str(data.get("summary", "")).strip()
                bullets = [str(b).strip() for b in data.get("bullets", []) if str(b).strip()]
                if _is_meta(summary):
                    summary = bullets[0] if bullets else ""
                if summary or bullets:
                    return {"summary": summary, "bullets": bullets}
            except Exception:
                pass

        # Fallback: best-effort line parsing.
        bullets = [
            ln.lstrip("-* ").strip()
            for ln in raw.splitlines()
            if ln.lstrip().startswith(("-", "*"))
        ]
        return {"summary": raw.strip()[:400], "bullets": bullets}
