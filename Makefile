PYTHON ?= python3
PIP ?= $(PYTHON) -m pip

.PHONY: install test lint run self-check dry-run setup bootstrap docker-build docker-up

install:
	$(PIP) install -r requirements.txt

setup:
	bash scripts/setup.sh

bootstrap:
	bash scripts/run.sh

docker-build:
	docker compose build

docker-up:
	docker compose up -d

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
