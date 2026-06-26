# autobot — dev tasks
# Usage: make <target>   (Windows: run via Git Bash/WSL, or see README)

PYTHON ?= python3
VENV   := .venv
BIN    := $(VENV)/bin
PY     := $(BIN)/python
PIP    := $(BIN)/pip

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
