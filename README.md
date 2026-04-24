# Trinity Nexus

Sovereign, terminal-native, adaptive intelligence. Installed like Claude Code,
runs entirely local via Ollama. Constitution: Omega Foundation 1.0 — a 33-section
operating prompt that defines identity, memory, truth rules, and response
behavior per every turn.

```
███    ██ ███████ ██   ██ ██    ██ ███████
████   ██ ██       ██ ██  ██    ██ ██
██ ██  ██ █████     ███   ██    ██ ███████
██  ██ ██ ██       ██ ██  ██    ██      ██
██   ████ ███████ ██   ██  ██████  ███████

T R I N I T Y   N E X U S
adaptive intelligence · local-first · truth before comfort
```

## Install

### Prereqs
1. Python 3.12+
2. Git
3. Ollama — https://ollama.com/download
4. `ollama pull qwen3:4b bge-m3`  (~2 GB total)

### macOS / Linux / WSL

```bash
ORACLE_REPO_URL=https://github.com/celestialarchitect-ux/trinity-nexus \
  curl -sSL https://github.com/celestialarchitect-ux/trinity-nexus/raw/main/install.sh | bash
```

### Windows (PowerShell)

```powershell
$env:ORACLE_REPO_URL="https://github.com/celestialarchitect-ux/trinity-nexus"; `
  irm https://github.com/celestialarchitect-ux/trinity-nexus/raw/main/install.ps1 | iex
```

Open a new terminal, type `nexus`. (Legacy alias `oracle` also works.)

## Usage

Just type `nexus`. You'll get the neon-purple banner and a `❯` prompt.

### REPL slash commands

| Command | What it does |
|---|---|
| `/help` | show all commands |
| `/onboard` | §04/§23/§24 orientation → writes `memory/user_map.md` |
| `/user-map` | print the active USER MAP |
| `/mode [name\|list\|off]` | switch operating mode (§13) — 12 modes |
| `/memory [tier] [read\|write\|append text]` | 9-tier memory (§06) |
| `/skills` | list the skill library |
| `/reflect` | review recent turns → themes + facts |
| `/evolve <intent>` | propose + sandbox-test + promote a new skill |
| `/spawn <task>` | sub-agent on its own thread (§19) |
| `/dangerous [on\|off]` | unlock destructive-op gate (§29) |
| `/paste` | open $EDITOR / notepad for big multi-line prompts |
| `/reset` | new thread (memory kept, chat context dropped) |
| `/thread [id]` | show or switch thread |
| `/clear` | clear screen, redraw banner |
| `/exit` | leave (Ctrl-D also works) |

Enter submits. **Shift+Enter** inserts a newline for multi-line input.

### Non-REPL

```
nexus doctor                          # env check
nexus ask "one-shot question"
nexus ask -                           # read prompt from stdin (paste big input)
type file.txt | nexus ask             # pipe stdin
nexus ingest <dir>                    # load docs into retrieval
nexus memory {stats,core,remember <fact>,recall <q>}
nexus skill {list,route <q>,run <id> '<json>'}
nexus evolve <intent>
nexus reflect
nexus distill --dry-run
nexus mesh {keygen,id,add-peer,peers,export,push,pull}
nexus mcp                             # stdio MCP server (Claude Desktop)
nexus mcp-config --write              # auto-merge MCP config
nexus update                          # git pull + reinstall
nexus version
```

## Architecture

| Layer | Implementation |
|---|---|
| Core model | qwen3:4b via Ollama (30B opt-in) |
| Embeddings | bge-m3 via Ollama |
| System prompt | full 33-section Omega Foundation constitution (`src/nexus/prompts.py`) |
| Runtime layers | constitution → NEXUS.md / ORACLE.md (project instructions) → USER MAP → 9-tier memory → active mode overlay → live memory context |
| Agent | LangGraph + SqliteSaver thread checkpoints |
| Memory | `core.md` + SQLite/FTS5 recall + LanceDB archival + 9-tier markdown (`§06`) |
| Retrieval | LanceDB over ingested docs |
| Skills | seed (13) + `evolved/` (judge-gated) + `mesh/` (Ed25519-signed) |
| Eval | judge-model 3-gate: regression · diversity · head-to-head |
| Distillation | collector → teacher → gold → eval → archive / QLoRA optional |
| Mesh | Ed25519 signed skill bundles over HTTP |
| MCP server | stdio — `nexus_ask`, `nexus_retrieve`, `nexus_recall`, `nexus_remember`, `nexus_skill_list`, `nexus_skill_run` |
| Tool layer | read/write/edit/glob/grep, web_fetch, web_search, run_command (§29 guarded), spawn_agent (§19), remember, retrieve_notes |
| Sandbox | Docker (no-net, cap-drop, read-only) |
| Sessions | JSONL transcripts under `data/sessions/<thread>.jsonl` |
| Hooks | `~/.nexus/hooks/{pre_prompt,post_response,pre_tool,post_tool,pre_exit}.sh/.bat/.ps1` |

## The Constitution

Trinity Nexus's identity is not a tagline — it's a 33-section operating prompt
(Omega Foundation 1.0) installed as the system prompt. See
[`src/nexus/prompts.py`](src/nexus/prompts.py). Highlights:

- §01 Core laws: **truth before comfort, clarity before agreement, usefulness
  before performance, evolution before repetition, structure before chaos,
  reality before fantasy**
- §02 Mind / Soul / Body identity model
- §06 9-tier memory structure
- §09 9-layer autonomous reasoning
- §10 Truth engine — never speculate as fact
- §13 12 operating modes
- §19 Multi-agent internal structure (Intent Parser → Context Retriever → Architect → Builder → Critic → Truth Checker → Risk Governor → Memory Curator → Final Synthesizer)
- §29 Security governor
- §33 Prime Directive — *build the next layer of the system on every command*

## Configuration (`.env`)

```
ORACLE_PRIMARY_MODEL=qwen3:4b
ORACLE_FAST_MODEL=qwen3:4b
ORACLE_EMBED_MODEL=bge-m3
ORACLE_NUM_CTX=16384
ORACLE_LLM_TIMEOUT_SEC=600
ORACLE_EMBED_KEEPALIVE=5m
ORACLE_TEACHER_PROVIDER=local
ORACLE_ENABLE_DISTILLATION=true
ORACLE_INSTANCE=Nexus
NEXUS_BANNER=pixel           # pixel | shadow | off
NEXUS_RECORD=1               # 1 = record session transcripts, 0 = off
NEXUS_HOOKS=                 # set off to disable hooks
```

Resolved from the project root — `nexus` works from any CWD.

## Running qwen3:30b primary

On a 24 GB GPU, the 30B MoE and `bge-m3` can't co-host. Either:
1. `ORACLE_EMBED_KEEPALIVE=0s` + `ORACLE_PRIMARY_MODEL=qwen3:30b` (embedder unloads per call, ~1s penalty), or
2. Run the embedder on a second GPU.

## Uninstall

```
./uninstall.ps1 [-KeepData]
./uninstall.sh [--keep-data]
```

## Tests

```
pytest tests/ -q      # 28/28 on the reference build
```

## For contributors / AI agents

Read [`HANDOFF.md`](HANDOFF.md) first — canonical state-of-system. Then:

```bash
cd trinity-nexus
git pull
nexus doctor
pytest tests/ -q
```

- Don't delete `src/nexus/skills/evolved/` or `src/nexus/skills/mesh/` — they contain self-written / signed artifacts.
- Make minimal changes (§17). Keep tests green.
- The constitution is the behavior layer. Don't duplicate its rules in code.

## License

Not yet declared. Treat as All Rights Reserved until specified.
