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
	@echo "then: make api  (uvicorn on :8000)  and  make web  (vite on :5173)"

.PHONY: api
api:  ## Run the API locally against the compose database
	GROMA_DATABASE_URL=postgresql+psycopg://groma:groma-dev@127.0.0.1:5433/groma \
	GROMA_JWT_SECRET=dev-secret-dev-secret-dev-secret-0000 GROMA_ARTEFACT_ROOT=/tmp/groma-artefacts \
	$(PY) uvicorn groma_api.main:app --host 127.0.0.1 --port 8000 --reload

.PHONY: web
web:  ## Run the web app dev server (proxies /api to :8000)
	cd apps/web && npm run dev

.PHONY: web-build
web-build:  ## Build the web app into apps/web/dist
	cd apps/web && npm ci --silent && npm run build

.PHONY: test
test:  ## Unit suite — must stay under 5 seconds
	$(PY) pytest tests/unit tests/golden -m "not slow and not bench"

.PHONY: test-integration
test-integration:  ## API against a real PostGIS (GROMA_TEST_DATABASE_URL)
	GROMA_TEST_DATABASE_URL=$${GROMA_TEST_DATABASE_URL:-postgresql+psycopg://groma:groma-dev@127.0.0.1:5433/groma_test} \
	$(PY) pytest tests/integration -q

.PHONY: test-web
test-web:  ## TypeScript kernel parity and unit tests
	cd apps/web && npx vitest run

.PHONY: test-e2e
test-e2e:  ## Playwright over a running stack (ADCP_E2E_URL, default the Vite dev server)
	cd apps/web && npx playwright test

.PHONY: test-all
test-all: test test-integration test-web  ## Everything except e2e

.PHONY: lint
lint:  ## ruff + mypy + tsc + eslint
	$(PY) ruff check .
	$(PY) ruff format --check .
	$(PY) mypy packages apps/cli apps/api apps/worker
	cd apps/web && npx tsc -b --noEmit && npx eslint src --ext .ts,.tsx

.PHONY: serve
serve:  ## Run the coverage service locally on http://127.0.0.1:6006
	GROMA_SITE_FIXTURE=fixtures/sites/site_alpha.json \
	$(PY) uvicorn groma_api.main:app --host 127.0.0.1 --port 6006 --reload

.PHONY: remote-test
remote-test:  ## Sync to the AutoDL instance and run the suite there
	scripts/dev/remote.sh test

.PHONY: deploy
deploy:  ## Sync the working tree to the instance and run the installer there
	scripts/dev/remote.sh sync
	scripts/dev/remote.sh run "GROMA_SKIP_TESTS=$${GROMA_SKIP_TESTS:-0} bash deploy/autodl/bootstrap.sh"

.PHONY: format
format:  ## Apply ruff formatting and import order
	$(PY) ruff check --fix .
	$(PY) ruff format .

.PHONY: seed
seed:  ## site_alpha fixture into the dev database
	GROMA_DATABASE_URL=postgresql+psycopg://groma:groma-dev@127.0.0.1:5433/groma GROMA_JWT_SECRET=dev-secret-dev-secret-dev-secret-0000 $(PY) groma seed --reset

.PHONY: kernel-bench
kernel-bench:  ## 173,184 cells x 6 cameras x 30 occluders + terrain, target < 800 ms
	$(PY) pytest tests/unit/test_kernel_bench.py -m bench -s

.PHONY: golden
golden:  ## Recompute the site_alpha golden stats. Explain any movement in the commit message.
	$(PY) python scripts/make_golden.py

.PHONY: contracts-ts
contracts-ts:  ## Generate TypeScript types from packages/contracts
	$(PY) python scripts/generate_ts_types.py apps/web/src/api/contracts.ts

.PHONY: kernel-fixture
kernel-fixture:  ## Export the TS kernel parity fixture from the Python kernel
	$(PY) python scripts/make_kernel_fixture.py

.PHONY: clean
clean:  ## Remove caches and build artefacts
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist build
