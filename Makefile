.DEFAULT_GOAL := help
SHELL := /bin/bash

UV ?= uv
PY := $(UV) run --

.PHONY: help
help:  ## List targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install:  ## Sync the uv workspace, including dev tooling
	$(UV) sync --all-extras --dev

.PHONY: dev
dev:  ## docker compose up (postgres+postgis, redis) + uvicorn + vite
	docker compose up -d postgres redis
	@echo "API and web land with M4/M3. Until then: make test, make kernel-bench."

.PHONY: test
test:  ## Unit suite — must stay under 5 seconds
	$(PY) pytest tests/unit tests/golden -m "not slow and not bench"

.PHONY: test-all
test-all:  ## Unit + integration (testcontainers) + Playwright e2e
	$(PY) pytest tests -m "not bench"

.PHONY: lint
lint:  ## ruff + mypy (+ tsc once apps/web exists)
	$(PY) ruff check .
	$(PY) ruff format --check .
	$(PY) mypy packages apps/cli apps/api

.PHONY: serve
serve:  ## Run the coverage service locally on http://127.0.0.1:6006
	GROMA_SITE_FIXTURE=fixtures/sites/site_alpha.json \
	$(PY) uvicorn groma_api.main:app --host 127.0.0.1 --port 6006 --reload

.PHONY: deploy-autodl
deploy-autodl:  ## Deploy to an AutoDL instance: make deploy-autodl SSH="ssh -p 12345 root@host"
	bash deploy/autodl/deploy.sh "$(SSH)"

.PHONY: format
format:  ## Apply ruff formatting and import order
	$(PY) ruff check --fix .
	$(PY) ruff format .

.PHONY: seed
seed:  ## site_alpha fixture into the dev database
	$(PY) groma seed --reset

.PHONY: kernel-bench
kernel-bench:  ## 173,184 cells x 6 cameras x 30 occluders + terrain, target < 800 ms
	$(PY) pytest tests/unit/test_kernel_bench.py -m bench -s

.PHONY: golden
golden:  ## Recompute the site_alpha golden stats. Explain any movement in the commit message.
	$(PY) python scripts/make_golden.py

.PHONY: contracts-ts
contracts-ts:  ## Generate TypeScript types from packages/contracts
	$(PY) python scripts/generate_ts_types.py apps/web/src/api/contracts.ts

.PHONY: clean
clean:  ## Remove caches and build artefacts
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist build
