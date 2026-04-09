#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

echo "开始安装 StandX Dual-Side Maker Bot 运行环境"

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 python3，请先安装 Python 3.11+"
  exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
pip install -r "$ROOT_DIR/requirements.txt"

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
  echo "已生成默认 .env，请继续执行："
  echo "bash scripts/setup.sh"
  exit 0
fi

echo "安装完成。"
echo "下一步建议执行："
echo "python3 standx_bot.py --self-check"
echo "或"
echo "bash scripts/run.sh"
