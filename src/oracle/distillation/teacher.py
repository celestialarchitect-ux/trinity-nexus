"""Teacher: calls a frontier model on sampled interactions to generate gold answers.

Provider options (set ORACLE_TEACHER_PROVIDER):
  - `deepseek`   — DeepSeek V3/V4 API (~$0.14/1M tokens, best for distillation)
  - `anthropic`  — Claude as teacher (expensive but highest quality)
  - `local`      — use the local primary model as teacher (free, but same as student)

Teacher responses run through a judge call to confirm they are actually better
than the student's local_response. Pure "accumulate not replace" policy:
only gold pairs where the teacher decisively beats the student are kept.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from oracle.config import settings
from oracle.distillation.collector import Interaction


@dataclass
class GoldPair:
    prompt: str
    teacher_response: str
    student_response: str
    judge_verdict: str  # "teacher" | "student" | "tie"
    source_ts: float


def _should_teach(ix: Interaction) -> bool:
    """Research-backed inclusion criteria."""
    if ix.user_correction:
        return True  # explicit correction is gold
    if ix.local_confidence < 0.7:
        return True
    if ix.outcome == "failure":
        return True
    # ~30% coverage sample so local-teacher runs have material to work with.
    # Tune down once a frontier teacher (deepseek/anthropic) is wired.
    return (hash(f"{ix.thread_id}|{ix.ts}") & 0xFF) < 77


class Teacher:
    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
    ):
        self.provider = provider or settings.oracle_teacher_provider
        self.model = model or self._default_model()
        self._client = httpx.Client(timeout=120.0)

    def _default_model(self) -> str:
        return {
            "deepseek": "deepseek-chat",
            "anthropic": "claude-opus-4-7",
            "local": settings.oracle_primary_model,
        }.get(self.provider, "deepseek-chat")

    def _call_deepseek(self, system: str, prompt: str) -> str:
        key = settings.deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        if not key:
            raise RuntimeError("DEEPSEEK_API_KEY not set")
        r = self._client.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 2048,
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _call_anthropic(self, system: str, prompt: str) -> str:
        key = settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        r = self._client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2048,
            },
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"]

    def _call_local(self, system: str, prompt: str) -> str:
        import ollama

        client = ollama.Client(host=settings.oracle_ollama_host)
        kw: dict = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            options={
                "temperature": 0.3,
                "num_predict": 2048,
                "num_ctx": settings.oracle_num_ctx,
            },
        )
        try:
            r = client.chat(**kw, think=False)
        except TypeError:
            r = client.chat(**kw)
        return r["message"]["content"] or ""

    def call(self, system: str, prompt: str) -> str:
        fn = {
            "deepseek": self._call_deepseek,
            "anthropic": self._call_anthropic,
            "local": self._call_local,
        }[self.provider]
        return fn(system, prompt)

    def judge_better(
        self,
        *,
        prompt: str,
        candidate_a: str,
        candidate_b: str,
        user_correction: str | None,
    ) -> str:
        """Returns 'a', 'b', or 'tie'."""
        system = "You judge which response is better. Reply with exactly one letter: A, B, or T (tie)."
        jp = (
            f"Prompt:\n{prompt}\n\nA:\n{candidate_a}\n\nB:\n{candidate_b}\n\n"
            f"User feedback: {user_correction or '(none)'}\n\nWhich is better? A, B, or T:"
        )
        raw = self.call(system, jp).strip().upper()[:1]
        return {"A": "a", "B": "b"}.get(raw, "tie")

    TEACHER_SYSTEM = (
        "You are the TEACHER Oracle. Compared to the student, you must:\n"
        "- be strictly more correct (check facts, math, and edge cases)\n"
        "- be strictly tighter (no filler, no apologies, no CoT in the output)\n"
        "- prefer the exact format the user asked for; if none, use terse bullets\n"
        "- when the student rambled, show the clean, final answer only\n"
        "- when the student was wrong, lead with the correction\n"
        "Do NOT explain that you are a teacher. Output ONLY the improved answer."
    )

    def generate_gold(self, interactions: list[Interaction]) -> list[GoldPair]:
        """For each teach-worthy interaction, run teacher then judge."""
        out: list[GoldPair] = []
        for ix in interactions:
            if not _should_teach(ix):
                continue
            if not (ix.intent or "").strip():
                continue
            try:
                teacher_resp = self.call(system=self.TEACHER_SYSTEM, prompt=ix.intent)
                if not teacher_resp or teacher_resp.strip() == (ix.local_response or "").strip():
                    continue
                verdict = self.judge_better(
                    prompt=ix.intent,
                    candidate_a=ix.local_response,
                    candidate_b=teacher_resp,
                    user_correction=ix.user_correction,
                )
                if verdict == "b":  # teacher won
                    out.append(
                        GoldPair(
                            prompt=ix.intent,
                            teacher_response=teacher_resp,
                            student_response=ix.local_response,
                            judge_verdict=verdict,
                            source_ts=ix.ts,
                        )
                    )
            except Exception:
                continue
        return out

    def close(self) -> None:
        self._client.close()
