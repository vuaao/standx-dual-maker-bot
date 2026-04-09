# Deployment Guide

## 1. Prepare the host

- Linux server with Python 3.11+
- Stable network access to StandX APIs
- Separate wallet for bot usage only
- Process manager such as `systemd`, `supervisor`, or Docker

## 2. Install

```bash
git clone https://github.com/<your-org-or-user>/standx-dual-maker-bot.git
cd standx-dual-maker-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 3. Safe first run

1. Set `DRY_RUN=true`
2. Set `CIRCUIT_BREAKER_ACTION=pause`
3. Fill wallet and bot config
4. Run self-check first

```bash
python3 standx_bot.py --self-check
python3 standx_bot.py
```

## 4. Move to real trading

Only after dry-run logs look correct:

```dotenv
DRY_RUN=false
CIRCUIT_BREAKER_ACTION=pause
STARTUP_CANCEL_STALE_ORDERS=true
```

## 5. Run with systemd

Example service:

```ini
[Unit]
Description=StandX Dual-Side Maker Bot
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/standx-dual-maker-bot
EnvironmentFile=/opt/standx-dual-maker-bot/.env
ExecStart=/opt/standx-dual-maker-bot/.venv/bin/python standx_bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## 6. Operational advice

- Start with small `ORDER_SIZE`
- Keep `DRY_RUN=true` for first validation
- Use dedicated API wallet
- Watch logs before enabling real trading
- Do not disable safety guards unless you understand the consequence
