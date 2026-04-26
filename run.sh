#!/usr/bin/env bash
# run.sh — Start backend + frontend dev server together
# Usage:
#   ./run.sh          — dev mode (Vite HMR on :5173, API on :8000)
#   ./run.sh --prod   — production mode (serves built frontend from FastAPI on :8000)

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

MODE="dev"
if [[ "$1" == "--prod" ]]; then
  MODE="prod"
fi

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${CYAN}[run]${NC} $*"; }
ok()   { echo -e "${GREEN}[run]${NC} $*"; }
warn() { echo -e "${YELLOW}[run]${NC} $*"; }
die()  { echo -e "${RED}[run]${NC} $*"; exit 1; }

# ── Checks ────────────────────────────────────────────────────────────────────
[[ -f .env ]] || die ".env not found — copy .env.example and fill in QDRANT_URL + QDRANT_API_KEY"

command -v python &>/dev/null || die "python not found"
command -v node   &>/dev/null || command -v npm &>/dev/null || warn "node/npm not found — frontend won't start"

# ── Cleanup on exit ───────────────────────────────────────────────────────────
PIDS=()
cleanup() {
  echo ""
  log "Shutting down..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null && wait "$pid" 2>/dev/null || true
  done
  ok "Done."
}
trap cleanup EXIT INT TERM

# ── Production mode: build first, then serve from FastAPI ─────────────────────
if [[ "$MODE" == "prod" ]]; then
  log "Building frontend..."
  cd frontend
  npm install --silent
  npm run build
  cd "$ROOT"
  ok "Frontend built → frontend/dist"
  log "Starting FastAPI on http://127.0.0.1:8000  (serves frontend + API)"
  python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
  exit 0
fi

# ── Dev mode: backend + Vite in parallel ──────────────────────────────────────
echo ""
echo -e "${BOLD}Income Tax Validator — Dev Mode${NC}"
echo -e "  API   → http://127.0.0.1:8000/docs"
echo -e "  App   → http://127.0.0.1:5173"
echo -e "  Press Ctrl+C to stop both"
echo ""

# Backend
log "Starting FastAPI backend..."
python -m uvicorn backend.main:app \
  --host 127.0.0.1 --port 8000 \
  --reload \
  --reload-dir backend \
  --log-level info \
  2>&1 | sed "s/^/${CYAN}[api]${NC} /" &
PIDS+=($!)

# Wait for backend to be ready
log "Waiting for backend..."
for i in {1..20}; do
  if curl -sf http://127.0.0.1:8000/api/health &>/dev/null; then
    ok "Backend ready"
    break
  fi
  sleep 0.5
done

# Frontend
if command -v npm &>/dev/null && [[ -d frontend ]]; then
  log "Starting Vite dev server..."
  cd frontend
  npm install --silent 2>/dev/null
  npm run dev 2>&1 | sed "s/^/${GREEN}[ui]${NC} /" &
  PIDS+=($!)
  cd "$ROOT"
else
  warn "npm not found — skipping frontend dev server"
fi

# Wait for all background processes
wait
