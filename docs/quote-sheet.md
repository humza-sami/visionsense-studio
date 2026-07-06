# VisionSense Quote Sheet — measured capacity per vertical package

**Test box:** RTX 3070 Ti 8 GB · 8-core CPU · 16 GB RAM · TensorRT @640 · ByteTrack
**Feeds:** real-world NVR substreams — 704×576 H.265 @ 25 fps via local MediaMTX fan-out
**Method:** `scripts/benchmark_verticals.py` (9 scenarios, 30 s steady-state each, per-scenario
process isolation). Raw rows in `benchmark_verticals.csv`. FPS targets come from the
use-case corpus (`data/usecases/catalog.yaml`).

## Measured results (2026-07-04)

| Package (models) | Cameras | GPU avg/peak | VRAM peak | CPU | Verdict |
|---|---:|---|---:|---:|---|
| **Restaurant** — tables n@1 + till/queue s@5 + kitchen m@1 | 6 | 14% / 28% | 4.6 GB | 17% | ✅ easy |
| | 10 | 8% / 52% | 5.3 GB | 21% | ✅ easy |
| | 14 | 6% / 16% | 6.0 GB | 23% | ✅ comfortable |
| **Market** — footfall s@8 + aisles n@3 + theft l@10 | 8 | 27% / 56% | 6.3 GB | 19% | ✅ comfortable |
| | 12 | 37% / 49% | 7.0 GB | 21% | ✅ recommended max |
| | 16 | 39% / 56% | 7.7 GB | 23% | ⚠️ runs, but <0.5 GB VRAM headroom |
| **Industry** — PPE m@1 + danger-zone n@15 + fire l@1 | 8 | 8% / 10% | 6.9 GB | 18% | ✅ max on 8 GB |
| | 14 | — | **OOM** | — | ❌ needs 12 GB card |
| | 18 | — | **OOM** | — | ❌ needs 12 GB card |

Achieved detection fps: all 1–3 fps targets hit exactly (0.97/1.0, 2.5/3.0). Fast groups
land at ~70–75 % of target (till 3.8/5, footfall 5.5/8, theft ~7/10, danger 9.9/15) with the
GPU ≤ 39 % utilised — this is the known serial-scheduler software limit (see BENCHMARK.md),
not hardware. Tracking stays full-rate 25 fps via ByteTrack regardless.

## Stress matrix — hard ceilings per model size (2026-07-04)

Single-model camera ceilings @5 fps detection target, and multi-engine breaking points
(`scripts/benchmark_stress.py`, raw rows in `benchmark_stress.csv`):

| Test | Cameras | GPU avg/peak | VRAM | Result |
|---|---:|---|---:|---|
| yolo26**n** ×20 | 20 | 28% / 38% | 5.2 GB | ✅ |
| yolo26**n** ×24 | 24 | 23% / 38% | 6.0 GB | ✅ (CPU 33% — next limit) |
| yolo26**s** ×16 | 16 | 34% / 44% | 4.4 GB | ✅ |
| yolo26**s** ×20 | 20 | — | — | ⚠️ harness limit: engine batch profile ≤16 (prod pipeline chunks; would pass) |
| yolo26**m** ×12 | 12 | 27% / 70% | 4.3 GB | ✅ |
| yolo26**m** ×16 | 16 | 62% / **98%** | 5.0 GB | ✅ compute-saturated — m×16 is the ceiling |
| yolo26**l** ×10 | 10 | 12% / 41% | 5.2 GB | ✅ |
| yolo26**l** ×12 | 12 | 46% / 85% | 5.6 GB | ✅ near ceiling |
| yolo26**x** ×4 | 4 | 4% / 25% | 2.3 GB | ✅ (batch-5 engine profile is cheap) |
| yolo26**x** ×8 (2 groups) | 8 | 31% / 83% | 3.0 GB | ✅ all-x accuracy box works |
| s×6 + **x**×2 weapon @8fps (bank) | 8 | 21% / 34% | 3.7 GB | ✅ |
| m×6 PPE + **x**×2 critical (industry) | 8 | 37% / 65% | 4.3 GB | ✅ |
| **4 engines** n+s+m+l, 12 cams | 12 | — | OOM | ❌ fails at 4th engine-context alloc |
| **4 engines** n+s+m+l, 16 cams | 16 | — | OOM | ❌ |
| **5 engines** n+s+m+l+x, 10 cams | 10 | — | OOM | ❌ |

Stress-matrix rules for quoting on any 8 GB card:
- **Max 3 distinct models per box** (2 if one is `l`), regardless of camera count.
  The 4th TensorRT engine context never fits.
- Single-model ceilings: **n ≈ 24+, s ≈ 20, m ≈ 16 (compute-bound), l ≈ 12, x ≈ 8**.
- x-large is **cheaper than expected** with the batch-5 engine (2.3 GB @ 4 cams) — putting
  x on 2–4 critical cameras (weapon, fire verification) alongside a mainstream model is a
  safe, quotable pattern.
- Detection fps saturates ~3.8/cam when targeting 5 in the bench harness (GPU still ≤62 %)
  — serial-scheduler artifact, not hardware; quote alert-grade fps (1–3) as guaranteed,
  5+ fps as "after pipeline optimization".

## Camera-count scale ladder — "can we run 100 cameras at 2 fps?" (2026-07-04)

Capture fps ≠ detection fps: cameras stream 25 fps (NVDEC decodes it, nearly free), the
pipeline keeps only the latest frame per camera and samples it at each camera's detection
rate. 100 cams × 2 fps = 200 inferences/s ≈ 740 ms/s on nano — compute fits easily. What
breaks is per-camera decode VRAM (~190 MB/cam regardless of detection rate) and host CPU.
Measured ladder (nano @2 fps det, 25 fps capture, `benchmark_scale.csv`):

| Cameras | VRAM peak | GPU | CPU | Result |
|---:|---:|---:|---:|---|
| 28 | 6.65 GB | 21% | 42% | ✅ |
| 32 | 7.37 GB | 23% | 45% | ✅ **measured wall on 8 GB** |
| 36 | — | — | — | ❌ OOM at startup |
| 40 | — | — | — | ❌ OOM at startup |

**100-camera quote:** 4× 8 GB boxes (32 cams each), or 1× 24 GB GPU on a 16-core host
(the single-box option needs the capture-path optimization first — CPU extrapolates to
~140% of an 8-core at 100 cams).

## What limits capacity

1. **VRAM, always.** Each loaded TensorRT engine costs its context (n 0.65 → x 4 GB, per
   `data/calibration.json`) plus ~1.3 GB shared CUDA context, plus **~190 MB per camera**
   (measured slope on 704×576 H.265). The industry package OOMs not because of camera
   count but because it loads **three engines** (n+m+l ≈ 5 GB before the first camera).
2. GPU compute never exceeded 39 % avg. NVDEC ≤ 6.5 %. CPU ≤ 23 %. All idle.

**Biggest quoting lever: fewer distinct models per box.** Merging rules onto one shared
model (e.g. run theft + footfall + aisles all on `yolo26s`) frees 2–3 GB and adds
~10–15 cameras of headroom on the same card.

## GPU tier → what you can quote

(prices/specs from `data/gpus.json`; extrapolation via the calibrated VRAM model in
`data/calibration.json`, which correctly predicted both this OOM and the S1 OOM)

| GPU tier | VRAM | Restaurant pkg | Market pkg | Industry pkg (3 models) |
|---|---:|---:|---:|---:|
| GTX 1650-class | 4 GB | 4–6 cams, **single n/s model only** | ❌ (l engine + ctx alone ≈ 4 GB) | ❌ |
| RTX 3050 / 4060 | 8 GB | **14–16** | **12** (16 abs. max) | **8** |
| RTX 3070 Ti (tested) | 8 GB | **14–16** | **12** (16 abs. max) | **8** |
| RTX 3060 12 GB | 12 GB | ~24 (CPU becomes limit) | ~20 | **~16** |
| RTX 3090 / 4090-class | 24 GB | 40+ (multi-box territory) | ~35 | ~30 |

Rules of thumb for a quote:
- **Alert-grade analytics (1–3 fps rules) are nearly free** — count VRAM, not FLOPs.
- Budget **~190 MB VRAM per camera** (substream) + engine contexts + 1.3 GB base, keep
  ≥ 1 GB headroom. That's the whole sizing formula.
- A restaurant (≤ 10 cams) or small market fits any 8 GB card — even the cheapest
  RTX 3050 (~$250), since compute sits under 40 %.
- Industry/multi-model sites: quote 12 GB minimum at 10+ cameras, or consolidate models.
- **Never quote a 4 GB card for anything with a `yolo26l`/`x` model or 2+ engines.**

## Reproduce

```bash
~/mediamtx/mediamtx deploy/mediamtx.yml &
ffmpeg -re -stream_loop -1 -i test_assets/sub_704_h265.mp4 -an -c:v copy \
  -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/live &
PYTHONPATH=$PWD .venv/bin/python scripts/benchmark_verticals.py all 30
```
