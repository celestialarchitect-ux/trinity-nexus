"""Evolve unit tests — syntactic gate + extractor. No LLM/Ollama needed."""

from __future__ import annotations

from nexus.skills.evolve import _extract_code, _guess_inputs, _syntactic_check


def test_extract_code_from_python_block():
    raw = "Here is the skill:\n\n```python\nclass X(Skill):\n    pass\n```\nDone."
    code = _extract_code(raw)
    assert code and "class X(Skill):" in code


def test_extract_code_from_generic_block():
    raw = "```\nclass X(Skill): pass\n```"
    code = _extract_code(raw)
    assert code and "class X" in code


def test_syntactic_check_ok():
    code = '''
from nexus.skills.base import Skill, SkillContext

class Ok(Skill):
    id = "ok"
    name = "Ok"
    description = "ok"
    tags = []
    inputs = {"x": "str"}
    outputs = {"y": "str"}
    origin = "self_written"

    def execute(self, ctx: SkillContext, inputs: dict) -> dict:
        return {"y": inputs.get("x", "")}
'''
    assert _syntactic_check(code) == []


def test_syntactic_check_blocks_os_and_subprocess():
    code = '''
import os
import subprocess
class Bad:
    def execute(self): return {}
'''
    reasons = _syntactic_check(code)
    assert any("forbidden import" in r for r in reasons)


def test_syntactic_check_blocks_exec_call():
    code = '''
class Bad:
    def execute(self):
        exec("1")
        return {}
'''
    reasons = _syntactic_check(code)
    assert any("exec" in r for r in reasons)


def test_guess_inputs_matches_declared_keys():
    code = '''
class X:
    inputs = {"text": "str", "k": "int"}
'''
    g = _guess_inputs(code, intent="summarize this paragraph")
    assert "text" in g and "k" in g
    assert g["k"] == 3
