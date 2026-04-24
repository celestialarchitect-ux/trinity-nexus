#!/usr/bin/env bash
# Oracle uninstaller — mac / linux / WSL / Git Bash
# Pass --keep-data to leave the install dir in place.

set -euo pipefail

KEEP_DATA=0
for arg in "$@"; do
  [ "$arg" = "--keep-data" ] && KEEP_DATA=1
done

BIN_DIR="$HOME/.local/bin"
LAUNCHER="$BIN_DIR/oracle"
ORACLE_HOME="${ORACLE_INSTALL_DIR:-$HOME/oracle}"

if [ -f "$LAUNCHER" ]; then
  rm -f "$LAUNCHER"
  echo "removed $LAUNCHER"
fi

if [ "$KEEP_DATA" = "0" ] && [ -d "$ORACLE_HOME" ]; then
  echo "removing install dir $ORACLE_HOME"
  rm -rf "$ORACLE_HOME"
elif [ -d "$ORACLE_HOME" ]; then
  echo "kept install dir $ORACLE_HOME (launcher removed)"
fi

echo "uninstall complete."
