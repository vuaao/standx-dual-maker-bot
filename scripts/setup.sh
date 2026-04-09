#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_EXAMPLE="$ROOT_DIR/.env.example"
ENV_FILE="$ROOT_DIR/.env"

if [[ ! -f "$ENV_EXAMPLE" ]]; then
  echo "缺少模板文件: $ENV_EXAMPLE"
  exit 1
fi

echo "StandX Dual-Side Maker Bot 配置向导"
echo

if [[ -f "$ENV_FILE" ]]; then
  read -r -p ".env 已存在，是否覆盖？[y/N]: " OVERWRITE
  if [[ ! "${OVERWRITE,,}" =~ ^y(es)?$ ]]; then
    echo "已取消。"
    exit 0
  fi
fi

cp "$ENV_EXAMPLE" "$ENV_FILE"

prompt_default() {
  local prompt_text="$1"
  local default_value="$2"
  local result
  read -r -p "$prompt_text [$default_value]: " result
  if [[ -z "$result" ]]; then
    result="$default_value"
  fi
  printf '%s' "$result"
}

prompt_required() {
  local prompt_text="$1"
  local result=""
  while [[ -z "$result" ]]; do
    read -r -p "$prompt_text: " result
  done
  printf '%s' "$result"
}

prompt_secret_required() {
  local prompt_text="$1"
  local result=""
  while [[ -z "$result" ]]; do
    read -r -s -p "$prompt_text: " result
    echo
  done
  printf '%s' "$result"
}

set_env_value() {
  local key="$1"
  local value="$2"
  python3 - "$ENV_FILE" "$key" "$value" <<'PY'
from pathlib import Path
import sys

env_path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = env_path.read_text(encoding="utf-8").splitlines()
target = f"{key}="
updated = False
for index, line in enumerate(lines):
    if line.startswith(target):
        lines[index] = f"{key}={value}"
        updated = True
        break
if not updated:
    lines.append(f"{key}={value}")
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

WALLET_PRIVATE_KEY="$(prompt_secret_required "请输入钱包私钥")"
WALLET_ADDRESS="$(prompt_required "请输入钱包地址")"
SYMBOL="$(prompt_default "交易对" "BTC-USD")"
ORDER_SIZE="$(prompt_default "单次数量" "0.001")"
ORDER_OFFSET_BUY="$(prompt_default "买单偏移" "100")"
ORDER_OFFSET_SELL="$(prompt_default "卖单偏移" "100")"
WARN_MOVE_BUY="$(prompt_default "买侧预警偏移" "30")"
WARN_MOVE_SELL="$(prompt_default "卖侧预警偏移" "30")"
CANCEL_MOVE_BUY="$(prompt_default "买侧撤单偏移" "60")"
CANCEL_MOVE_SELL="$(prompt_default "卖侧撤单偏移" "60")"
DRY_RUN="$(prompt_default "是否先启用 DRY_RUN (true/false)" "true")"
CIRCUIT_BREAKER_ACTION="$(prompt_default "熔断动作 (stop/pause/cancel-only)" "pause")"

set_env_value "WALLET_PRIVATE_KEY" "$WALLET_PRIVATE_KEY"
set_env_value "WALLET_ADDRESS" "$WALLET_ADDRESS"
set_env_value "SYMBOL" "$SYMBOL"
set_env_value "ORDER_SIZE" "$ORDER_SIZE"
set_env_value "ORDER_OFFSET_BUY" "$ORDER_OFFSET_BUY"
set_env_value "ORDER_OFFSET_SELL" "$ORDER_OFFSET_SELL"
set_env_value "WARN_MOVE_BUY" "$WARN_MOVE_BUY"
set_env_value "WARN_MOVE_SELL" "$WARN_MOVE_SELL"
set_env_value "CANCEL_MOVE_BUY" "$CANCEL_MOVE_BUY"
set_env_value "CANCEL_MOVE_SELL" "$CANCEL_MOVE_SELL"
set_env_value "DRY_RUN" "$DRY_RUN"
set_env_value "CIRCUIT_BREAKER_ACTION" "$CIRCUIT_BREAKER_ACTION"

echo
echo "配置完成：$ENV_FILE"
echo "建议下一步执行："
echo "bash scripts/run.sh"
