.PHONY: help install data requirements test lint format check eval eval-quick

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

install: ## Install Python dependencies
	uv sync

data: ## Clone or update the organizer repo (training data, schemas) into data/uzp
	@if [ -d data/uzp/.git ]; then git -C data/uzp pull --ff-only; \
	else git clone --depth 1 https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026 data/uzp; fi
	@git -C data/uzp log --oneline -n 1

requirements: ## Regenerate requirements.txt from uv.lock (the jury installs with pip)
	uv export --quiet --frozen --no-hashes --no-dev --no-emit-project -o requirements.txt

test: ## Run tests
	uv run pytest

lint: ## Check formatting and lint
	uv run ruff format --check .
	uv run ruff check .

format: ## Format and autofix
	uv run ruff format .
	uv run ruff check --fix .

check: lint test ## Lint and test

eval-quick: ## F1 eval on the dev subset (before a push)
	uv run python -m evals.run --quick

eval: ## F1 eval on all training cases (before submitting)
	uv run python -m evals.run
