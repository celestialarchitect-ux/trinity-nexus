# Oracle

Sovereign personal AI, terminal-native. Runs local on your own GPU via Ollama.
No cloud, no telemetry, no leash. Think of it as your own Claude Code — yours
to mod, teach, and evolve.

```
 ██████╗ ██████╗  █████╗  ██████╗██╗     ███████╗
██╔═══██╗██╔══██╗██╔══██╗██╔════╝██║     ██╔════╝
██║   ██║██████╔╝███████║██║     ██║     █████╗
██║   ██║██╔══██╗██╔══██║██║     ██║     ██╔══╝
╚██████╔╝██║  ██║██║  ██║╚██████╗███████╗███████╗
 ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚══════╝╚══════╝
```

## Install

### Prereqs (every machine)

1. **Python 3.12+** — https://python.org (Windows) or your package manager
2. **Git**
3. **Ollama** — https://ollama.com/download
4. Pull the models once:
   ```
   ollama pull qwen3:4b bge-m3
   ```

### Windows (PowerShell)

```powershell
# from an Oracle repo clone:
cd path\to\oracle
.\install.ps1
```

```powershell
# no clone yet — one-liner once hosted:
$env:ORACLE_REPO_URL="https://github.com/<you>/oracle"; irm https://raw.githubusercontent.com/<you>/oracle/main/install.ps1 | iex
```

Opens `oracle` in every new PowerShell / CMD / Git Bash window.

### macOS / Linux / WSL

```bash
# from a clone:
./install.sh

# fresh machine:
ORACLE_REPO_URL=https://github.com/<you>/oracle \
  curl -sSL https://raw.githubusercontent.com/<you>/oracle/main/install.sh | bash
```

Adds a launcher at `~/.local/bin/oracle`. If that dir isn't on PATH, the
installer prints the exact line to add to your shell rc file.

## Use

Just type `oracle`.

```
$ oracle

 ██████╗ ██████╗  █████╗  ██████╗██╗     ███████╗
██╔═══██╗██╔══██╗██╔══██╗██╔════╝██║     ██╔════╝
...

   sovereign personal ai · local first · no leash

   v0.1.0  ·  model qwen3:4b  ·  nexus-pc

type /help for commands · /exit to leave

❯ _
```

### REPL slash commands

| Command | What it does |
|---|---|
| `/help` | show commands |
| `/memory` | memory stats; then `/memory core`, `/memory recall <q>`, `/memory remember <fact>` |
| `/skills` | list the skill library (seed + evolved + mesh) |
| `/reflect` | review recent turns → themes + facts |
| `/evolve <intent>` | propose + sandbox-test + promote a new skill for intent |
| `/reset` | fresh thread (memory kept, chat context dropped) |
| `/thread [id]` | show or switch thread |
| `/clear` | clear screen, redraw banner |
| `/exit` | leave (Ctrl-D works too) |

Anything else is sent to the agent.

### Non-REPL commands

```
oracle doctor              # environment check
oracle ask "question"      # one-shot
oracle ingest <dir>        # load docs into retrieval index
oracle memory stats | core | remember <fact> | recall <q>
oracle skill list | route <q> | run <id> '<json>'
oracle evolve <intent>     # propose + test + promote a skill
oracle reflect             # digest recent turns
oracle distill --dry-run   # teacher → eval gate
oracle mesh keygen | id | add-peer <pubkey> <url> | push <url> | pull <url>
oracle mcp                 # stdio MCP server (Claude Desktop)
oracle mcp-config --write  # auto-merge Oracle into Claude Desktop's MCP config
```

## Stack

| Layer | Implementation |
|---|---|
| Primary model | `qwen3:4b` via Ollama (`qwen3:30b` opt-in) |
| Embeddings | `bge-m3` via Ollama |
| Agent | LangGraph + SqliteSaver thread checkpoints |
| Memory (tiered) | `core.md` + SQLite/FTS5 recall + LanceDB archival |
| Retrieval | LanceDB over your ingested docs |
| Skills | seed + `evolved/` + `mesh/`, embedding-routed, confidence-weighted |
| Eval | judge-model 3-gate: regression · diversity · head-to-head |
| Distillation | collector → teacher → gold → eval → archive / (optional QLoRA) |
| Mesh | Ed25519 signed skill bundles over HTTP |
| MCP server | stdio (Claude Desktop / Cursor) |
| Sandbox | Docker (no-net, cap-drop, read-only) |

## Config (`.env`, repo root)

```
ORACLE_PRIMARY_MODEL=qwen3:4b
ORACLE_FAST_MODEL=qwen3:4b
ORACLE_EMBED_MODEL=bge-m3
ORACLE_NUM_CTX=2048
ORACLE_LLM_TIMEOUT_SEC=600
ORACLE_EMBED_KEEPALIVE=5m
ORACLE_TEACHER_PROVIDER=local
ORACLE_ENABLE_DISTILLATION=true
```

The path resolves from the repo root, so `oracle` works from any CWD.

## Running qwen3:30b primary

On a 24GB GPU the 30B MoE can't co-host with `bge-m3`. Either:

1. Set `ORACLE_EMBED_KEEPALIVE=0s` and `ORACLE_PRIMARY_MODEL=qwen3:30b` (embedder unloads per call, ~1s penalty each embed), or
2. Run the embedder on a second GPU.

## Uninstall

```
# Windows
.\uninstall.ps1 [-KeepData]

# mac / linux / WSL
./uninstall.sh [--keep-data]
```

## Tests

```
pytest tests/ -q
```

## Roadmap

- **v1** — agent + memory + CLI + MCP + retrieval + sandbox
- **v2** — eval gate + live distillation + skill evolution + Ed25519 mesh + reflection
- **v3** — real QLoRA nightly runs, libp2p gossip replacing HTTP mesh, richer skill coverage from actual usage
