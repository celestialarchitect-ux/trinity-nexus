"""Trinity Nexus REPL.

Default experience when the user types `nexus`. Renders the neon-purple
banner, prompt-toolkit input with Shift+Enter multiline, slash commands
for every constitutional surface (§04 onboarding, §13 modes, §06 9-tier
memory, §19 subagents, §29 dangerous-op gate), and Claude-Code-style
streaming with esoteric thinking verbs.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion, PathCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.text import Text as RichText

from nexus import __version__
from nexus import hooks as _hooks
from nexus.banner import render_banner
from nexus.config import settings
from nexus.thinking import Thinking


HISTORY_PATH = Path.home() / ".nexus_history"


SLASH_COMMANDS = [
    "/help", "/status", "/exit", "/quit",
    "/onboard", "/user-map",
    "/mode", "/memory", "/skills", "/cost", "/rate",
    "/plan", "/execute", "/compact", "/rewind",
    "/sessions", "/resume", "/reset", "/thread",
    "/reflect", "/evolve", "/spawn", "/trace",
    "/frontier", "/model",
    "/dangerous", "/safe", "/readonly", "/encrypt",
    "/permissions", "/allow", "/deny",
    "/paste", "/clear",
]


SHORTCUTS_TEXT = """\
**keyboard shortcuts**

  Enter            send message
  Shift+Enter      insert newline (multi-line message)
  Tab              autocomplete slash command or file path
  ?                show this shortcuts reference
  Ctrl+C           cancel current turn (press again to exit)
  Ctrl+D           exit
  Up / Down        history

**input prefixes**

  /command         slash command (see /help)
  @path/to/file    attach file contents to your message
  !shell command   run shell, result injected (bypasses agent decision)
  #note to save    quick-add to archival memory, no agent round-trip

Most commands also have CLI equivalents: `nexus ask`, `nexus frontier test`,
`nexus doctor`, etc. Run `nexus --help` to see the full CLI.
"""


class _NexusCompleter(Completer):
    """Tab-complete slash commands and @path references."""

    def __init__(self):
        self._path = PathCompleter(expanduser=True)

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        # slash-command completion at start of line
        if text.startswith("/") and " " not in text:
            for cmd in SLASH_COMMANDS:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))
            return
        # @path completion — delegate to PathCompleter on the fragment
        at_idx = text.rfind("@")
        if at_idx >= 0 and (at_idx == 0 or text[at_idx - 1] in " \t\n"):
            fragment = text[at_idx + 1:]
            from prompt_toolkit.document import Document
            sub = Document(fragment, cursor_position=len(fragment))
            for c in self._path.get_completions(sub, complete_event):
                yield Completion(
                    c.text, start_position=c.start_position,
                )


HELP_TEXT = """\
**commands** (§04/§13/§06/§19/§29)

  /help                show this help
  /status              one-glance current setup (thread, model, mode,
                       backends, security, cost)
  /config [show|get|set|edit]
                       inspect or edit .env settings inline
  /replay <thread>     re-run a past session's user turns against
                       current model (side-by-side comparison)
  /graph <entity> [depth]     BFS through the personal knowledge graph
  /graph ingest [thread_id]   extract triples from a thread
  /code-agent <task>   run smolagents-style code-writing agent loop
                       (model writes Python that calls the tools)
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
  /readonly [on|off]   total read-only — zero mutation tools
  /rate                show per-minute rate-limit status
  /encrypt [status|unlock|setup <passphrase>]
                       at-rest encryption for protected tier (§06.7)
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


def _bottom_toolbar_factory(get_state):
    """Return a callable prompt-toolkit uses to render the bottom status bar."""
    def render():
        try:
            state = get_state()
        except Exception:
            return ""
        parts = [
            f"  {state['instance']}",
            f"model {state['model']}",
            f"mode {state['mode'] or 'free'}",
            f"thread {state['thread']}",
        ]
        ctx_pct = state.get("ctx_pct")
        if ctx_pct is not None:
            color = ""  # can't style plain-text toolbar easily
            parts.append(f"ctx {ctx_pct:.0f}%")
        if state.get("safe"):
            parts.append("SAFE")
        if state.get("readonly"):
            parts.append("READONLY")
        if state.get("dangerous"):
            parts.append("DANGEROUS")
        if state.get("cost_usd", 0.0) > 0:
            parts.append(f"${state['cost_usd']:.3f}")
        parts.append("? shortcuts · Tab complete · Ctrl+C cancel")
        return "  ·  ".join(parts)
    return render


def _build_session(get_state=None) -> PromptSession | None:
    """prompt-toolkit session if possible; None = caller falls back to input()."""
    try:
        bindings = KeyBindings()

        @bindings.add(Keys.Escape, Keys.Enter)
        def _(event):
            event.current_buffer.insert_text("\n")

        kwargs = dict(
            history=FileHistory(str(HISTORY_PATH)),
            enable_history_search=True,
            mouse_support=False,
            multiline=False,
            key_bindings=bindings,
            completer=_NexusCompleter(),
            complete_while_typing=False,
        )
        if get_state is not None:
            kwargs["bottom_toolbar"] = _bottom_toolbar_factory(get_state)
        return PromptSession(**kwargs)
    except Exception:
        return None


_SESSION_BROKEN = False  # set to True after prompt-toolkit crashes mid-session


def _read_line(session: PromptSession | None, console: Console) -> str:
    """Unified input — prompt-toolkit where available, stdlib input() elsewhere.

    Returns the user's line. Propagates EOFError / KeyboardInterrupt so the
    caller can decide (break vs continue). Any other error in prompt-toolkit
    permanently switches the session over to input() for the rest of the run.
    """
    global _SESSION_BROKEN
    if session is not None and not _SESSION_BROKEN:
        try:
            return session.prompt("❯ ", multiline=False)
        except (EOFError, KeyboardInterrupt):
            raise
        except Exception as e:
            console.print(
                f"[dim](prompt crashed: {type(e).__name__}: {e} — falling back to plain input)[/]"
            )
            _SESSION_BROKEN = True

    try:
        return input("❯ ")
    except UnicodeDecodeError:
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


def _expand_attachments(line: str, console: Console) -> str:
    """Replace @path tokens with file contents inline so the agent sees them.

    A token is a whitespace-separated word starting with @ whose rest is a
    path. Missing files are left in place with a warning; they won't crash
    the turn. Large files are truncated with a note.
    """
    import re as _re
    from pathlib import Path as _P

    MAX_ATTACH_BYTES = 64_000

    def _sub(m):
        p = m.group(1)
        path = _P(p).expanduser()
        if not path.is_absolute():
            path = (_P.cwd() / path).resolve()
        if not path.exists():
            console.print(f"[yellow]@{p}: not found[/]")
            return f"@{p}"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            console.print(f"[yellow]@{p}: {e}[/]")
            return f"@{p}"
        if len(text.encode("utf-8", errors="ignore")) > MAX_ATTACH_BYTES:
            text = text[:MAX_ATTACH_BYTES] + "\n…[truncated]"
        console.print(f"[dim]attached @{p} ({len(text):,} chars)[/]")
        return f"\n\n<FILE path={path}>\n{text}\n</FILE>\n\n"

    return _re.sub(r"(?:^|(?<=\s))@(\S+)", _sub, line)


def _condense_tool_result(content: str) -> str:
    if not content:
        return "(no output)"
    one = " ".join(content.split())
    return one[:160] + ("…" if len(one) > 160 else "")


def _echo_user_message(console: Console, text: str) -> None:
    """Render the user's message as a purple-accented panel right after send.

    Skips hidden-prefix messages (attachments expanded inline are noisy) and
    collapses multi-line pastes to the first few lines + a line count.
    """
    preview = text.strip()
    # If there's an expanded file block, show the raw user line not the
    # attached content (which already got announced via "attached @...")
    if "<FILE path=" in preview:
        preview = preview.split("<FILE", 1)[0].rstrip()
        if not preview:
            return
    lines = preview.splitlines()
    if len(lines) > 6:
        preview = "\n".join(lines[:6]) + f"\n… ({len(lines)} lines total)"

    panel = Panel(
        RichText(preview, style="#e8d4ff"),
        border_style="#c77dff",
        padding=(0, 1),
        expand=False,
    )
    console.print(panel)


def _render_diff(console: Console, d: dict) -> None:
    """Print a colorized unified diff for a recorded file mutation."""
    import difflib as _dl
    from pathlib import Path as _P

    path = d["path"]
    rel = path
    try:
        rel = str(_P(path).resolve().relative_to(_P.cwd()))
    except Exception:
        pass

    diff_lines = list(_dl.unified_diff(
        d["before"].splitlines(keepends=True),
        d["after"].splitlines(keepends=True),
        fromfile=f"a/{rel}",
        tofile=f"b/{rel}",
        n=3,
    ))
    if not diff_lines:
        console.print(f"  [#7cffb0]✓[/] [dim]{d['action']} {rel} (no change)[/]")
        return

    # Trim giant diffs
    MAX_DIFF_LINES = 120
    trimmed = False
    if len(diff_lines) > MAX_DIFF_LINES:
        diff_lines = diff_lines[:MAX_DIFF_LINES]
        trimmed = True

    body = RichText()
    for line in diff_lines:
        line = line.rstrip("\n")
        if line.startswith("+++") or line.startswith("---"):
            body.append(line + "\n", style="dim")
        elif line.startswith("@@"):
            body.append(line + "\n", style="#c77dff")
        elif line.startswith("+"):
            body.append(line + "\n", style="#7cffb0")
        elif line.startswith("-"):
            body.append(line + "\n", style="#ff6a6a")
        else:
            body.append(line + "\n", style="dim")
    if trimmed:
        body.append(f"…[diff truncated at {MAX_DIFF_LINES} lines]\n", style="dim")

    title = f"{d['action']} · {rel}"
    panel = Panel(body, title=title, border_style="#9d00ff", padding=(0, 1), expand=False)
    console.print(panel)


def _render_error(console: Console, *, where: str, err: BaseException) -> None:
    body = RichText()
    body.append(f"{type(err).__name__}: {err}\n", style="#ff6a6a")
    body.append("REPL is fine — keep going, /help for commands, /exit to leave.", style="dim")
    panel = Panel(body, title=f"error · {where}", border_style="#ff6a6a", padding=(0, 1), expand=False)
    console.print(panel)


def _render_turn_separator(console: Console) -> None:
    console.print(Rule(style="dim #3a2a5a"))


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
                    tool_name = evt.get("name", "")
                    thinking.pause()
                    # Real diff rendering for file mutations (§17 + Claude-Code parity)
                    from nexus.tools import pop_recent_diff as _pop
                    if tool_name in {"edit_file", "apply_diff", "write_file"}:
                        d = _pop()
                        if d is not None:
                            _render_diff(console, d)
                        else:
                            console.print(f"  [#7cffb0]✓[/] [dim]{_condense_tool_result(content_preview)}[/]")
                    else:
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
                        # code-theme="monokai" gives readable syntax highlighting
                        # in streamed code blocks; ▋ is a typing-cursor suffix.
                        live = Live(
                            Markdown(final_text + " ▋", code_theme="monokai"),
                            console=console,
                            refresh_per_second=15,
                            vertical_overflow="visible",
                        )
                        live.__enter__()
                    else:
                        final_text += chunk
                        if live is not None:
                            live.update(Markdown(final_text + " ▋", code_theme="monokai"))
                elif t == "final":
                    # Drop the typing cursor from the final frame.
                    if live is not None and final_text:
                        live.update(Markdown(final_text, code_theme="monokai"))
                    # If the whole answer came through a non-streaming path
                    # (no `token` events), render it now.
                    elif not shown_first_text and evt.get("text"):
                        if thinking is not None:
                            thinking.pause()
                            thinking = None
                        final_text = evt["text"]
                        console.print(Markdown(final_text, code_theme="monokai"))
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


def _handle_config(args: list[str], console: Console) -> None:
    """/config [show|get KEY|set KEY=VAL|edit]"""
    import os as _os
    from pathlib import Path as _P

    env_path = _P(settings.oracle_home).parent / ".env"
    if not env_path.exists():
        # settings.oracle_home is <repo>/data by default; .env is next to it
        from nexus import config as _c
        cand = _P(_c.__file__).resolve().parents[2] / ".env"
        if cand.exists():
            env_path = cand

    if not args or args[0] == "show":
        if not env_path.exists():
            console.print("[yellow]no .env found[/]")
            return
        from nexus.security import redact
        body = redact(env_path.read_text(encoding="utf-8"))
        console.print(Markdown(f"```env\n{body}\n```"))
        console.print(f"[dim]file: {env_path}[/]")
        return

    sub = args[0].lower()
    if sub == "edit":
        import subprocess as _sp
        editor = _os.environ.get("EDITOR") or ("notepad" if _os.name == "nt" else "nano")
        _sp.run([editor, str(env_path)])
        console.print("[dim]saved. restart nexus (or the setting's reader) for changes to take effect.[/]")
        return

    if sub == "get" and len(args) >= 2:
        key = args[1]
        val = _os.environ.get(key, "<unset>")
        from nexus.security import redact
        console.print(f"[cyan]{key}[/] = {redact(val)}")
        return

    if sub == "set" and len(args) >= 2:
        expr = " ".join(args[1:])
        if "=" not in expr:
            console.print("[yellow]usage: /config set KEY=VAL[/]")
            return
        key, _, val = expr.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        # Update env for this process
        _os.environ[key] = val
        # Persist to .env
        try:
            lines: list[str] = []
            found = False
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith(f"{key}="):
                        lines.append(f"{key}={val}")
                        found = True
                    else:
                        lines.append(line)
            if not found:
                lines.append(f"{key}={val}")
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            console.print(f"[#7cffb0]set[/] {key} (persisted to {env_path.name})")
        except Exception as e:
            console.print(f"[yellow]set in-process only · persist failed: {e}[/]")
        return

    console.print("[yellow]usage: /config [show|get KEY|set KEY=VAL|edit][/]")


def _handle_status(console: Console, thread: str) -> None:
    """/status — one-glance Claude-Code-style summary of current setup."""
    import os as _os

    from nexus import cost as _cost
    from nexus import modes as _modes
    from nexus.runtime import available_backends
    from nexus.security import is_readonly, is_safe_mode, rate_status

    active = _modes.get_active()
    backends = available_backends()
    session_cost = _cost.session_total(thread)
    rs = rate_status()

    console.print()
    console.print("[bold #00ff88]Trinity Nexus[/] · status\n")
    console.print(f"  thread:   [cyan]{thread}[/]")
    console.print(f"  model:    [cyan]{settings.oracle_primary_model}[/]  "
                  f"[dim](fast: {settings.oracle_fast_model} · embed: {settings.oracle_embed_model})[/]")
    console.print(f"  instance: [cyan]{getattr(settings, 'oracle_instance', 'Nexus')}[/]")
    console.print(f"  cwd:      {_os.getcwd()}")
    console.print(f"  mode:     [cyan]{active.name if active else 'none'}[/]")
    console.print()
    console.print("  [bold]backends[/]")
    for b, ok in backends.items():
        m = "[#7cffb0]●[/]" if ok else "[dim]○[/]"
        console.print(f"    {m} {b}")
    console.print()
    console.print("  [bold]security[/]")
    console.print(f"    safe:      {'[#7cffb0]on[/]' if is_safe_mode() else '[dim]off[/]'}")
    console.print(f"    readonly:  {'[#7cffb0]on[/]' if is_readonly() else '[dim]off[/]'}")
    console.print(f"    dangerous: "
                  f"{'[red]unlocked[/]' if _os.environ.get('NEXUS_ALLOW_DANGEROUS') == '1' else '[#7cffb0]guarded[/]'}")
    console.print(f"    rate:      tools {rs['tools_remaining_this_min']}/{rs['tools_limit']}  ·  "
                  f"llm {rs['llm_remaining_this_min']}/{rs['llm_limit']}")
    console.print()
    console.print("  [bold]session cost[/]")
    console.print(f"    calls: {session_cost['calls']}  ·  "
                  f"tokens: {session_cost['prompt_tokens']:,}+{session_cost['completion_tokens']:,}  ·  "
                  f"${session_cost['usd']:.4f}")
    console.print()


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
    """/sessions — list past threads with titles."""
    from nexus import sessions as _s

    threads = _s.list_threads()
    if not threads:
        console.print("[dim]no recorded sessions yet[/]")
        return
    console.print()
    console.print(f"[bold #c77dff]sessions[/] · {len(threads)}")
    for tid in threads[-30:]:
        title = _s.get_title(tid) or ""
        # Grab the first user line if no title
        if not title:
            events = _s.read_thread(tid, limit=5)
            for e in events:
                if e.get("kind") == "user":
                    title = str(e.get("content", ""))[:60].splitlines()[0]
                    break
        console.print(f"  [cyan]{tid:32s}[/]  [dim]{title}[/]")
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


def _handle_readonly(args: list[str], console: Console) -> None:
    """/readonly [on|off] — kill all mutation tools (§29)."""
    target = (args[0].lower() if args else None)
    current = os.environ.get("NEXUS_READONLY") == "1"
    if target == "on":
        os.environ["NEXUS_READONLY"] = "1"
        console.print("[bold #7cffb0]READ-ONLY ON[/] · no write_file / edit / run_command · reads OK")
    elif target == "off":
        os.environ.pop("NEXUS_READONLY", None)
        console.print("[#c77dff]read-only OFF[/] · write tools restored")
    else:
        state = "[#7cffb0]ON[/]" if current else "[dim]off[/]"
        console.print(f"read-only mode: {state} · /readonly on|off to toggle")


def _handle_rate(console: Console) -> None:
    """/rate — show current per-minute rate-limit status."""
    from nexus.security import rate_status

    s = rate_status()
    console.print()
    console.print("[bold #c77dff]rate limits[/]  (per minute, sliding window)")
    console.print(f"  tools: [cyan]{s['tools_remaining_this_min']}[/] / {s['tools_limit']} remaining")
    console.print(f"  llm  : [cyan]{s['llm_remaining_this_min']}[/] / {s['llm_limit']} remaining")
    console.print()
    console.print("[dim]tune via NEXUS_RATE_TOOLS_PER_MIN / NEXUS_RATE_LLM_PER_MIN[/]")


def _handle_encrypt(args: list[str], console: Console) -> None:
    """/encrypt [status|unlock <passphrase>|setup] — at-rest encryption for
    protected tier (§06.7)."""
    from nexus import security as _sec

    sub = (args[0].lower() if args else "status")
    if sub == "status":
        state = "[#7cffb0]unlocked[/]" if _sec.is_unlocked() else "[dim]locked[/]"
        console.print(f"encryption: {state}")
        console.print("[dim]commands:[/]")
        console.print("[dim]  /encrypt unlock <passphrase>   derive key + verify[/]")
        console.print("[dim]  /encrypt setup <passphrase>    first-time setup[/]")
        return
    if sub in {"unlock", "setup"} and len(args) >= 2:
        passphrase = " ".join(args[1:])
        ok = _sec.unlock_session(passphrase)
        if ok:
            console.print("[#7cffb0]session unlocked[/] · encrypted tiers readable this session")
        else:
            console.print("[red]wrong passphrase[/] · probe decryption failed")
    else:
        console.print("[yellow]usage: /encrypt [status|unlock <passphrase>][/]")


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

    # State accessor for the bottom status toolbar. Captured by closure so
    # it reflects the current thread / mode / flags every render.
    def _state():
        import os as _os
        from nexus import cost as _cost
        from nexus import sessions as _sess
        from nexus.modes import get_active as _active_mode
        m = _active_mode()
        c = _cost.session_total(thread)
        # Rough ctx-usage estimate: count chars in recent session events vs num_ctx*4 (4 chars/token heuristic).
        ctx_pct = None
        try:
            events = _sess.read_thread(thread, limit=80)
            used_chars = sum(len(str(e.get("content", ""))) for e in events)
            budget_chars = settings.oracle_num_ctx * 4
            ctx_pct = min(100.0, 100.0 * used_chars / max(1, budget_chars))
        except Exception:
            pass
        return {
            "instance": getattr(settings, "oracle_instance", "Nexus"),
            "model": settings.oracle_primary_model,
            "mode": m.name if m else None,
            "thread": thread,
            "ctx_pct": ctx_pct,
            "safe": _os.environ.get("NEXUS_SAFE") == "1",
            "readonly": _os.environ.get("NEXUS_READONLY") == "1",
            "dangerous": _os.environ.get("NEXUS_ALLOW_DANGEROUS") == "1",
            "cost_usd": c["usd"],
        }

    session = _build_session(get_state=_state)
    if session is None:
        console.print(
            "[dim](prompt-toolkit unavailable in this shell — plain input mode. "
            "No Tab-complete, no Shift+Enter, no status bar. /paste still works.)[/]\n"
        )

    # Double-Ctrl+C tracker
    _last_ctrl_c = [0.0]

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
                now = time.time()
                if now - _last_ctrl_c[0] < 2.0:
                    console.print("[dim]goodbye.[/]")
                    break
                _last_ctrl_c[0] = now
                console.print("[dim](ctrl-c once more within 2s to exit · /exit also works)[/]")
                continue
            except EOFError:
                break

            if not user_in:
                continue

            # ? → shortcuts reference
            if user_in in {"?", "/?", "/shortcuts"}:
                console.print(Markdown(SHORTCUTS_TEXT))
                continue

            # !<shell cmd> → bash passthrough, no agent round-trip
            if user_in.startswith("!"):
                cmd = user_in[1:].strip()
                if not cmd:
                    console.print("[yellow]usage: !<shell command>[/]")
                    continue
                try:
                    from nexus.tools import run_command as _rc
                    r = _rc.invoke({"command": cmd, "timeout_sec": 30})
                    if r.get("stdout"):
                        console.print(r["stdout"])
                    if r.get("stderr"):
                        console.print(f"[yellow]{r['stderr']}[/]")
                    console.print(f"[dim]rc={r['returncode']}[/]\n")
                except Exception as e:
                    console.print(f"[red]shell failed[/] {type(e).__name__}: {e}")
                continue

            # #<text> → quick-add to archival memory
            if user_in.startswith("#"):
                fact = user_in[1:].strip()
                if not fact:
                    console.print("[yellow]usage: #<fact to remember>[/]")
                    continue
                try:
                    from nexus.memory import MemoryTiers
                    mid = MemoryTiers().remember(fact, tags=["repl"], source="hash")
                    console.print(f"[#c77dff]remembered[/] id={mid[:8]}  {fact[:80]}")
                except Exception as e:
                    console.print(f"[red]remember failed[/] {e}")
                continue

            # @path → attach file contents to the next message
            if user_in.startswith("@") or " @" in " " + user_in:
                user_in = _expand_attachments(user_in, console)
                if not user_in:
                    continue

            if user_in.startswith("/"):
              try:
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
                if cmd == "/readonly":
                    _handle_readonly(args, console)
                    continue
                if cmd == "/rate":
                    _handle_rate(console)
                    continue
                if cmd == "/encrypt":
                    _handle_encrypt(args, console)
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
                if cmd in {"/code-agent", "/code_agent", "/codeagent"}:
                    from nexus import code_agent as _ca
                    task_text = " ".join(args) if args else ""
                    if not task_text:
                        console.print("[yellow]usage: /code-agent <task>[/]")
                        continue
                    console.print(f"[dim]code-agent: {task_text}[/]")
                    with Thinking(console) as th:
                        th.set_verb("Weaving")
                        res = _ca.run(task_text, max_iterations=5)
                    for step, act in enumerate(res.actions, 1):
                        console.print(f"[dim]--- step {step} ---[/]")
                        console.print(Syntax(act["code"], "python", theme="monokai", line_numbers=False))
                        if act.get("stdout"):
                            console.print(f"[dim]stdout:[/] {act['stdout'][:500]}")
                        if act.get("error"):
                            console.print(f"[red]error:[/] {act['error'][:500]}")
                    if res.final:
                        console.print(Panel(Markdown(res.final, code_theme="monokai"),
                                             title="final", border_style="#9d00ff"))
                    continue
                if cmd == "/graph":
                    from nexus import graph as _g
                    if not args:
                        console.print_json(json.dumps(_g.stats()))
                        console.print("[dim]/graph <entity> [depth]  /graph ingest[/]")
                    elif args[0] == "ingest":
                        tid = args[1] if len(args) > 1 else thread
                        console.print(f"[dim]ingesting {tid}…[/]")
                        r = _g.ingest_thread(tid)
                        console.print_json(json.dumps(r))
                    else:
                        ent = args[0]
                        depth = int(args[1]) if len(args) > 1 and args[1].isdigit() else 2
                        r = _g.query(ent, depth=depth)
                        if r["matches"] == 0:
                            console.print(f"[yellow]no entity like {ent!r}[/]")
                        else:
                            console.print(f"[bold #c77dff]{r['entity']}[/] · "
                                          f"{len(r['neighbors'])} neighbors")
                            for e in r["edges"][:20]:
                                console.print(
                                    f"  [cyan]{e['from']}[/] "
                                    f"[dim]—{e['kind']}→[/] [cyan]{e['to']}[/]"
                                )
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
                if cmd == "/status":
                    _handle_status(console, thread)
                    continue
                if cmd == "/config":
                    _handle_config(args, console)
                    continue
                if cmd == "/replay":
                    if not args:
                        console.print("[yellow]usage: /replay <thread_id>[/]")
                    else:
                        # Delegate to the CLI command logic
                        try:
                            from nexus.sessions import read_thread
                            from nexus.agent import Oracle as _O
                            tid = args[0]
                            events = read_thread(tid, limit=120)
                            turns = [e for e in events if e.get("kind") == "user"][:20]
                            if not turns:
                                console.print(f"[yellow]no user turns in {tid}[/]")
                            else:
                                new_t = f"replay-{tid}-{int(time.time())}"
                                sub = _O(thread_id=new_t)
                                try:
                                    for i, t in enumerate(turns, 1):
                                        p = str(t.get("content", ""))[:1000]
                                        console.print(f"[dim]--- {i}/{len(turns)} ---[/] [cyan]{p[:120]}[/]")
                                        sub.ask(p)
                                finally:
                                    sub.close()
                                console.print(f"[#7cffb0]replay done[/] → thread [cyan]{new_t}[/]")
                        except Exception as e:
                            console.print(f"[red]replay failed[/] {e}")
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
              except Exception as e:
                _render_error(console, where=f"command {cmd}", err=e)
                try:
                    from nexus import security as _sec
                    _sec.audit("slash_failed", cmd=cmd, error=f"{type(e).__name__}: {e}")
                except Exception:
                    pass
                continue

            # Echo the user's message in a styled panel (Claude-Code-style).
            _echo_user_message(console, user_in)

            # Auto-title the session on the first real user turn.
            try:
                from nexus import sessions as _sessions_mod
                from nexus.config import settings as _s
                if _sessions_mod.get_title(thread) is None:
                    _sessions_mod.ensure_title(thread, user_in, _s.oracle_fast_model)
            except Exception:
                pass

            # Chat turn — §31: catch any stream / tool / render error so
            # one bad turn never exits the REPL.
            t0 = time.perf_counter()
            try:
                _stream_answer(oracle, user_in, console)
                dt = time.perf_counter() - t0
                console.print(f"[dim]  {dt:.1f}s[/]")
                _render_turn_separator(console)
            except KeyboardInterrupt:
                console.print("\n[dim](stream interrupted · type /exit to leave)[/]")
                _render_turn_separator(console)
            except Exception as e:
                import traceback as _tb
                _render_error(console, where="turn", err=e)
                _render_turn_separator(console)
                try:
                    from nexus import security as _sec
                    _sec.audit("turn_failed", error=f"{type(e).__name__}: {e}",
                               traceback=_tb.format_exc()[:4000])
                except Exception:
                    pass
    finally:
        _hooks.run("pre_exit", {"thread": oracle.thread_id})
        oracle.close()

    console.print("\n[dim]session ended.[/]")
