"""Oracle CLI — terminal-native sovereign AI.

Type `oracle` (no args) to boot the interactive REPL.
"""

from __future__ import annotations

import io
import json
import sys
import time

import click
import httpx
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from nexus import __version__
from nexus.config import settings

# Force UTF-8 on Windows consoles — qwen3 emits arrows/em-dashes that cp1252 chokes on.
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper) and stream.encoding.lower() != "utf-8":
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass

console = Console(soft_wrap=True, legacy_windows=False)


@click.group(invoke_without_command=True)
@click.option("--thread", default=None, help="Thread id for the REPL session (default: resume latest).")
@click.option("--new", "new_thread", is_flag=True, help="Start a fresh thread instead of resuming latest.")
@click.pass_context
def cli(ctx: click.Context, thread: str | None, new_thread: bool):
    """Trinity Nexus — sovereign adaptive intelligence.

    Run without a subcommand to enter the interactive terminal.
    """
    if ctx.invoked_subcommand is None:
        from nexus.repl import run_repl

        if thread is None:
            if new_thread:
                thread = f"thread-{int(time.time())}"
            else:
                # Resume the most-recently-written thread, fall back to default
                try:
                    from nexus.sessions import list_threads
                    from pathlib import Path as _P
                    from nexus.config import settings as _s
                    base = _s.oracle_home / "sessions"
                    if base.exists():
                        files = sorted(base.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
                        if files:
                            thread = files[-1].stem
                except Exception:
                    pass
                if thread is None:
                    thread = "default"

        run_repl(console=console, thread=thread)


@cli.command()
def version():
    """Print Trinity Nexus version."""
    console.print(f"[bold #c77dff]trinity-nexus[/] [dim]v{__version__}[/] [dim](omega foundation)[/]")


@cli.command()
@click.option("--branch", default="main", help="Git branch to pull from.")
def update(branch: str):
    """Pull the latest Oracle from git and reinstall in-place."""
    import subprocess as _sub
    from pathlib import Path as _P
    import sys as _sys

    repo = _P(__file__).resolve().parents[2]
    console.print(f"[dim]updating {repo} from {branch}…[/]")

    def _run(cmd: list[str]) -> int:
        proc = _sub.run(cmd, cwd=str(repo), capture_output=True, text=True)
        if proc.returncode != 0:
            console.print(f"[red]{' '.join(cmd)} failed[/]")
            if proc.stderr:
                console.print(f"[red]{proc.stderr.strip()}[/]")
        elif proc.stdout.strip():
            console.print(f"[dim]{proc.stdout.strip()}[/]")
        return proc.returncode

    if _run(["git", "fetch", "origin", branch]) != 0:
        return
    if _run(["git", "checkout", branch]) != 0:
        return
    if _run(["git", "pull", "--ff-only", "origin", branch]) != 0:
        return
    if _run([_sys.executable, "-m", "pip", "install", "-q", "-e", "."]) != 0:
        return
    console.print("[#7cffb0]oracle updated[/]")


@cli.command()
def doctor():
    """Check the environment: Ollama, models, memory, skills, retrieval."""
    from nexus.memory import MemoryTiers
    from nexus.retrieval import RetrievalIndex
    from nexus.skills import SkillRegistry
    from nexus.sandbox import DockerSandbox

    table = Table(title="Oracle — environment check", show_header=True)
    table.add_column("Check", style="cyan")
    table.add_column("Result")

    try:
        r = httpx.get(f"{settings.oracle_ollama_host}/api/tags", timeout=3)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        table.add_row("Ollama daemon", f"[green]OK[/] ({len(models)} models)")
    except Exception as e:
        table.add_row("Ollama daemon", f"[red]FAIL[/] {e}")
        models = []

    for role, name in [
        ("primary", settings.oracle_primary_model),
        ("fast", settings.oracle_fast_model),
        ("embed", settings.oracle_embed_model),
    ]:
        found = any(name == m or name in m for m in models)
        icon = "[green]OK[/]" if found else "[yellow]missing[/]"
        table.add_row(f"model ({role})", f"{icon} {name}")

    try:
        t = MemoryTiers()
        stats = t.stats()
        table.add_row(
            "memory tiers",
            f"[green]OK[/] core={stats['core_chars']}c recall={stats['recall_turns']} archival={stats['archival_memories']}",
        )
    except Exception as e:
        table.add_row("memory tiers", f"[red]FAIL[/] {e}")

    try:
        reg = SkillRegistry()
        reg.load_all()
        s = reg.stats()
        table.add_row(
            "skills",
            f"[green]OK[/] total={s['total']} avg_conf={s['avg_confidence']}",
        )
    except Exception as e:
        table.add_row("skills", f"[red]FAIL[/] {e}")

    try:
        idx = RetrievalIndex()
        table.add_row(
            "retrieval index",
            f"[green]OK[/] chunks={idx.count()} sources={len(idx.sources())}",
        )
    except Exception as e:
        table.add_row("retrieval index", f"[red]FAIL[/] {e}")

    sb = DockerSandbox()
    table.add_row(
        "docker sandbox",
        "[green]OK[/] docker CLI present" if sb.is_available() else "[yellow]docker CLI missing[/]",
    )

    console.print(table)


@cli.command()
@click.argument("prompt", nargs=-1, required=False)
@click.option("--thread", default="default")
@click.option("--stream/--no-stream", default=True)
def ask(prompt, thread: str, stream: bool):
    """Ask Trinity Nexus a question. Use `-` to read the prompt from stdin."""
    from nexus.agent import Oracle

    if prompt and list(prompt) == ["-"]:
        question = sys.stdin.read().strip()
    elif prompt:
        question = " ".join(prompt).strip()
    else:
        # no args: read all of stdin (enables pipes like `type file | nexus ask`)
        if sys.stdin.isatty():
            console.print("[yellow]usage: nexus ask 'question' OR nexus ask - (stdin)[/]")
            return
        question = sys.stdin.read().strip()

    if not question:
        console.print("[yellow]empty prompt[/]")
        return

    console.print(f"[dim]thread={thread} • model={settings.oracle_primary_model}[/]")

    t0 = time.perf_counter()
    oracle = Oracle(thread_id=thread)
    try:
        if stream:
            from nexus.repl import _stream_answer

            _stream_answer(oracle, question, console)
        else:
            console.print(Markdown(oracle.ask(question)))
    finally:
        oracle.close()
    console.print(f"[dim]({time.perf_counter() - t0:.1f}s)[/]")


@cli.command()
@click.option("--thread", default="default")
def chat(thread: str):
    """Interactive chat with Oracle — same REPL you get from `oracle`."""
    from nexus.repl import run_repl

    run_repl(console=console, thread=thread)


@cli.group()
def frontier():
    """Test + list frontier API backends (Claude / GPT / Gemini / DeepSeek / ...)."""


@frontier.command("test")
@click.option("--provider", default=None, help="openrouter|anthropic|openai|deepseek|groq|xai|mistral|together|fireworks")
@click.option("--model", default=None, help="override default model for this call")
@click.option("--prompt", default="Reply in one sentence: what is 2+2?", help="test prompt")
def frontier_test(provider, model, prompt):
    """Send a tiny ping to the configured frontier provider. Fails fast if something's off."""
    import os as _os
    from nexus.runtime import get_backend
    from nexus.runtime.types import ChatRequest, Message

    key = provider or _os.environ.get("NEXUS_FRONTIER_PROVIDER") or "frontier"
    be = get_backend(key)

    if not be.is_available():
        console.print(
            "[red]frontier unavailable[/] — NEXUS_FRONTIER_API_KEY is not set"
        )
        console.print(
            "[dim]edit .env and set NEXUS_FRONTIER_PROVIDER + NEXUS_FRONTIER_API_KEY, or use `/frontier` in the REPL[/]"
        )
        return

    console.print(f"[dim]provider={key} · model={model or getattr(be, 'default_model', '?')}[/]")
    req = ChatRequest(
        messages=[
            Message(role="system", content="Be terse."),
            Message(role="user", content=prompt),
        ],
        model=model or "",
        temperature=0.2,
        num_ctx=4096,
        max_tokens=100,
    )
    try:
        t0 = time.perf_counter()
        resp = be.chat(req)
        dt = time.perf_counter() - t0
    except Exception as e:
        console.print(f"[red]FAIL[/] {type(e).__name__}: {e}")
        return
    console.print(
        f"[#7cffb0]OK[/] {dt:.1f}s  · {resp.prompt_tokens}+{resp.completion_tokens} tokens"
    )
    console.print(Markdown(resp.content or "_(empty response)_"))


@frontier.command("models")
@click.option("--provider", default=None)
def frontier_models(provider):
    """List models exposed by the configured frontier provider's /models endpoint."""
    import os as _os

    import httpx as _httpx

    from nexus.runtime.backends.openai_compat import OpenAICompatBackend, PROVIDER_PRESETS

    be = OpenAICompatBackend(
        provider=provider or _os.environ.get("NEXUS_FRONTIER_PROVIDER")
    )
    if not be.is_available():
        console.print("[red]NEXUS_FRONTIER_API_KEY not set[/]")
        return
    try:
        r = _httpx.get(
            f"{be.base_url}/models",
            headers=be._headers(),
            timeout=30.0,
        )
        r.raise_for_status()
    except Exception as e:
        console.print(f"[red]FAIL[/] {e}")
        return

    data = r.json().get("data") or r.json().get("models") or []
    if not data:
        console.print("[yellow]no models returned[/]")
        return
    t = Table(title=f"models at {be.base_url}")
    t.add_column("id", style="cyan")
    t.add_column("context", justify="right")
    t.add_column("price/1M in", justify="right")
    t.add_column("price/1M out", justify="right")
    for m in data[:200]:
        mid = m.get("id") or m.get("name") or ""
        ctx = m.get("context_length") or m.get("context_window") or ""
        pricing = m.get("pricing") or {}
        pin = pricing.get("prompt", "")
        pout = pricing.get("completion", "")
        t.add_row(str(mid), str(ctx), str(pin), str(pout))
    console.print(t)


@cli.group()
def graph():
    """Personal knowledge graph — GraphRAG-style triples."""


@graph.command("ingest")
@click.argument("thread_id", required=False)
def graph_ingest(thread_id):
    """Extract (entity, relation, entity) triples from one or all threads."""
    from nexus import graph as _g

    if thread_id:
        console.print(f"[dim]ingesting thread {thread_id}…[/]")
        r = _g.ingest_thread(thread_id)
    else:
        console.print("[dim]ingesting ALL threads — this can take a while…[/]")
        r = _g.ingest_all()
    console.print_json(json.dumps(r))


@graph.command("query")
@click.argument("entity")
@click.option("--depth", default=2, help="How many hops out to traverse.")
def graph_query(entity, depth):
    """BFS from an entity. Prints neighbors + the edges that connect them."""
    from nexus import graph as _g

    r = _g.query(entity, depth=depth)
    if r["matches"] == 0:
        console.print(f"[yellow]no entity matching {entity!r}[/]")
        return
    console.print(
        f"[bold #c77dff]{r['entity']}[/] · {len(r['neighbors'])} neighbors · {len(r['edges'])} edges"
    )
    for e in r["edges"][:30]:
        console.print(f"  [cyan]{e['from']}[/] —[dim]{e['kind']}[/]→ [cyan]{e['to']}[/]")


@graph.command("stats")
def graph_stats():
    from nexus import graph as _g

    console.print_json(json.dumps(_g.stats()))


@cli.command("optimize-prompt")
@click.option("--section", default=14, type=int, help="Section number to mutate (non-frozen sections only).")
@click.option("--iterations", default=3, type=int)
@click.option("--variations", default=3, type=int)
@click.option("--apply", is_flag=True, help="If the best candidate beats baseline, write it into prompts.py (keeps backup).")
def optimize_prompt(section: int, iterations: int, variations: int, apply: bool):
    """Evolutionary prompt optimizer — mutate a section + score vs the 3-gate eval."""
    from nexus import optimizer as _opt

    console.print(f"[dim]optimizing §{section} · {iterations} iterations · {variations} variations each[/]")
    r = _opt.optimize(
        section_num=section, iterations=iterations,
        variations_per_iter=variations, apply=apply,
    )
    console.print_json(json.dumps(r, indent=2))


@cli.command()
@click.argument("thread_id")
@click.option("--limit", default=40, help="Max user turns to replay.")
def replay(thread_id: str, limit: int):
    """Replay a past session's user turns against the current model, side-by-side."""
    from nexus.agent import Oracle
    from nexus.sessions import read_thread

    events = read_thread(thread_id, limit=limit * 4)
    user_turns = [e for e in events if e.get("kind") == "user"][:limit]
    if not user_turns:
        console.print(f"[yellow]no user turns in {thread_id}[/]")
        return

    console.print(f"[bold #c77dff]replaying[/] {len(user_turns)} turns from [cyan]{thread_id}[/]\n")
    new_thread = f"replay-{thread_id}-{int(time.time())}"
    oracle = Oracle(thread_id=new_thread)
    try:
        for i, turn in enumerate(user_turns, 1):
            prompt = str(turn.get("content", ""))[:2000]
            console.print(f"[dim]--- turn {i}/{len(user_turns)} ---[/]")
            console.print(f"[cyan]user:[/] {prompt[:200]}")
            t0 = time.perf_counter()
            try:
                resp = oracle.ask(prompt)
                console.print(f"[#c77dff]now:[/]  {(resp or '')[:300]}")
                console.print(f"[dim]({time.perf_counter() - t0:.1f}s)[/]\n")
            except Exception as e:
                console.print(f"[red]failed[/] {e}\n")
    finally:
        oracle.close()
    console.print(f"[#7cffb0]replay complete[/] · new thread: {new_thread}")


@cli.command()
def mcp():
    """Run Oracle as an MCP server over stdio (for Claude Desktop / Cursor)."""
    from nexus.mcp_server import run_stdio

    run_stdio()


@cli.command("mcp-config")
@click.option(
    "--write/--no-write",
    default=False,
    help="Merge into %APPDATA%/Claude/claude_desktop_config.json on Windows.",
)
def mcp_config(write: bool):
    """Emit the Claude Desktop config snippet to hook Oracle as an MCP server."""
    import os
    import sys
    from pathlib import Path as _P

    venv_py = _P(sys.executable)
    snippet = {
        "oracle": {
            "command": str(venv_py),
            "args": ["-m", "oracle.cli", "mcp"],
            "cwd": str(_P(__file__).resolve().parents[2]),
        }
    }
    console.print("[bold]Add this under `mcpServers` in Claude Desktop config:[/]")
    console.print_json(json.dumps(snippet, indent=2))

    if not write:
        return

    if sys.platform != "win32":
        console.print("[yellow]--write only auto-merges on Windows for now.[/]")
        return

    cfg_path = _P(os.environ["APPDATA"]) / "Claude" / "claude_desktop_config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    current = {}
    if cfg_path.exists():
        try:
            current = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            current = {}
    servers = current.get("mcpServers", {})
    servers.update(snippet)
    current["mcpServers"] = servers
    cfg_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    console.print(f"[green]merged[/] → {cfg_path}")


@cli.command()
@click.argument("directory")
def ingest(directory: str):
    """Ingest a directory of notes/docs into the retrieval index."""
    from nexus.retrieval import ingest_directory

    console.print(f"[bold]ingesting[/] {directory}")

    def progress(i, n, path):
        if i == 1 or i % 20 == 0 or i == n:
            console.print(f"  [{i:>4}/{n}] {str(path)[-80:]}")

    t0 = time.perf_counter()
    report = ingest_directory(directory, progress=progress)
    dt = time.perf_counter() - t0
    console.print(
        f"[green]done[/] files={report['files']} chunks={report['chunks']} "
        f"bytes={report['bytes']:,} ({dt:.1f}s) total_index={report['index_total']}"
    )


@cli.group()
def skill():
    """Manage the skill library."""


@skill.command("list")
def skill_list():
    """List all skills with confidence + usage stats."""
    from nexus.skills import SkillRegistry

    reg = SkillRegistry()
    reg.load_all()
    t = Table(title=f"skills — {reg.stats()}")
    t.add_column("id", style="cyan")
    t.add_column("confidence", justify="right")
    t.add_column("used", justify="right")
    t.add_column("origin")
    t.add_column("description")
    for s in sorted(reg.all(), key=lambda x: x.id):
        t.add_row(
            s.id,
            f"{s.confidence:.3f}",
            str(s.usage_count),
            s.origin,
            s.description[:70],
        )
    console.print(t)


@skill.command("route")
@click.argument("intent", nargs=-1, required=True)
def skill_route(intent):
    """Show which skills the router picks for a given intent."""
    from nexus.skills import SkillRegistry, SkillRouter

    reg = SkillRegistry()
    reg.load_all()
    router = SkillRouter(reg)
    router.build_index()

    q = " ".join(intent)
    console.print(f"[bold]intent:[/] {q}")
    for s, score in router.route(q, top_k=5):
        console.print(f"  [cyan]{s.id:22s}[/] {score:.3f}  {s.description[:60]}")


@skill.command("run")
@click.argument("skill_id")
@click.argument("inputs_json")
def skill_run(skill_id: str, inputs_json: str):
    """Run a skill directly: oracle skill run summarize_text '{\"text\":\"...\"}'"""
    import ollama

    from nexus.memory import MemoryTiers
    from nexus.skills import SkillContext, SkillRegistry

    try:
        inputs = json.loads(inputs_json)
    except Exception as e:
        console.print(f"[red]inputs_json invalid: {e}[/]")
        return

    reg = SkillRegistry()
    reg.load_all()
    s = reg.get(skill_id)
    if not s:
        console.print(f"[red]unknown skill: {skill_id}[/]")
        return

    client = ollama.Client(host=settings.oracle_ollama_host)
    ctx = SkillContext(
        llm=client,
        model=settings.oracle_primary_model,
        memory=MemoryTiers(),
        user=settings.oracle_user,
    )
    console.print(f"[dim]running {skill_id}...[/]")
    result = s.run(ctx, inputs)
    reg.save_stats()
    console.print(
        f"[{'green' if result.ok else 'red'}]{'ok' if result.ok else 'fail'}[/] "
        f"elapsed={result.elapsed_ms:.0f}ms"
    )
    console.print(Markdown("```json\n" + json.dumps(result.output, indent=2, default=str) + "\n```"))
    if result.error:
        console.print(f"[red]error:[/] {result.error}")


@cli.group()
def memory():
    """Inspect and manage memory tiers."""


@memory.command("stats")
def memory_stats():
    from nexus.memory import MemoryTiers

    t = MemoryTiers()
    console.print_json(json.dumps(t.stats()))


@memory.command("core")
def memory_core():
    from nexus.memory import MemoryTiers

    console.print(Markdown(MemoryTiers().core.read()))


@memory.command("remember")
@click.argument("fact")
@click.option("--tag", "-t", multiple=True)
def memory_remember(fact: str, tag):
    from nexus.memory import MemoryTiers

    mid = MemoryTiers().remember(fact, tags=list(tag), source="cli")
    console.print(f"[green]stored[/] id={mid}")


@memory.command("recall")
@click.argument("query", nargs=-1, required=True)
@click.option("-k", default=5)
def memory_recall(query, k: int):
    from nexus.memory import MemoryTiers

    t = MemoryTiers()
    q = " ".join(query)
    hits = t.archival.query(q, k=k)
    if not hits:
        console.print("[dim]no hits[/]")
        return
    for h in hits:
        console.print(f"- [dim]{h.get('tags', '')}[/] {h['content'][:200]}")


@cli.command()
@click.option("-n", "--n-turns", default=40, help="How many recent turns to review.")
@click.option("--apply/--preview", default=False, help="Apply proposed core edits.")
@click.option("--remember/--no-remember", default=True, help="Store proposed facts in archival.")
def reflect(n_turns: int, apply: bool, remember: bool):
    """Review recent turns; surface themes, facts, and core-memory edits."""
    from nexus.reflect import reflect as _reflect

    console.print(f"[bold]reflecting[/] on last {n_turns} turns  apply={apply}")
    rep = _reflect(n_turns=n_turns, apply=apply, remember_facts=remember)
    console.print_json(json.dumps(rep.to_dict(), indent=2))
    if rep.core_edits and not apply:
        console.print("[dim]re-run with --apply to replace core memory with the proposal.[/]")


@cli.group()
def mesh():
    """Ed25519-signed skill sync between trusted peers."""


@mesh.command("keygen")
@click.option("--label", default=None, help="Human label for this node (default: device name).")
def mesh_keygen(label: str | None):
    """Create (or rotate) this node's mesh identity."""
    from nexus.mesh import new_identity

    ident = new_identity(label=label or settings.oracle_device_name)
    console.print(f"[green]keypair written[/] pubkey={ident.pubkey_b64[:32]}…")
    console.print(f"label: {ident.label}")


@mesh.command("id")
def mesh_id():
    """Show this node's mesh identity (pubkey)."""
    from nexus.mesh import load_identity

    ident = load_identity()
    if not ident:
        console.print("[red]no identity[/] — run `oracle mesh keygen` first")
        return
    console.print(f"label: [cyan]{ident.label}[/]")
    console.print(f"pubkey: {ident.pubkey_b64}")


@mesh.command("add-peer")
@click.argument("pubkey_b64")
@click.argument("url")
@click.option("--label", default="peer")
def mesh_add_peer(pubkey_b64: str, url: str, label: str):
    """Allowlist a peer: add-peer <their pubkey> <their url> --label mac-mini."""
    from nexus.mesh.identity import add_peer

    add_peer(pubkey_b64=pubkey_b64, url=url, label=label)
    console.print(f"[green]trusted[/] {label} @ {url}")


@mesh.command("peers")
def mesh_peers():
    """List allowlisted peers."""
    from nexus.mesh.identity import load_allowlist

    peers = load_allowlist()
    if not peers:
        console.print("[dim]no peers yet[/]")
        return
    t = Table(title=f"mesh peers ({len(peers)})")
    t.add_column("label", style="cyan")
    t.add_column("url")
    t.add_column("pubkey")
    for p in peers:
        t.add_row(p.get("label", ""), p.get("url", ""), p.get("pubkey_b64", "")[:32] + "…")
    console.print(t)


@mesh.command("export")
@click.option(
    "--origins",
    default="self_written,mesh",
    help="Comma list of skill origins to include (default: self_written,mesh).",
)
def mesh_export(origins: str):
    """Build + sign a bundle of local skills; print JSON."""
    from nexus.mesh import build_bundle

    include = tuple(o.strip() for o in origins.split(",") if o.strip())
    bundle = build_bundle(include_origins=include)
    console.print_json(json.dumps(bundle.to_dict()))


@mesh.command("push")
@click.argument("peer_url")
@click.option("--origins", default="self_written,mesh")
def mesh_push(peer_url: str, origins: str):
    """Push this node's skills to PEER_URL (e.g. http://mac-mini.local:8088)."""
    from nexus.mesh import push_bundle

    include = tuple(o.strip() for o in origins.split(",") if o.strip())
    console.print(f"[bold]pushing[/] to {peer_url}")
    report = push_bundle(peer_url=peer_url, include_origins=include)
    console.print_json(json.dumps(report))


@mesh.command("pull")
@click.argument("peer_url")
def mesh_pull(peer_url: str):
    """Fetch + verify + install PEER_URL's skill bundle."""
    from nexus.mesh import pull_bundle

    console.print(f"[bold]pulling[/] from {peer_url}")
    report = pull_bundle(peer_url=peer_url)
    console.print_json(json.dumps(report))


@cli.command()
@click.argument("intent", nargs=-1, required=True)
@click.option("--min-score", default=0.55, type=float, help="Judge threshold for promotion.")
@click.option(
    "--force/--no-force",
    default=False,
    help="Evolve even if the existing router has a good match.",
)
def evolve(intent, min_score: float, force: bool):
    """Propose, sandbox-test, and promote a new skill for INTENT."""
    from nexus.skills.evolve import evolve_from_router_gap, evolve_skill

    q = " ".join(intent)
    console.print(f"[bold]evolving[/] target: [cyan]{q}[/]  min_score={min_score}")
    result = (
        evolve_skill(intent=q, min_score=min_score)
        if force
        else evolve_from_router_gap(intent=q, min_score=min_score)
    )
    if result is None:
        console.print(
            "[yellow]skipped[/] — existing router already covers this intent. "
            "Use --force to override."
        )
        return
    if result.ok:
        console.print(
            f"[green]promoted[/] {result.skill_id} → {result.skill_file} "
            f"(score {result.score:.2f}, {result.elapsed_sec}s)"
        )
    else:
        console.print(
            f"[red]rejected[/] ({result.elapsed_sec}s) "
            f"reasons: {result.rejection_reasons}"
        )


@cli.command()
@click.option("--lookback-hours", default=24)
@click.option("--dry-run", is_flag=True, help="Stop after gold generation; no eval.")
@click.option(
    "--train/--no-train",
    default=False,
    help="Run the Unsloth QLoRA trainer (requires .[training] extras).",
)
def distill(lookback_hours: int, dry_run: bool, train: bool):
    """Run one distillation cycle (collect → teach → [train] → eval)."""
    from nexus.distillation import DistillationOrchestrator

    orch = DistillationOrchestrator()
    console.print(
        f"[bold]distillation[/] lookback={lookback_hours}h "
        f"dry_run={dry_run} train={train}"
    )
    report = orch.run(
        lookback_hours=lookback_hours, dry_run=dry_run, skip_training=not train
    )
    console.print_json(json.dumps(report.__dict__, default=str))


if __name__ == "__main__":
    cli(prog_name="oracle")
