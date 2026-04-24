"""Oracle agent loop — LangGraph + memory tiers + retrieval + interaction logging.

Every turn:
  1. Build context from memory tiers (core + top-k archival + recent recall)
  2. Inject into system prompt
  3. LLM runs with tool access (built-ins + retrieve_notes)
  4. Log the turn into InteractionCollector (for nightly distillation)
  5. Persist state via LangGraph SqliteSaver (thread resumability)
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_ollama import ChatOllama
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from nexus.config import settings
from nexus.distillation.collector import InteractionCollector
from nexus.memory import MemoryTiers
from nexus.memory.nine_tier import NineTier
from nexus.modes import overlay as mode_overlay
from nexus.onboarding import to_prompt_block as user_map_block
from nexus.project import load_instructions
from nexus.prompts import build_system_prompt
from nexus.retrieval.tool import retrieve_notes
from nexus.tools import BUILTIN_TOOLS


class OracleState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def _all_tools() -> list:
    return BUILTIN_TOOLS + [retrieve_notes]


def _make_llm(model: str | None = None) -> ChatOllama:
    return ChatOllama(
        model=model or settings.oracle_primary_model,
        base_url=settings.oracle_ollama_host,
        temperature=0.7,
        num_ctx=settings.oracle_num_ctx,
        # reasoning=True (default) keeps qwen3's CoT in a separate field so
        # `content` stays clean. Flip to False for snappier non-tool chat.
        client_kwargs={"timeout": settings.oracle_llm_timeout_sec},
    ).bind_tools(_all_tools())


def _make_graph(checkpoint_path: Path):
    llm = _make_llm()

    def llm_node(state: OracleState) -> dict:
        response = llm.invoke(state["messages"])
        return {"messages": [response]}

    tool_node = ToolNode(_all_tools())

    graph = StateGraph(OracleState)
    graph.add_node("llm", llm_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "llm")
    graph.add_conditional_edges("llm", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "llm")

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    saver_cm = SqliteSaver.from_conn_string(str(checkpoint_path))
    saver = saver_cm.__enter__()
    return graph.compile(checkpointer=saver), saver_cm


def _build_system_with_context(
    memory: MemoryTiers, intent: str, thread_id: str
) -> SystemMessage:
    """Assemble the full system prompt per turn.

    Layers:
      [constitution]          ← static identity + directives
      [project instructions]  ← NEXUS.md / ORACLE.md walked from cwd
      [USER MAP]              ← §24 memory/user_map.md
      [9-tier memory]         ← §06 non-empty tiers
      [ACTIVE MODE]           ← §13 overlay when set
      [live memory]           ← core + archival (top-k) + recall (recent)
    """
    base = build_system_prompt(
        user=settings.oracle_user,
        device=settings.oracle_device_name,
        instance=getattr(settings, "oracle_instance", "Nexus"),
    )
    parts: list[str] = [base]

    instructions = load_instructions()
    if instructions:
        parts.append("## PROJECT INSTRUCTIONS\n" + instructions)

    um = user_map_block()
    if um:
        parts.append(um)

    try:
        nine = NineTier().to_prompt_block(max_chars_each=600)
        if nine:
            parts.append(nine)
    except Exception:
        pass

    mo = mode_overlay()
    if mo:
        parts.append(mo)

    ctx = memory.build_context(intent, thread_id=thread_id, archival_k=4, recall_n=6)
    parts.append(ctx.to_prompt_block())

    return SystemMessage(content="\n\n".join(parts))


class Oracle:
    """Thin facade over LangGraph agent, memory tiers, and interaction logging."""

    def __init__(self, thread_id: str = "default"):
        ckpt = settings.oracle_home / "memory" / "agent_checkpoints.sqlite"
        self.graph, self._saver_cm = _make_graph(ckpt)
        self.thread_id = thread_id
        self.config = {"configurable": {"thread_id": thread_id}}
        self.memory = MemoryTiers()
        self.collector = InteractionCollector()

    def _seed_messages(self, prompt: str) -> list[BaseMessage]:
        # Always rebuild system message so memory context stays fresh
        sys_msg = _build_system_with_context(self.memory, prompt, self.thread_id)
        return [sys_msg, HumanMessage(content=prompt)]

    def ask(self, prompt: str) -> str:
        from nexus import sessions as _sessions

        self.memory.log_turn(role="user", content=prompt, thread_id=self.thread_id)
        _sessions.log(self.thread_id, "user", content=prompt)

        final = self.graph.invoke(
            {"messages": self._seed_messages(prompt)}, self.config
        )
        last = final["messages"][-1]
        answer = last.content if isinstance(last, AIMessage) else str(last)

        self.memory.log_turn(role="assistant", content=answer, thread_id=self.thread_id)
        _sessions.log(self.thread_id, "assistant", content=answer)
        self.collector.log_turn(
            intent=prompt,
            response=answer,
            thread_id=self.thread_id,
        )
        return answer

    def stream(self, prompt: str):
        """Back-compat: yields whole BaseMessages. Prefer stream_events()."""
        from nexus import sessions as _sessions

        self.memory.log_turn(role="user", content=prompt, thread_id=self.thread_id)
        _sessions.log(self.thread_id, "user", content=prompt)

        last_text = ""
        for event in self.graph.stream(
            {"messages": self._seed_messages(prompt)},
            self.config,
            stream_mode="values",
        ):
            if event.get("messages"):
                msg = event["messages"][-1]
                yield msg
                text = getattr(msg, "content", "") or ""
                if isinstance(msg, AIMessage):
                    last_text = text

        if last_text:
            self.memory.log_turn(
                role="assistant", content=last_text, thread_id=self.thread_id
            )
            _sessions.log(self.thread_id, "assistant", content=last_text)
            self.collector.log_turn(
                intent=prompt,
                response=last_text,
                thread_id=self.thread_id,
            )

    def stream_events(self, prompt: str):
        """Token-level streaming with tagged events.

        Yields dicts with a 'type' field:
          {"type": "token",       "text": str}          # incremental AI content
          {"type": "tool_call",   "name": str, "args": dict, "id": str}
          {"type": "tool_result", "name": str, "content": str, "id": str}
          {"type": "final",       "text": str}          # the complete assistant answer

        Uses LangGraph's multi-mode stream: `messages` for token chunks,
        `updates` for node transitions (tool calls + tool results).
        """
        from nexus import sessions as _sessions

        self.memory.log_turn(role="user", content=prompt, thread_id=self.thread_id)
        _sessions.log(self.thread_id, "user", content=prompt)

        final_text = ""
        seen_tool_call_ids: set[str] = set()

        # Multi-mode stream: each event is (mode, payload)
        stream = self.graph.stream(
            {"messages": self._seed_messages(prompt)},
            self.config,
            stream_mode=["messages", "updates"],
        )
        for mode, payload in stream:
            if mode == "messages":
                # payload = (AIMessageChunk|str, metadata_dict)
                chunk = payload[0] if isinstance(payload, tuple) else payload
                text = getattr(chunk, "content", None)
                if isinstance(text, list):
                    text = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in text)
                if text:
                    final_text += text
                    yield {"type": "token", "text": text}
                # tool calls arrive in chunks as well — emit once per id
                for tc in getattr(chunk, "tool_calls", None) or []:
                    tid = tc.get("id") or tc.get("name", "")
                    if tid and tid not in seen_tool_call_ids and tc.get("name"):
                        seen_tool_call_ids.add(tid)
                        yield {
                            "type": "tool_call",
                            "name": tc.get("name"),
                            "args": tc.get("args") or {},
                            "id": tid,
                        }
                        _sessions.log(
                            self.thread_id,
                            "tool_call",
                            name=tc.get("name"),
                            args=tc.get("args") or {},
                        )

            elif mode == "updates":
                # payload = {node_name: state_dict}
                for _node, state in payload.items():
                    msgs = state.get("messages", []) if isinstance(state, dict) else []
                    for m in msgs:
                        if isinstance(m, ToolMessage):
                            content = getattr(m, "content", "") or ""
                            if isinstance(content, list):
                                content = " ".join(str(c) for c in content)
                            yield {
                                "type": "tool_result",
                                "name": getattr(m, "name", None) or "",
                                "content": str(content),
                                "id": getattr(m, "tool_call_id", "") or "",
                            }
                            _sessions.log(
                                self.thread_id,
                                "tool_result",
                                name=getattr(m, "name", ""),
                                content=str(content)[:2000],
                            )
                        elif isinstance(m, AIMessage):
                            # Catch tool_calls that didn't come through the
                            # `messages` stream (e.g. non-streaming LLM nodes).
                            for tc in getattr(m, "tool_calls", None) or []:
                                tid = tc.get("id") or tc.get("name", "")
                                if tid and tid not in seen_tool_call_ids and tc.get("name"):
                                    seen_tool_call_ids.add(tid)
                                    yield {
                                        "type": "tool_call",
                                        "name": tc.get("name"),
                                        "args": tc.get("args") or {},
                                        "id": tid,
                                    }
                                    _sessions.log(
                                        self.thread_id,
                                        "tool_call",
                                        name=tc.get("name"),
                                        args=tc.get("args") or {},
                                    )

        yield {"type": "final", "text": final_text}
        if final_text:
            self.memory.log_turn(
                role="assistant", content=final_text, thread_id=self.thread_id
            )
            _sessions.log(self.thread_id, "assistant", content=final_text)
            self.collector.log_turn(
                intent=prompt,
                response=final_text,
                thread_id=self.thread_id,
            )

    def close(self):
        try:
            self._saver_cm.__exit__(None, None, None)
        except Exception:
            pass
        try:
            self.memory.close()
        except Exception:
            pass
