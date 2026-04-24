"""Trinity Nexus REPL.

Default experience when the user types `nexus`. Renders the neon-purple
banner, prompt-toolkit input with Shift+Enter multiline, slash commands
for every constitutional surface (§04 onboarding, §13 modes, §06 9-tier
memory, §19 subagents, §29 dangerous-op gate), and Claude-Code-style
streaming with esoteric thinking verbs.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown

from nexus import __version__
from nexus import hooks as _hooks
from nexus.banner import render_banner
from nexus.config import settings
from nexus.thinking import Thinking


HISTORY_PATH = Path.home() / ".nexus_history"


HELP_TEXT = """\
**commands** (§04/§13/§06/§19/§29)

  /help                show this help
  /onboard             walk §04/§23/§24 orientation to build the USER MAP
  /user-map            print the active USER MAP
  /mode [name|list|off] switch operating mode (§13). Names: architect,
                       builder, strategist, codex, critic, executor,
                       mirror, research, memory, evolution, governor,
                       orchestrator
  /memory [tier] [read|write|append text]
                       inspect / edit the 9-tier memory (§06)
                       tiers: core, projects, strategic, creative,
                              technical, personal, protected, threads,
                              artifacts
  /skills              list the skill library
  /reflect             review recent turns, surface themes + facts
  /evolve <intent>     propose + test + promote a new skill
  /spawn <task>        run a sub-agent on a self-contained task (§19)
  /dangerous [on|off]  toggle destructive-command unlock (§29)
  /permissions [list|allow <tool> <p>|deny <tool> <p>|remove <t> <p>]
                       per-tool glob permissions (§29)
  /allow <tool> <pat>  shortcut: allow tool:pattern
  /deny <tool> <pat>   shortcut: deny tool:pattern
  /trace               show tool calls + memory tiers used recently
  /paste               open $EDITOR / notepad for a big multi-line prompt
  /reset               new thread (memory kept, chat context dropped)
  /thread [id]         show or switch thread
  /clear               clear screen, redraw banner
  /exit                leave (Ctrl-D works too)

type anything else to talk to Trinity Nexus.
shift+enter = newline · enter = submit
"""


def _build_session() -> PromptSession:
    """Prompt with history + Shift+Enter newline, Enter submit."""
    bindings = KeyBindings()

    # Shift+Enter → insert newline (when terminal supports Meta/Esc+Enter)
    @bindings.add(Keys.Escape, Keys.Enter)
    def _(event):
        event.current_buffer.insert_text("\n")

    return PromptSession(
        history=FileHistory(str(HISTORY_PATH)),
        enable_history_search=True,
        mouse_support=False,
        multiline=False,
        key_bindings=bindings,
    )


def _tool_call_line(name: str, args: dict) -> str:
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
    if not content:
        return "(no output)"
    one = " ".join(content.split())
    return one[:160] + ("…" if len(one) > 160 else "")


def _stream_answer(oracle, prompt: str, console: Console) -> str:
    """Token-by-token streaming Claude-Code-style, with esoteric thinking verbs.

    Uses oracle.stream_events() → tagged dicts (token / tool_call / tool_result
    / final), falls back to oracle.stream() if the event API isn't present.
    """
    final_text = ""
    live: Live | None = None
    shown_first_text = False
    thinking: Thinking | None = None

    _hooks.run("pre_prompt", {"prompt": prompt, "thread": oracle.thread_id})

    # Use the new event API if available
    use_events = hasattr(oracle, "stream_events")

    try:
        thinking = Thinking(console).__enter__()

        if use_events:
            for evt in oracle.stream_events(prompt):
                t = evt.get("type")
                if t == "tool_call":
                    thinking.pause()
                    console.print(
                        f"[bold #b23bf2]✦[/] [dim]{_tool_call_line(evt['name'], evt.get('args', {}))}[/]"
                    )
                    _hooks.run("pre_tool", {"name": evt["name"], "args": evt.get("args")})
                    thinking.resume(verb="Invoking")
                elif t == "tool_result":
                    thinking.pause()
                    console.print(
                        f"  [dim]⎿[/] [dim]{_condense_tool_result(evt.get('content', ''))}[/]"
                    )
                    _hooks.run("post_tool", {"content": evt.get("content", "")[:2000]})
                    thinking.resume(verb="Receiving")
                elif t == "token":
                    chunk = evt.get("text", "")
                    if not chunk:
                        continue
                    if not shown_first_text:
                        thinking.pause()
                        thinking = None
                        shown_first_text = True
                        final_text = chunk
                        live = Live(
                            Markdown(final_text), console=console, refresh_per_second=12
                        )
                        live.__enter__()
                    else:
                        final_text += chunk
                        if live is not None:
                            live.update(Markdown(final_text))
                elif t == "final":
                    # If the whole answer came through a non-streaming path
                    # (no `token` events), render it now.
                    if not shown_first_text and evt.get("text"):
                        if thinking is not None:
                            thinking.pause()
                            thinking = None
                        final_text = evt["text"]
                        console.print(Markdown(final_text))
        else:
            # Fallback path (should be rare) — use the old message stream
            seen: set[str] = set()
            for msg in oracle.stream(prompt):
                if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                    for tc in msg.tool_calls:
                        tc_id = tc.get("id") or f"{tc.get('name')}-{len(seen)}"
                        if tc_id in seen:
                            continue
                        seen.add(tc_id)
                        if thinking:
                            thinking.pause()
                        console.print(
                            f"[bold #b23bf2]✦[/] [dim]{_tool_call_line(tc.get('name', '?'), tc.get('args', {}))}[/]"
                        )
                        if thinking:
                            thinking.resume(verb="Invoking")
                elif isinstance(msg, ToolMessage):
                    content = getattr(msg, "content", "") or ""
                    if thinking:
                        thinking.pause()
                    console.print(
                        f"  [dim]⎿[/] [dim]{_condense_tool_result(str(content))}[/]"
                    )
                    if thinking:
                        thinking.resume(verb="Receiving")
                elif isinstance(msg, AIMessage):
                    text = (getattr(msg, "content", "") or "").strip()
                    if text and text != final_text:
                        final_text = text
                        if not shown_first_text:
                            if thinking:
                                thinking.pause()
                                thinking = None
                            shown_first_text = True
                            live = Live(
                                Markdown(text), console=console, refresh_per_second=10
                            )
                            live.__enter__()
                        elif live is not None:
                            live.update(Markdown(text))
    finally:
        if live is not None:
            try:
                live.__exit__(None, None, None)
            except Exception:
                pass
        if thinking is not None:
            try:
                thinking.stop()
            except Exception:
                pass

    _hooks.run(
        "post_response",
        {"response": final_text[:4000], "thread": oracle.thread_id},
    )
    return final_text


# ---------- slash-command handlers ----------


def _handle_memory(args: list[str], console: Console) -> None:
    """/memory [tier] [read|write|append text…]"""
    from nexus.memory.nine_tier import NineTier, TIER_LABELS

    nine = NineTier()
    if not args:
        console.print()
        console.print("[bold #c77dff]memory tiers (§06)[/]")
        for t in nine.all():
            size = t.size()
            console.print(f"  [cyan]{t.key:10s}[/] {t.label}  [dim]{size} chars[/]")
        console.print()
        console.print("[dim]/memory <tier>              read tier[/]")
        console.print("[dim]/memory <tier> append text  append a line[/]")
        console.print("[dim]/memory <tier> write text   replace content[/]")
        return

    key, *rest = args
    tier = nine.get(key)
    if not tier:
        console.print(f"[yellow]unknown tier {key!r}[/]  valid: {', '.join(TIER_LABELS.keys())}")
        return
    if not rest:
        console.print(Markdown(tier.read() or "_empty_"))
        return
    sub = rest[0].lower()
    payload = " ".join(rest[1:]).strip()
    if sub == "append" and payload:
        tier.append(payload)
        console.print(f"[#7cffb0]appended[/] → {tier.label}")
    elif sub == "write" and payload:
        tier.write(payload)
        console.print(f"[#7cffb0]replaced[/] → {tier.label}")
    else:
        console.print("[yellow]usage: /memory <tier> [read|write|append] <text>[/]")


def _handle_mode(args: list[str], console: Console) -> None:
    from nexus.modes import MODES, describe_all, get_active, set_active

    if not args or args[0] == "list":
        active = get_active()
        console.print()
        console.print("[bold #c77dff]operating modes (§13)[/]")
        for key, one in describe_all():
            marker = "●" if (active and active.key == key) else " "
            color = "#c77dff" if marker == "●" else "dim"
            console.print(f"  [{color}]{marker}[/] [cyan]{key:13s}[/] [dim]{one}[/]")
        console.print()
        if active:
            console.print(f"[dim]active: {active.name}[/]")
        console.print("[dim]/mode <name>  to switch · /mode off  to clear[/]")
        return
    target = args[0].lower()
    mode = set_active(target)
    if target in {"off", "none", "clear", "default"}:
        console.print("[dim]mode cleared[/]")
    elif mode:
        console.print(f"[#9d00ff]mode → {mode.name}[/]  [dim]{mode.one_line}[/]")
    else:
        console.print(f"[yellow]unknown mode {target!r}[/] · try /mode list")


def _handle_onboard(console: Console) -> None:
    from nexus.onboarding import ORIENTATION_QUESTIONS, UserMap, save_user_map

    console.print()
    console.print("[bold #c77dff]onboarding — §04 / §23 / §24[/]")
    console.print(
        "[dim]i'll ask four short questions. skip any with empty-enter.[/]\n"
    )
    answers: dict[str, str] = {}
    for key, q in ORIENTATION_QUESTIONS:
        try:
            ans = console.input(f"[#c77dff]?[/] {q}\n  > ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("[dim]onboarding cancelled[/]")
            return
        answers[key] = ans

    try:
        name = console.input(
            "[#c77dff]?[/] what name should I call you? (optional)\n  > "
        ).strip()
    except (EOFError, KeyboardInterrupt):
        name = ""

    um = UserMap(
        preferred_name=name,
        primary_mission=answers.get("mission", ""),
        operating_role=answers.get("role", ""),
        mind=answers.get("mental", ""),
        current_priority=answers.get("priority", ""),
    )
    path = save_user_map(um)
    console.print(f"\n[#7cffb0]USER MAP written[/] → {path}\n")
    console.print("[dim]it's loaded into every turn now. edit the markdown anytime.[/]")


def _handle_user_map(console: Console) -> None:
    from nexus.onboarding import load_user_map

    body = load_user_map().strip()
    if not body:
        console.print("[dim]no USER MAP yet · run /onboard[/]")
        return
    console.print(Markdown(body))


def _handle_spawn(args: list[str], console: Console) -> None:
    from nexus.agent import Oracle
    import uuid as _uuid

    if not args:
        console.print("[yellow]usage: /spawn <task description>[/]")
        return
    task = " ".join(args)
    tid = f"sub-{_uuid.uuid4().hex[:10]}"
    console.print(f"[dim]spawning sub-agent · thread={tid}[/]")
    sub = Oracle(thread_id=tid)
    try:
        with Thinking(console) as t:
            t.set_verb("Summoning")
            answer = sub.ask(task)
    finally:
        sub.close()
    console.print(Markdown(answer or "_no response_"))


def _handle_permissions(args: list[str], console: Console) -> None:
    """/permissions [list|allow <tool> <pattern>|deny <tool> <pattern>|remove <tool> <pattern>]"""
    from nexus import permissions as perms

    if not args or args[0] == "list":
        rules = perms.list_rules()
        if not rules:
            console.print(
                "[dim]no rules set · read-family tools allowed by default, "
                "mutation denied by default[/]"
            )
            console.print(
                "[dim]add a rule: /allow bash 'git *' · /deny write '**/.env'[/]"
            )
            return
        from rich.table import Table as _T
        t = _T(title="permissions")
        t.add_column("verdict")
        t.add_column("tool", style="cyan")
        t.add_column("pattern")
        for tool, pattern, verdict in rules:
            color = "#7cffb0" if verdict == "allow" else "red"
            t.add_row(f"[{color}]{verdict}[/]", tool, pattern)
        console.print(t)
        return

    sub = args[0].lower()
    if sub in {"allow", "deny"} and len(args) >= 3:
        tool, pattern = args[1], " ".join(args[2:])
        (perms.allow if sub == "allow" else perms.deny)(tool, pattern)
        console.print(f"[#7cffb0]{sub}[/] {tool}:{pattern}")
    elif sub == "remove" and len(args) >= 3:
        tool, pattern = args[1], " ".join(args[2:])
        ok = perms.remove(tool, pattern)
        console.print("[#7cffb0]removed[/]" if ok else "[dim]no such rule[/]")
    else:
        console.print("[yellow]usage: /permissions [list|allow|deny|remove] <tool> <pattern>[/]")


def _handle_trace(console: Console) -> None:
    """/trace — show what memory tiers / tools / skills were used most recently."""
    from nexus import sessions as _sessions

    # find the most recent session file
    from nexus.config import settings as _s

    base = _s.oracle_home / "sessions"
    if not base.exists():
        console.print("[dim]no session data[/]")
        return
    files = sorted(base.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not files:
        console.print("[dim]no session data[/]")
        return
    events = _sessions.read_thread(files[-1].stem, limit=60)
    tool_calls = [e for e in events if e.get("kind") == "tool_call"]
    tool_results = [e for e in events if e.get("kind") == "tool_result"]
    console.print()
    console.print(f"[bold #c77dff]trace[/] · thread [cyan]{files[-1].stem}[/] · {len(events)} events")
    if not tool_calls:
        console.print("[dim]no tool calls in recent turns[/]")
    for tc in tool_calls[-10:]:
        name = tc.get("name", "?")
        args = tc.get("args", {})
        arg_preview = ", ".join(f"{k}={str(v)[:40]}" for k, v in args.items())
        console.print(f"  [#b23bf2]✦[/] [cyan]{name}[/]  [dim]{arg_preview}[/]")
    if tool_results:
        console.print(f"[dim]  …{len(tool_results)} tool results observed[/]")
    console.print()


def _handle_dangerous(args: list[str], console: Console) -> None:
    target = (args[0].lower() if args else None)
    current = os.environ.get("NEXUS_ALLOW_DANGEROUS") == "1"
    if target == "on":
        os.environ["NEXUS_ALLOW_DANGEROUS"] = "1"
        console.print("[bold red]DANGEROUS OPS UNLOCKED[/] · run_command will execute destructive patterns.")
        console.print("[dim]disable with /dangerous off · lasts until session end[/]")
    elif target == "off":
        os.environ.pop("NEXUS_ALLOW_DANGEROUS", None)
        console.print("[#7cffb0]guard restored[/] · destructive patterns blocked")
    else:
        state = "[red]UNLOCKED[/]" if current else "[#7cffb0]guarded[/]"
        console.print(f"destructive ops: {state} · /dangerous on|off to toggle")


def _handle_paste(console: Console) -> str:
    """Open the user's $EDITOR (or notepad on Windows) and return what they saved."""
    import subprocess
    import tempfile

    editor = os.environ.get("EDITOR") or ("notepad" if os.name == "nt" else "nano")
    with tempfile.NamedTemporaryFile(
        mode="w+", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        path = f.name
    try:
        subprocess.run([editor, path])
        with open(path, "r", encoding="utf-8") as f:
            body = f.read().strip()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if not body:
        console.print("[dim]paste cancelled (empty)[/]")
        return ""
    console.print(f"[dim]paste loaded · {len(body)} chars, {body.count(chr(10))+1} lines[/]")
    return body


def _handle_skills(console: Console) -> None:
    from nexus.skills import SkillRegistry

    reg = SkillRegistry()
    reg.load_all()
    console.print()
    console.print(
        f"[bold #c77dff]skills[/]  total={reg.count()}  avg_conf={reg.stats()['avg_confidence']}"
    )
    for s in sorted(reg.all(), key=lambda x: x.id):
        origin = {"seed": "·", "self_written": "★", "mesh": "◆"}.get(s.origin, "·")
        console.print(f"  [dim]{origin}[/] [cyan]{s.id:22s}[/] {s.description[:70]}")
    console.print()


def _handle_reflect(console: Console) -> None:
    from nexus.reflect import reflect as _reflect

    console.print("[dim]reflecting on recent turns…[/]")
    rep = _reflect(n_turns=40, apply=False, remember_facts=False)
    console.print(f"[bold #c77dff]reflect[/] · {rep.turns_reviewed} turns reviewed")
    for t in rep.themes:
        console.print(f"  · theme: {t}")
    for f in rep.facts_to_remember:
        console.print(f"  · fact: {f}")
    for n in rep.notes:
        console.print(f"  [dim]note: {n}[/]")
    console.print()


def _handle_evolve(args: list[str], console: Console) -> None:
    from nexus.skills.evolve import evolve_from_router_gap

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


# ---------- main loop ----------


def run_repl(*, console: Console, thread: str = "default") -> None:
    from nexus.agent import Oracle
    from nexus.onboarding import is_onboarded

    render_banner(
        console=console,
        model=settings.oracle_primary_model,
        device=settings.oracle_device_name,
        version=__version__,
        instance=getattr(settings, "oracle_instance", "Nexus"),
    )

    oracle = Oracle(thread_id=thread)
    session = _build_session()

    # First-run orientation (§23) — non-blocking invite, not a forced intake.
    if not is_onboarded():
        console.print(
            "[dim]first run detected · I am Trinity Nexus. type[/] [#c77dff]/onboard[/] "
            "[dim]to orient me, or just start talking.[/]\n"
        )

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
                        instance=getattr(settings, "oracle_instance", "Nexus"),
                    )
                    continue
                if cmd == "/memory":
                    _handle_memory(args, console)
                    continue
                if cmd == "/mode":
                    _handle_mode(args, console)
                    continue
                if cmd == "/onboard":
                    _handle_onboard(console)
                    continue
                if cmd in {"/user-map", "/user_map", "/usermap"}:
                    _handle_user_map(console)
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
                if cmd == "/spawn":
                    _handle_spawn(args, console)
                    continue
                if cmd == "/dangerous":
                    _handle_dangerous(args, console)
                    continue
                if cmd in {"/permissions", "/perm", "/perms"}:
                    _handle_permissions(args, console)
                    continue
                if cmd in {"/allow", "/deny"} and len(args) >= 2:
                    from nexus import permissions as _p
                    tool, pattern = args[0], " ".join(args[1:])
                    (_p.allow if cmd == "/allow" else _p.deny)(tool, pattern)
                    console.print(
                        f"[#7cffb0]{cmd.lstrip('/')}[/] {tool}:{pattern}"
                    )
                    continue
                if cmd == "/trace":
                    _handle_trace(console)
                    continue
                if cmd == "/paste":
                    pasted = _handle_paste(console)
                    if pasted:
                        user_in = pasted  # fall through to chat turn
                    else:
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
                if cmd != "/paste":  # /paste already fell through
                    console.print(f"[yellow]unknown command: {cmd}[/]  try /help")
                    continue

            t0 = time.perf_counter()
            _stream_answer(oracle, user_in, console)
            console.print(f"[dim]({time.perf_counter() - t0:.1f}s)[/]\n")
    finally:
        _hooks.run("pre_exit", {"thread": oracle.thread_id})
        oracle.close()

    console.print("\n[dim]session ended.[/]")
