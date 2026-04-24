"""Review a code snippet for bugs, security, style."""

from oracle.skills.base import Skill, SkillContext, llm_complete


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
            "You are a senior engineer reviewing code. Lead with the WORST issue. "
            "Cite line numbers. Don't praise. Don't rewrite unless asked."
        )
        prompt = (
            f"Language: {lang}. "
            + (f"Focus: {focus}. " if focus else "")
            + "\n\nCode:\n```\n"
            + code
            + "\n```\n\nReturn:\n"
            "VERDICT: <ship | ship-with-fixes | block> — <one-line why>\n\n"
            "ISSUES:\n"
            "1) [SEVERITY] <summary>\n   LINE: <n>\n   FIX: <one-line fix>\n"
            "2) ...\n"
        )
        raw = llm_complete(
            ctx, system=system, prompt=prompt, max_tokens=1200, temperature=0.2
        )
        verdict = ""
        if "VERDICT:" in raw:
            verdict = raw.split("VERDICT:", 1)[1].split("\n", 1)[0].strip()
        issues: list[dict] = []
        current: dict = {}
        for line in raw.splitlines():
            ls = line.strip()
            if ls and ls[0].isdigit() and ")" in ls:
                if current:
                    issues.append(current)
                current = {"summary": ls}
            elif ls.startswith("LINE:"):
                current["line"] = ls.split(":", 1)[1].strip()
            elif ls.startswith("FIX:"):
                current["fix"] = ls.split(":", 1)[1].strip()
        if current:
            issues.append(current)
        return {"issues": issues, "verdict": verdict}
