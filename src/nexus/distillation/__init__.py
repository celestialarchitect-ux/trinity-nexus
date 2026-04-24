"""Nightly distillation pipeline — the moat.

    collect → teach → train (QLoRA) → validate → deploy

Research grounding:
  - "Accumulate not replace" (arXiv 2404.01413): never train on pure synthetic.
  - SLAO (arXiv 2512.23017): orthogonal init + time-aware merging for forgetting.
  - Verification gate (arXiv 2510.16657): always judge-filter synthetic gold.
"""

from nexus.distillation.collector import InteractionCollector
from nexus.distillation.eval import EvalCase, EvalReport, run_full_eval
from nexus.distillation.orchestrator import DistillationOrchestrator
from nexus.distillation.teacher import Teacher
from nexus.distillation.validator import AdapterValidator

__all__ = [
    "InteractionCollector",
    "Teacher",
    "AdapterValidator",
    "DistillationOrchestrator",
    "EvalCase",
    "EvalReport",
    "run_full_eval",
]
