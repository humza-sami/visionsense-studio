"""Clean per-model inference-cost ladder (no capture/preview overhead).

For each model engine, times batched inference on dummy 704x576 frames at several
batch sizes -> ms/batch and amortized ms/frame, plus resident VRAM. This isolates the
pure GPU cost used to calibrate the sizing calculator.

  python scripts/bench_infer_ladder.py run <engine> <weights> <name> <csv>
  python scripts/bench_infer_ladder.py all   <csv>
"""
from __future__ import annotations
import csv, os, subprocess, sys, time

LADDER_CSV = "model_ladder.csv"
BATCHES = [1, 4, 8, 16]
MODELS = [  # name, engine, weights
    ("yolo26n","models/yolo26n.engine","models/yolo26n.pt"),
    ("yolo26s","models/yolo26s.engine","models/yolo26s.pt"),
    ("yolo26m","models/yolo26m.engine","models/yolo26m.pt"),
    ("yolo26l","models/yolo26l.engine","models/yolo26l.pt"),
    ("yolo26x","models/yolo26x.engine","models/yolo26x.pt"),
]
COLUMNS = ["model","engine_MB","imgsz","batch","ms_per_batch","ms_per_frame",
           "throughput_fps","vram_used_MB"]

def nv(q):
    try: return float(subprocess.check_output(["nvidia-smi",f"--query-gpu={q}","--format=csv,noheader,nounits"],text=True).split("\n")[0])
    except: return -1.0

def run_one(engine, weights, name, csv_path):
    import numpy as np
    from src.config import ModelConfig
    from src.inference.engine import Detector
    cfg = ModelConfig(weights=weights, engine=engine, imgsz=640, conf=0.25, iou=0.45,
                      device="cuda:0", classes=None, max_batch=16)
    det = Detector(cfg)
    frame = (np.random.rand(576,704,3)*255).astype("uint8")
    vram = nv("memory.used")
    emb = round(os.path.getsize(engine)/1e6,1) if os.path.exists(engine) else ""
    new = not os.path.exists(csv_path)
    with open(csv_path,"a",newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new: w.writeheader()
        for b in BATCHES:
            frames = [frame]*b
            det.detect_batch(frames); det.detect_batch(frames)  # warmup
            t0=time.monotonic(); N=30
            for _ in range(N): det.detect_batch(frames)
            ms = (time.monotonic()-t0)/N*1000
            w.writerow({"model":name,"engine_MB":emb,"imgsz":640,"batch":b,
                        "ms_per_batch":round(ms,2),"ms_per_frame":round(ms/b,3),
                        "throughput_fps":round(b/ms*1000,1),"vram_used_MB":round(nv("memory.used"))})
            print(f"  {name} b={b:2d}: {ms:6.1f} ms/batch · {ms/b:5.2f} ms/frame · {b/ms*1000:6.1f} fps · VRAM {round(nv('memory.used'))}MB")
    print(f"[ladder] {name}: VRAM at load ≈ {round(vram)}MB")

def main():
    mode = sys.argv[1] if len(sys.argv)>1 else "all"
    if mode=="run":
        run_one(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5] if len(sys.argv)>5 else LADDER_CSV)
        sys.stdout.flush(); os._exit(0)
    csv_path = sys.argv[2] if len(sys.argv)>2 else LADDER_CSV
    if os.path.exists(csv_path): os.remove(csv_path)
    for name,engine,weights in MODELS:
        if not os.path.exists(engine):
            print(f"[skip] {name} — engine missing ({engine})"); continue
        print(f"\n=== {name} ===")
        subprocess.run([sys.executable, __file__, "run", engine, weights, name, csv_path],
                       env={**os.environ,"PYTHONPATH":os.getcwd()})
        time.sleep(3)
    print(f"\nladder CSV: {csv_path}")

if __name__=="__main__":
    sys.exit(main())
