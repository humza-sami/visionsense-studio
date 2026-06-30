#!/usr/bin/env bash
# Run AFTER the reboot that activated the NVIDIA driver. Verifies the GPU,
# builds the TensorRT engine for this card, and benchmarks it. Idempotent.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
PY=".venv/bin/python"

echo "== 1) nvidia-smi =="
nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used --format=csv,noheader || {
  echo "XX nvidia driver still not active — did the box reboot? (nouveau may still be loaded)"; exit 1; }

echo "== 2) torch sees CUDA =="
$PY -c "import torch; assert torch.cuda.is_available(), 'torch.cuda not available'; print('CUDA OK:', torch.cuda.get_device_name(0), '| torch', torch.__version__)" || exit 1

echo "== 3) build TensorRT engine (FP16, dynamic batch 15, imgsz 640) =="
if [ -f models/yolo26n.engine ]; then
  echo "engine already exists: models/yolo26n.engine (delete to rebuild)"
else
  PYTHONPATH="$PWD" $PY scripts/export_model.py models/yolo26n.pt 640 15 || exit 1
fi

echo "== 4) benchmark =="
PYTHONPATH="$PWD" $PY scripts/benchmark.py 15 50 || true

echo
echo "GPU READY. Launch the pipeline with:"
echo "  PYTHONPATH=\$PWD .venv/bin/python -m src.main   # http://<server-ip>:8000/"
