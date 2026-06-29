"""Export YOLO .pt → TensorRT .engine (FP16, dynamic batch). RUN ON THE UBUNTU BOX.

The engine is built for the specific GPU + driver it runs on, so build it on the
3070 Ti, not on your Mac (TensorRT/CUDA don't exist on macOS — this will no-op
there with a clear message).

  python scripts/export_model.py [weights.pt] [imgsz] [max_batch]
"""
from __future__ import annotations

import sys


def main() -> None:
    weights = sys.argv[1] if len(sys.argv) > 1 else "models/yolo26n.pt"
    imgsz = int(sys.argv[2]) if len(sys.argv) > 2 else 640
    batch = int(sys.argv[3]) if len(sys.argv) > 3 else 15

    try:
        import torch
    except Exception:
        print("PyTorch not installed."); sys.exit(1)

    if not torch.cuda.is_available():
        print("No CUDA GPU detected. TensorRT export requires an NVIDIA GPU.")
        print("Run this on the Ubuntu / RTX 3070 Ti box, not on macOS.")
        sys.exit(1)

    from ultralytics import YOLO

    print(f"Exporting {weights} → TensorRT engine (fp16, imgsz={imgsz}, batch≤{batch})")
    model = YOLO(weights)
    model.export(
        format="engine",
        half=True,        # FP16 — uses the Ampere tensor cores
        dynamic=True,     # variable batch size up to `batch`
        batch=batch,
        imgsz=imgsz,
        device=0,
        workspace=4,      # cap TRT scratch on the 8 GB card
    )
    print("Done. Point model.engine in config/settings.yaml at the produced .engine")


if __name__ == "__main__":
    main()
