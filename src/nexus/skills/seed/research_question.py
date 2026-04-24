"""Multi-step reasoning on a research question (no external tools, LLM-only)."""

from nexus.skills.base import Skill, SkillContext, llm_json


class ResearchQuestion(Skill):
    id = "research_question"
    name = "Research Question"
    description = "Think through a hard question with explicit reasoning steps; flag what you don't know."
    tags = ["research", "reasoning", "analysis", "thinking"]
    inputs = {"question": "str", "context": "str (optional)"}
    outputs = {"answer": "str", "confidence": "float", "unknowns": "list[str]"}
    model_preference = "reasoning"

    def execute(self, ctx: SkillContext, inputs: dict) -> dict:
        q = inputs["question"]
        ctx_text = inputs.get("context", "")
        system = (
            "You answer hard questions rigorously. When you don't know, say so "
            "and list what you'd need to know. Never bluff. Flag assumptions."
        )
        schema = (
            'Output JSON: {"answer":"direct answer (1-3 sentences)",'
            '"confidence":"low"|"medium"|"high","unknowns":["thing 1","thing 2"]}'
        )
        prompt = (
            f"Question: {q}\n"
            + (f"Context: {ctx_text}\n" if ctx_text else "")
            + "\nProduce the JSON answer."
        )
        data = llm_json(
            ctx, system=system, prompt=prompt, schema_hint=schema,
            temperature=0.3, max_tokens=1000,
            default={"answer": "", "confidence": "medium", "unknowns": []},
        )
        conf_raw = str(data.get("confidence", "medium")).strip().lower()
        conf = {"low": 0.3, "medium": 0.6, "high": 0.9}.get(conf_raw, 0.5)
        unknowns = [str(u).strip() for u in (data.get("unknowns") or []) if str(u).strip()]
        return {
            "answer": str(data.get("answer", "")).strip(),
            "confidence": conf,
            "unknowns": unknowns,
        }
