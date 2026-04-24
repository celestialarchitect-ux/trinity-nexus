# Trinity Nexus — Handoff

> This file is written for the next human or AI agent picking up this project.
> Read it first. It is the single source of truth for state-of-system as of
> 2026-04-23 (Omega Foundation 1.0 release).

## What Trinity Nexus is

A sovereign, terminal-native, adaptive intelligence system modeled after
Claude Code's UX but running fully local via Ollama. Product identity, voice,
and operating principles are encoded in the 33-section Master Operating Prompt
(Omega Foundation 1.0), installed as the system prompt at
`src/nexus/prompts.py :: TRINITY_NEXUS_CONSTITUTION`.

- Owner: Zachariah Kalahiki (GitHub: `celestialarchitect-ux`)
- Repo: https://github.com/celestialarchitect-ux/trinity-nexus
- Parent architecture: Trinity Intelligence Network
- License: not yet declared — pick before going more public

## One-line install

```bash
# mac / linux / WSL
ORACLE_REPO_URL=https://github.com/celestialarchitect-ux/trinity-nexus \
  curl -sSL https://github.com/celestialarchitect-ux/trinity-nexus/raw/main/install.sh | bash

# windows PowerShell
$env:ORACLE_REPO_URL="https://github.com/celestialarchitect-ux/trinity-nexus"; `
  irm https://github.com/celestialarchitect-ux/trinity-nexus/raw/main/install.ps1 | iex
```

Prereqs: Python 3.12+, Git, Ollama, `ollama pull qwen3:4b bge-m3`.

After install: open new terminal, type `nexus` (or legacy alias `oracle`).

## State of the build

**Shipped and tested (28/28 tests green):**
- Full 33-section Omega Foundation constitution as system prompt
- Package renamed `oracle → nexus`; dist name `trinity-nexus v1.0.0`
- CLI command `nexus` (primary) + `oracle` (alias)
- Banner: neon purple NEXUS pixel block + "TRINITY NEXUS" tagline
- LangGraph agent with SqliteSaver thread checkpoints
- Three-tier memory: `core.md` + SQLite/FTS5 recall + LanceDB archival
- Retrieval (LanceDB) + `nexus ingest <dir>`
- Skills: 13 seed + evolved (self-written, judge-gated) + mesh (Ed25519-signed)
- Eval harness: regression + diversity + head-to-head gates
- Distillation pipeline (teacher=local default; DeepSeek/Anthropic optional)
- Skill self-evolution (`nexus evolve`)
- Reflection (`nexus reflect`)
- Ed25519 mesh (`nexus mesh {keygen,id,add-peer,push,pull}`)
- MCP server (`nexus mcp`) + Claude Desktop config helper
- File tools: `read_file`, `write_file`, `edit_file`, `glob_paths`, `grep_files`
- Web tools: `web_fetch`, `web_search` (DuckDuckGo, no API key)
- Shell: `run_command`
- Memory tools: `remember`, `retrieve_notes`
- Esoteric thinking indicator (100+ verbs, pulsing glyph, elapsed time)
- Tool-call display Claude-Code-style (`✦ tool(args)` → `⎿ result`)
- Docker sandbox for LLM-generated code
- `ORACLE.md` / `NEXUS.md` per-project instruction loader (walks cwd upward)
- `nexus update` command (git pull + reinstall in place)

## What's missing (top 10 in impact order)

1. **Onboarding + USER MAP (§04, §23, §24)** — no `/onboard`; no `memory/user_map.md`.
2. **9-tier memory (§06)** — only 2 of 9 tiers exist (core + archival).
3. **`/mode` operating mode overlays (§13)** — 12 modes documented in constitution but no runtime switch.
4. **`spawn_agent` tool (§19)** — multi-agent internal structure not wired as an agent-callable tool.
5. **`/dangerous` confirmation gate (§29)** — `run_command` is unsandboxed; needs destructive-op allowlist.
6. **Multi-line REPL input + clipboard pipe** — Shift+Enter, and `nexus ask -` reading stdin (unblocks the 32-line conhost paste cap).
7. **Token-level streaming** — currently `stream_mode=values` (whole messages); should be `stream_mode=messages`.
8. **Session transcript recording** (`data/sessions/`) — needed for reflection + distillation inputs.
9. **Hooks (`~/.nexus/hooks/`)** — pre/post tool + pre/post prompt shell scripts.
10. **PyPI publish** — rename already done; just needs `python -m build && twine upload` + a PyPI token.

See the full audit written by the previous session (in conversation context) for 30 decision questions with default answers.

## Locked-in defaults (don't re-ask the user)

- Product name: **Trinity Nexus**. Command: `nexus`. Package: `nexus`. Dist: `trinity-nexus`.
- Primary model: `qwen3:4b`. 30B opt-in via `.env` once VRAM permits.
- Memory is **per-machine**. Cross-machine sync is explicit via `nexus mesh push/pull`.
- Repo is **public**. Runtime data (`data/`, `logs/`, `.env`) is .gitignored.
- Teacher for distillation: `local` until DeepSeek/Anthropic keys are added.
- Default mode on launch: free (no mode overlay) until `/mode` ships, then BUILDER.
- Instance name at launch: `Nexus` (override via `ORACLE_INSTANCE`).
- Banner style: `pixel` (override: `NEXUS_BANNER=shadow|off`).

## Known risks / open loops

- `run_command` tool is unsandboxed. Add §29 confirmation gate before heavy external use.
- VRAM: 16k ctx + qwen3:4b + bge-m3 ≈ 6.5 GB used on a 24 GB 4090. Fine locally; will break on smaller GPUs. Document this on the install page.
- Data is not encrypted at rest. Protected-Notes tier (§06.7) should get disk encryption before real sensitive data lands.
- `oracle` alias still exists for back-compat. Docs reference both names in places. Clean sweep pending.
- Self-modification: agent can't edit `src/nexus/` by default. If later allowed, add `--allow-self-modify` gate.
- Ollama single-queue: `spawn_agent` parallelism will serialize at the Ollama layer until multiple Ollama instances run.

## How to resume

Fresh session, any machine:

```bash
cd trinity-nexus          # or ~/oracle, or wherever you installed
git pull
pytest tests/ -q          # expect 28/28
nexus doctor              # expect 8/8 OK
cat HANDOFF.md            # this file
cat MEMORY.md             # (if present — index of persistent memory)
```

Then read the most recent commits to catch up:

```bash
git log --oneline -20
```

## Who to hand to

- **Zach personally:** run `nexus` and start using it; next build priorities are items 1-3 above.
- **Another AI agent (Claude Code, Cursor, etc.):** you are standing in a Python project with 28/28 passing tests. The system prompt at `src/nexus/prompts.py` is the operating constitution — you do not need to invent behavior; it is already written. Start with the audit's top-10 pending items. Make minimal commits. Keep tests green. Do not delete the mesh/ or skills/evolved/ directories — they contain signed artifacts.
- **Mac mini Claude Code specifically:** clone the repo, install, verify `nexus doctor`, then inspect + extend. Pair by exchanging signed skill bundles via `nexus mesh push`.

## Contact

- GitHub issues on the repo (public)
- MCP server (`nexus mcp`) — Claude Desktop can call this directly

---

*Per §33: begin every session by orienting to the user's objective; continue by
increasing clarity; end every major response with completion, not dependency.
When the user gives a command, do not merely answer — build the next layer of
the system.*
