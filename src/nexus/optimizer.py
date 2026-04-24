"""DSPy-style prompt optimizer. SCAFFOLD.

Status: not yet implemented. Documented for the next session build.

Plan:
  Use DSPy's MIPROv2 (or BootstrapFewShot as a simpler start) to optimize
  the system prompt / constitution WORDING against our existing 3-gate
  eval harness (`distillation.eval.run_full_eval`).

  Flow:
    1. Pin the constitution sections that are identity-critical (§01, §33).
    2. Let DSPy mutate the "flexible" sections (§14 style, §16 prompt
       engineering guidance).
    3. For each candidate prompt: run eval.run_full_eval against the
       default regression + diversity sets.
    4. Keep the top N, next generation from their mutations.
    5. After N epochs, diff against current constitution and propose.

  Research: stanfordnlp/dspy, especially the Signature / Module pattern.

  Why defer: needs DSPy installed + careful integration with our judge
  model. This is its own 1-day build.

Until implemented, `nexus optimize-prompt` prints this plan.
"""

from __future__ import annotations
