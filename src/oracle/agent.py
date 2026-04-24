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

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from oracle.config import settings
from oracle.distillation.collector import InteractionCollector
from oracle.memory import MemoryTiers
from oracle.project import load_instructions
from oracle.prompts import build_system_prompt
from oracle.retrieval.tool import retrieve_notes
from oracle.tools import BUILTIN_TOOLS


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
    base = build_system_prompt(
        user=settings.oracle_user, device=settings.oracle_device_name
    )
    ctx = memory.build_context(intent, thread_id=thread_id, archival_k=4, recall_n=6)
    instructions = load_instructions()
    parts = [base]
    if instructions:
        parts.append("## instructions\n" + instructions)
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
        self.memory.log_turn(
            role="user", content=prompt, thread_id=self.thread_id
        )
        final = self.graph.invoke(
            {"messages": self._seed_messages(prompt)}, self.config
        )
        last = final["messages"][-1]
        answer = last.content if isinstance(last, AIMessage) else str(last)

        self.memory.log_turn(
            role="assistant", content=answer, thread_id=self.thread_id
        )
        self.collector.log_turn(
            intent=prompt,
            response=answer,
            thread_id=self.thread_id,
        )
        return answer

    def stream(self, prompt: str):
        self.memory.log_turn(
            role="user", content=prompt, thread_id=self.thread_id
        )
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
            self.collector.log_turn(
                intent=prompt,
                response=last_text,
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
