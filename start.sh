#!/usr/bin/env bash
# start.sh — One-click TaxIQ launcher for Linux/Mac
# Usage: ./start.sh

set -e

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${CYAN}[TaxIQ]${NC} $*"; }
ok()   { echo -e "${GREEN}[TaxIQ]${NC} $*"; }
warn() { echo -e "${YELLOW}[TaxIQ]${NC} $*"; }
die()  { echo -e "${RED}[TaxIQ]${NC} $*"; exit 1; }

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}          TaxIQ — Income Tax AI Assistant        ${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ── Check Docker ──────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    die "Docker not found. Install Docker Desktop from: https://www.docker.com/products/docker-desktop"
fi

if ! docker info &>/dev/null; then
    die "Docker is not running. Please start Docker Desktop and try again."
fi

ok "Docker is running ✓"

# ── Check .env ────────────────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
    warn ".env not found — creating from template..."
    cp .env.example .env
    warn "Please edit .env and set your LLM API key, then run ./start.sh again."
    echo ""
    echo "  Open .env in a text editor and fill in your Ollama Cloud API key"
    echo "  (or leave as-is to use Ollama signed-in mode via the Settings UI)"
    echo ""
    exit 0
fi

ok ".env found ✓"

# ── Start services ────────────────────────────────────────────────────────────
log "Starting TaxIQ services..."
echo ""

# Build if image doesn't exist yet
if ! docker image inspect taxiq-app &>/dev/null 2>&1; then
    log "First run — building Docker image (this takes ~5 minutes)..."
fi

docker compose up -d

echo ""
log "Waiting for TaxIQ to be ready..."

# Poll health endpoint
URL="http://localhost:8000"
READY=false
for i in $(seq 1 60); do
    if curl -sf "$URL/api/health" &>/dev/null; then
        READY=true
        break
    fi
    echo -ne "  ${CYAN}·${NC} Waiting... (${i}/60)\r"
    sleep 3
done

echo ""

if [[ "$READY" == "true" ]]; then
    ok "TaxIQ is ready! ✓"
    echo ""
    echo -e "${BOLD}  → Opening http://localhost:8000${NC}"
    echo ""
    echo -e "  ${CYAN}First run?${NC} Data loads automatically in the background (~2 min)."
    echo -e "  ${CYAN}Stop app:${NC}  docker compose down"
    echo -e "  ${CYAN}Full reset:${NC} docker compose down -v"
    echo ""

    # Open browser
    if command -v xdg-open &>/dev/null; then
        xdg-open "$URL" &>/dev/null &
    elif command -v open &>/dev/null; then
        open "$URL"
    else
        echo "  Open your browser and go to: $URL"
    fi
else
    warn "TaxIQ is taking longer than expected to start."
    echo "  Check logs with: docker compose logs app"
    echo "  App URL: $URL (may still be loading)"
fi
