#!/usr/bin/env bash
# Deploy Groma to an AutoDL instance from your own computer.
#
#   bash deploy/autodl/deploy.sh "ssh -p 54959 root@connect.bjb2.seetacloud.com"
#
# Paste the whole SSH command AutoDL shows you, in quotes. You will be asked for
# the instance password once. Everything else happens on the instance: this
# script only sends bootstrap.sh across and runs it there.
#
# Optional: GROMA_BRANCH=<branch> to deploy something other than main.

set -euo pipefail

SSH_CMD="${1:-}"
if [ -z "$SSH_CMD" ]; then
  echo "usage: bash deploy/autodl/deploy.sh \"ssh -p <PORT> root@<HOST>\"" >&2
  exit 2
fi
case "$SSH_CMD" in ssh\ *) ;; *) echo "the argument should start with 'ssh '" >&2; exit 2 ;; esac

HERE="$(cd "$(dirname "$0")" && pwd)"
BRANCH="${GROMA_BRANCH:-main}"

echo "Deploying branch $BRANCH via: $SSH_CMD"
echo "(you will be asked for the instance password)"
# shellcheck disable=SC2086
$SSH_CMD "GROMA_BRANCH='$BRANCH' bash -s" < "$HERE/bootstrap.sh"
