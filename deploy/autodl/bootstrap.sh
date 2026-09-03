#!/usr/bin/env bash
# Groma on AutoDL: fresh box to running service in one command. Build-spec 19.2.
#
#   bash bootstrap.sh                # install or update, then start
#   GROMA_BRANCH=main bash bootstrap.sh
#
# Safe to run again at any time: every step checks what is already there. After
# it finishes, `groma-ctl` is on the PATH for day-to-day management; run
# `groma-ctl help` to see what it does.
#
# Layout it creates (all on the persistent data disk):
#
#   /root/autodl-tmp/groma/
#     app/          the repository, with its virtual environment in app/.venv
#     logs/         service and supervisor logs
#     run/          supervisord's socket and pid, plus the generated config
#
# Overrides, mostly for testing this script somewhere that is not AutoDL:
#
#   GROMA_HOME      where everything goes            (default /root/autodl-tmp/groma)
#   GROMA_REPO      git URL or local path to clone   (default the GitHub repository)
#   GROMA_BRANCH    branch to check out              (default main)
#   GROMA_PORT      port to serve on                 (default 6006, AutoDL's exposed port)
#   GROMA_SKIP_TESTS=1   skip the test suite (not recommended)
#
# Slow network (common from mainland China without full acceleration coverage):
#
#   GROMA_PYPI_MIRROR   a PyPI-compatible index URL for package downloads, e.g.
#                       https://pypi.tuna.tsinghua.edu.cn/simple . Does not
#                       speed up the Python interpreter download itself (that
#                       comes from GitHub releases, not PyPI) — for that, make
#                       sure /etc/network_turbo exists and gets sourced above,
#                       or wait it out; it is usually a one-off per instance
#                       image, cached afterwards.
#
# Private repository:
#
#   GROMA_GITHUB_TOKEN   a GitHub token with read access to the repository's
#                        contents. Stored once, in a root-only file on the
#                        instance, so that `groma-ctl update` works afterwards
#                        without asking again. Not needed for a public repository.

set -euo pipefail

GROMA_HOME="${GROMA_HOME:-/root/autodl-tmp/groma}"
GROMA_REPO="${GROMA_REPO:-https://github.com/samw212/aerial-data-compute-platform.git}"
GROMA_BRANCH="${GROMA_BRANCH:-main}"
GROMA_PORT="${GROMA_PORT:-6006}"

APP="$GROMA_HOME/app"
LOGS="$GROMA_HOME/logs"
RUN="$GROMA_HOME/run"

say()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m    ok  %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m    FAILED: %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- prerequisites
say "Checking the machine"
[ "$(id -u)" = "0" ] || fail "run this as root (AutoDL logs you in as root already)"
command -v git  >/dev/null || fail "git is not installed (apt-get install -y git)"
command -v curl >/dev/null || fail "curl is not installed (apt-get install -y curl)"
mkdir -p "$APP" "$LOGS" "$RUN"
ok "root, git and curl present; using $GROMA_HOME"

# AutoDL's academic network acceleration makes GitHub and PyPI reachable at a
# usable speed from mainland China. It is a no-op anywhere it does not exist.
if [ -f /etc/network_turbo ]; then
  # shellcheck disable=SC1091
  source /etc/network_turbo >/dev/null 2>&1 || true
  ok "AutoDL network acceleration enabled for this run"
fi

# ---------------------------------------------------------------------------- uv
say "Installing uv (the Python package manager this project uses)"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
if ! command -v uv >/dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
  export PATH="$HOME/.local/bin:$PATH"
fi
command -v uv >/dev/null || fail "uv did not install; check network access"
ok "uv $(uv --version | awk '{print $2}')"

# ------------------------------------------------------------------------- code
say "Fetching the code ($GROMA_REPO, branch $GROMA_BRANCH)"

# A private GitHub repository needs a token. It goes into git's credential
# store in a root-only file rather than into the remote URL, so it never shows
# up in `git remote -v`, in `groma-ctl where`, or in a pasted screenshot.
if [ -n "${GROMA_GITHUB_TOKEN:-}" ]; then
  CRED="$RUN/git-credentials"
  ( umask 077; printf 'https://x-access-token:%s@github.com\n' "$GROMA_GITHUB_TOKEN" > "$CRED" )
  git config --global credential.helper "store --file=$CRED"
  ok "GitHub token stored in $CRED (readable by root only)"
fi

clone_failed() {
  cat >&2 <<EOF

    Could not fetch $GROMA_REPO (branch $GROMA_BRANCH).

    If the repository is private, GitHub refuses anonymous downloads. Either:
      - make the repository public (GitHub -> Settings -> Danger zone -> Change visibility), or
      - run this again with a read-only token:  GROMA_GITHUB_TOKEN=github_pat_... bash bootstrap.sh
    docs/runbook-autodl.md section 4 walks through creating that token.

    If the branch name is wrong, GROMA_BRANCH=<name> selects another.
EOF
  fail "code download failed"
}

if [ -d "$APP/.git" ]; then
  git -C "$APP" remote set-url origin "$GROMA_REPO"
  git -C "$APP" fetch --quiet origin "$GROMA_BRANCH" || clone_failed
  git -C "$APP" checkout --quiet -B "$GROMA_BRANCH" "origin/$GROMA_BRANCH"
  ok "updated to $(git -C "$APP" rev-parse --short HEAD)"
else
  rm -rf "$APP"
  git clone --quiet --branch "$GROMA_BRANCH" "$GROMA_REPO" "$APP" || clone_failed
  ok "cloned at $(git -C "$APP" rev-parse --short HEAD)"
fi

# ---------------------------------------------------------------- environment
say "Installing Python 3.12 and the project's dependencies"
echo "    First run only: this downloads a Python 3.12 interpreter (if the"
echo "    instance doesn't already have one) plus every package this project"
echo "    needs. It can take a few minutes on a slow connection. Progress"
echo "    below is uv's own output, not ours — a quiet terminal here for a"
echo "    while is normal; a completely blank one for over five minutes on a"
echo "    fresh instance usually means the network to PyPI or GitHub is slow"
echo "    or blocked (GROMA_PYPI_MIRROR helps with PyPI; see the top of this"
echo "    script)."
cd "$APP"
if [ -n "${GROMA_PYPI_MIRROR:-}" ]; then
  export UV_INDEX_URL="$GROMA_PYPI_MIRROR"
  ok "using PyPI mirror $GROMA_PYPI_MIRROR"
fi
# `uv sync` installs a matching Python interpreter itself if none is found, so
# a separate `uv python install` step is redundant — it was also silenced
# (>/dev/null 2>&1), which meant this entire step showed no output at all for
# however long both downloads took, indistinguishable from a genuine hang.
uv sync --dev --frozen
ok "environment ready in $APP/.venv"

# ------------------------------------------------------------------------ tests
if [ "${GROMA_SKIP_TESTS:-0}" != "1" ]; then
  say "Running the test suite (this is how you know the install is good)"
  if uv run pytest tests/unit tests/golden -m "not slow and not bench" >"$LOGS/tests.log" 2>&1; then
    ok "$(tail -n 1 "$LOGS/tests.log")"
  else
    tail -n 30 "$LOGS/tests.log" >&2
    fail "tests failed; nothing was started. Full output: $LOGS/tests.log"
  fi
fi

# ------------------------------------------------------------------ supervisor
say "Installing supervisord (keeps the service running)"
if ! uv tool list 2>/dev/null | grep -q '^supervisor '; then
  uv tool install supervisor --quiet
fi
ok "supervisord $(uv tool run --from supervisor supervisord --version)"

# Render the config template with the real paths.
sed -e "s#__GROMA_HOME__#$GROMA_HOME#g" -e "s#--port 6006#--port $GROMA_PORT#" \
  "$APP/deploy/autodl/supervisord.conf" > "$RUN/supervisord.conf"

# Put the management command on the PATH.
install -m 0755 "$APP/deploy/autodl/groma-ctl" /usr/local/bin/groma-ctl
{
  echo "GROMA_HOME=$GROMA_HOME"
  echo "GROMA_PORT=$GROMA_PORT"
} > "$RUN/env"
cp "$RUN/env" /etc/groma.env
ok "groma-ctl installed to /usr/local/bin"

# ---------------------------------------------------------------------- start
say "Starting the service on port $GROMA_PORT"
groma-ctl start >/dev/null
groma-ctl health || { groma-ctl logs 40 >&2; fail "the service did not come up; see the log above"; }

say "Done"
cat <<EOF

  The Groma coverage service is running on this machine, port $GROMA_PORT.

  See it in your browser:
    AutoDL console -> your instance -> "自定义服务" (Custom service) opens port $GROMA_PORT,
    or from your own computer:
      ssh -L $GROMA_PORT:127.0.0.1:$GROMA_PORT -p <PORT> root@<HOST>   then open http://localhost:$GROMA_PORT

  Manage it:
    groma-ctl status     is it running?
    groma-ctl logs       what is it saying?
    groma-ctl restart    turn it off and on again
    groma-ctl update     fetch the latest code, test it, restart
    groma-ctl help       everything else

EOF
