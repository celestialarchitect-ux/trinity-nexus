"""Skill base class. Every skill is a subclass of Skill implementing `execute`."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillContext:
    """What a skill receives at call time. Kept small + orthogonal."""

    llm: Any  # ollama.Client or compatible
    model: str
    memory: Any | None = None  # MemoryTiers
    user: str = "zach"
    thread_id: str = "default"
    dry_run: bool = False


@dataclass
class SkillResult:
    ok: bool
    output: dict[str, Any]
    skill_id: str
    elapsed_ms: float = 0.0
    error: str | None = None


class Skill(ABC):
    """A single callable capability."""

    # Identity
    id: str = ""
    name: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)

    # Schema (informal — used for prompt-time documentation)
    inputs: dict[str, str] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)

    # Model hint (override per skill)
    model_preference: str = "primary"  # primary | fast | coder | reasoning

    # Runtime stats (persisted by SkillRegistry)
    confidence: float = 0.5
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    last_used_ts: float = 0.0
    origin: str = "seed"  # seed | self_written | mesh

    @abstractmethod
    def execute(
        self, ctx: SkillContext, inputs: dict[str, Any]
    ) -> dict[str, Any]:  # pragma: no cover
        """Do the work. Must return a dict matching `outputs` schema."""

    def run(self, ctx: SkillContext, inputs: dict[str, Any]) -> SkillResult:
        """Wrapper that tracks timing + stats."""
        t0 = time.perf_counter()
        self.usage_count += 1
        self.last_used_ts = time.time()
        try:
            out = self.execute(ctx, inputs)
            self.success_count += 1
            self._bump_confidence(True)
            return SkillResult(
                ok=True,
                output=out,
                skill_id=self.id,
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception as e:
            self.failure_count += 1
            self._bump_confidence(False)
            return SkillResult(
                ok=False,
                output={},
                skill_id=self.id,
                elapsed_ms=(time.perf_counter() - t0) * 1000,
                error=f"{type(e).__name__}: {e}",
            )

    def _bump_confidence(self, success: bool) -> None:
        target = 1.0 if success else 0.0
        self.confidence = max(0.0, min(1.0, 0.9 * self.confidence + 0.1 * target))

    def describe(self) -> str:
        """Short, embedding-friendly description of this skill."""
        tag_s = ", ".join(self.tags) if self.tags else ""
        return f"{self.name}: {self.description}. Tags: {tag_s}."

    def to_stats(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "confidence": round(self.confidence, 3),
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "last_used_ts": self.last_used_ts,
            "origin": self.origin,
        }


def llm_complete(
    ctx: SkillContext,
    *,
    system: str,
    prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    think: bool = False,
    format: str | dict | None = None,
) -> str:
    """Common helper: call the LLM via Ollama and return text.

    `think=False` disables chain-of-thought on thinking-capable models (qwen3
    etc.), which keeps output tight and guarantees the requested schema fits
    inside `max_tokens`.

    `format="json"` constrains output to valid JSON via Ollama's grammar mode.
    Use when the skill needs structured output from a small quantized model.
    """
    import ollama

    client = ctx.llm if ctx.llm else ollama.Client()
    kwargs: dict = dict(
        model=ctx.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        options={"temperature": temperature, "num_predict": max_tokens},
    )
    if format is not None:
        kwargs["format"] = format
    # Ollama 0.4+ accepts think=False to suppress reasoning. Older servers ignore.
    try:
        r = client.chat(**kwargs, think=think)
    except TypeError:
        r = client.chat(**kwargs)
    content = r["message"]["content"] or ""
    # qwen3 sometimes emits <think>...</think> even with think=False. Strip it
    # so downstream parsers see only the final answer.
    if "<think>" in content:
        import re
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
        # Unclosed <think> at start (streaming truncation): drop everything up
        # to the last </think>, or strip the whole opener if none closes.
        if "<think>" in content:
            if "</think>" in content:
                content = content.split("</think>", 1)[1]
            else:
                content = content.split("<think>", 1)[0]
    return content.strip()
