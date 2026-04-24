"""Store an important fact in Oracle's long-term memory."""

from oracle.skills.base import Skill, SkillContext


class StoreMemory(Skill):
    id = "store_memory"
    name = "Store Memory"
    description = "Store an important fact, decision, or lesson in Oracle's long-term memory (archival tier)."
    tags = ["memory", "remember", "store", "save", "archival"]
    inputs = {"fact": "str", "tags": "list[str] (optional)"}
    outputs = {"memory_id": "str"}
    model_preference = "fast"

    def execute(self, ctx: SkillContext, inputs: dict) -> dict:
        if ctx.memory is None:
            return {"memory_id": "", "_error": "no memory configured"}
        mid = ctx.memory.remember(
            inputs["fact"], tags=inputs.get("tags") or [], source="agent"
        )
        return {"memory_id": mid}
