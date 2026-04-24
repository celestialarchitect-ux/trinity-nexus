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
from langchain_core.language_models.chat_models import BaseChatModel
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


def _frontier_enabled() -> bool:
    """True when the agent loop should route through a frontier (cloud) model.

    Triggered by:
      - env NEXUS_USE_FRONTIER=1|true|yes
      - --frontier flag on `nexus` / `nexus ask` (sets env above)
      - settings.oracle_use_frontier=true in .env
    """
    import os
    if os.environ.get("NEXUS_USE_FRONTIER", "").lower() in {"1", "true", "yes", "on"}:
        return True
    return bool(getattr(settings, "oracle_use_frontier", False))


def _make_frontier_llm(model: str | None = None) -> BaseChatModel:
    """Build a frontier-backed (Claude/GPT/Llama-via-Groq/etc.) chat model.

    Reuses NEXUS_FRONTIER_* env config and the openai_compat provider presets
    (base_url + default model). Tool-call format is OpenAI-style; works with
    Groq/OpenAI/OpenRouter/Together/Fireworks/DeepSeek/Mistral.
    """
    import os
    from langchain_openai import ChatOpenAI
    from nexus.runtime.backends.openai_compat import PROVIDER_PRESETS

    provider = os.environ.get("NEXUS_FRONTIER_PROVIDER", "groq").lower()
    preset = PROVIDER_PRESETS.get(provider, {})
    base_url = (
        os.environ.get("NEXUS_FRONTIER_BASE_URL")
        or preset.get("base_url")
        or "https://api.groq.com/openai/v1"
    ).rstrip("/")
    api_key = os.environ.get("NEXUS_FRONTIER_API_KEY", "") or "no-key-set"
    model_name = (
        model
        or os.environ.get("NEXUS_FRONTIER_MODEL")
        or preset.get("default_model")
        or "llama-3.3-70b-versatile"
    )
    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0.7,
        timeout=settings.oracle_llm_timeout_sec,
    ).bind_tools(_all_tools())


def _make_local_llm(model: str | None = None) -> BaseChatModel:
    """Build a local Ollama LangChain chat model (the sovereign brain)."""
    if model is None:
        try:
            from nexus.modes import preferred_model_for_active
            mode_model = preferred_model_for_active()
            if mode_model:
                model = mode_model
        except Exception:
            pass

    ka_raw = settings.oracle_primary_keepalive
    try:
        keep_alive: str | int = int(ka_raw)
    except (TypeError, ValueError):
        keep_alive = ka_raw

    return ChatOllama(
        model=model or settings.oracle_primary_model,
        base_url=settings.oracle_ollama_host,
        temperature=0.7,
        num_ctx=settings.oracle_num_ctx,
        keep_alive=keep_alive,
        client_kwargs={"timeout": settings.oracle_llm_timeout_sec},
    ).bind_tools(_all_tools())


# Back-compat — older callers import _make_llm. Routes the same as the graph
# would: frontier when NEXUS_USE_FRONTIER=1, otherwise local.
def _make_llm(model: str | None = None) -> BaseChatModel:
    if _frontier_enabled():
        try:
            return _make_frontier_llm(model)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "frontier LLM init failed (%s); falling back to local Ollama", e
            )
    return _make_local_llm(model)


_ACTION_VERBS = (
    "build", "create", "make", "write", "generate", "scaffold", "implement",
    "edit", "fix", "patch", "modify", "change", "refactor", "rename",
    "run", "execute", "install", "compile", "test",
    "delete", "remove",
    "read", "open", "show me", "find", "search", "grep",
    "fetch", "download", "scrape",
)


_ACTION_VERB_REGEX = None  # compiled lazily on first call


def _looks_like_action_request(text: str) -> bool:
    """Heuristic: does this user message want an artifact, not just an answer?

    Used to auto-route to the frontier model when one is configured. Keep this
    cheap (no LLM call) and slightly over-eager — false positives just send
    chatty questions to the bigger model, which is acceptable.

    Matches whole-word verbs only ("create" yes, "created" no) so things like
    "what year was python created" don't trigger.
    """
    global _ACTION_VERB_REGEX
    if not text:
        return False
    t = text.lower().strip()
    if t.startswith(("/", "@", "!", "#", "?")):
        return False
    head = t[:200]

    if _ACTION_VERB_REGEX is None:
        import re as _re
        # Match each verb only as a whole word OR followed by a space — so
        # "create" matches "create file" but not "created" or "creator".
        # Multi-word triggers like "show me" still match.
        verbs_pattern = "|".join(
            _re.escape(v) for v in sorted(_ACTION_VERBS, key=len, reverse=True)
        )
        _ACTION_VERB_REGEX = _re.compile(rf"\b(?:{verbs_pattern})\b")

    if _ACTION_VERB_REGEX.search(head):
        return True

    for trigger in ("can you ", "please ", "i want you to ", "i need you to "):
        if t.startswith(trigger):
            return True
    return False


def _frontier_available() -> bool:
    """True iff a frontier API key is configured. Cheap env check."""
    import os as _os
    return bool(_os.environ.get("NEXUS_FRONTIER_API_KEY"))


def _make_graph(checkpoint_path: Path):
    """Compile the agent graph with both local + frontier LLMs.

    Local Ollama is always built (free, sovereign). Frontier is built lazily
    iff a key is configured. The llm_node picks per-turn based on:
      1. NEXUS_USE_FRONTIER env var (set by --frontier flag or /model frontier)
      2. NEXUS_AUTO_FRONTIER env var (default 1) — auto-route action requests
         to frontier when one is available

    On frontier API failure (rate limit, network, etc.) the node falls back
    to the local model so the turn still completes instead of crashing.
    """
    import logging as _logging
    import os as _os

    log = _logging.getLogger(__name__)

    # Pre-build both LLMs at graph-compile time so per-turn routing is free.
    local_llm = _make_local_llm()
    frontier_llm = None
    if _frontier_available():
        try:
            frontier_llm = _make_frontier_llm()
        except Exception as e:
            log.warning("frontier LLM init skipped (%s)", e)

    def _last_user_text(state: OracleState) -> str:
        for msg in reversed(state.get("messages") or []):
            if isinstance(msg, HumanMessage):
                content = msg.content if isinstance(msg.content, str) else ""
                return content
        return ""

    def _should_use_frontier(state: OracleState) -> bool:
        if frontier_llm is None:
            return False
        # Explicit on-switch always wins.
        if _os.environ.get("NEXUS_USE_FRONTIER", "").lower() in {"1", "true", "yes", "on"}:
            return True
        # Auto-route action requests when allowed.
        auto = _os.environ.get("NEXUS_AUTO_FRONTIER", "1").lower() in {"1", "true", "yes", "on"}
        if auto and _looks_like_action_request(_last_user_text(state)):
            return True
        return False

    _REFUSAL_PHRASES = (
        "i can't",
        "i cannot",
        "i don't have access",
        "i don't have the ability",
        "i do not have the capability",
        "i'm unable",
        "i am unable",
        "i'm not able",
        "i am not able",
        "sorry, i can't",
        "i'm sorry, i can't",
        "as an ai",
        "i lack the",
    )

    def _looks_like_refusal(response) -> bool:
        """Did the local model bail out instead of doing the work?

        We only count this when there are NO tool calls (a tool call means
        the model is actually trying). We look at the first ~300 chars of
        content for the common refusal openers.
        """
        if not isinstance(response, AIMessage):
            return False
        if getattr(response, "tool_calls", None):
            return False
        content = response.content if isinstance(response.content, str) else ""
        head = content.lower().lstrip()[:300]
        return any(p in head for p in _REFUSAL_PHRASES)

    def llm_node(state: OracleState) -> dict:
        use_frontier = _should_use_frontier(state)
        if use_frontier:
            try:
                response = frontier_llm.invoke(state["messages"])
                return {"messages": [response]}
            except Exception as e:
                # Common: 413 over-TPM, 401 bad key, network. Fall back so the
                # turn still completes; surface a small note in the response.
                log.warning("frontier LLM failed (%s); falling back to local", e)
                response = local_llm.invoke(state["messages"])
                fallback_note = (
                    f"\n\n_(frontier unavailable: {type(e).__name__}; answered locally)_"
                )
                if isinstance(response, AIMessage):
                    response = AIMessage(
                        content=str(response.content) + fallback_note,
                        tool_calls=getattr(response, "tool_calls", []) or [],
                        id=getattr(response, "id", None),
                    )
                return {"messages": [response]}

        # Local path. After the response, escalate to frontier if local refused
        # outright AND we haven't already disabled escalation.
        response = local_llm.invoke(state["messages"])

        if (
            frontier_llm is not None
            and _os.environ.get("NEXUS_AUTO_ESCALATE", "1").lower() in {"1", "true", "yes", "on"}
            and _looks_like_refusal(response)
        ):
            log.info("local refused; escalating to frontier")
            try:
                escalated = frontier_llm.invoke(state["messages"])
                if isinstance(escalated, AIMessage):
                    return {"messages": [escalated]}
            except Exception as e:
                log.warning("frontier escalation failed (%s); keeping local response", e)

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

    # Graph context — include 1-hop neighbors of entities the user mentions,
    # if any match the graph. Lightweight; no LLM calls, just a SQLite BFS.
    try:
        from nexus import graph as _g
        # Heuristic: capitalized nouns in the intent that are 2+ chars.
        import re as _re
        candidates = list({*_re.findall(r"\b[A-Z][A-Za-z][A-Za-z0-9_\- ]{1,30}\b", intent or "")})[:6]
        graph_lines: list[str] = []
        for entity in list(candidates)[:3]:
            r = _g.query(entity, depth=1, limit=8)
            if r.get("matches"):
                for e in r["edges"][:5]:
                    graph_lines.append(f"- {e['from']} —{e['kind']}→ {e['to']}")
        if graph_lines:
            parts.append(
                "## GRAPH CONTEXT (personal knowledge graph, 1-hop neighbors)\n"
                + "\n".join(graph_lines)
            )
    except Exception:
        pass

    mo = mode_overlay()
    if mo:
        parts.append(mo)

    try:
        ctx = memory.build_context(intent, thread_id=thread_id, archival_k=4, recall_n=6)
        parts.append(ctx.to_prompt_block())
    except Exception:
        # Memory subsystem unavailable (e.g. Ollama VRAM pressure during
        # embedding). Skip that block — the agent still has the constitution,
        # USER MAP, 9-tier, and mode overlay.
        pass

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

    def _maybe_prune_checkpoint(self) -> None:
        """Keep LangGraph's in-thread message history bounded.

        Without this, checkpoints grow forever and every turn re-sends the
        whole history to the LLM. We cap in-thread messages at
        NEXUS_CHECKPOINT_MAX_MESSAGES (default 40) — plenty for recent
        context; older content lives in the 9-tier memory + graph instead.
        """
        import os as _os
        try:
            cap = int(_os.environ.get("NEXUS_CHECKPOINT_MAX_MESSAGES", "40"))
        except (TypeError, ValueError):
            cap = 40
        try:
            state = self.graph.get_state(self.config)
            msgs = list((state.values or {}).get("messages") or [])
            if len(msgs) <= cap:
                return
            from langchain_core.messages import RemoveMessage
            # Drop all but the most recent `cap` messages.
            to_remove = msgs[:-cap]
            self.graph.update_state(
                self.config,
                {"messages": [RemoveMessage(id=m.id) for m in to_remove if getattr(m, "id", None)]},
            )
        except Exception:
            pass

    def _maybe_compact(self) -> None:
        """Auto-compact when uncompacted events exceed the threshold.

        Tracks a "compact" marker event in the session. Only counts events
        AFTER the most recent marker — so once we've compacted, we don't
        re-trigger every turn until new activity piles up again.
        """
        import os as _os
        try:
            if _os.environ.get("NEXUS_AUTOCOMPACT", "1") != "1":
                return
            threshold = int(_os.environ.get("NEXUS_AUTOCOMPACT_EVENTS", "80"))
            from nexus import sessions as _s
            events = _s.read_thread(self.thread_id, limit=500)
            if not events:
                return
            # Walk backwards to find the last compact marker
            last_mark_idx = -1
            for i in range(len(events) - 1, -1, -1):
                if events[i].get("kind") == "compact":
                    last_mark_idx = i
                    break
            new_events = len(events) - 1 - last_mark_idx
            if new_events < threshold:
                return
            from nexus.compaction import compact as _compact
            report = _compact(self.thread_id, keep_recent=max(10, threshold // 4))
            if report.get("ok"):
                _s.log(self.thread_id, "compact", summary_chars=report.get("summary_chars", 0))
        except Exception:
            pass

    def ask(self, prompt: str) -> str:
        from nexus import sessions as _sessions

        self._maybe_prune_checkpoint()
        self._maybe_compact()
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
        self._maybe_prune_checkpoint()
        self._maybe_compact()
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
