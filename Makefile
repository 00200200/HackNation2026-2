.PHONY: help install data requirements test lint format check eval eval-quick eval-real eval-variants

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

install: ## Install Python dependencies
	uv sync

UZP_REPO := https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026
UZP_CACHE := .cache/uzp

data: ## Refresh data/uzp from the organizer repo (review git diff data/uzp, then commit)
	@if [ -d $(UZP_CACHE)/.git ]; then git -C $(UZP_CACHE) pull -q --ff-only; \
	else git clone -q --depth 1 $(UZP_REPO) $(UZP_CACHE); fi
	rsync -a --delete --exclude .git --exclude UPSTREAM $(UZP_CACHE)/ data/uzp/
	git -C $(UZP_CACHE) log -n 1 --format='%H %cI' > data/uzp/UPSTREAM
	@cat data/uzp/UPSTREAM; git status --short data/uzp | head -20

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

HN_REAL_CORPUS ?= /Users/domin/hn2-real-eval
HN_REAL_SPLIT ?= all
export HN_REAL_CORPUS HN_REAL_SPLIT

eval-real: ## F1 eval on the local real corpus
	@uv run python -m evals.run --corpus "$$HN_REAL_CORPUS" --split "$$HN_REAL_SPLIT"

N ?= 1
SEED ?= 2026

eval-variants: ## Robustness eval on re-rendered variants of the training cases (make eval-variants N=2 SEED=7)
	uv run python -m evals.variants --n $(N) --seed $(SEED)
