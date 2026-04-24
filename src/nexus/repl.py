"""Oracle REPL — the default experience when you type `oracle`.

- Boots with the neon-purple ORACLE banner
- Uses prompt-toolkit for a real terminal input (history, arrow keys, Ctrl-R)
- Streams responses via the LangGraph agent
- Slash commands: /help /memory /skills /reflect /evolve /reset /thread /exit
"""

from __future__ import annotations

import time
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

from nexus import __version__
from nexus.banner import render_banner
from nexus.config import settings
from nexus.thinking import Thinking


HISTORY_PATH = Path.home() / ".oracle_history"


HELP_TEXT = """\
**commands**
  /help            show this help
  /memory          open the memory menu (stats · core · recall · remember)
  /skills          list skills in the library
  /reflect         review recent turns, surface themes + facts
  /evolve <intent> propose + test + promote a new skill for <intent>
  /reset           start a new thread (keeps memory, forgets current chat)
  /thread [id]     show or switch thread
  /clear           clear the screen
  /exit            leave (Ctrl-D also works)

type anything else to talk to Oracle.
"""


def _build_session() -> PromptSession:
    bindings = KeyBindings()
    # Nothing custom yet — placeholder for future bindings
    return PromptSession(
        history=FileHistory(str(HISTORY_PATH)),
        enable_history_search=True,
        mouse_support=False,
        key_bindings=bindings,
    )


def _tool_call_line(name: str, args: dict) -> str:
    """Claude-Code-style tool call: `name(key=preview, …)`."""
    if not args:
        return f"{name}()"
    parts = []
    for k, v in args.items():
        s = repr(v) if not isinstance(v, str) else v
        if len(s) > 60:
            s = s[:57] + "…"
        parts.append(f"{k}={s}")
    return f"{name}({', '.join(parts)})"


def _condense_tool_result(content: str) -> str:
    """A one-line summary of a tool's output for inline display."""
    if not content:
        return "(no output)"
    one = " ".join(content.split())
    return one[:160] + ("…" if len(one) > 160 else "")


def _stream_answer(oracle, prompt: str, console: Console) -> str:
    """Stream the agent's reply with Claude-Code-style UX:

      ✦ Channeling… (4s)           ← spinner before first token
      ✦ retrieve_notes(query=…)    ← on tool call
        ⎿ 3 hits · oracle, memory, …
      <streamed markdown answer>
    """
    final_text = ""
    seen_tool_ids: set[str] = set()
    shown_first_text = False

    with Thinking(console) as thinking:
        live: Live | None = None
        try:
            for msg in oracle.stream(prompt):
                # Tool invocation announcement
                if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                    for tc in msg.tool_calls:
                        tc_id = tc.get("id") or f"{tc.get('name')}-{len(seen_tool_ids)}"
                        if tc_id in seen_tool_ids:
                            continue
                        seen_tool_ids.add(tc_id)
                        thinking.pause()
                        console.print(
                            f"[bold #b23bf2]✦[/] [dim]{_tool_call_line(tc.get('name', '?'), tc.get('args', {}))}[/]"
                        )
                        thinking.resume(verb="Invoking")
                    continue

                # Tool result
                if isinstance(msg, ToolMessage):
                    content = (getattr(msg, "content", "") or "")
                    if isinstance(content, list):
                        content = " ".join(str(c) for c in content)
                    thinking.pause()
                    console.print(f"  [dim]⎿[/] [dim]{_condense_tool_result(str(content))}[/]")
                    thinking.resume(verb="Receiving")
                    continue

                # Final assistant text
                if isinstance(msg, AIMessage):
                    text = (getattr(msg, "content", "") or "").strip()
                    if not text or text == final_text:
                        continue
                    final_text = text
                    if not shown_first_text:
                        thinking.pause()
                        shown_first_text = True
                        live = Live(Markdown(text), console=console, refresh_per_second=10)
                        live.__enter__()
                    else:
                        if live is not None:
                            live.update(Markdown(text))
        finally:
            if live is not None:
                try:
                    live.__exit__(None, None, None)
                except Exception:
                    pass
    return final_text


def _handle_memory(console: Console) -> None:
    from nexus.memory import MemoryTiers

    tiers = MemoryTiers()
    console.print()
    console.print(f"[bold #c77dff]memory[/]")
    console.print(f"  core:     {tiers.core.size()} chars")
    console.print(f"  recall:   {tiers.recall.count()} turns")
    console.print(f"  archival: {tiers.archival.count()} entries")
    console.print()
    console.print("[dim]/memory core     — print core memory[/]")
    console.print("[dim]/memory recall Q — archival semantic search[/]")
    console.print("[dim]/memory remember F — store a fact[/]\n")


def _handle_memory_sub(args: list[str], console: Console) -> None:
    from nexus.memory import MemoryTiers

    tiers = MemoryTiers()
    if not args:
        _handle_memory(console)
        return
    sub, *rest = args
    if sub == "core":
        console.print(Markdown(tiers.core.read()))
    elif sub == "recall" and rest:
        q = " ".join(rest)
        hits = tiers.archival.query(q, k=5)
        if not hits:
            console.print("[dim]no hits[/]")
        for h in hits:
            console.print(f"- [dim]{h.get('tags', '')}[/] {h['content'][:200]}")
    elif sub == "remember" and rest:
        fact = " ".join(rest)
        mid = tiers.remember(fact, tags=["repl"], source="repl")
        console.print(f"[#c77dff]stored[/] id={mid[:8]}  {fact[:80]}")
    else:
        _handle_memory(console)


def _handle_skills(console: Console) -> None:
    from nexus.skills import SkillRegistry

    reg = SkillRegistry()
    reg.load_all()
    console.print()
    console.print(f"[bold #c77dff]skills[/]  total={reg.count()}  avg_conf={reg.stats()['avg_confidence']}")
    for s in sorted(reg.all(), key=lambda x: x.id):
        origin = {"seed": "·", "self_written": "★", "mesh": "◆"}.get(s.origin, "·")
        console.print(f"  [dim]{origin}[/] [cyan]{s.id:22s}[/] {s.description[:70]}")
    console.print()


def _handle_reflect(console: Console) -> None:
    from nexus.reflect import reflect as _reflect

    console.print("[dim]reflecting on recent turns…[/]")
    rep = _reflect(n_turns=40, apply=False, remember_facts=False)
    console.print(f"[bold #c77dff]reflect[/] · {rep.turns_reviewed} turns reviewed")
    if rep.themes:
        console.print("  [dim]themes:[/]")
        for t in rep.themes:
            console.print(f"    · {t}")
    if rep.facts_to_remember:
        console.print("  [dim]facts:[/]")
        for f in rep.facts_to_remember:
            console.print(f"    · {f}")
    if rep.notes:
        for n in rep.notes:
            console.print(f"  [dim]note: {n}[/]")
    console.print()


def _handle_evolve(args: list[str], console: Console) -> None:
    from nexus.skills.evolve import evolve_from_router_gap, evolve_skill

    if not args:
        console.print("[yellow]usage: /evolve <intent description>[/]")
        return
    intent = " ".join(args)
    console.print(f"[dim]evolving for: {intent}…[/]")
    t0 = time.time()
    result = evolve_from_router_gap(intent=intent, min_score=0.55)
    if result is None:
        console.print("[dim]skipped — existing skill covers this intent[/]")
        return
    dt = time.time() - t0
    if result.ok:
        console.print(
            f"[#9d00ff]promoted[/] {result.skill_id}  score {result.score:.2f}  ({dt:.1f}s)"
        )
    else:
        console.print(f"[yellow]rejected[/]  {result.rejection_reasons}  ({dt:.1f}s)")


def run_repl(*, console: Console, thread: str = "default") -> None:
    """Main loop. Returns when the user exits."""
    from nexus.agent import Oracle

    render_banner(
        console=console,
        model=settings.oracle_primary_model,
        device=settings.oracle_device_name,
        version=__version__,
    )

    oracle = Oracle(thread_id=thread)
    session = _build_session()

    try:
        while True:
            try:
                user_in = session.prompt("❯ ", multiline=False).strip()
            except KeyboardInterrupt:
                console.print("[dim](ctrl-c — type /exit to quit)[/]")
                continue
            except EOFError:
                break

            if not user_in:
                continue

            # Slash commands
            if user_in.startswith("/"):
                parts = user_in.split()
                cmd, args = parts[0].lower(), parts[1:]
                if cmd in {"/exit", "/quit"}:
                    break
                if cmd == "/help":
                    console.print(Markdown(HELP_TEXT))
                    continue
                if cmd == "/clear":
                    console.clear()
                    render_banner(
                        console=console,
                        model=settings.oracle_primary_model,
                        device=settings.oracle_device_name,
                        version=__version__,
                    )
                    continue
                if cmd == "/memory":
                    _handle_memory_sub(args, console)
                    continue
                if cmd == "/skills":
                    _handle_skills(console)
                    continue
                if cmd == "/reflect":
                    _handle_reflect(console)
                    continue
                if cmd == "/evolve":
                    _handle_evolve(args, console)
                    continue
                if cmd == "/reset":
                    oracle.close()
                    thread = f"{thread}-{int(time.time())}"
                    oracle = Oracle(thread_id=thread)
                    console.print(f"[dim]new thread: {thread}[/]")
                    continue
                if cmd == "/thread":
                    if args:
                        oracle.close()
                        thread = args[0]
                        oracle = Oracle(thread_id=thread)
                    console.print(f"[dim]thread: {thread}[/]")
                    continue
                console.print(f"[yellow]unknown command: {cmd}[/]  try /help")
                continue

            # Chat turn
            t0 = time.perf_counter()
            _stream_answer(oracle, user_in, console)
            console.print(f"[dim]({time.perf_counter() - t0:.1f}s)[/]\n")
    finally:
        oracle.close()

    console.print("\n[dim]session ended.[/]")
