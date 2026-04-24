"""Multi-step reasoning on a research question (no external tools, LLM-only)."""

from nexus.skills.base import Skill, SkillContext, llm_complete


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
            "You answer hard questions. Think out loud. When you don't know, "
            "say so and list what you'd need to know to decide. Flag assumptions."
        )
        prompt = (
            f"Question: {q}\n"
            + (f"Context: {ctx_text}\n" if ctx_text else "")
            + "\nRespond in this exact format:\n"
            "REASONING: <3-6 bullets of thinking>\n\n"
            "ANSWER: <direct answer>\n\n"
            "CONFIDENCE: <low | medium | high>\n\n"
            "UNKNOWNS:\n- <thing you'd need>\n- <thing you'd need>"
        )
        raw = llm_complete(
            ctx, system=system, prompt=prompt, max_tokens=1000, temperature=0.3
        )
        answer, conf, unknowns = "", 0.5, []
        if "ANSWER:" in raw:
            after = raw.split("ANSWER:", 1)[1]
            answer = after.split("CONFIDENCE:")[0].strip()
        if "CONFIDENCE:" in raw:
            level = raw.split("CONFIDENCE:", 1)[1].split("\n", 1)[0].strip().lower()
            conf = {"low": 0.3, "medium": 0.6, "high": 0.9}.get(level, 0.5)
        if "UNKNOWNS:" in raw:
            ublock = raw.split("UNKNOWNS:", 1)[1]
            unknowns = [
                ln.lstrip("- ").strip()
                for ln in ublock.splitlines()
                if ln.lstrip().startswith("-")
            ]
        return {"answer": answer or raw, "confidence": conf, "unknowns": unknowns}
