"""Code-agent unit tests — no model calls. Verifies the parsing + exec layer."""

from __future__ import annotations


def test_extract_python_from_action_block():
    from nexus.code_agent import _extract_block, _extract_python

    assistant = """
<thinking>plan: compute 2+2</thinking>
<action>
```python
result = 2 + 2
print(result)
```
</action>
""".strip()

    action = _extract_block("action", assistant)
    assert action is not None
    code = _extract_python(action)
    assert "2 + 2" in code


def test_extract_final_block():
    from nexus.code_agent import _extract_block

    assistant = "<final>done — the answer is **42**.</final>"
    final = _extract_block("final", assistant)
    assert "42" in final


def test_run_code_captures_stdout_and_result():
    from nexus.code_agent import _run_code_with_timeout

    ns: dict = {"__builtins__": __builtins__}
    out = _run_code_with_timeout("print('hi'); result = 7 * 6", ns, timeout_sec=5.0)
    assert "hi" in out["stdout"]
    assert out["result"] == "42"
    assert out["error"] is None


def test_run_code_catches_exception():
    from nexus.code_agent import _run_code_with_timeout

    ns: dict = {"__builtins__": __builtins__}
    out = _run_code_with_timeout("raise ValueError('nope')", ns, timeout_sec=5.0)
    assert out["error"] is not None
    assert "ValueError" in out["error"]


def test_namespace_includes_tools():
    from nexus.code_agent import _build_namespace

    ns = _build_namespace()
    # a few canonical tools should be callable objects in the namespace
    for name in ("read_file", "glob_paths", "grep_files", "web_search", "remember"):
        assert name in ns, f"{name} missing from code-agent namespace"
        assert callable(ns[name])
