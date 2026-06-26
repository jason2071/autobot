# autobot — dev tasks
# Usage: make <target>
#   macOS/Linux: GNU make (preinstalled / `brew install make`)
#   Windows:     run from Git Bash or WSL (`choco install make` for the binary)
#
# Only the venv layout differs by OS (Scripts\ vs bin/); shell commands assume
# a Unix-ish shell (bash), which Git Bash/WSL both provide on Windows.

VENV := .venv

ifeq ($(OS),Windows_NT)
  PYTHON ?= python
  BIN    := $(VENV)/Scripts
else
  PYTHON ?= python3
  BIN    := $(VENV)/bin
endif

PY  := $(BIN)/python
PIP := $(PY) -m pip

.DEFAULT_GOAL := help

.PHONY: help
help: ## list available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

$(VENV): requirements.txt ## create venv + install dependencies
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements.txt
	@touch $(VENV)

.PHONY: install
install: $(VENV) ## install (alias of venv)

.PHONY: run
run: $(VENV) ## launch the bot GUI
	$(PY) main.py

.PHONY: test
test: $(VENV) ## run smoke test (detector + capture + scale)
	$(PY) -m tests.smoke

.PHONY: detect
detect: $(VENV) ## test template match: make detect IMG=a.png TPL=b.png
	$(PY) -m src.detector $(IMG) $(TPL)

.PHONY: clean
clean: ## remove venv + __pycache__
	rm -rf $(VENV)
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
