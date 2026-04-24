# Installing Oracle

Oracle runs entirely on your own computer. No account, no cloud, no leash.

## Prerequisites (all platforms)

1. **Python 3.12+** — https://python.org
2. **Git**
3. **Ollama** — https://ollama.com/download
4. Pull the models once (≈2 GB total):
   ```
   ollama pull qwen3:4b bge-m3
   ```

## Install — one line

> Replace `<REPO_URL>` with the Oracle repo you were given
> (e.g. `https://github.com/elysianwand/oracle`).

### macOS / Linux / WSL

```bash
ORACLE_REPO_URL=<REPO_URL> \
  curl -sSL <REPO_URL>/raw/main/install.sh | bash
```

### Windows (PowerShell)

```powershell
$env:ORACLE_REPO_URL="<REPO_URL>"; `
  irm <REPO_URL>/raw/main/install.ps1 | iex
```

Both installers:

1. Clone the repo to `~/oracle` (override with `ORACLE_INSTALL_DIR`).
2. Create a Python venv at `~/oracle/.venv`.
3. Install Oracle in editable mode.
4. Drop a launcher to `~/.local/bin/oracle` (mac/linux) or `%USERPROFILE%\bin\oracle.bat` (Windows).
5. Add that dir to PATH if it isn't already.

**Open a new terminal** after install so the PATH change takes effect.

## Install — from a clone (dev)

```bash
git clone <REPO_URL>
cd oracle
./install.sh             # or .\install.ps1 on Windows
```

## Verify

```
oracle doctor
```

All checks should report `OK`. If a model is missing, the command tells you which `ollama pull` to run.

## First run

```
oracle
```

You'll see the neon ORACLE banner and a `❯` prompt. Type anything to talk to it.

## Uninstall

```bash
./uninstall.sh          # or .\uninstall.ps1 on Windows
```

Add `--keep-data` / `-KeepData` to preserve your memory + skills.

## Troubleshooting

**`oracle: command not found`** — open a NEW terminal window. The installer added `~/.local/bin` (unix) or `%USERPROFILE%\bin` (Windows) to your user PATH, which existing shells don't see until they restart.

**Python too old** — the installer needs 3.12 or newer. `python --version` to check.

**Ollama not running** — on Windows, Ollama runs as a background service; start it via the tray icon. On mac/linux run `ollama serve` in another terminal.

**VRAM error on big models** — on a 24 GB GPU, `qwen3:30b` can't co-host with the embedder. Set `ORACLE_EMBED_KEEPALIVE=0s` in `~/oracle/.env` or stay on the default `qwen3:4b`.

**Banner looks broken** — make sure your terminal font is a modern monospace (Cascadia Code, JetBrains Mono, Menlo, etc.). Or set `ORACLE_BANNER=shadow` or `ORACLE_BANNER=off` in `.env`.
