"""Code-as-action agent (smolagents / TaskWeaver pattern).

Instead of JSON tool-calls, the model writes Python that calls the same
tools directly. Smaller models tend to plan further ahead when they can
compose loops + conditionals instead of emitting discrete tool calls.

MVP here is intentionally single-shot-with-retry: the model emits ONE
<action>...</action> block, we run it in a restricted namespace with a
timeout, feed stdout+result back, loop up to N iterations. No Docker
yet (that's the next hardening pass) — writes go through the same
§29 guards as every other tool call.

Use:  /mode code-agent   then ask normally
      or the CodeAgent class programmatically.
"""

from __future__ import annotations

import contextlib
import io
import re
import signal
import time
import traceback
from dataclasses import dataclass

from nexus.config import settings


CODE_SYSTEM = """\
You are Trinity Nexus operating in CODE-AGENT mode (§13 BUILDER + ORCHESTRATOR).

Instead of emitting JSON tool calls, you write Python that calls tools
directly. All the usual Nexus tools are pre-imported:

  read_file(path, start_line=1, end_line=0)    -> str
  write_file(path, content)                    -> str
  edit_file(path, old_string, new_string)      -> str
  apply_diff(path, search, replace)            -> str
  glob_paths(pattern, root=".")                -> list[str]
  grep_files(pattern, path=".", glob="*")      -> list[dict]
  run_command(command, timeout_sec=30)         -> dict
  web_fetch(url, max_chars=4000)               -> str
  web_search(query, max_results=8)             -> list[dict]
  remember(fact, tags="")                      -> str
  retrieve_notes(query, k=4)                   -> list[dict]
  retrieve_graph(entity, depth=2)              -> dict

Use Python control flow freely. Loops, conditionals, comprehensions.
Keep final answers in a variable called `result`.

Respond in this exact shape, EVERY turn:

  <thinking>
  one short paragraph of reasoning (optional — leave empty if trivial)
  </thinking>

  <action>
  ```python
  # your code here
  result = ...
  ```
  </action>

When the task is DONE and no further code is needed, replace <action>
with <final>your final answer as markdown</final>.

Never fabricate tool results. If you need information, call a tool to get it.
"""


@dataclass
class CodeAgentResult:
    final: str
    iterations: int
    actions: list[dict]  # [{code, stdout, result, error}, ...]


def _extract_block(tag: str, text: str) -> str | None:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL | re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip()


def _extract_python(code_block: str) -> str:
    m = re.search(r"```(?:python)?\s*([\s\S]+?)```", code_block)
    return (m.group(1) if m else code_block).strip()


def _build_namespace() -> dict:
    """Make all @tool-decorated callables available as plain functions."""
    from nexus import tools as _t

    # tools.py exports @tool-decorated objects; they expose .invoke()
    # but we want direct calls in user code, so wrap.
    def _wrap(tool_obj):
        def _call(*args, **kwargs):
            # If positional args given, map them to the underlying schema
            if args and not kwargs:
                schema = getattr(tool_obj, "args", None) or getattr(tool_obj, "args_schema", None)
                # Fall back to invoking with a dict of args by name order
                try:
                    names = list(tool_obj.args.keys())
                    kwargs = dict(zip(names, args))
                    return tool_obj.invoke(kwargs)
                except Exception:
                    pass
            return tool_obj.invoke(kwargs)
        _call.__name__ = getattr(tool_obj, "name", "tool")
        return _call

    ns: dict = {"__builtins__": __builtins__}
    for t in _t.BUILTIN_TOOLS:
        ns[getattr(t, "name", None) or t.__class__.__name__] = _wrap(t)
    return ns


def _run_code_with_timeout(code: str, namespace: dict, timeout_sec: float = 60.0) -> dict:
    """Exec code, capture stdout + result + any exception. Timeout via threading."""
    import threading

    out = {"stdout": "", "result": None, "error": None}
    buf = io.StringIO()

    def _target():
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                exec(compile(code, "<code-agent>", "exec"), namespace)
        except Exception:
            out["error"] = traceback.format_exc()[-4000:]

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)
    out["stdout"] = buf.getvalue()[-4000:]
    if t.is_alive():
        out["error"] = f"timeout after {timeout_sec}s (still running in background thread)"
    if "result" in namespace:
        try:
            out["result"] = repr(namespace["result"])[:2000]
        except Exception:
            out["result"] = "<unrepr-able>"
    return out


def run(task: str, *, max_iterations: int = 6, model: str | None = None) -> CodeAgentResult:
    """Run the code-agent loop. Returns CodeAgentResult with full trace."""
    import ollama as _ollama

    client = _ollama.Client(host=settings.oracle_ollama_host)
    namespace = _build_namespace()
    history: list[dict] = [
        {"role": "system", "content": CODE_SYSTEM},
        {"role": "user", "content": task},
    ]
    actions: list[dict] = []
    final = ""

    for i in range(max_iterations):
        kw: dict = dict(
            model=model or settings.oracle_primary_model,
            messages=history,
            options={
                "temperature": 0.2,
                "num_ctx": settings.oracle_num_ctx,
                "num_predict": 2000,
            },
        )
        try:
            r = client.chat(**kw, think=False)
        except TypeError:
            r = client.chat(**kw)
        from nexus._llm_util import strip_think
        assistant = strip_think(r["message"]["content"])
        history.append({"role": "assistant", "content": assistant})

        final_block = _extract_block("final", assistant)
        if final_block:
            final = final_block
            break

        action_block = _extract_block("action", assistant)
        if not action_block:
            # Last-ditch: treat the whole response as a final answer.
            final = assistant
            break

        code = _extract_python(action_block)
        outcome = _run_code_with_timeout(code, namespace)
        actions.append({"code": code, **outcome})

        feedback = (
            f"<result>\nstdout:\n{outcome['stdout'] or '(empty)'}\n\n"
            f"result: {outcome['result']}\n"
            f"error: {outcome['error']}\n</result>"
        )
        history.append({"role": "user", "content": feedback})

    return CodeAgentResult(final=final or "(no final answer produced)", iterations=len(actions), actions=actions)
