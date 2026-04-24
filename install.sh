#!/usr/bin/env bash
# Oracle installer — macOS / Linux / WSL / Git Bash
#
# Usage (from cloned repo):
#   ./install.sh
#
# Usage (fresh machine):
#   ORACLE_REPO_URL=https://github.com/you/oracle curl -sSL https://raw.githubusercontent.com/you/oracle/main/install.sh | bash
#
# What it does:
#   1. Clones (or reuses) the Oracle repo at ~/oracle
#   2. Creates a Python 3.12+ venv at <repo>/.venv
#   3. Installs Oracle in editable mode
#   4. Drops `oracle` launcher into ~/.local/bin (standard user bin on mac/linux)
#   5. Warns if ~/.local/bin is not on PATH

set -euo pipefail

step()  { printf '\033[36m[oracle]\033[0m %s\n' "$*"; }
ok()    { printf '\033[32m[oracle]\033[0m %s\n' "$*"; }
warn()  { printf '\033[33m[oracle]\033[0m %s\n' "$*"; }
die()   { printf '\033[31m[oracle]\033[0m %s\n' "$*" >&2; exit 1; }

ORACLE_HOME="${ORACLE_INSTALL_DIR:-$HOME/oracle}"
ORACLE_REPO="${ORACLE_REPO_URL:-}"
BIN_DIR="$HOME/.local/bin"
LAUNCHER="$BIN_DIR/oracle"

# ---------- 1. Python ----------
step "checking Python"
PYTHON=""
for cand in python3.13 python3.12 python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    ver=$("$cand" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    case "$ver" in
      3.12|3.13|3.14|3.15) PYTHON="$cand"; break ;;
    esac
  fi
done
[ -n "$PYTHON" ] || die "Python 3.12+ not found. Install it then re-run."
ok "using Python: $PYTHON ($($PYTHON --version))"

# ---------- 2. Clone or detect ----------
# When the script is piped (curl | bash) BASH_SOURCE is unreliable, so only
# treat the script dir as the repo when it actually has a pyproject.toml.
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" 2>/dev/null && pwd )" || SCRIPT_DIR=""
fi
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
  ORACLE_HOME="$SCRIPT_DIR"
  ok "installing from local repo: $ORACLE_HOME"
elif [ -d "$ORACLE_HOME/.git" ]; then
  step "repo already at $ORACLE_HOME — pulling"
  git -C "$ORACLE_HOME" pull --ff-only
else
  [ -n "$ORACLE_REPO" ] || die "not inside a repo and ORACLE_REPO_URL not set"
  step "cloning $ORACLE_REPO to $ORACLE_HOME"
  git clone "$ORACLE_REPO" "$ORACLE_HOME"
fi

# ---------- 3. venv + install ----------
VENV="$ORACLE_HOME/.venv"
if [ ! -x "$VENV/bin/python" ] && [ ! -x "$VENV/Scripts/python.exe" ]; then
  step "creating venv at $VENV"
  "$PYTHON" -m venv "$VENV"
fi

if [ -x "$VENV/bin/python" ]; then
  VENV_PY="$VENV/bin/python"
elif [ -x "$VENV/Scripts/python.exe" ]; then
  VENV_PY="$VENV/Scripts/python.exe"
else
  die "venv python not found at $VENV"
fi

step "installing dependencies"
"$VENV_PY" -m pip install --upgrade pip >/dev/null
"$VENV_PY" -m pip install -e "$ORACLE_HOME"

# ---------- 4. .env ----------
if [ ! -f "$ORACLE_HOME/.env" ] && [ -f "$ORACLE_HOME/.env.example" ]; then
  step "creating .env from .env.example"
  cp "$ORACLE_HOME/.env.example" "$ORACLE_HOME/.env"
fi

# ---------- 5. launcher ----------
mkdir -p "$BIN_DIR"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
ORACLE_PY="$VENV_PY"
if [ ! -x "\$ORACLE_PY" ]; then
  echo "[oracle] venv python missing at \$ORACLE_PY" >&2
  exit 1
fi
exec "\$ORACLE_PY" -m oracle.cli "\$@"
EOF
chmod +x "$LAUNCHER"
ok "launcher installed at $LAUNCHER"

# ---------- 6. PATH hint ----------
case ":$PATH:" in
  *":$BIN_DIR:"*) ok "$BIN_DIR already on PATH" ;;
  *)
    warn "$BIN_DIR is NOT on PATH"
    echo "    add this line to ~/.zshrc or ~/.bashrc:"
    echo "      export PATH=\"\$HOME/.local/bin:\$PATH\""
    ;;
esac

echo
ok "oracle installed · home = $ORACLE_HOME"
echo
echo "next:"
echo "  1. open a new terminal (or source your rc file)"
echo "  2. make sure Ollama is running  (https://ollama.com/download)"
echo "  3. ollama pull qwen3:4b bge-m3"
echo "  4. oracle doctor"
echo "  5. oracle"
echo
