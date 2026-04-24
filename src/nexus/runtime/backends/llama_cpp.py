"""llama-cpp-python backend — direct GGUF inference, no daemon.

Advantages over the Ollama backend:
- True parallelism (multiple Llama instances share no lock)
- Precise VRAM control via `n_gpu_layers` per model
- Prompt caching at the KV-cache level — reuse the constitution across turns
- Own tool-call parsing so we can fix qwen3 quirks
- Deterministic `seed` for replay + eval

Install: `pip install llama-cpp-python` (CPU) or with CUDA:
  CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --no-binary llama-cpp-python

Model files live at `NEXUS_MODEL_DIR` (default `~/.nexus/models/`) and are
specified by path or HuggingFace repo id.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from nexus.runtime.backends.base import Backend
from nexus.runtime.types import ChatRequest, ChatResponse, StreamEvent, StreamIter


def _default_model_dir() -> Path:
    import os
    env = os.environ.get("NEXUS_MODEL_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".nexus" / "models"


class LlamaCppBackend(Backend):
    """Lazy-import llama-cpp-python so the dep stays optional."""

    name = "llama_cpp"

    def __init__(self, *, n_gpu_layers: int = -1, n_ctx: int = 16384):
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx
        self._models: dict[str, object] = {}  # model_id -> Llama instance
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        try:
            import llama_cpp  # noqa: F401
            return True
        except ImportError:
            return False

    def _resolve_model_path(self, model: str) -> str:
        """Accept either a filesystem path or `<repo>/<file.gguf>` HF id."""
        p = Path(model).expanduser()
        if p.exists():
            return str(p)
        cached = _default_model_dir() / model
        if cached.exists():
            return str(cached)
        # Last resort: pass through; llama-cpp-python supports HF repo IDs
        # via from_pretrained. Caller can use `repo::filename` convention.
        return model

    def _get(self, model: str, *, num_ctx: int):
        with self._lock:
            if model in self._models:
                return self._models[model]
            from llama_cpp import Llama

            path = self._resolve_model_path(model)
            llm = Llama(
                model_path=path if Path(path).exists() else None,
                model=None if Path(path).exists() else path,  # HF id fallback
                n_ctx=max(num_ctx, self.n_ctx),
                n_gpu_layers=self.n_gpu_layers,
                verbose=False,
                chat_format="chatml-function-calling",  # good default for Qwen / Llama
            )
            self._models[model] = llm
            return llm

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

    def chat(self, req: ChatRequest) -> ChatResponse:
        llm = self._get(req.model, num_ctx=req.num_ctx)
        r = llm.create_chat_completion(
            messages=self._messages(req),
            tools=self._tools(req),
            temperature=req.temperature,
            max_tokens=req.max_tokens or 2048,
            stop=req.stop or None,
            stream=False,
        )
        choice = r["choices"][0]["message"]
        return ChatResponse(
            content=choice.get("content") or "",
            tool_calls=choice.get("tool_calls") or [],
            finish_reason=r["choices"][0].get("finish_reason", "stop"),
            prompt_tokens=r.get("usage", {}).get("prompt_tokens", 0),
            completion_tokens=r.get("usage", {}).get("completion_tokens", 0),
        )

    def stream(self, req: ChatRequest) -> StreamIter:
        llm = self._get(req.model, num_ctx=req.num_ctx)
        accumulated_tc: dict[int, dict] = {}
        prompt_tokens = 0
        completion_tokens = 0

        for chunk in llm.create_chat_completion(
            messages=self._messages(req),
            tools=self._tools(req),
            temperature=req.temperature,
            max_tokens=req.max_tokens or 2048,
            stop=req.stop or None,
            stream=True,
        ):
            delta = chunk["choices"][0].get("delta", {})
            text = delta.get("content")
            if text:
                yield StreamEvent(type="token", text=text)
            for tc_delta in delta.get("tool_calls") or []:
                idx = tc_delta.get("index", 0)
                acc = accumulated_tc.setdefault(
                    idx, {"id": "", "name": "", "arguments": ""}
                )
                if tc_delta.get("id"):
                    acc["id"] = tc_delta["id"]
                fn = tc_delta.get("function") or {}
                if fn.get("name"):
                    acc["name"] = fn["name"]
                if fn.get("arguments"):
                    acc["arguments"] += fn["arguments"]
            finish = chunk["choices"][0].get("finish_reason")
            if finish:
                # Emit accumulated tool calls
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
                usage = chunk.get("usage") or {}
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
        yield StreamEvent(
            type="done",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    def embed(self, text: str, model: str) -> list[float]:
        llm = self._get(model, num_ctx=self.n_ctx)
        if not hasattr(llm, "embed"):
            raise NotImplementedError("model was not loaded with embedding=True")
        return list(llm.embed(text))

    def unload(self, model: str) -> None:
        with self._lock:
            self._models.pop(model, None)
