# autobot — dev tasks
# Usage: make <target>   (Windows: ใช้ผ่าน Git Bash/WSL หรือดูคำสั่งใน README)

PYTHON ?= python3
VENV   := .venv
BIN    := $(VENV)/bin
PY     := $(BIN)/python
PIP    := $(BIN)/pip

.DEFAULT_GOAL := help

.PHONY: help
help: ## แสดงรายการคำสั่ง
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

$(VENV): requirements.txt ## สร้าง venv + ลง dependencies
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements.txt
	@touch $(VENV)

.PHONY: install
install: $(VENV) ## ติดตั้ง (alias ของ venv)

.PHONY: run
run: $(VENV) ## เปิด GUI บอท
	$(PY) main.py

.PHONY: test
test: $(VENV) ## รัน smoke test (detector + capture + scale)
	$(PY) -m tests.smoke

.PHONY: detect
detect: $(VENV) ## ทดสอบ template match: make detect IMG=a.png TPL=b.png
	$(PY) -m src.detector $(IMG) $(TPL)

.PHONY: clean
clean: ## ลบ venv + __pycache__
	rm -rf $(VENV)
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
