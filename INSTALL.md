# Installing Trinity Nexus

Trinity Nexus runs entirely on your own machine. No account, no cloud, no leash.

## Prerequisites (all platforms)

1. **Python 3.12+** — https://python.org
2. **Git**
3. **Ollama** — https://ollama.com/download
4. Pull the models once (~2 GB total):
   ```
   ollama pull qwen3:4b bge-m3
   ```

## Install — one line

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

Both installers:

1. Clone the repo to `~/oracle` (override with `ORACLE_INSTALL_DIR`).
2. Create a Python venv at `<repo>/.venv`.
3. Install Trinity Nexus in editable mode.
4. Drop a `nexus` launcher (plus legacy `oracle` alias) into `~/.local/bin` (unix) or `%USERPROFILE%\bin` (Windows).
5. Add that dir to PATH if it isn't already.

**Open a new terminal** after install so the PATH change takes effect.

## Install from a clone (dev)

```bash
git clone https://github.com/celestialarchitect-ux/trinity-nexus
cd trinity-nexus
./install.sh           # or .\install.ps1 on Windows
```

## Verify

```
nexus doctor
```

Every check should be `OK`. If a model is missing, the command tells you which `ollama pull` to run.

## First run

```
nexus
```

You'll see the neon-purple banner and a `❯` prompt. Type `/onboard` once to let Trinity Nexus build your USER MAP (§04/§23/§24).

## Update

```
nexus update
```

Pulls latest, reinstalls in place.

## Uninstall

```
./uninstall.sh [--keep-data]      # unix
.\uninstall.ps1 [-KeepData]       # windows
```

## Troubleshooting

**`nexus: command not found`** — open a new terminal. The installer added `~/.local/bin` or `%USERPROFILE%\bin` to your user PATH; existing shells don't see it until they restart.

**Big paste gets cut off at 32 lines (Windows conhost limit)** — three fixes:
- Pipe via stdin: `type file.txt | nexus ask`
- From clipboard: `nexus ask "$(Get-Clipboard -Raw)"` (PowerShell)
- From the REPL: `/paste` opens Notepad, you paste, save, close

**VRAM error on qwen3:30b** — on a 24 GB GPU, the 30B MoE can't co-host with `bge-m3`. Set `ORACLE_EMBED_KEEPALIVE=0s` in `.env` or stay on the default `qwen3:4b`.

**Ollama not reachable** — on Windows, Ollama runs as a background service; start it from the tray icon. On mac/linux: `ollama serve` in another terminal.

**Banner looks broken** — use a modern monospace font (Cascadia Code, JetBrains Mono, Fira Code, Menlo). Or set `NEXUS_BANNER=shadow` (lighter) or `NEXUS_BANNER=off`.

**Hooks not running** — drop executable scripts into `~/.nexus/hooks/` named `pre_prompt`, `post_response`, `pre_tool`, `post_tool`, `pre_exit`. Suffixes `.sh`, `.bat`, `.ps1` also work. Set `NEXUS_HOOKS=off` to disable entirely.

**Destructive command blocked** — §29 guards `run_command` against `rm -rf /`, `git reset --hard`, `DROP TABLE`, etc. Unlock for the session with `/dangerous on` in the REPL or `NEXUS_ALLOW_DANGEROUS=1` in the env.

## Mac mini pairing

Oracle / Trinity Nexus on the Mac mini sees code on the Mac mini filesystem —
not the nexus-pc filesystem. To pair:

```bash
# Mac mini
ORACLE_REPO_URL=https://github.com/celestialarchitect-ux/trinity-nexus \
  curl -sSL https://github.com/celestialarchitect-ux/trinity-nexus/raw/main/install.sh | bash

# Exchange mesh identities:
#   on both machines:  nexus mesh keygen && nexus mesh id
#   on nexus-pc:       nexus mesh add-peer <mac-pubkey>  http://mac-mini.local:8088  --label mac-mini
#   on mac-mini:       nexus mesh add-peer <pc-pubkey>   http://nexus-pc.local:8088   --label nexus-pc

# Share skills:
#   nexus mesh push http://mac-mini.local:8088
#   nexus mesh pull http://mac-mini.local:8088
```

Note: mesh sync uses plain HTTP + Ed25519 signatures (libp2p gossip is v3 roadmap). Each node keeps its own memory + skills; cross-machine sync is explicit, not automatic.
