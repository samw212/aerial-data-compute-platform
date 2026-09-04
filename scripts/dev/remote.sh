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
# uv.lock pins wheel URLs on files.pythonhosted.org, which the instance reaches
# slowly. The mirror serves byte-identical files under the same path, so the
# hashes in the lock still verify. Rewritten on the instance only.
PYPI_MIRROR="${ADCP_PYPI_MIRROR:-https://mirrors.aliyun.com/pypi/packages/}"

sync() {
  rsync -az --delete \
    --exclude '.git/' --exclude '.venv/' --exclude 'node_modules/' \
    --exclude '__pycache__/' --exclude '.pytest_cache/' --exclude '.mypy_cache/' \
    --exclude '.ruff_cache/' --exclude 'apps/web/dist/' --exclude 'AUTODL.md' \
    --exclude 'SPEC.md' --exclude '.DS_Store' \
    "$HERE/" "$HOST:$REMOTE_APP/"
  # shellcheck disable=SC2029
  ssh -o BatchMode=yes "$HOST" "sed -i 's#https://files.pythonhosted.org/packages/#$PYPI_MIRROR#g' '$REMOTE_APP/uv.lock'"
}

run() {
  # shellcheck disable=SC2029
  ssh -o BatchMode=yes "$HOST" "cd '$REMOTE_APP' && unset http_proxy https_proxy && export PATH=\"\$HOME/.local/bin:\$HOME/.pixi/bin:\$PATH\" UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple && $*"
}

case "${1:-}" in
  sync)  sync ;;
  run)   shift; run "$@" ;;
  test)  sync; run "uv sync --dev --frozen -q && uv run pytest tests/unit tests/golden -m 'not slow and not bench' -q" ;;
  shell) ssh -t "$HOST" "cd '$REMOTE_APP' && exec bash -l" ;;
  *) sed -n '2,12p' "$0"; exit 2 ;;
esac
