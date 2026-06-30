#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# VisionSense Studio — GPU bootstrap for the Ubuntu / RTX box (PLAN.md Phase 0→1)
#
# Brings a bare Ubuntu machine to the point where the pipeline runs on the GPU:
#   1. NVIDIA driver           (needs sudo + a REBOOT, then re-run this script)
#   2. CUDA-enabled PyTorch     into the project venv (replaces the CPU build)
#   3. TensorRT + onnx + pynvml + PyNvVideoCodec (NVDEC) into the venv
#   4. Redis                    (via docker if present, else apt)
#   5. Build the YOLO26 .engine for THIS exact GPU  (scripts/export_model.py)
#
# Idempotent: every phase checks if it is already satisfied and skips if so.
# Run from the repo root:   bash scripts/setup_gpu.sh
#
# NOTE: this is the part that genuinely needs root. The rest of the project
# (Python 3.12 venv + CPU deps) is set up by uv with no sudo — see README.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
VENV="$REPO/.venv"
PY="$VENV/bin/python"
# CUDA wheel index for Ampere (RTX 3070 Ti). cu124 works with driver >= 550.
CUDA_INDEX="${CUDA_INDEX:-https://download.pytorch.org/whl/cu124}"

say()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mXX %s\033[0m\n' "$*" >&2; exit 1; }

# ── preflight ────────────────────────────────────────────────────────────────
say "Preflight"
lspci 2>/dev/null | grep -qi nvidia || die "No NVIDIA GPU found on the PCI bus."
echo "GPU: $(lspci | grep -i 'vga\|3d' | grep -i nvidia | head -1)"
[ -x "$PY" ] || die "venv missing at $VENV — create it first:  uv venv --python 3.12 .venv"

# ── 1) NVIDIA driver ─────────────────────────────────────────────────────────
say "1) NVIDIA driver"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    echo "Driver already working:"
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
else
    warn "nvidia-smi not working — installing the recommended driver (needs sudo)."
    warn "A REBOOT is required afterwards. Re-run this script after rebooting."
    sudo apt-get update
    # ubuntu-drivers picks the best driver for this GPU automatically.
    sudo apt-get install -y ubuntu-drivers-common
    # ubuntu-drivers auto-picks the best driver for this GPU+kernel; 570 is the
    # current stable fallback on Ubuntu 26.04 for the RTX 3070 Ti (Ampere).
    sudo ubuntu-drivers install || sudo apt-get install -y nvidia-driver-570
    die "Driver installed. REBOOT now ('sudo reboot'), then re-run: bash scripts/setup_gpu.sh"
fi

# ── 2) CUDA PyTorch into the venv ────────────────────────────────────────────
say "2) CUDA-enabled PyTorch (venv)"
if "$PY" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
    echo "torch already sees CUDA: $("$PY" -c 'import torch;print(torch.__version__, torch.version.cuda)')"
else
    UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
    [ -x "$UV" ] || die "uv not found — install it: curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "Installing torch/torchvision from $CUDA_INDEX (replaces the CPU build)…"
    "$UV" pip install --python "$PY" --reinstall torch torchvision --index-url "$CUDA_INDEX"
    "$PY" -c "import torch; assert torch.cuda.is_available(); print('CUDA OK:', torch.cuda.get_device_name(0))"
fi

# ── 3) TensorRT + NVDEC + telemetry ──────────────────────────────────────────
say "3) TensorRT / onnx / pynvml / PyNvVideoCodec (venv)"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
"$UV" pip install --python "$PY" tensorrt onnx onnxruntime-gpu pynvml || \
    warn "tensorrt/onnxruntime-gpu install hit an issue — check CUDA version match."
# PyNvVideoCodec is the zero-copy NVDEC path; optional, don't fail the run on it.
"$UV" pip install --python "$PY" PyNvVideoCodec || \
    warn "PyNvVideoCodec not installed — pipeline will use the OpenCV/FFmpeg decode path."

# ── 4) Redis ─────────────────────────────────────────────────────────────────
say "4) Redis (event bus)"
if "$PY" - <<'EOF' 2>/dev/null
import socket; s=socket.create_connection(("localhost",6379),1); s.close()
EOF
then
    echo "Redis already reachable on localhost:6379."
elif command -v docker >/dev/null 2>&1; then
    echo "Starting redis via docker…"
    docker run -d --restart unless-stopped --name vss-redis -p 6379:6379 redis:7-alpine || \
        warn "could not start redis container (already running?)"
else
    warn "No docker — installing redis-server via apt (needs sudo)."
    sudo apt-get update && sudo apt-get install -y redis-server
    sudo systemctl enable --now redis-server || true
fi
echo "Tip: set redis.enabled=true in config/settings.yaml to publish to the stream."

# ── 5) Build the TensorRT engine for THIS GPU ────────────────────────────────
say "5) Build YOLO26 TensorRT engine (GPU-specific)"
WEIGHTS="models/yolo26n.pt"
ENGINE="models/yolo26n.engine"
[ -f "$WEIGHTS" ] || { echo "Fetching $WEIGHTS…"; "$PY" -c "from ultralytics import YOLO; YOLO('yolo26n.pt')"; mv -f yolo26n.pt "$WEIGHTS" 2>/dev/null || true; }
if [ -f "$ENGINE" ]; then
    echo "Engine already present: $ENGINE (delete it to rebuild)."
else
    echo "Building $ENGINE (FP16, dynamic batch ≤15, imgsz 640) — takes a few minutes…"
    "$PY" scripts/export_model.py "$WEIGHTS" 640 15
fi

say "Done"
cat <<EOF
GPU stack ready. Verify and run:

  .venv/bin/python -c "import torch; print('CUDA', torch.cuda.is_available(), torch.cuda.get_device_name(0))"
  .venv/bin/python scripts/benchmark.py            # confirm the 8–12 FPS/cam @ 15 cams target
  .venv/bin/python -m src.main                     # then open http://<server-ip>:8000/

Set real RTSP substream URLs and enabled:true in config/cameras.yaml first.
The .engine is loaded automatically once model.device resolves to cuda:0.
EOF
