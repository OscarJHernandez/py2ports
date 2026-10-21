PYTHON ?= python3
RUN := .venv/bin/python -m py2ports
SELECT := $(if $(GAME),--game $(GAME),)
export DEVICE_HOST DEVICE_USER DEVICE_PORT
DEVICE_HOST ?= knulli
DEVICE_USER ?= root

.PHONY: help setup list validate build package check-device deploy add test
help:
	@echo 'make setup | list | validate | build | package | check-device | deploy | test'
	@echo 'Deploy one game: make deploy GAME=py2port_pygame_template [DEVICE_HOST=192.168.1.50]'

setup:
	@$(PYTHON) -c 'import sys; sys.exit("Python 3.11+ required. Retry make setup PYTHON=python3.12" if sys.version_info < (3,11) else 0)'
	$(PYTHON) -m venv .venv
	.venv/bin/python -m pip install -e '.[dev]'

list validate build package:
	$(RUN) $@ $(SELECT)

check-device:
	$(RUN) check-device

deploy:
	$(RUN) deploy $(SELECT)

add:
	$(RUN) add "$(REPOSITORY)" --name "$(GAME)" --entrypoint "$(ENTRYPOINT)" $(if $(SOURCE),--source "$(SOURCE)",)

test:
	.venv/bin/python -m pytest
