"""Ollama backend — wraps the existing ollama.Client usage.

This is the safe default. Keeps the current behavior so nothing breaks for
users with an Ollama daemon. For parallelism, prompt caching, and better
tool-call handling, switch to the llama_cpp backend.
"""

from __future__ import annotations

import httpx

from nexus.config import settings
from nexus.runtime.backends.base import Backend
from nexus.runtime.types import ChatRequest, ChatResponse, StreamEvent, StreamIter


def _tools_to_ollama(tools) -> list[dict]:
    out: list[dict] = []
    for t in tools:
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
        )
    return out


def _messages_to_ollama(messages) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        row: dict = {"role": m.role, "content": m.content}
        if m.tool_calls:
            row["tool_calls"] = m.tool_calls
        if m.tool_call_id:
            row["tool_call_id"] = m.tool_call_id
        if m.name:
            row["name"] = m.name
        out.append(row)
    return out


class OllamaBackend(Backend):
    name = "ollama"

    def __init__(self, host: str | None = None):
        import ollama

        self.host = host or settings.oracle_ollama_host
        self._client = ollama.Client(host=self.host, timeout=settings.oracle_llm_timeout_sec)

    def is_available(self) -> bool:
        try:
            httpx.get(f"{self.host}/api/tags", timeout=2).raise_for_status()
            return True
        except Exception:
            return False

    def _call(self, req: ChatRequest, *, stream: bool):
        kw: dict = dict(
            model=req.model,
            messages=_messages_to_ollama(req.messages),
            options={
                "temperature": req.temperature,
                "num_ctx": req.num_ctx,
            },
            stream=stream,
        )
        if req.max_tokens is not None:
            kw["options"]["num_predict"] = req.max_tokens
        if req.tools:
            kw["tools"] = _tools_to_ollama(req.tools)
        if req.stop:
            kw["options"]["stop"] = req.stop
        # qwen3 think=False support
        if "think" in req.extra:
            try:
                return self._client.chat(**kw, think=req.extra["think"])
            except TypeError:
                pass
        return self._client.chat(**kw)

    def chat(self, req: ChatRequest) -> ChatResponse:
        r = self._call(req, stream=False)
        msg = r.get("message", {}) if isinstance(r, dict) else r["message"]
        return ChatResponse(
            content=msg.get("content", "") or "",
            tool_calls=msg.get("tool_calls") or [],
            finish_reason=r.get("done_reason", "stop") if isinstance(r, dict) else "stop",
            prompt_tokens=int(r.get("prompt_eval_count") or 0) if isinstance(r, dict) else 0,
            completion_tokens=int(r.get("eval_count") or 0) if isinstance(r, dict) else 0,
        )

    def stream(self, req: ChatRequest) -> StreamIter:
        last_p = 0
        last_c = 0
        for chunk in self._call(req, stream=True):
            msg = chunk.get("message", {}) if isinstance(chunk, dict) else {}
            text = msg.get("content", "") or ""
            if text:
                yield StreamEvent(type="token", text=text)
            for tc in msg.get("tool_calls") or []:
                yield StreamEvent(type="tool_call", tool_call=tc)
            if chunk.get("done"):
                last_p = int(chunk.get("prompt_eval_count") or 0)
                last_c = int(chunk.get("eval_count") or 0)
        yield StreamEvent(type="done", prompt_tokens=last_p, completion_tokens=last_c)

    def embed(self, text: str, model: str) -> list[float]:
        r = httpx.post(
            f"{self.host}/api/embeddings",
            json={
                "model": model,
                "prompt": text,
                "keep_alive": settings.oracle_embed_keepalive,
            },
            timeout=settings.oracle_llm_timeout_sec,
        )
        r.raise_for_status()
        return list(r.json()["embedding"])

    def unload(self, model: str) -> None:
        try:
            httpx.post(
                f"{self.host}/api/generate",
                json={"model": model, "keep_alive": 0},
                timeout=10,
            )
        except Exception:
            pass
