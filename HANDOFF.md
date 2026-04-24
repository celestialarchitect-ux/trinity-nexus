# Trinity Nexus — Handoff

> Read first. This is the canonical state-of-system for any human or AI
> picking up the project. Current as of v1.0.8.

## What Trinity Nexus is

Terminal-native sovereign AI, modeled on Claude Code's UX. The identity,
voice, and operating rules are encoded in the 33-section Omega Foundation
constitution (`src/nexus/prompts.py :: TRINITY_NEXUS_CONSTITUTION`).

- Owner: Zachariah Kalahiki (GitHub: `celestialarchitect-ux`)
- Repo: https://github.com/celestialarchitect-ux/trinity-nexus
- PyPI: https://pypi.org/project/trinity-nexus/
- License: MIT
- Current: v1.0.8 · 80/80 tests green

## Install

```bash
pipx install trinity-nexus
```

Prereqs: Python 3.12+, Ollama (https://ollama.com), then `ollama pull qwen3:4b bge-m3`.

Then any terminal:

```
nexus
```

## Complete feature matrix

**Core agent**
- LangGraph loop with SqliteSaver thread checkpoints
- Constitution (33 sections) injected as system prompt every turn
- Per-turn layers: project instructions (`NEXUS.md`/`ORACLE.md`) → USER MAP → 9-tier memory → active mode overlay → graph context → live memory context
- Ed25519 identity per node

**Memory**
- 3-tier: core.md + SQLite/FTS5 recall + LanceDB archival
- 9-tier markdown: core, projects, strategic, creative, technical, personal_os, protected, threads, artifacts
- Knowledge graph (SQLite, BFS over triples extracted per-thread)
- Session transcripts JSONL with auto-titling
- Context compaction (manual + auto past threshold)
- At-rest Fernet encryption via passphrase (§29.8)

**Tools bound to the agent**
- `read_file`, `write_file`, `edit_file`, `apply_diff`, `glob_paths`, `grep_files`
- `run_command` (destructive-pattern gate, interactive y/N prompt, rate-limited)
- `web_fetch`, `web_search` (DuckDuckGo; tainted output per §29.4)
- `remember`, `retrieve_notes`, `retrieve_graph`
- `spawn_agent`, `frontier_ask`, `browser_task` (optional, `.[browser]` extra)

**Runtime**
- `nexus.runtime` with pluggable backends:
  - `ollama` (default)
  - `llama_cpp` (direct GGUF, parallel, KV-cache reuse) — install `.[local-runtime]`
  - `openai_compat` — one client for OpenAI / Anthropic / OpenRouter / Groq / DeepSeek / xAI / Mistral / Together / Fireworks
- Prompt caching (Anthropic `cache_control`) on large system blocks
- Cost ledger (tokens + $ per call per backend)

**Security (§29)**
- 10 layers: destructive-pattern gate, safe mode, read-only mode, taint on untrusted content, injection scanner, rate limiter, secret redactor on transcripts, encrypted memory at rest, HMAC audit log, interactive write confirmation
- REPL toggles: `/safe`, `/readonly`, `/dangerous`, `/encrypt`, `/permissions`

**Skills**
- 13 seed skills + evolved (judge-gated) + mesh (Ed25519-signed peer-to-peer)
- `nexus evolve <intent>` promotes new skills into the registry
- `nexus mesh discover|listen|export|push|pull` for peer federation
- mDNS LAN discovery (zeroconf) for finding peers automatically

**Evolution**
- 3-gate eval harness: regression · diversity · head-to-head
- Distillation pipeline: collector → teacher → gold → eval → archive
- Reflection: `/reflect` digests recent turns
- Prompt optimizer: `nexus optimize-prompt --section N` evolves non-frozen constitution sections against the eval harness
- Code-as-action: `/code-agent <task>` — model writes Python, we run it, it loops

**UX (Claude-Code parity)**
- Retro purple NEXUS banner + "Trinity Intelligence Network" + green/purple accents
- Always-visible bottom status bar (model, mode, ctx %, cost, session thread)
- User messages echoed in purple Panels
- Real unified diffs with red/green/purple syntax colors
- Errors rendered in red Panels, REPL continues
- Turn separators, typing cursor, monokai code highlighting
- `?` shortcuts popup, `Tab` autocomplete, `Ctrl+C` double-tap exit
- Prefixes: `@path` attach file, `!cmd` bash passthrough, `#text` memory add
- 33+ slash commands
- `/onboard` builds the USER MAP (§04, §23, §24)
- `/status` one-glance setup
- `/config` inline .env editor
- `/mode` 12 operating modes with per-mode model routing
- `/resume` + `/sessions` list past threads (with auto-generated titles)
- `/plan` + `/execute` architect→executor split
- `/rewind N` drop last N checkpoints
- `/compact` force context compaction
- `/graph <entity>` knowledge-graph BFS

**Distribution**
- Installable via pipx, pip, or clone+`install.sh`/`install.ps1`
- `nexus version --check` · `nexus upgrade`
- MCP server (stdio) for Claude Desktop integration via `nexus mcp`
- `nexus mcp-config --write` auto-merges config

## Where things live

| Path | What |
|---|---|
| `src/nexus/prompts.py` | 33-section constitution (the identity layer) |
| `src/nexus/agent.py` | LangGraph agent + per-turn system prompt assembly |
| `src/nexus/repl.py` | Interactive REPL, slash commands, streaming UX |
| `src/nexus/banner.py` | Startup banner |
| `src/nexus/modes.py` | 12 operating modes + per-mode model routing |
| `src/nexus/memory/` | 3-tier + 9-tier memory, embeddings |
| `src/nexus/retrieval/` | LanceDB doc index + ingest |
| `src/nexus/skills/` | Seed / evolved / mesh skills + router |
| `src/nexus/mesh/` | Ed25519 identity, signed sync, mDNS discovery |
| `src/nexus/runtime/` | Pluggable inference backends |
| `src/nexus/security.py` | 10 security layers |
| `src/nexus/cost.py` | Token/$ ledger |
| `src/nexus/sessions.py` | JSONL transcripts + titles |
| `src/nexus/graph.py` | Personal knowledge graph (SQLite + BFS) |
| `src/nexus/code_agent.py` | Code-as-action loop |
| `src/nexus/optimizer.py` | Evolutionary constitution optimizer |
| `src/nexus/compaction.py` | Context squash via fast model |
| `src/nexus/distillation/` | Teacher → gold → eval → archive |
| `src/nexus/mcp_server/` | stdio MCP server |
| `src/nexus/sandbox/` | Docker sandbox wrapper |

## Config knobs (`.env`)

Critical ones:
- `ORACLE_PRIMARY_MODEL` / `ORACLE_FAST_MODEL` / `ORACLE_EMBED_MODEL`
- `ORACLE_NUM_CTX` (default 16384)
- `NEXUS_BACKEND` (ollama / llama_cpp)
- `NEXUS_FRONTIER_PROVIDER` + `_API_KEY` + `_MODEL`
- `NEXUS_SAFE`, `NEXUS_READONLY`, `NEXUS_WRITE_ALLOW`, `NEXUS_CONFIRM_WRITES`
- `NEXUS_AUTO_COMMIT`, `NEXUS_AUTO_APPROVE`
- `NEXUS_AUTOCOMPACT`, `NEXUS_AUTOCOMPACT_EVENTS`
- `NEXUS_MODEL_<MODE_KEY>` for per-mode model overrides
- `NEXUS_RATE_TOOLS_PER_MIN`, `NEXUS_RATE_LLM_PER_MIN`
- `NEXUS_BANNER` (pixel / shadow / off), `NEXUS_RECORD`, `NEXUS_HOOKS`

## Known gaps (roadmap)

- **Full Docker sandbox for code-agent** — currently runs `exec()` in-process with threading timeout. Safe-ish (§29 gates still apply) but not hermetic. Wrap in `DockerSandbox` for hermetic untrusted execution.
- **Nexus-1 fine-tune** — the distillation pipeline is built; needs ~5K real interactions before a meaningful SFT. Accumulates by using the tool.
- **libp2p proper mesh gossip** — we have mDNS + signed bundles. True DHT-based discovery is a larger lift.
- **Voice (TTS/ASR)** — intentionally deferred.
- **IDE extension** — out of scope (use MCP instead).

## How to resume in a new session

```bash
cd trinity-nexus
git pull
pipx upgrade trinity-nexus   # if installed via pipx
pytest tests/ -q              # expect 80/80
nexus doctor
cat HANDOFF.md
git log --oneline -20
```

## Security reminders for operators

- Rotate any API tokens that were pasted into conversation transcripts
- The repo is public — `data/`, `logs/`, `.env` are gitignored
- For sensitive sessions: `NEXUS_SAFE=1` + `NEXUS_WRITE_ALLOW=...`
- For machine-theft protection: `/encrypt unlock <passphrase>`

---

*Per §33 Prime Directive — orient to objective, increase clarity, end with
completion. When the user gives a command: build the next layer of the system.*
