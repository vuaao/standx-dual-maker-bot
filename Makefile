PYTHON ?= python3
PIP ?= $(PYTHON) -m pip

.PHONY: install test lint run self-check dry-run

install:
	$(PIP) install -r requirements.txt

test:
	$(PYTHON) -m unittest -v tests/test_standx_runtime_guards.py

lint:
	$(PYTHON) -m py_compile standx_bot.py tests/test_standx_runtime_guards.py

run:
	$(PYTHON) standx_bot.py

self-check:
	$(PYTHON) standx_bot.py --self-check

dry-run:
	DRY_RUN=true $(PYTHON) standx_bot.py
