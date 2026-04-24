"""Query Oracle's archival memory semantically."""

from oracle.skills.base import Skill, SkillContext


class RecallMemorySkill(Skill):
    id = "recall_memory"
    name = "Recall Memory"
    description = "Semantic search of Oracle's long-term archival memory for prior facts, decisions, lessons."
    tags = ["memory", "recall", "search", "archival", "long-term"]
    inputs = {"query": "str", "k": "int (default 5)"}
    outputs = {"hits": "list[dict]"}
    model_preference = "primary"

    def execute(self, ctx: SkillContext, inputs: dict) -> dict:
        if ctx.memory is None:
            return {"hits": [], "_error": "no memory configured"}
        k = int(inputs.get("k", 5))
        hits = ctx.memory.archival.query(inputs["query"], k=k)
        return {"hits": hits}
