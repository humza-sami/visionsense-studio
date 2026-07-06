"""Download a YOLO26 weight, export ONNX (dynamic), build a TensorRT engine (batch 16).
Sidesteps ultralytics' modelopt requirement by using our own ONNX->engine builder.

  python scripts/build_model.py yolo26s
"""
from __future__ import annotations
import subprocess, sys, os
from pathlib import Path

def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "yolo26s"
    imgsz = int(sys.argv[2]) if len(sys.argv) > 2 else 640
    max_b = int(sys.argv[3]) if len(sys.argv) > 3 else 16
    pt = f"models/{name}.pt"
    onnx = f"models/{name}.onnx"

    from ultralytics import YOLO
    if not Path(pt).exists():
        print(f"downloading {name}.pt ...")
        m = YOLO(f"{name}.pt")            # downloads to CWD
        if Path(f"{name}.pt").exists():
            os.replace(f"{name}.pt", pt)
    else:
        m = YOLO(pt)

    if not Path(onnx).exists():
        print(f"exporting {onnx} (dynamic, imgsz={imgsz}) ...")
        out = m.export(format="onnx", dynamic=True, imgsz=imgsz, simplify=True)
        # ultralytics writes next to the .pt; ensure it's at models/<name>.onnx
        if str(out) != onnx and Path(out).exists():
            os.replace(str(out), onnx)

    print(f"building TensorRT engine (batch {max_b}) ...")
    r = subprocess.run([sys.executable, "scripts/build_engine_from_onnx.py", onnx, str(imgsz), str(max_b)],
                       env={**os.environ, "PYTHONPATH": os.getcwd()})
    return r.returncode

if __name__ == "__main__":
    sys.exit(main())
