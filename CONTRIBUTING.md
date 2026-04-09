# Contributing

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Before opening a PR

```bash
python3 -m unittest -v tests/test_standx_runtime_guards.py
python3 -m py_compile standx_bot.py tests/test_standx_runtime_guards.py
```

## Scope

- Keep changes focused
- Do not commit secrets
- Preserve safety guards unless the PR explicitly improves them
