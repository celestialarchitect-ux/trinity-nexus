"""Runtime types — normalised request / response / stream events.

Every backend converts its native format to / from these types so the
agent layer is backend-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Literal


Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class Message:
    role: Role
    content: str
    tool_call_id: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    name: str | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema


@dataclass
class ChatRequest:
    messages: list[Message]
    model: str
    tools: list[ToolSpec] = field(default_factory=list)
    temperature: float = 0.7
    num_ctx: int = 8192
    max_tokens: int | None = None
    stream: bool = False
    stop: list[str] = field(default_factory=list)
    # Passthrough for backend-specific knobs (think=False for qwen3, etc.)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResponse:
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: str = "stop"
    # Accounting
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class StreamEvent:
    """One tagged event in a streaming response."""
    type: Literal["token", "tool_call", "done"]
    text: str = ""                 # present for 'token'
    tool_call: dict | None = None  # present for 'tool_call'
    prompt_tokens: int = 0         # populated at 'done'
    completion_tokens: int = 0     # populated at 'done'


StreamIter = Iterator[StreamEvent]
