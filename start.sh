#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[VisionSense]${RESET} $*"; }
success() { echo -e "${GREEN}[VisionSense]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[VisionSense]${RESET} $*"; }
error()   { echo -e "${RED}[VisionSense]${RESET} $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e ""
echo -e "${BOLD}  ██╗   ██╗██╗███████╗██╗ ██████╗ ███╗   ██╗${RESET}"
echo -e "${BOLD}  ██║   ██║██║██╔════╝██║██╔═══██╗████╗  ██║${RESET}"
echo -e "${BOLD}  ██║   ██║██║███████╗██║██║   ██║██╔██╗ ██║${RESET}"
echo -e "${CYAN}  ╚██╗ ██╔╝██║╚════██║██║██║   ██║██║╚██╗██║${RESET}"
echo -e "${CYAN}   ╚████╔╝ ██║███████║██║╚██████╔╝██║ ╚████║${RESET}"
echo -e "${CYAN}    ╚═══╝  ╚═╝╚══════╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝${RESET}"
echo -e "${BOLD}  VisionSense Studio  —  by XronAI${RESET}"
echo -e ""

# ── only requirement: Docker ──────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || \
  error "Docker not found. Install Docker Desktop from https://docker.com/products/docker-desktop"

docker info >/dev/null 2>&1 || \
  error "Docker is not running. Please start Docker Desktop first."

success "Docker is running."

# ── detect GPU → choose compose file ─────────────────────────────────────────
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.mac.yml"   # default: CPU / Mac
MEDIA_AGENT_PID=""

if command -v nvidia-smi >/dev/null 2>&1; then
  GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo "")
  if [[ -n "$GPU_NAME" ]]; then
    success "NVIDIA GPU detected: $GPU_NAME — using GPU build."
    COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
  fi
else
  warn "No NVIDIA GPU — using Mac / CPU compose profile."
fi

# MediaMTX must be reachable before the native agent starts publishing WHIP.
info "Starting the WebRTC media server..."
docker compose -f "$COMPOSE_FILE" up -d mediamtx
for _ in {1..30}; do
  if curl -sS http://127.0.0.1:8889/ >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done
success "WebRTC media server is ready."

# ── native media agent ───────────────────────────────────────────────────────
if curl -fsS http://127.0.0.1:9010/health >/dev/null 2>&1; then
  success "Native media agent is already running."
else
  info "Building and starting the native media agent..."
  "$SCRIPT_DIR/scripts/build-media-agent.sh"
  VS_MEDIA_PUBLISH_BASE="${VS_MEDIA_PUBLISH_BASE:-rtsp://127.0.0.1:8554}" \
  VS_WEBRTC_PUBLIC_BASE="${VS_WEBRTC_PUBLIC_BASE:-http://localhost:8889}" \
    "$SCRIPT_DIR/media-agent/build/visionsense-media-agent" --port 9010 &
  MEDIA_AGENT_PID=$!
  for _ in {1..30}; do
    if curl -fsS http://127.0.0.1:9010/health >/dev/null 2>&1; then
      break
    fi
    sleep 0.2
  done
  curl -fsS http://127.0.0.1:9010/health >/dev/null 2>&1 || \
    error "Native media agent did not become ready."
  success "Native media agent started (PID $MEDIA_AGENT_PID)."
fi

# ── cleanup on Ctrl+C ─────────────────────────────────────────────────────────
cleanup() {
  echo -e "\n${YELLOW}[VisionSense]${RESET} Stopping containers..."
  docker compose -f "$COMPOSE_FILE" down
  if [[ -n "$MEDIA_AGENT_PID" ]]; then
    kill "$MEDIA_AGENT_PID" >/dev/null 2>&1 || true
  fi
  success "Stopped. Goodbye!"
}
trap cleanup EXIT INT TERM

# ── build + start ─────────────────────────────────────────────────────────────
info "Building images (first run takes a few minutes, cached after that)..."
docker compose -f "$COMPOSE_FILE" build

echo -e ""
echo -e "${BOLD}  ╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}  ║  VisionSense Studio is starting...   ║${RESET}"
echo -e "${BOLD}  ╠══════════════════════════════════════╣${RESET}"
echo -e "${BOLD}  ║  App  →  http://localhost:3000        ║${RESET}"
echo -e "${BOLD}  ║  API  →  http://localhost:8000        ║${RESET}"
echo -e "${BOLD}  ╚══════════════════════════════════════╝${RESET}"
echo -e ""
echo -e "  Press ${BOLD}Ctrl+C${RESET} to stop everything.\n"

docker compose -f "$COMPOSE_FILE" up
