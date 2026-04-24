"""Extract structured entities (people, orgs, dates, amounts) from unstructured text."""

import json
import re

from nexus.skills.base import Skill, SkillContext, llm_complete


class ExtractEntities(Skill):
    id = "extract_entities"
    name = "Extract Entities"
    description = "Pull structured entities from free-form text: people, orgs, places, dates, amounts, URLs."
    tags = ["extraction", "ner", "parsing", "data", "structured"]
    inputs = {"text": "str", "types": "list[str] (optional)"}
    outputs = {"entities": "dict[str, list[str]]"}
    model_preference = "primary"

    def execute(self, ctx: SkillContext, inputs: dict) -> dict:
        text = inputs["text"]
        types = inputs.get("types") or [
            "people",
            "organizations",
            "locations",
            "dates",
            "amounts",
            "urls",
            "emails",
        ]
        system = (
            "You extract structured entities. Return VALID JSON only, no prose. "
            "If an entity type has no matches, return empty list."
        )
        schema_hint = {t: [] for t in types}
        prompt = (
            f"Extract entities from the text. Return JSON matching this schema exactly:\n"
            f"{json.dumps(schema_hint)}\n\n"
            f"TEXT:\n{text}"
        )
        raw = llm_complete(
            ctx, system=system, prompt=prompt, temperature=0.1, max_tokens=600
        )
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return {"entities": schema_hint, "_raw": raw}
        try:
            return {"entities": json.loads(match.group(0))}
        except Exception:
            return {"entities": schema_hint, "_raw": raw}
