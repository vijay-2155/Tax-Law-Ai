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
    ok ".env created from template ✓  (using default local Ollama settings)"
fi

ok ".env found ✓"

# ── Determine model to pull ───────────────────────────────────────────────────
OLLAMA_MODEL="${OLLAMA_CHAT_MODEL:-qwen2.5:7b}"
# Read from .env if set there
if grep -q "^OLLAMA_CHAT_MODEL=" .env 2>/dev/null; then
    OLLAMA_MODEL=$(grep "^OLLAMA_CHAT_MODEL=" .env | cut -d'=' -f2 | tr -d '"' | tr -d "'")
fi
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:7b}"

# ── Start services ────────────────────────────────────────────────────────────
log "Starting TaxIQ services (Qdrant + Ollama + App)..."
echo ""

# Pull latest image if not present
if ! docker image inspect ghcr.io/vijay-2155/tax-law-ai:latest &>/dev/null 2>&1; then
    log "First run — pulling TaxIQ image from registry (~2-3 GB, one-time download)..."
    log "Grab a coffee ☕ this takes a few minutes..."
fi

docker compose up -d

echo ""
log "Waiting for Ollama to be ready..."

# Wait for Ollama API to be available
OLLAMA_READY=false
for i in $(seq 1 30); do
    if curl -sf "http://localhost:11434/api/tags" &>/dev/null; then
        OLLAMA_READY=true
        break
    fi
    echo -ne "  ${CYAN}·${NC} Waiting for Ollama... (${i}/30)\r"
    sleep 3
done
echo ""

if [[ "$OLLAMA_READY" == "true" ]]; then
    ok "Ollama is ready ✓"

    # Check if the model is already pulled
    if ! curl -sf "http://localhost:11434/api/tags" | grep -q "\"${OLLAMA_MODEL}\"" 2>/dev/null; then
        log "Pulling model '${OLLAMA_MODEL}' into Ollama (one-time download, ~4-5 GB)..."
        log "This only happens once — models are cached between restarts."
        echo ""
        docker compose exec ollama ollama pull "${OLLAMA_MODEL}" || \
            warn "Model pull failed — the app will retry on first use."
        echo ""
        ok "Model '${OLLAMA_MODEL}' ready ✓"
    else
        ok "Model '${OLLAMA_MODEL}' already cached ✓"
    fi
else
    warn "Ollama is taking longer than expected to start."
    warn "The app will pull the model automatically on first use."
fi

echo ""
log "Waiting for TaxIQ app to be ready..."

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
    echo -e "${BOLD}  → Open: http://localhost:8000${NC}"
    echo ""
    echo -e "  ${CYAN}LLM Model:${NC}  ${OLLAMA_MODEL} (running locally in Docker)"
    echo -e "  ${CYAN}First run?${NC}  Data loads automatically in the background (~2 min)."
    echo -e "  ${CYAN}Stop app:${NC}   docker compose down"
    echo -e "  ${CYAN}Full reset:${NC} docker compose down -v  ⚠ clears models + data"
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
