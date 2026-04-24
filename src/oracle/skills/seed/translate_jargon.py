"""Translate technical jargon into plain language."""

from oracle.skills.base import Skill, SkillContext, llm_complete


class TranslateJargon(Skill):
    id = "translate_jargon"
    name = "Translate Jargon"
    description = "Translate technical/specialist text into plain language a smart non-expert understands."
    tags = ["translation", "explain", "simplify", "jargon", "plain-english"]
    inputs = {"text": "str", "reader": "str (optional)"}
    outputs = {"plain": "str", "glossary": "list[dict]"}
    model_preference = "primary"

    def execute(self, ctx: SkillContext, inputs: dict) -> dict:
        text = inputs["text"]
        reader = inputs.get("reader", "a smart non-expert")
        system = (
            "You translate technical text into plain language. Keep meaning intact. "
            "Extract a short glossary of terms you chose to keep + their plain meaning."
        )
        prompt = (
            f"Target reader: {reader}\n\nOriginal:\n{text}\n\n"
            "Return:\nPLAIN:\n<plain-language version>\n\n"
            "GLOSSARY:\nTERM: <term> -- PLAIN: <meaning>\n..."
        )
        raw = llm_complete(
            ctx, system=system, prompt=prompt, max_tokens=len(text) + 500
        )
        plain = raw
        glossary: list[dict] = []
        if "PLAIN:" in raw:
            after = raw.split("PLAIN:", 1)[1]
            if "GLOSSARY:" in after:
                plain, gblock = after.split("GLOSSARY:", 1)
                for line in gblock.splitlines():
                    if line.startswith("TERM:"):
                        parts = line.split("--", 1)
                        if len(parts) == 2:
                            term = parts[0].replace("TERM:", "").strip()
                            meaning = parts[1].replace("PLAIN:", "").strip()
                            glossary.append({"term": term, "plain": meaning})
            else:
                plain = after
        return {"plain": plain.strip(), "glossary": glossary}
