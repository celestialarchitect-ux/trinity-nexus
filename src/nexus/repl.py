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
  /safe [on|off]       hard lockdown: no run_command, write globs only
  /permissions [list|allow <tool> <p>|deny <tool> <p>|remove <t> <p>]
                       per-tool glob permissions (§29)
  /allow <tool> <pat>  shortcut: allow tool:pattern
  /deny <tool> <pat>   shortcut: deny tool:pattern
  /trace               show tool calls + memory tiers used recently
  /model [list|<id>]   show or swap the primary model (session)
  /frontier [test|<provider> [model] [key=...]]
                       configure OpenAI-compat frontier backend
                       providers: openrouter, openai, deepseek, groq,
                                  together, fireworks, xai, mistral
  /cost                session + daily token/spend totals
  /plan <intent>       draft an ordered task plan (§09 / §13 orchestrator)
  /execute             run the next pending task in the active plan
  /compact [N]         summarize old turns into the 'threads' memory tier
  /rewind [N]          drop the last N agent turns
  /sessions            list recorded threads
  /resume <thread_id>  jump back into a past thread
  /paste               open $EDITOR / notepad for a big multi-line prompt
  /reset               new thread (memory kept, chat context dropped)
  /thread [id]         show or switch thread
  /clear               clear screen, redraw banner
  /exit                leave (Ctrl-D works too)

type anything else to talk to Trinity Nexus.
shift+enter = newline · enter = submit
"""


def _build_session() -> PromptSession | None:
    """prompt-toolkit session if possible; None = caller falls back to input().

    prompt-toolkit's Windows backend (Win32Output) requires a real Windows
    console — it raises NoConsoleScreenBufferError in Git Bash / MSYS / Cygwin
    which would crash the REPL on startup. We return None in that case so the
    main loop can use stdlib `input()` instead.
    """
    try:
        bindings = KeyBindings()

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
    except Exception:
        return None


def _read_line(session: PromptSession | None, console: Console) -> str:
    """Unified input — prompt-toolkit where available, stdlib input() elsewhere.

    Returns the user's line, or raises EOFError / KeyboardInterrupt as usual.
    """
    if session is not None:
        return session.prompt("❯ ", multiline=False)
    # Fallback: plain input(). No per-char key bindings, but works in every shell.
    try:
        return input("❯ ")
    except UnicodeDecodeError:
        # Some consoles emit non-UTF-8 bytes on certain paste events
        return ""


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
                    content_preview = evt.get("content", "")
                    thinking.pause()
                    console.print(
                        f"  [dim]⎿[/] [dim]{_condense_tool_result(content_preview)}[/]"
                    )
                    _hooks.run("post_tool", {"content": content_preview[:2000]})
                    # §31 Failure Recovery / self-heal hint: if the tool
                    # returned an obvious error, nudge the agent to adjust.
                    low = content_preview.lower()
                    if any(
                        marker in low
                        for marker in ("error:", "traceback", "not found", "permission denied", "timeout")
                    ):
                        thinking.set_verb("Recovering")
                    else:
                        thinking.resume(verb="Receiving")
                        continue
                    thinking.resume()
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


def _handle_cost(console: Console, thread: str) -> None:
    """/cost — session + daily token/spend summary."""
    from nexus import cost as _cost

    session = _cost.session_total(thread)
    day = _cost.daily_total()
    console.print()
    console.print("[bold #c77dff]cost ledger[/]")
    console.print(
        f"  session  · {session['calls']} calls · "
        f"{session['prompt_tokens']:,} in + {session['completion_tokens']:,} out · "
        f"${session['usd']:.4f}"
    )
    console.print(
        f"  today    · {day['calls']} calls · "
        f"{day['prompt_tokens']:,} in + {day['completion_tokens']:,} out · "
        f"${day['usd']:.4f}"
    )
    if day["by_model"]:
        console.print("\n  [dim]by model[/]")
        for m, stats in sorted(day["by_model"].items(), key=lambda kv: -kv[1]["usd"]):
            console.print(
                f"    [cyan]{m}[/]  calls={stats['calls']}  "
                f"tok={stats['prompt_tokens']:,}+{stats['completion_tokens']:,}  "
                f"${stats['usd']:.4f}"
            )
    console.print()


def _handle_plan(args: list[str], console: Console, thread: str) -> None:
    """/plan <intent> — draft an ordered task plan without executing."""
    from nexus import plan as _plan

    if not args:
        existing = _plan.load(thread)
        if not existing:
            console.print("[yellow]usage: /plan <intent>[/]  no active plan")
            return
        console.print(f"[bold #c77dff]plan[/]  intent: [cyan]{existing.intent}[/]")
        for i, t in enumerate(existing.tasks, 1):
            mark = {"pending": "○", "done": "●", "failed": "✗", "skipped": "—"}.get(t.status, "?")
            console.print(f"  {mark} [{i}] {t.description}")
        return

    intent = " ".join(args)
    console.print(f"[dim]drafting plan for: {intent}…[/]")
    with Thinking(console) as t:
        t.set_verb("Planning")
        p = _plan.draft(intent, thread)
    console.print(f"[#9d00ff]plan drafted[/] · {len(p.tasks)} tasks")
    for i, task in enumerate(p.tasks, 1):
        console.print(f"  [{i}] {task.description}")
    console.print()
    console.print("[dim]/execute  to run the next pending task · /plan  to re-display[/]")


def _handle_execute(args: list[str], console: Console, oracle, thread: str) -> None:
    """/execute — run the next pending task in the active plan."""
    from nexus import plan as _plan

    p = _plan.load(thread)
    if not p:
        console.print("[yellow]no plan for this thread · /plan <intent> first[/]")
        return
    task = _plan.next_pending(p)
    if not task:
        console.print("[#7cffb0]plan complete[/]")
        return
    console.print(f"[dim]executing [{task.id}][/] {task.description}")
    t0 = time.time()
    try:
        result = _stream_answer(oracle, task.description, console)
        _plan.mark(p, task.id, status="done", result=result, thread_id=thread)
        remaining = len([t for t in p.tasks if t.status == "pending"])
        console.print(f"[#7cffb0]done[/] ({time.time()-t0:.1f}s) · {remaining} pending")
    except Exception as e:
        _plan.mark(p, task.id, status="failed", result=str(e), thread_id=thread)
        console.print(f"[red]failed[/] {e}")


def _handle_compact(args: list[str], console: Console, thread: str) -> None:
    """/compact — summarize old turns into the 'threads' memory tier."""
    from nexus import compaction as _compact

    keep = 10
    if args and args[0].isdigit():
        keep = int(args[0])
    console.print(f"[dim]compacting · keeping last {keep} events…[/]")
    with Thinking(console) as t:
        t.set_verb("Compacting")
        report = _compact.compact(thread, keep_recent=keep)
    if report.get("ok"):
        console.print(
            f"[#7cffb0]compacted[/] · {report['compacted_events']} events → "
            f"{report['summary_chars']} char summary in threads tier"
        )
    else:
        console.print(f"[dim]{report.get('reason', 'nothing to do')}[/]")


def _handle_rewind(args: list[str], console: Console, oracle, thread: str) -> int | None:
    """/rewind N — drop the last N agent turns from LangGraph checkpoints."""
    n = 1
    if args and args[0].isdigit():
        n = int(args[0])
    try:
        cfg = {"configurable": {"thread_id": thread}}
        ckpts = list(oracle.graph.get_state_history(cfg))
        if len(ckpts) <= n:
            console.print(f"[yellow]only {len(ckpts)} checkpoints exist · can't rewind {n}[/]")
            return None
        target = ckpts[n]  # nth back
        oracle.graph.update_state(
            {**cfg, "checkpoint_id": target.config["configurable"]["checkpoint_id"]},
            {},
        )
        console.print(f"[#7cffb0]rewound {n} turn(s)[/]")
    except Exception as e:
        console.print(f"[red]rewind failed[/] {type(e).__name__}: {e}")
    return None


def _handle_sessions(console: Console) -> None:
    """/sessions — list past threads."""
    from nexus import sessions as _s

    threads = _s.list_threads()
    if not threads:
        console.print("[dim]no recorded sessions yet[/]")
        return
    console.print()
    console.print(f"[bold #c77dff]sessions[/] · {len(threads)}")
    for tid in threads[-30:]:
        events = _s.read_thread(tid, limit=1)
        first = events[0] if events else {}
        console.print(f"  [cyan]{tid}[/]  [dim]{first.get('kind', '')}[/]")
    console.print()
    console.print("[dim]/resume <thread_id> to jump back[/]")


def _handle_resume(args: list[str], console: Console) -> str | None:
    """/resume <thread_id> — switch to a past thread."""
    if not args:
        console.print("[yellow]usage: /resume <thread_id>[/]")
        return None
    return args[0]


def _handle_model(args: list[str], console: Console) -> None:
    """/model [list|<model_id>] — show or switch the primary model."""
    import os as _os

    from nexus.runtime import available_backends

    if not args or args[0].lower() == "list":
        console.print()
        console.print("[bold #c77dff]models[/]")
        backends = available_backends()
        console.print(f"  [cyan]primary[/]   {settings.oracle_primary_model}")
        console.print(f"  [cyan]fast[/]      {settings.oracle_fast_model}")
        console.print(f"  [cyan]embed[/]     {settings.oracle_embed_model}")
        console.print()
        console.print("[bold #c77dff]backends[/]")
        for name, avail in backends.items():
            marker = "[#7cffb0]●[/]" if avail else "[dim]○[/]"
            console.print(f"  {marker} {name}")
        front_key = _os.environ.get("NEXUS_FRONTIER_API_KEY")
        front_model = _os.environ.get("NEXUS_FRONTIER_MODEL", "(none set)")
        front_provider = _os.environ.get("NEXUS_FRONTIER_PROVIDER", "(unset — using env base_url)")
        console.print()
        console.print("[bold #c77dff]frontier (via OpenAI-compat)[/]")
        console.print(
            f"  provider   {front_provider}\n"
            f"  model      {front_model}\n"
            f"  key        {'set' if front_key else '[yellow]NOT SET[/]'}"
        )
        console.print()
        console.print("[dim]/model <model_id>     swap primary model for this session[/]")
        console.print("[dim]/frontier <provider> <model>  set frontier provider + default model[/]")
        return

    new_model = args[0]
    _os.environ["ORACLE_PRIMARY_MODEL"] = new_model
    # Reload settings so downstream sees it
    import importlib as _il
    from nexus import config as _c
    _il.reload(_c)
    console.print(f"[#7cffb0]primary model →[/] {new_model}  [dim](this session)[/]")


def _handle_frontier(args: list[str], console: Console) -> None:
    """/frontier [test|<provider> [model] [key=...]]"""
    import os as _os

    if not args:
        console.print("[yellow]usage:[/]")
        console.print("  [dim]/frontier test                     ping the configured provider[/]")
        console.print("  [dim]/frontier <provider> [model] [key=...]   configure[/]")
        console.print(
            "[dim]providers: openrouter, openai, deepseek, groq, together, "
            "fireworks, xai, mistral[/]"
        )
        return

    # /frontier test
    if args[0].lower() == "test":
        from nexus.runtime import get_backend as _gb
        from nexus.runtime.types import ChatRequest as _CR, Message as _M
        import time as _t

        key = _os.environ.get("NEXUS_FRONTIER_PROVIDER") or "frontier"
        be = _gb(key)
        if not be.is_available():
            console.print(
                "[red]frontier unavailable[/] — set NEXUS_FRONTIER_API_KEY first "
                "(via .env or /frontier <provider> key=...)"
            )
            return
        console.print(f"[dim]ping · provider={key} · model={getattr(be, 'default_model', '?')}[/]")
        req = _CR(
            messages=[
                _M(role="system", content="Be terse."),
                _M(role="user", content="Reply in one sentence: what is 2+2?"),
            ],
            model="",
            temperature=0.2,
            num_ctx=4096,
            max_tokens=60,
        )
        t0 = _t.perf_counter()
        try:
            resp = be.chat(req)
        except Exception as e:
            console.print(f"[red]FAIL[/] {type(e).__name__}: {e}")
            return
        dt = _t.perf_counter() - t0
        console.print(f"[#7cffb0]OK[/] {dt:.1f}s · {resp.prompt_tokens}+{resp.completion_tokens} tokens")
        console.print(f"[dim]→[/] {(resp.content or '').strip()[:240]}")
        return

    provider = args[0].lower()
    _os.environ["NEXUS_FRONTIER_PROVIDER"] = provider
    if len(args) >= 2 and not args[1].startswith("key="):
        _os.environ["NEXUS_FRONTIER_MODEL"] = args[1]
    for a in args:
        if a.startswith("key="):
            _os.environ["NEXUS_FRONTIER_API_KEY"] = a.split("=", 1)[1]
    # Clear cached backend so next use picks up new env
    from nexus.runtime import _BACKENDS
    for k in list(_BACKENDS.keys()):
        if k in {"frontier", "openai_compat", provider}:
            _BACKENDS.pop(k, None)
    console.print(
        f"[#7cffb0]frontier →[/] provider={provider} "
        f"model={_os.environ.get('NEXUS_FRONTIER_MODEL', '(preset default)')}"
    )


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


def _handle_safe(args: list[str], console: Console) -> None:
    """/safe [on|off] — hard lockdown (§29). Blocks run_command, restricts writes."""
    target = (args[0].lower() if args else None)
    current = os.environ.get("NEXUS_SAFE") == "1"
    if target == "on":
        os.environ["NEXUS_SAFE"] = "1"
        console.print("[bold #7cffb0]SAFE MODE ON[/] · run_command blocked · "
                      "write_file limited to NEXUS_WRITE_ALLOW globs")
        if not os.environ.get("NEXUS_WRITE_ALLOW"):
            console.print("[dim]  tip: set NEXUS_WRITE_ALLOW in .env to a colon-separated list "
                          "of glob patterns (e.g. /home/you/scratch/**)[/]")
    elif target == "off":
        os.environ.pop("NEXUS_SAFE", None)
        console.print("[#c77dff]safe mode OFF[/] · full tool access restored")
    else:
        state = "[#7cffb0]ON[/]" if current else "[dim]off[/]"
        console.print(f"safe mode: {state} · /safe on|off to toggle")
        console.print("[dim]safe mode blocks run_command entirely and restricts "
                      "writes to NEXUS_WRITE_ALLOW[/]")


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
    if session is None:
        console.print(
            "[dim](prompt-toolkit unavailable in this shell — using plain input. "
            "Shift+Enter newline + history won't work; /paste still will.)[/]\n"
        )

    # First-run orientation (§23) — non-blocking invite, not a forced intake.
    if not is_onboarded():
        console.print(
            "[dim]first run detected · I am Trinity Nexus. type[/] [#c77dff]/onboard[/] "
            "[dim]to orient me, or just start talking.[/]\n"
        )

    try:
        while True:
            try:
                user_in = _read_line(session, console).strip()
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
                if cmd == "/safe":
                    _handle_safe(args, console)
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
                if cmd == "/model":
                    _handle_model(args, console)
                    continue
                if cmd == "/frontier":
                    _handle_frontier(args, console)
                    continue
                if cmd == "/cost":
                    _handle_cost(console, thread)
                    continue
                if cmd == "/plan":
                    _handle_plan(args, console, thread)
                    continue
                if cmd == "/execute":
                    _handle_execute(args, console, oracle, thread)
                    continue
                if cmd == "/compact":
                    _handle_compact(args, console, thread)
                    continue
                if cmd == "/rewind":
                    _handle_rewind(args, console, oracle, thread)
                    continue
                if cmd == "/sessions":
                    _handle_sessions(console)
                    continue
                if cmd == "/resume":
                    new_thread = _handle_resume(args, console)
                    if new_thread:
                        oracle.close()
                        thread = new_thread
                        oracle = Oracle(thread_id=thread)
                        console.print(f"[dim]resumed thread: {thread}[/]")
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
