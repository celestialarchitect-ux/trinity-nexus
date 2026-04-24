"""Skill engine — retrieval-indexed library of callable skills.

Research caps retrieval-quality skill count near ~2000 (RAG-MCP, arXiv 2505.03275).
We ship ~12-20 seeded skills and grow via DGM-style evolution, not 100K theater.
"""

from nexus.skills.base import Skill, SkillContext, SkillResult
from nexus.skills.registry import SkillRegistry
from nexus.skills.router import SkillRouter

__all__ = ["Skill", "SkillContext", "SkillResult", "SkillRegistry", "SkillRouter"]
