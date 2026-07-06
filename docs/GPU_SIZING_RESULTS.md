# GPU Sizing Study — Results & Calibrated Model

Measured on **RTX 3070 Ti (8 GB)** · TensorRT (FP16/TF32) · imgsz 640 · H.265 704×576.
All raw data: `model_ladder.csv`, `benchmark_results.csv`, `combinations.csv`.

## 1. Per-model inference cost (clean, batched, no preview overhead)

| Model | ms/frame (batch≥8) | throughput (1 GPU) | COCO mAP | engine MB |
|---|---|---|---|---|
| yolo26n | 3.7 | ~270 fps | 40.9 | 14 |
| yolo26s | 5.2 | ~192 fps | 48.0 | 45 |
| yolo26m | 8.1 | ~124 fps | 52.5 | 96 |
| yolo26l | 9.6 | ~104 fps | 54.5 | 125 |
| yolo26x | 15.5 | ~64 fps | 56.0 | 264 |

**Key fact:** one RTX 3070 Ti delivers **~1000 ms/s of inference** at 100% GPU (verified: 270 fps × 3.7 ms = 295 fps × 3.4 ms = 124 fps × 8.1 ms ≈ 1000). Usable budget ≈ **800 ms/s** at 80%.

## 2. The cost model (calibrated & validated)

For a workload = set of camera **groups** `g` (count, model, resolution, **detection fps**):

```
Inference load   T = Σ  count_g · det_fps_g · ms_per_frame(model_g, imgsz)      [ms/s]
                 fits if  T ≤ 1000 · usable · (GPU_fp16 / 43.5)
VRAM (MB)        = 1300 + Σ_models base(model) + Σ_g count_g · per_cam(res)
                 per_cam(res) = 100 + 0.00021 · (W·H)      (≈185 MB @704×576, ≈535 MB @1080p)
                 base: n650 s900 m1700 l2585 x4024
Decode           = Σ count · input_fps · pixels   vs NVDEC capacity (×decoder count)
```
`ms_per_frame` scales ≈ `(imgsz/640)²` for other input sizes, and inversely with the
target GPU's FP16 throughput.

**Validation against measurements:**
- nano max @low fps → predicted **29**, measured **~30** ✓
- medium ×15 VRAM → predicted 5.78 GB, measured 5.29 GB ✓ (conservative)
- medium+large ×15 → predicted **OOM** (8.36 GB > 8 GB), measured **OOM** ✓

## 3. Mixed-workload scenarios (the point of the study)

Different camera roles need different model+fps. Measured on the 3070 Ti:

| Scenario | Groups | GPU peak | VRAM | CPU | Verdict |
|---|---|---|---|---|---|
| **S2 Retail** | 8× people (small @8) + 4× theft (large @10) | 55% | 6.8 GB | 23% | ✅ fits |
| **S3 Safety** | 12× PPE (medium @3) + 3× fire (xl @1) | 69% | 6.1 GB | 26% | ✅ fits |
| **S4 Mixed-fps** | 5× live (medium @15) + 10× periodic (medium @3) | 75% | 5.3 GB | 24% | ✅ fits |
| **S1 Warehouse** | 10× attendance (medium @10) + 5× fire (large @1) | — | **>8 GB** | — | ❌ **OOM** → needs ≥12 GB or lighter models |

**Lesson:** two *heavy* models (medium **and** large) resident together eat ~2.4 GB of TensorRT
context each — on 8 GB that leaves no room for 15 cameras. Fix: use a lighter model for the
high-count group (small for attendance), or a bigger-VRAM GPU.

## 4. MAX CAMERAS — RTX 3070 Ti (8 GB), 704×576 input

By model × detection fps (V = VRAM-bound, C = compute-bound, 80% usable GPU):

| Model | @1 fps | @2 fps | @5 fps | @10 fps | @15 fps | @25 fps |
|---|---|---|---|---|---|---|
| yolo26n | 29 (V) | 29 | 29 | 27 (C) | 18 | 10 |
| yolo26s | 27 (V) | 27 | 27 | 19 (C) | 12 | 7 |
| yolo26m | 23 (V) | 23 | 23 | 12 (C) | 8 | 4 |
| yolo26l | 18 (V) | 18 | 18 | 10 (C) | 6 | 4 |
| yolo26x | 11 (V) | 11 | 11 | 6 (C) | 4 | 2 |

**Read this as:** low-fps tasks (fire/parking) are **VRAM-bound** — you can pack many; high-fps
tasks (attendance/theft) are **compute-bound** — far fewer. This is exactly why mixing pays off.

## 5. What changes on other GPUs
- **More VRAM** → the V (low-fps) numbers scale ~linearly (12 GB ≈ 1.5×, 24 GB ≈ 3×).
- **More FP16 throughput** → the C (high-fps) numbers scale by the FP16 ratio.
- **More NVDEC engines** → more raw decode headroom (rarely the limit for substreams).

The interactive calculator (`gpu_calculator.html`) applies all of the above to any workload +
any GPU in `data/gpus.json`.

## Caveat
The current single-Python-loop pipeline delivers ~50–60% of the GPU's inference *capacity*
(it is loop-bound on preview/color-convert, GPU sat ~50% while fps caps). The calculator sizes
to **GPU capacity** (what an efficient multi-worker or DeepStream implementation reaches) with
an adjustable "usable %" slider; keep it at 60–70% to size for the current implementation.
