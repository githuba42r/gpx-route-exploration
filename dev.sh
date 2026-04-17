#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# Colours
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[dev]${NC} $*"; }
warn() { echo -e "${YELLOW}[dev]${NC} $*"; }
err() { echo -e "${RED}[dev]${NC} $*" >&2; }

usage() {
    cat <<EOF
Usage: ./dev.sh [--env-file PATH] [--test | --test-only] [--help]

Starts the GPX Route Exploration Flask dev server. Tests are OFF by default.

Options:
  -e, --env-file PATH   Load environment variables from a dotenv file before
                        starting (e.g. .env.development). Values already set
                        in the shell environment take precedence.
      --test            Run the unit test suite before starting the server.
                        Server starts only if the tests pass.
      --test-only       Run the unit test suite, then exit without starting
                        the server. Exit status mirrors pytest's.
  -h, --help            Show this help and exit.

Environment variables (see .env.example for the full list):
  FLASK_PORT            Port for the Flask dev server (default: 5050)
  DATA_DIR              Directory for route/backup storage (default: ./data)
  VALHALLA_URL          Valhalla routing service URL
  NOMINATIM_URL         Nominatim geocoding service URL
EOF
}

# --- Parse args ---
ENV_FILE=""
RUN_TESTS=0
TEST_ONLY=0
while [ $# -gt 0 ]; do
    case "$1" in
        -e|--env-file)
            [ $# -ge 2 ] || { err "$1 requires a path argument."; exit 2; }
            ENV_FILE="$2"
            shift 2
            ;;
        --env-file=*)
            ENV_FILE="${1#--env-file=}"
            shift
            ;;
        --test)
            RUN_TESTS=1
            shift
            ;;
        --test-only)
            RUN_TESTS=1
            TEST_ONLY=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            err "Unknown argument: $1"
            usage >&2
            exit 2
            ;;
    esac
done

# --- Load dotenv ---
if [ -n "$ENV_FILE" ]; then
    if [ ! -f "$ENV_FILE" ]; then
        err "Env file not found: $ENV_FILE"
        exit 1
    fi
    log "Loading environment from $ENV_FILE..."
    # Shell-set vars win over dotenv (matches python-dotenv / docker-compose).
    # Only KEY=VALUE lines are honoured; comments and blanks are ignored.
    while IFS= read -r line; do
        case "$line" in
            ''|\#*) continue ;;
        esac
        line="${line#export }"
        line="${line# }"
        key="${line%%=*}"
        val="${line#*=}"
        case "$key" in
            *[!A-Za-z0-9_]*|'') continue ;;
        esac
        # Strip matching surrounding single or double quotes.
        case "$val" in
            \"*\") val="${val#\"}"; val="${val%\"}" ;;
            \'*\') val="${val#\'}"; val="${val%\'}" ;;
        esac
        if [ -z "${!key+x}" ]; then
            export "$key=$val"
        fi
    done < "$ENV_FILE"
fi

DATA_DIR="${DATA_DIR:-$SCRIPT_DIR/data}"
FLASK_PORT="${FLASK_PORT:-5050}"

# --- Python venv ---
if [ ! -d "$VENV_DIR" ]; then
    log "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

log "Activating venv..."
source "$VENV_DIR/bin/activate"

log "Installing Python dependencies..."
pip install -q -r "$SCRIPT_DIR/requirements-dev.txt"

# --- Node dependencies ---
if [ ! -d "$SCRIPT_DIR/node_modules" ]; then
    log "Installing Node dependencies..."
    npm --prefix "$SCRIPT_DIR" install
fi

# --- Build frontend ---
log "Building frontend bundles..."
npm --prefix "$SCRIPT_DIR" run build

# --- Run tests (only if --test or --test-only) ---
if [ "$RUN_TESTS" = "1" ]; then
    log "Running unit tests..."
    if pytest tests/ --ignore=tests/test_ui_library.py --ignore=tests/test_ui_analysis.py --ignore=tests/test_ui_create.py -v --tb=short; then
        log "All tests passed."
    else
        err "Tests failed."
        exit 1
    fi
    if [ "$TEST_ONLY" = "1" ]; then
        log "--test-only set, exiting without starting the server."
        exit 0
    fi
fi

# --- Ensure data directory ---
mkdir -p "$DATA_DIR"

# --- Check port availability ---
if ss -tln 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${FLASK_PORT}\$"; then
    err "Port ${FLASK_PORT} is already in use."
    err "  Something else is listening — likely another dev server, Docker, or Swarm service."
    err "  Find it with: sudo ss -tlnp | grep :${FLASK_PORT}   (or: docker service ls)"
    err "  Or pick another port: FLASK_PORT=5051 ./dev.sh"
    exit 1
fi

# --- Start dev server ---
log "Starting Flask dev server on port $FLASK_PORT..."
log "  DATA_DIR=$DATA_DIR"
log "  VALHALLA_URL=${VALHALLA_URL:-http://10.0.1.25:8002}"
log "  NOMINATIM_URL=${NOMINATIM_URL:-http://10.0.1.25:8001}"
log ""
warn "Press Ctrl+C to stop."
echo ""

export DATA_DIR
export FLASK_PORT
export BACKUP_ENABLED="${BACKUP_ENABLED:-false}"
# Re-export anything else the app reads (already exported if loaded from dotenv).
[ -n "${VALHALLA_URL:-}" ] && export VALHALLA_URL
[ -n "${NOMINATIM_URL:-}" ] && export NOMINATIM_URL
[ -n "${FLASK_SECRET_KEY:-}" ] && export FLASK_SECRET_KEY
[ -n "${AUTH_USER_HEADER:-}" ] && export AUTH_USER_HEADER
[ -n "${BACKUP_INTERVAL_HOURS:-}" ] && export BACKUP_INTERVAL_HOURS
[ -n "${BACKUP_DAILY_KEEP:-}" ] && export BACKUP_DAILY_KEEP
[ -n "${BACKUP_WEEKLY_KEEP:-}" ] && export BACKUP_WEEKLY_KEEP
[ -n "${BACKUP_MONTHLY_KEEP:-}" ] && export BACKUP_MONTHLY_KEEP

exec python -c "
from server import create_app
app = create_app()
app.run(host='0.0.0.0', port=${FLASK_PORT}, debug=True, use_reloader=True)
"
