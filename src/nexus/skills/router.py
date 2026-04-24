"""SkillRouter — embedding-indexed + confidence-weighted skill selection.

Two-stage router (per RAG-MCP research):
    1. Embed user intent, cosine-sim top-K candidates from skill library
    2. Score = similarity * (0.5 + 0.5 * confidence)   [recency+quality weight]
    3. Return top-N for the agent to choose from

We deliberately don't use the LLM for routing — that's handled by the agent's
tool-calling loop. The router just narrows the candidate set.
"""

from __future__ import annotations

import logging

import numpy as np

from nexus.memory.embeddings import Embedder, get_embedder
from nexus.skills.base import Skill
from nexus.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


class SkillRouter:
    def __init__(
        self,
        registry: SkillRegistry,
        embedder: Embedder | None = None,
    ):
        self.registry = registry
        self.embedder = embedder or get_embedder()
        self._skill_ids: list[str] = []
        self._matrix: np.ndarray | None = None

    def build_index(self) -> None:
        skills = list(self.registry.all())
        if not skills:
            self._matrix = None
            self._skill_ids = []
            return
        descs = [s.describe() for s in skills]
        self._matrix = self.embedder.embed_batch(descs)
        self._skill_ids = [s.id for s in skills]

    def route(
        self,
        intent: str,
        *,
        top_k: int = 3,
        min_similarity: float = 0.35,
    ) -> list[tuple[Skill, float]]:
        if self._matrix is None:
            self.build_index()
        if self._matrix is None or not self._skill_ids:
            return []
        q = self.embedder.embed(intent)
        # cosine similarity
        mat_norms = np.linalg.norm(self._matrix, axis=1) + 1e-9
        q_norm = np.linalg.norm(q) + 1e-9
        sims = (self._matrix @ q) / (mat_norms * q_norm)

        confidences = np.array(
            [self.registry.skills[sid].confidence for sid in self._skill_ids]
        )
        scores = sims * (0.5 + 0.5 * confidences)

        order = np.argsort(-scores)
        out: list[tuple[Skill, float]] = []
        for idx in order:
            if sims[idx] < min_similarity:
                break
            out.append((self.registry.skills[self._skill_ids[idx]], float(scores[idx])))
            if len(out) >= top_k:
                break
        return out
