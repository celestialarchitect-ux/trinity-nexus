"""Review a code snippet for bugs, security, style."""

from nexus.skills.base import Skill, SkillContext, llm_json


class CodeReview(Skill):
    id = "code_review"
    name = "Code Review"
    description = "Review code for correctness, bugs, security holes, and style. Return ordered issues."
    tags = ["code", "review", "audit", "security", "bug", "programming"]
    inputs = {"code": "str", "language": "str (optional)", "focus": "str (optional)"}
    outputs = {"issues": "list[dict]", "verdict": "str"}
    model_preference = "coder"

    def execute(self, ctx: SkillContext, inputs: dict) -> dict:
        code = inputs["code"]
        lang = inputs.get("language", "auto-detect")
        focus = inputs.get("focus", "")
        system = (
            "You are a senior engineer reviewing code. Lead with the worst "
            "issue. Cite line numbers when possible. Don't praise. Don't rewrite "
            "unless asked."
        )
        schema = (
            'Output JSON: {"verdict":"ship"|"ship-with-fixes"|"block",'
            '"issues":[{"severity":"low"|"med"|"high","summary":"what is wrong",'
            '"line":1,"fix":"one-line fix"}, ...]}\n'
            "Order issues from worst to least severe."
        )
        prompt = (
            f"Language: {lang}. "
            + (f"Focus: {focus}. " if focus else "")
            + "\n\nCode:\n```\n" + code + "\n```"
        )
        data = llm_json(
            ctx, system=system, prompt=prompt, schema_hint=schema,
            temperature=0.2, max_tokens=1400,
            default={"verdict": "", "issues": []},
        )
        issues: list[dict] = []
        for item in (data.get("issues") or []):
            if not isinstance(item, dict):
                continue
            summary = str(item.get("summary", "")).strip()
            if not summary:
                continue
            issues.append({
                "severity": str(item.get("severity", "med")).strip().lower() or "med",
                "summary": summary,
                "line": item.get("line", ""),
                "fix": str(item.get("fix", "")).strip(),
            })
        return {
            "issues": issues,
            "verdict": str(data.get("verdict", "")).strip(),
        }
