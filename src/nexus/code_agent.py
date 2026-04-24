"""Code-as-action agent (smolagents / TaskWeaver pattern). SCAFFOLD.

Status: not yet implemented. Documented for the next session build.

Plan:
  Instead of JSON tool-calls, the agent writes Python that imports and
  calls our tools directly. Runs the Python in a Docker sandbox
  (already have `sandbox.docker_sandbox.DockerSandbox`).

  Flow:
    1. System prompt: "you write Python, don't call tools via JSON"
       with the tool API stubs pre-imported.
    2. LLM emits a ```python block.
    3. Extract + run in Docker with timeout + memory cap.
    4. Capture stdout/stderr → feed back as a ToolMessage.
    5. Loop until no more code block OR max N iterations.

  Research: smolagents CodeAgent + TaskWeaver.

  Why defer: needs careful Docker wiring + streaming + partial-code
  handling. Rushing it produces an unsafe agent. Do it right.

Until implemented, /mode code-agent is accepted but just says so.
"""

from __future__ import annotations
