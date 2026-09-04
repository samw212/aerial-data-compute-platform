#!/usr/bin/env bash
# Develop on the AutoDL instance from this machine.
#
#   scripts/dev/remote.sh sync            rsync the working tree to the instance
#   scripts/dev/remote.sh run  <cmd...>   run a command in the instance checkout
#   scripts/dev/remote.sh test            sync, then run the unit + golden suite there
#   scripts/dev/remote.sh shell           interactive shell in the checkout
#
# The instance is the execution environment (GPU, Postgres, Redis, ODM); edits are
# made here and mirrored on every sync. Needs the `adcp` SSH host alias
# (~/.ssh/config.adcp) with key auth; see docs/OPERATOR-GUIDE.md.
set -euo pipefail

HOST="${ADCP_SSH_HOST:-adcp}"
REMOTE_APP="${ADCP_REMOTE_APP:-/root/autodl-tmp/groma/app}"
HERE="$(cd "$(dirname "$0")/../.." && pwd)"

sync() {
  rsync -az --delete \
    --exclude '.git/' --exclude '.venv/' --exclude 'node_modules/' \
    --exclude '__pycache__/' --exclude '.pytest_cache/' --exclude '.mypy_cache/' \
    --exclude '.ruff_cache/' --exclude 'apps/web/dist/' --exclude 'AUTODL.md' \
    --exclude 'SPEC.md' --exclude '.DS_Store' \
    "$HERE/" "$HOST:$REMOTE_APP/"
}

run() {
  # shellcheck disable=SC2029
  ssh -o BatchMode=yes "$HOST" "cd '$REMOTE_APP' && export PATH=\"\$HOME/.local/bin:\$HOME/.pixi/bin:\$PATH\" && $*"
}

case "${1:-}" in
  sync)  sync ;;
  run)   shift; run "$@" ;;
  test)  sync; run "uv sync --dev --frozen -q && uv run pytest tests/unit tests/golden -m 'not slow and not bench' -q" ;;
  shell) ssh -t "$HOST" "cd '$REMOTE_APP' && exec bash -l" ;;
  *) sed -n '2,12p' "$0"; exit 2 ;;
esac
