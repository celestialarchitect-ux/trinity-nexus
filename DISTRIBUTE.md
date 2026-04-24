# Distributing Oracle

This is the operator's playbook — how to get Oracle onto other people's machines.

## Path A — one-line GitHub install (fastest, today)

### 1. Publish the repo

```bash
cd C:/Users/Zach/Projects/oracle-prototype

git init
git add .
git commit -m "oracle: initial sovereign release"

# Create a repo on GitHub (gh CLI, if installed):
gh repo create oracle --public --source=. --push
# Or: go to github.com/new, create "oracle", then:
#   git remote add origin https://github.com/<you>/oracle.git
#   git branch -M main
#   git push -u origin main
```

### 2. Share the install command

Tell anyone who wants Oracle:

**macOS / Linux / WSL**
```bash
ORACLE_REPO_URL=https://github.com/<you>/oracle \
  curl -sSL https://github.com/<you>/oracle/raw/main/install.sh | bash
```

**Windows (PowerShell)**
```powershell
$env:ORACLE_REPO_URL="https://github.com/<you>/oracle"; `
  irm https://github.com/<you>/oracle/raw/main/install.ps1 | iex
```

That's the whole install. After it finishes they open a new terminal and type `oracle`.

### 3. Ship updates

Users re-run the same one-liner — the installer does `git pull` when the repo is already present.

## Path B — PyPI + pipx (polished)

Upside: people don't need git, just `pipx install oracle-sovereign`. Downside: renaming + PyPI account + signing.

### 1. Rename the PyPI distribution

`oracle` is already taken on PyPI. Pick a unique dist name, e.g. `oracle-sovereign`, and update `pyproject.toml`:

```toml
[project]
name = "oracle-sovereign"
version = "0.2.0"
```

Keep the `[project.scripts]` entry pointing at `oracle = "oracle.cli:cli"` — that stays `oracle` on the user's PATH.

### 2. Build + upload

```bash
cd C:/Users/Zach/Projects/oracle-prototype
.venv/Scripts/python.exe -m pip install --upgrade build twine
.venv/Scripts/python.exe -m build
.venv/Scripts/python.exe -m twine upload dist/*
```

Twine will prompt for your PyPI token (get one at https://pypi.org/manage/account/token/).

### 3. Users install

```bash
pipx install oracle-sovereign
```

Done — no repo, no venv management.

## Path C — Homebrew tap (Mac users)

Ship a `homebrew-oracle` repo with a Formula that points at a GitHub release tarball. Users then:

```bash
brew tap <you>/oracle
brew install oracle
```

Skip for now unless there's demand.

## What other people need locally

Remind installers that each user machine still needs:

1. Python 3.12+
2. Git
3. Ollama (https://ollama.com/download)
4. `ollama pull qwen3:4b bge-m3` — ~2 GB download once
5. A GPU or Apple Silicon for reasonable speed (4090 is overkill, M2+ is fine)

`oracle doctor` will call out anything missing.

## Versioning

Bump `__version__` in `src/oracle/__init__.py` AND `version` in `pyproject.toml` together. Tag it:

```bash
git tag v0.2.0
git push --tags
```

## Telemetry / privacy

Oracle sends nothing home. No analytics, no crash reports, no model usage stats. The only outbound network calls are to:

- `localhost:11434` (Ollama)
- DeepSeek / Anthropic APIs **if** the user sets keys and enables distillation with a remote teacher
- Explicit peer URLs passed to `oracle mesh push/pull`

That's the whole list. Keep it that way.
