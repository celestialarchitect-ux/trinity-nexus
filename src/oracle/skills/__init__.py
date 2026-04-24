"""Skill engine — retrieval-indexed library of callable skills.

Research caps retrieval-quality skill count near ~2000 (RAG-MCP, arXiv 2505.03275).
We ship ~12-20 seeded skills and grow via DGM-style evolution, not 100K theater.
"""

from oracle.skills.base import Skill, SkillContext, SkillResult
from oracle.skills.registry import SkillRegistry
from oracle.skills.router import SkillRouter

__all__ = ["Skill", "SkillContext", "SkillResult", "SkillRegistry", "SkillRouter"]
