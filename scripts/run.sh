#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  echo "未找到 .env，请先执行:"
  echo "bash scripts/setup.sh"
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip >/dev/null
pip install -r "$ROOT_DIR/requirements.txt"

cd "$ROOT_DIR"
python standx_bot.py --self-check
python standx_bot.py
