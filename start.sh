#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[VisionSense]${RESET} $*"; }
success() { echo -e "${GREEN}[VisionSense]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[VisionSense]${RESET} $*"; }
error()   { echo -e "${RED}[VisionSense]${RESET} $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=/opt/homebrew/bin/python3.13
PIDS=()

echo -e ""
echo -e "${BOLD}  ██╗   ██╗██╗███████╗██╗ ██████╗ ███╗   ██╗${RESET}"
echo -e "${BOLD}  ██║   ██║██║██╔════╝██║██╔═══██╗████╗  ██║${RESET}"
echo -e "${BOLD}  ██║   ██║██║███████╗██║██║   ██║██╔██╗ ██║${RESET}"
echo -e "${CYAN}  ╚██╗ ██╔╝██║╚════██║██║██║   ██║██║╚██╗██║${RESET}"
echo -e "${CYAN}   ╚████╔╝ ██║███████║██║╚██████╔╝██║ ╚████║${RESET}"
echo -e "${CYAN}    ╚═══╝  ╚═╝╚══════╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝${RESET}"
echo -e "${BOLD}  VisionSense Studio  —  by XronAI${RESET}"
echo -e ""

# ── Cleanup on exit ───────────────────────────────────────────────────────────

cleanup() {
  echo -e "\n${YELLOW}[VisionSense]${RESET} Stopping services..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  success "Stopped. Goodbye!"
}
trap cleanup EXIT INT TERM

# ── 1. Check Python ───────────────────────────────────────────────────────────

command -v "$PYTHON" >/dev/null 2>&1 || \
  error "Python 3.13 not found at $PYTHON. Install: brew install python@3.13"

# ── 2. Backend venv ───────────────────────────────────────────────────────────

BACKEND_VENV="$SCRIPT_DIR/backend/.venv"
if [ ! -f "$BACKEND_VENV/bin/uvicorn" ]; then
  info "Setting up backend Python environment (first run, ~3 minutes)..."
  "$PYTHON" -m venv "$BACKEND_VENV"
  "$BACKEND_VENV/bin/pip" install -q --upgrade pip
  info "Installing PyTorch with Metal (MPS) support..."
  "$BACKEND_VENV/bin/pip" install -q torch torchvision
  info "Installing backend dependencies..."
  "$BACKEND_VENV/bin/pip" install -q -r "$SCRIPT_DIR/backend/requirements.txt"
  success "Backend environment ready."
fi

# ── 3. Frontend build ─────────────────────────────────────────────────────────

FRONTEND_DIST="$SCRIPT_DIR/frontend/dist/index.html"
if [ ! -f "$FRONTEND_DIST" ]; then
  info "Building frontend (first run, ~30 seconds)..."
  command -v npm >/dev/null 2>&1 || error "npm not found. Install Node.js from https://nodejs.org"
  cd "$SCRIPT_DIR/frontend"
  npm install --silent
  npm run build --silent
  cd "$SCRIPT_DIR"
  success "Frontend built."
fi

# ── 4. MediaMTX (WebRTC server) ───────────────────────────────────────────────

MTX_BIN="$SCRIPT_DIR/bin/mediamtx"
MTX_CONF="$SCRIPT_DIR/bin/mediamtx.yml"

if [ ! -f "$MTX_BIN" ]; then
  info "Downloading MediaMTX WebRTC server..."
  mkdir -p "$SCRIPT_DIR/bin"
  MTX_VERSION="1.19.1"
  curl -fsSL "https://github.com/bluenviron/mediamtx/releases/download/v${MTX_VERSION}/mediamtx_v${MTX_VERSION}_darwin_arm64.tar.gz" \
    | tar -xz -C "$SCRIPT_DIR/bin"
  success "MediaMTX downloaded."
fi

# Write minimal working config
cat > "$MTX_CONF" << 'MTXEOF'
logLevel: warn
rtspAddress: :8554
webrtcAddress: :8889
webrtcLocalUDPAddress: :8189

paths:
  all_others:
MTXEOF

info "Starting WebRTC media server (mediamtx)..."
"$MTX_BIN" "$MTX_CONF" > /tmp/vs-mediamtx.log 2>&1 &
PIDS+=($!)

for _ in {1..30}; do
  curl -sS http://127.0.0.1:8889/ >/dev/null 2>&1 && break
  sleep 0.3
done
success "WebRTC media server ready  →  :8554 (RTSP) / :8889 (WebRTC)"

# ── 5. Native media agent ─────────────────────────────────────────────────────

MEDIA_AGENT_BIN="$SCRIPT_DIR/media-agent/build/visionsense-media-agent"

if [ -f "$MEDIA_AGENT_BIN" ]; then
  if ! curl -fsS http://127.0.0.1:9010/health >/dev/null 2>&1; then
    info "Starting native media agent (VideoToolbox / H.265 hardware decode)..."
    VS_MEDIA_PUBLISH_BASE="rtsp://127.0.0.1:8554" \
    VS_WEBRTC_PUBLIC_BASE="http://localhost:8889" \
      "$MEDIA_AGENT_BIN" --port 9010 > /tmp/vs-media-agent.log 2>&1 &
    PIDS+=($!)
    for _ in {1..20}; do
      curl -fsS http://127.0.0.1:9010/health >/dev/null 2>&1 && break
      sleep 0.3
    done
    success "Native media agent ready  →  :9010"
  else
    success "Native media agent already running."
  fi
else
  warn "Native media agent binary not found — run scripts/build-media-agent.sh to build it."
fi

# ── 6. Backend ────────────────────────────────────────────────────────────────

info "Starting backend with Metal (MPS) inference..."

# Ensure data directory exists
mkdir -p "$SCRIPT_DIR/backend/data"

cd "$SCRIPT_DIR/backend"
PYTORCH_ENABLE_MPS_FALLBACK=0 \
PYTORCH_MPS_FAST_MATH=1 \
VS_YOLO_DEVICE=mps \
VS_MEDIA_AGENT_URL=http://localhost:9010 \
VS_PREFER_NATIVE_MEDIA=true \
VS_DATABASE_PATH="$SCRIPT_DIR/backend/data/visionsense.db" \
  "$BACKEND_VENV/bin/uvicorn" app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level warning &
PIDS+=($!)
cd "$SCRIPT_DIR"

# Wait for backend to be ready
for _ in {1..30}; do
  curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break
  sleep 0.5
done
curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 || error "Backend failed to start."

echo -e ""
echo -e "${BOLD}  ╔═══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}  ║  VisionSense Studio is running        ║${RESET}"
echo -e "${BOLD}  ╠═══════════════════════════════════════╣${RESET}"
echo -e "${BOLD}  ║  App  →  http://localhost:8000         ║${RESET}"
echo -e "${BOLD}  ║  API  →  http://localhost:8000/api     ║${RESET}"
echo -e "${BOLD}  ║  Docs →  http://localhost:8000/docs    ║${RESET}"
echo -e "${BOLD}  ╠═══════════════════════════════════════╣${RESET}"
echo -e "${GREEN}  ║  Inference: Metal (MPS) on M-series   ║${RESET}"
echo -e "${BOLD}  ╚═══════════════════════════════════════╝${RESET}"
echo -e ""
echo -e "  Press ${BOLD}Ctrl+C${RESET} to stop everything.\n"

wait "${PIDS[0]}"
