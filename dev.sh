#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
DATA_DIR="${DATA_DIR:-$SCRIPT_DIR/data}"
FLASK_PORT="${FLASK_PORT:-5000}"

# Colours
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[dev]${NC} $*"; }
warn() { echo -e "${YELLOW}[dev]${NC} $*"; }
err() { echo -e "${RED}[dev]${NC} $*" >&2; }

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

# --- Run tests ---
log "Running unit tests..."
if pytest tests/ --ignore=tests/test_ui_library.py --ignore=tests/test_ui_analysis.py -v --tb=short; then
    log "All tests passed."
else
    err "Tests failed. Fix issues before starting the server."
    exit 1
fi

# --- Ensure data directory ---
mkdir -p "$DATA_DIR"

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

exec python -c "
from server import create_app
app = create_app()
app.run(host='0.0.0.0', port=${FLASK_PORT}, debug=True, use_reloader=True)
"
