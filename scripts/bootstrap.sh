#!/usr/bin/env bash
# One-shot bootstrap for the Oracle prototype on this PC.
# Run from the repo root:  bash scripts/bootstrap.sh

set -euo pipefail

cd "$(dirname "$0")/.."

echo "[oracle] 1/4 creating venv"
python -m venv .venv

echo "[oracle] 2/4 activating + installing"
source .venv/Scripts/activate
pip install --upgrade pip
pip install -e .

echo "[oracle] 3/4 copying .env"
[ -f .env ] || cp .env.example .env

echo "[oracle] 4/4 running doctor"
oracle doctor

echo ""
echo "[oracle] Next:"
echo "  source .venv/Scripts/activate"
echo "  oracle ask 'hello, who are you?'"
