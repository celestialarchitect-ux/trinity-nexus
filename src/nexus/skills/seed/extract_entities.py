"""Extract structured entities (people, orgs, dates, amounts) from unstructured text."""

import json

from nexus.skills.base import Skill, SkillContext, llm_json


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
            "people", "organizations", "locations", "dates",
            "amounts", "urls", "emails",
        ]
        default_shape = {t: [] for t in types}
        system = (
            "You extract structured entities. If a type has no matches, return "
            "an empty list for it."
        )
        schema = (
            "Output JSON with exactly these keys, each mapping to a list of strings:\n"
            + json.dumps(default_shape)
        )
        prompt = f"TEXT:\n{text}"
        data = llm_json(
            ctx, system=system, prompt=prompt, schema_hint=schema,
            temperature=0.1, max_tokens=700,
            default=default_shape,
        )
        entities: dict[str, list[str]] = {}
        for t in types:
            vals = data.get(t, [])
            if isinstance(vals, list):
                entities[t] = [str(v).strip() for v in vals if str(v).strip()]
            else:
                entities[t] = []
        return {"entities": entities}
