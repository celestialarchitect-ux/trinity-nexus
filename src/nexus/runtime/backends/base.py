"""Backend abstract base. Each backend produces ChatResponse + StreamEvent."""

from __future__ import annotations

from abc import ABC, abstractmethod

from nexus.runtime.types import ChatRequest, ChatResponse, StreamIter


class Backend(ABC):
    """Inference backend — stateful where it helps (KV cache, model warmup)."""

    name: str = "base"

    @abstractmethod
    def chat(self, req: ChatRequest) -> ChatResponse:
        """Non-streaming completion."""

    @abstractmethod
    def stream(self, req: ChatRequest) -> StreamIter:
        """Streaming completion — yields StreamEvent."""

    def embed(self, text: str, model: str) -> list[float]:
        raise NotImplementedError(f"{self.name} does not implement embed")

    # Optional lifecycle hooks
    def warmup(self, model: str) -> None:
        pass

    def unload(self, model: str) -> None:
        pass

    def is_available(self) -> bool:
        return True
