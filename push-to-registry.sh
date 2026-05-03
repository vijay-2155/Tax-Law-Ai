#!/usr/bin/env bash
# push-to-registry.sh — Build & push TaxIQ to GHCR + Docker Hub
# Usage: ./push-to-registry.sh [version]
#        ./push-to-registry.sh 1.0.0
#        ./push-to-registry.sh          (defaults to "latest")

set -e

# ── Config ────────────────────────────────────────────────────────────────────
GITHUB_USER="vijay-2155"
DOCKERHUB_USER="vijay2155"          # ← change if your Docker Hub username differs
IMAGE_NAME="tax-law-ai"
VERSION="${1:-latest}"

GHCR_IMAGE="ghcr.io/${GITHUB_USER}/${IMAGE_NAME}"
HUB_IMAGE="${DOCKERHUB_USER}/${IMAGE_NAME}"

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${CYAN}[push]${NC} $*"; }
ok()   { echo -e "${GREEN}[push]${NC} $*"; }
warn() { echo -e "${YELLOW}[push]${NC} $*"; }
die()  { echo -e "${RED}[push]${NC} $*"; exit 1; }

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}       TaxIQ — Push to Docker Registries        ${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
log "Version tag  : ${VERSION}"
log "GHCR image   : ${GHCR_IMAGE}:${VERSION}"
log "Hub image    : ${HUB_IMAGE}:${VERSION}"
echo ""

# ── Pre-flight checks ─────────────────────────────────────────────────────────
command -v docker &>/dev/null || die "Docker not found."
docker info &>/dev/null       || die "Docker daemon not running."

# ── Set up buildx builder (multi-platform) ────────────────────────────────────
BUILDER="taxiq-builder"
if ! docker buildx inspect "${BUILDER}" &>/dev/null; then
    log "Creating buildx builder for multi-platform support..."
    docker buildx create --name "${BUILDER}" --driver docker-container --bootstrap
fi
docker buildx use "${BUILDER}"
ok "Buildx builder ready ✓"

# ── Build & push (linux/amd64 + linux/arm64) ──────────────────────────────────
log "Building and pushing (amd64 + arm64) — this takes ~10 minutes on first run..."
echo ""

docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --tag "${GHCR_IMAGE}:${VERSION}" \
    --tag "${HUB_IMAGE}:${VERSION}" \
    $( [[ "${VERSION}" != "latest" ]] && echo "--tag ${GHCR_IMAGE}:latest --tag ${HUB_IMAGE}:latest" ) \
    --push \
    .

echo ""
ok "✅ Successfully pushed TaxIQ ${VERSION} to both registries!"
echo ""
echo -e "  ${CYAN}GHCR:${NC}       ${GHCR_IMAGE}:${VERSION}"
echo -e "  ${CYAN}Docker Hub:${NC} ${HUB_IMAGE}:${VERSION}"
echo ""
echo -e "  ${BOLD}Share this with users:${NC}"
echo -e "  ${GREEN}docker compose up${NC}  (using the published docker-compose.yml)"
echo ""
