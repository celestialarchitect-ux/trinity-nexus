"""Translate technical jargon into plain language."""

from nexus.skills.base import Skill, SkillContext, llm_json


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
            "You translate technical text into plain language. Keep meaning "
            "intact. Extract a short glossary of essential terms with plain "
            "meanings."
        )
        schema = (
            'Output JSON: {"plain":"the plain-language rewrite",'
            '"glossary":[{"term":"original jargon","plain":"plain meaning"}, ...]}'
        )
        prompt = f"Target reader: {reader}\n\nOriginal:\n{text}"
        data = llm_json(
            ctx, system=system, prompt=prompt, schema_hint=schema,
            temperature=0.2, max_tokens=len(text) + 600,
            default={"plain": "", "glossary": []},
        )
        glossary: list[dict] = []
        for item in (data.get("glossary") or []):
            if isinstance(item, dict):
                term = str(item.get("term", "")).strip()
                meaning = str(item.get("plain", "")).strip()
                if term and meaning:
                    glossary.append({"term": term, "plain": meaning})
        return {
            "plain": str(data.get("plain", "")).strip(),
            "glossary": glossary,
        }
