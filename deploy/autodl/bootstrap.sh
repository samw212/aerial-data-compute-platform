#!/usr/bin/env bash
# ADCP on AutoDL: fresh instance to running service in one command. Build spec 19.2.
#
#   bash bootstrap.sh                          # install or update, then start
#   GROMA_BRANCH=main bash bootstrap.sh
#
# Safe to run again at any time: every step checks what is already there. After
# it finishes, `groma-ctl` is on the PATH; `groma-ctl help` lists what it does.
#
# Layout (all on the persistent data disk):
#
#   /root/autodl-tmp/groma/
#     app/         the repository, Python env in app/.venv, web build in app/apps/web/dist
#     data/pg      PostgreSQL data          data/  Redis dump
#     artefacts/   uploads, point clouds, tiles, coverage grids, reports
#     backups/     nightly pg_dump + artefact manifest
#     logs/        one rotated log per program
#     run/         supervisord socket, pids, generated configs
#   /etc/groma.env  settings and secrets (root-only)
#
# Overrides: GROMA_HOME, GROMA_REPO, GROMA_BRANCH, GROMA_PORT (6006),
#            GROMA_SKIP_TESTS=1, GROMA_GITHUB_TOKEN (private repository).

set -euo pipefail

GROMA_HOME="${GROMA_HOME:-/root/autodl-tmp/groma}"
GROMA_REPO="${GROMA_REPO:-https://github.com/samw212/aerial-data-compute-platform.git}"
GROMA_BRANCH="${GROMA_BRANCH:-main}"
GROMA_PORT="${GROMA_PORT:-6006}"
PG_BIN=/usr/lib/postgresql/14/bin

APP="$GROMA_HOME/app"; LOGS="$GROMA_HOME/logs"; RUN="$GROMA_HOME/run"; DATA="$GROMA_HOME/data"
ART="$GROMA_HOME/artefacts"; BACK="$GROMA_HOME/backups"

say()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m    ok  %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m    !!  %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m    FAILED: %s\033[0m\n' "$*" >&2; exit 1; }

# The AutoDL GitHub accelerator slows every other host; use it for git only.
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
PYPI_MIRROR="${GROMA_PYPI_MIRROR:-https://mirrors.aliyun.com/pypi}"

# ---------------------------------------------------------------- prerequisites
say "Checking the machine"
[ "$(id -u)" = "0" ] || fail "run this as root (AutoDL logs you in as root already)"
mkdir -p "$APP" "$LOGS" "$RUN" "$DATA" "$ART" "$BACK"
# The postgres user must be able to traverse to its data directory.
chmod o+x /root "$(dirname "$GROMA_HOME")" "$GROMA_HOME" "$DATA" "$LOGS" 2>/dev/null || true
ok "root; using $GROMA_HOME"
GPU="none"; command -v nvidia-smi >/dev/null && GPU="$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1 || echo none)"
ok "GPU: $GPU"
ok "disk: $(df -h "$GROMA_HOME" | awk 'NR==2{print $4" free of "$2}')"

# --------------------------------------------------------------- system packages
say "Installing system packages (PostgreSQL 14 + PostGIS, Redis, nginx, Node 20, GDAL, PDAL, exiftool, ffmpeg)"
export DEBIAN_FRONTEND=noninteractive
need=""
for p in postgresql-14 postgresql-14-postgis-3 postgresql-client-14 redis-server nginx cron libimage-exiftool-perl ffmpeg gdal-bin pdal libgl1 rsync ca-certificates gnupg; do
  dpkg -s "$p" >/dev/null 2>&1 || need="$need $p"
done
if [ -n "$need" ]; then
  apt-get update -qq
  # shellcheck disable=SC2086
  apt-get install -y -qq --no-install-recommends $need >"$LOGS/apt.log" 2>&1 || { tail -20 "$LOGS/apt.log"; fail "apt install failed; see $LOGS/apt.log"; }
fi
ok "apt packages present"
if ! command -v node >/dev/null || [ "$(node -v | cut -c2-3)" -lt 20 ]; then
  mkdir -p /etc/apt/keyrings
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list
  apt-get update -qq && apt-get install -y -qq nodejs >>"$LOGS/apt.log" 2>&1
fi
ok "node $(node -v), npm $(npm -v)"

# ---------------------------------------------------------------------------- uv
say "Installing uv (the Python package manager this project uses)"
export PATH="$HOME/.local/bin:$PATH"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
ok "uv $(uv --version | awk '{print $2}')"

# ------------------------------------------------------------------------- code
say "Fetching the code ($GROMA_REPO, branch $GROMA_BRANCH)"
if [ -n "${GROMA_GITHUB_TOKEN:-}" ]; then
  ( umask 077; printf 'https://x-access-token:%s@github.com\n' "$GROMA_GITHUB_TOKEN" > "$RUN/git-credentials" )
  git config --global credential.helper "store --file=$RUN/git-credentials"
fi
if [ -d "$APP/.git" ]; then
  git -C "$APP" checkout -q -- uv.lock 2>/dev/null || true
  git -C "$APP" remote set-url origin "$GROMA_REPO"
  git -C "$APP" fetch --quiet origin "$GROMA_BRANCH" || fail "could not fetch $GROMA_BRANCH"
  git -C "$APP" checkout --quiet -B "$GROMA_BRANCH" "origin/$GROMA_BRANCH"
  ok "updated to $(git -C "$APP" rev-parse --short HEAD)"
elif [ -f "$APP/pyproject.toml" ]; then
  ok "using the synced working tree in $APP (no .git)"
else
  rm -rf "$APP"
  git clone --quiet --branch "$GROMA_BRANCH" "$GROMA_REPO" "$APP" || fail "code download failed (private repository? see docs/OPERATOR-GUIDE.md)"
  ok "cloned at $(git -C "$APP" rev-parse --short HEAD)"
fi

# ----------------------------------------------------------------- python env
say "Installing Python 3.12 and the project's dependencies"
cd "$APP"
export UV_PYTHON_INSTALL_MIRROR="${UV_PYTHON_INSTALL_MIRROR:-https://ghfast.top/https://github.com/astral-sh/python-build-standalone/releases/download}"
uv python install 3.12 --quiet >/dev/null 2>&1 || true
# The lock pins files.pythonhosted.org; the mirror serves byte-identical files.
sed -i "s#https://files.pythonhosted.org/packages/#$PYPI_MIRROR/packages/#g" uv.lock
UV_INDEX_URL="$PYPI_MIRROR/simple" uv sync --dev --frozen --quiet --extra m6
ok "environment ready in $APP/.venv"

# ------------------------------------------------------------------- web build
say "Building the web app"
# apps/web/src/api/contracts.ts is generated from packages/contracts and gitignored.
uv run python scripts/generate_ts_types.py apps/web/src/api/contracts.ts >/dev/null
cd "$APP/apps/web"
npm config set registry "${GROMA_NPM_REGISTRY:-https://registry.npmmirror.com}" >/dev/null
npm ci --silent --no-audit --no-fund >"$LOGS/npm.log" 2>&1 || { tail -20 "$LOGS/npm.log"; fail "npm ci failed; see $LOGS/npm.log"; }
npx vite build >"$LOGS/vite-build.log" 2>&1 || { tail -20 "$LOGS/vite-build.log"; fail "web build failed; see $LOGS/vite-build.log"; }
ok "built apps/web/dist ($(du -sh dist | cut -f1))"
cd "$APP"

# ----------------------------------------------------------------- settings
say "Settings"
if [ ! -f /etc/groma.env ]; then
  DBPASS="$(openssl rand -hex 16)"
  ( umask 077; cat > /etc/groma.env <<ENV
GROMA_DATABASE_URL=postgresql+psycopg://groma:${DBPASS}@127.0.0.1:5432/groma
GROMA_REDIS_URL=redis://127.0.0.1:6379/0
GROMA_ARTEFACT_ROOT=${ART}
GROMA_JWT_SECRET=$(openssl rand -hex 32)
GROMA_DEFAULT_SRID=2326
GROMA_MAX_UPLOAD_GB=20
GROMA_KERNEL_MAX_CELLS=2000000
GROMA_MAPS_PROVIDER=hk-landsd
GROMA_NODEODM_URL=
GROMA_COLMAP_BIN=
GROMA_VERSION=$(git -C "$APP" describe --tags --always 2>/dev/null || echo dev)
ENV
  )
  ok "wrote /etc/groma.env (root-only)"
else
  sed -i "s#^GROMA_VERSION=.*#GROMA_VERSION=$(git -C "$APP" describe --tags --always 2>/dev/null || echo dev)#" /etc/groma.env
  ok "/etc/groma.env exists; kept"
fi
# shellcheck disable=SC1091
set -a; . /etc/groma.env; set +a
DBPASS="$(echo "$GROMA_DATABASE_URL" | sed -E 's#.*://groma:([^@]+)@.*#\1#')"

# ---------------------------------------------------------------- postgres
say "PostgreSQL"
PG="$DATA/pg"
if [ ! -f "$PG/PG_VERSION" ]; then
  mkdir -p "$PG"; chown -R postgres:postgres "$DATA"
  ( cd /tmp && su postgres -c "$PG_BIN/initdb -D $PG --auth-local=trust --auth-host=scram-sha-256 -E UTF8 --locale=C.UTF-8" >"$LOGS/initdb.log" 2>&1 ) || fail "initdb failed; see $LOGS/initdb.log"
  su postgres -c "cat >> $PG/postgresql.conf" <<CONF
listen_addresses = '127.0.0.1'
port = 5432
shared_buffers = 512MB
max_connections = 100
unix_socket_directories = '/var/run/postgresql'
log_min_duration_statement = 2000
CONF
  ok "initialised $PG"
fi
mkdir -p /var/run/postgresql && chown postgres:postgres /var/run/postgresql
chown -R postgres:postgres "$DATA/pg"; touch "$LOGS/postgres.log"; chown postgres "$LOGS/postgres.log"

# ---------------------------------------------------------------- supervisor
say "Installing supervisord and rendering the service configs"
uv tool list 2>/dev/null | grep -q '^supervisor ' || uv tool install supervisor --quiet
sed -e "s#__GROMA_HOME__#$GROMA_HOME#g" "$APP/deploy/autodl/supervisord.conf" > "$RUN/supervisord.conf"
sed -e "s#__GROMA_HOME__#$GROMA_HOME#g" -e "s#__GROMA_PORT__#$GROMA_PORT#g" "$APP/deploy/autodl/nginx.conf" > "$RUN/nginx.conf"
mkdir -p "$RUN/nginx-body" "$RUN/nginx-proxy" "$RUN/nginx-fcgi" "$RUN/nginx-uwsgi" "$RUN/nginx-scgi" "$ART/tiles" "$ART/coverage"
install -m 0755 "$APP/deploy/autodl/groma-ctl" /usr/local/bin/groma-ctl
{ echo "GROMA_HOME=$GROMA_HOME"; echo "GROMA_PORT=$GROMA_PORT"; } > "$RUN/env"
ok "configs in $RUN; groma-ctl in /usr/local/bin"

# Start (or restart) the datastores first, then migrate, then everything else.
groma-ctl start postgres redis >/dev/null
for _ in $(seq 20); do su postgres -c "$PG_BIN/pg_isready -q" && break; sleep 1; done
su postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='groma'\"" | grep -q 1 \
  || su postgres -c "psql -qc \"CREATE ROLE groma LOGIN PASSWORD '$DBPASS'\""
su postgres -c "psql -qc \"ALTER ROLE groma PASSWORD '$DBPASS'\""
for db in groma groma_test; do
  su postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='$db'\"" | grep -q 1 || su postgres -c "createdb -O groma $db"
  su postgres -c "psql -q -d $db -c 'CREATE EXTENSION IF NOT EXISTS postgis'"
done
ok "database ready"

say "Applying migrations"
GROMA_ENV_FILE=/etc/groma.env uv run groma migrate >"$LOGS/migrate.log" 2>&1 || { tail -20 "$LOGS/migrate.log"; fail "migrations failed; see $LOGS/migrate.log"; }
ok "schema at head"

if [ "${GROMA_SKIP_TESTS:-0}" != "1" ]; then
  say "Running the test suite (this is how you know the install is good)"
  if GROMA_ENV_FILE=/etc/groma.env GROMA_TEST_DATABASE_URL="postgresql+psycopg://groma:${DBPASS}@127.0.0.1:5432/groma_test" \
     uv run pytest tests/unit tests/golden tests/integration -m "not slow and not bench" >"$LOGS/tests.log" 2>&1; then
    ok "$(grep -E 'passed' "$LOGS/tests.log" | tail -1)"
  else
    tail -30 "$LOGS/tests.log" >&2; fail "tests failed; the services were not started. Full output: $LOGS/tests.log"
  fi
fi

say "Starting all services on port $GROMA_PORT"
# `start` leaves already-running programs alone, so on an update the api and
# worker would keep serving the previous code. Restart the app programs; the
# datastores stay up.
if [ -f "$RUN/supervisord.pid" ] && kill -0 "$(cat "$RUN/supervisord.pid")" 2>/dev/null; then
  groma-ctl restart api worker nginx >/dev/null
else
  groma-ctl start >/dev/null
fi
groma-ctl health || { groma-ctl logs api 40 >&2; fail "the service did not come up; see the log above"; }

SEEDED=""
if ! GROMA_ENV_FILE=/etc/groma.env uv run groma users list 2>/dev/null | grep -q '@'; then
  say "Seeding the sample site and the first admin account"
  SEEDED="$(GROMA_ENV_FILE=/etc/groma.env uv run groma seed --admin-email "${GROMA_ADMIN_EMAIL:-admin@adcp.local}" 2>&1 | tail -3)"
fi

say "Installing the nightly backup"
groma-ctl backup-install >/dev/null 2>&1 || warn "could not install the backup cron; run groma-ctl backup by hand"

say "Done"
cat <<EOM

  ADCP is running on this machine, port $GROMA_PORT.

  Open it: AutoDL console -> your instance -> "自定义服务" (Custom service),
  or from your own computer:  ssh -L $GROMA_PORT:127.0.0.1:$GROMA_PORT -p <PORT> root@<HOST>
                              then http://localhost:$GROMA_PORT
${SEEDED:+
  First sign-in (change the password straight away):
$SEEDED
}
  Manage it:  groma-ctl status | health | logs | restart | update | backup | help
  Guide:      $APP/docs/OPERATOR-GUIDE.md

EOM
