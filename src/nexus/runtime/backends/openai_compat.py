"""OpenAI-compatible backend — one shape, many providers.

Works with any endpoint that speaks the OpenAI Chat Completions protocol:
  - OpenAI itself (api.openai.com)
  - OpenRouter (openrouter.ai/api/v1) — Claude, GPT, Gemini, Grok, DeepSeek, Llama, Qwen, Mistral — all through one key
  - DeepSeek (api.deepseek.com)
  - Anthropic via OpenAI-compat (api.anthropic.com/v1)
  - Groq (api.groq.com/openai/v1)
  - Together (api.together.xyz/v1)
  - Fireworks (api.fireworks.ai/inference/v1)
  - Any local server that exposes OpenAI-compat (vLLM, TGI, Ollama's /v1)

Config via env, per-call override allowed:

    NEXUS_FRONTIER_BASE_URL   e.g. https://openrouter.ai/api/v1
    NEXUS_FRONTIER_API_KEY    the provider's key
    NEXUS_FRONTIER_MODEL      default model id e.g. anthropic/claude-opus-4-7

Or override any of these per ChatRequest.extra for mid-session routing.
"""

from __future__ import annotations

import json
import os

import httpx

from nexus.runtime.backends.base import Backend
from nexus.runtime.types import ChatRequest, ChatResponse, StreamEvent, StreamIter


PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "anthropic/claude-opus-4-7",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-5",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "default_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    },
    "fireworks": {
        "base_url": "https://api.fireworks.ai/inference/v1",
        "default_model": "accounts/fireworks/models/llama-v3p3-70b-instruct",
    },
    "xai": {
        "base_url": "https://api.x.ai/v1",
        "default_model": "grok-4",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "default_model": "mistral-large-latest",
    },
}


def _preset(name: str | None) -> dict[str, str]:
    if not name:
        return {}
    return PROVIDER_PRESETS.get(name.lower(), {})


class OpenAICompatBackend(Backend):
    name = "openai_compat"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        provider: str | None = None,
        default_model: str | None = None,
        timeout: float = 300.0,
    ):
        p = _preset(provider or os.environ.get("NEXUS_FRONTIER_PROVIDER"))
        self.base_url = (
            base_url
            or os.environ.get("NEXUS_FRONTIER_BASE_URL")
            or p.get("base_url")
            or "https://openrouter.ai/api/v1"
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("NEXUS_FRONTIER_API_KEY", "")
        self.default_model = (
            default_model
            or os.environ.get("NEXUS_FRONTIER_MODEL")
            or p.get("default_model")
            or "anthropic/claude-opus-4-7"
        )
        self._client = httpx.Client(timeout=timeout)

    def is_available(self) -> bool:
        return bool(self.api_key)

    # ---- request shaping ----

    def _headers(self) -> dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        # OpenRouter best-practice headers (optional, improves routing/analytics)
        if "openrouter" in self.base_url:
            h["HTTP-Referer"] = os.environ.get(
                "NEXUS_OPENROUTER_REFERER", "https://github.com/celestialarchitect-ux/trinity-nexus"
            )
            h["X-Title"] = os.environ.get("NEXUS_OPENROUTER_TITLE", "Trinity Nexus")
        return h

    def _tools(self, req: ChatRequest) -> list[dict] | None:
        if not req.tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in req.tools
        ]

    def _messages(self, req: ChatRequest) -> list[dict]:
        out: list[dict] = []
        for m in req.messages:
            row: dict = {"role": m.role, "content": m.content}
            if m.tool_calls:
                row["tool_calls"] = m.tool_calls
            if m.tool_call_id:
                row["tool_call_id"] = m.tool_call_id
            if m.name:
                row["name"] = m.name
            out.append(row)
        return out

    def _body(self, req: ChatRequest, *, stream: bool) -> dict:
        body: dict = {
            "model": req.extra.get("model_override") or req.model or self.default_model,
            "messages": self._messages(req),
            "temperature": req.temperature,
            "stream": stream,
        }
        if req.max_tokens is not None:
            body["max_tokens"] = req.max_tokens
        if req.tools:
            body["tools"] = self._tools(req)
        if req.stop:
            body["stop"] = req.stop
        # Pass through provider-specific knobs (e.g. anthropic-beta, extra_body)
        if "extra_body" in req.extra:
            body.update(req.extra["extra_body"])
        return body

    # ---- calls ----

    def chat(self, req: ChatRequest) -> ChatResponse:
        if not self.api_key:
            raise RuntimeError(
                "NEXUS_FRONTIER_API_KEY not set — add it to .env or export it."
            )
        r = self._client.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=self._body(req, stream=False),
        )
        if r.status_code >= 400:
            raise RuntimeError(f"{self.base_url} HTTP {r.status_code}: {r.text[:500]}")
        data = r.json()
        choice = data["choices"][0]["message"]
        usage = data.get("usage") or {}
        resp = ChatResponse(
            content=choice.get("content") or "",
            tool_calls=choice.get("tool_calls") or [],
            finish_reason=data["choices"][0].get("finish_reason", "stop"),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
        )
        # Log to cost ledger (non-fatal on failure)
        try:
            from nexus import cost as _cost
            _cost.record(
                backend=self.name,
                model=req.extra.get("model_override") or req.model or self.default_model,
                prompt_tokens=resp.prompt_tokens,
                completion_tokens=resp.completion_tokens,
                thread_id=req.extra.get("thread_id", ""),
                purpose=req.extra.get("purpose", "chat"),
            )
        except Exception:
            pass
        return resp

    def stream(self, req: ChatRequest) -> StreamIter:
        if not self.api_key:
            raise RuntimeError("NEXUS_FRONTIER_API_KEY not set")

        accumulated_tc: dict[int, dict] = {}
        prompt_tokens = 0
        completion_tokens = 0

        with self._client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=self._body(req, stream=True),
        ) as r:
            if r.status_code >= 400:
                raise RuntimeError(
                    f"{self.base_url} HTTP {r.status_code}: {r.read().decode()[:500]}"
                )
            for line in r.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    continue
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choice = (obj.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                text = delta.get("content")
                if text:
                    yield StreamEvent(type="token", text=text)
                for tc_d in delta.get("tool_calls") or []:
                    idx = tc_d.get("index", 0)
                    acc = accumulated_tc.setdefault(
                        idx, {"id": "", "name": "", "arguments": ""}
                    )
                    if tc_d.get("id"):
                        acc["id"] = tc_d["id"]
                    fn = tc_d.get("function") or {}
                    if fn.get("name"):
                        acc["name"] = fn["name"]
                    if fn.get("arguments"):
                        acc["arguments"] += fn["arguments"]
                usage = obj.get("usage")
                if usage:
                    prompt_tokens = usage.get("prompt_tokens", prompt_tokens)
                    completion_tokens = usage.get("completion_tokens", completion_tokens)
                if choice.get("finish_reason"):
                    for acc in accumulated_tc.values():
                        try:
                            args = json.loads(acc["arguments"] or "{}")
                        except Exception:
                            args = {}
                        yield StreamEvent(
                            type="tool_call",
                            tool_call={
                                "id": acc["id"],
                                "name": acc["name"],
                                "args": args,
                            },
                        )
                    accumulated_tc.clear()

        yield StreamEvent(
            type="done",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def embed(self, text: str, model: str) -> list[float]:
        r = self._client.post(
            f"{self.base_url}/embeddings",
            headers=self._headers(),
            json={"input": text, "model": model},
        )
        r.raise_for_status()
        return list(r.json()["data"][0]["embedding"])
