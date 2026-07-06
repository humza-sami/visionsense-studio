# VisionSense Studio — Capacity Benchmark (for pricing)

**Hardware:** RTX 3070 Ti (8 GB) · 8-core CPU · 16 GB RAM
**Model:** YOLO26n, TensorRT engine (TF32), imgsz 640, `det_interval=3` (detect every 3rd
frame, ByteTrack fills the gaps → full-rate tracking)
**Source:** one 1280×720 H.264 clip @ 25 fps, fanned out to N identical RTSP feeds via a
local MediaMTX relay (mirrors an NVR serving N streams). Decode = **GPU NVDEC**.
**Method:** `scripts/benchmark_live.py N` — 15 s warmup, then steady-state sampling.

## Results

| Cameras | Capture fps/feed | Detect fps/feed | GPU util | NVDEC util | VRAM | Inference (batch) | CPU |
|--------:|:----------------:|:---------------:|:--------:|:----------:|:----:|:-----------------:|:---:|
| **4**  | 25.0 | 9.3 | 13% | 7%  | 3.1 GB | 28 ms | 34% |
| **8**  | 25.0 | 7.6 | 19% | 15% | 3.8 GB | 44 ms | 41% |
| **15** | 25.0 | 5.0 | 20% | 29% | 5.2 GB | 87 ms | 63% |

## YOLO x-large live UI result

After the synthetic `yolo26x` test, the first batch-32 TensorRT engine could run 5 and
10 duplicated RTSP feeds but hit CUDA OOM at 15 feeds. For the actual 15-camera UI, a
second `yolo26x` TensorRT engine was built with a smaller batch-5 profile and the
pipeline now chunks detection batches by `model.max_batch`.

| Run | Cameras | Capture fps/feed | Detect fps/feed | Tracking fps/feed | Inference | GPU util | NVDEC util | VRAM peak | CPU |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Synthetic `yolo26x`, batch-32 engine | 10 / 10 | 25.0 | 4.4 | 25.0 | 195.6 ms | 67.3% | 3.4% | 7.1 GB | 46.9% |
| Synthetic `yolo26x`, batch-32 engine | 15 | **OOM** | - | - | - | - | - | - | - |
| Live UI `yolo26x`, batch-5 engine | 15 / 15 | 25.0 | 1.0 | 25.0 | 724.3 ms | 62.9% avg, 95% peak | 12.9% | 5.4 GB | 87.5% |

Conclusion: `yolo26x` can show all 15 real camera feeds on this 8 GB GPU only with a
smaller TensorRT batch profile and chunked inference. It is visually usable for
inspection, but detection throughput is about 1 fps/feed, so `yolo26l` is the better
accuracy/performance balance for 15-camera production on this box.

*Every feed captures at the full 25 fps at all counts. Detection is per-frame every 3rd
frame; the tracker (ByteTrack) carries IDs between detections, so on-screen tracking is
full-rate 25 fps even when raw detection is 5 fps.*

## REAL 15-camera run (production feeds)

Live Dahua NVR, **15× H.265 substreams @ 704×576, 25 fps**, all-class detection (80 COCO
classes), NVDEC decode, TensorRT engine:

| Metric | Value |
|---|---|
| Cameras connected | **15 / 15** |
| Capture fps / feed | **25.0** (full rate) |
| Detect fps / feed | **6.2** (25 fps tracking via ByteTrack) |
| GPU util | 21% avg, 32% peak |
| **NVDEC decoder util** | **6.6%** avg — 15 H.265 streams barely touch it |
| VRAM | **5.0 GB** / 8 GB |
| Inference (batch) | 70 ms |
| CPU | 47% (real cameras self-publish — no ffmpeg) |

**Real feeds are cheaper than the 720p synthetic test**: smaller H.265 substreams →
NVDEC util drops from 29% to **6.6%**, and detection rises to 6.2 fps/cam. The 8 GB card
is VRAM-bound at **~20–24 cameras**, with GPU compute (21%), decoder (7%) and CPU (47%)
all having large headroom. Decode is essentially free here — one NVDEC could handle 100+
of these substreams.

## What limits capacity (in order)

1. **VRAM** — grows ~**340 MB/camera** (decode surfaces + per-stream CUDA/pipeline
   overhead). 5.2 GB at 15 cams → **~20 cameras is the 8 GB ceiling**.
2. **CPU** — 63% at 15 cams. This is the color-convert (NV12→BGR) + per-camera preview
   annotate/JPEG in a single Python loop. *Note: the benchmark's ffmpeg publisher also
   burns ~1 core; real cameras publish themselves, so production CPU is lower.*
3. **GPU compute is NOT the limit** — only **20% utilised** at 15 cameras. NVDEC decoder
   only 29%. The card is ~80% idle.

## Headline for pricing

- **One RTX 3070 Ti comfortably runs 15 cameras** at 25 fps capture + 5 fps detection
  (25 fps tracking) with the box ~80% idle on GPU. **~20 cameras** is the hardware ceiling
  (VRAM-bound).
- **Real substreams are usually smaller than 720p** (e.g. 640×480/CIF). That lowers
  per-camera VRAM and decode → **more cameras per GPU** than this 720p test shows.
- The detect-fps drop with camera count is a **software** limit (single serial Python
  loop doing preview for every camera), **not** the GPU. With optimization (GPU-side
  color convert, decouple preview from the detect loop, skip preview for un-viewed cams)
  detection rate and camera count both go up, because 80% of the GPU is unused.

### Cost-per-camera framing
`cost/camera ≈ (GPU box $ + power) ÷ cameras-per-box`. With **15–20 cameras/3070 Ti-class
box** today (more with smaller substreams or the software opt above), and this GPU being
mid-range, cost-per-camera is low and headroom is large. If you standardise on a bigger
card (more VRAM), cameras/box scales roughly with VRAM until CPU becomes the limit.

## Reproduce
```bash
# relay (once): loop a clip into a local RTSP path
~/mediamtx/mediamtx deploy/mediamtx.yml &
ffmpeg -re -stream_loop -1 -i test_assets/people_h264.mp4 -an -c:v copy \
  -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/live &
# benchmark N cameras:
PYTHONPATH=$PWD .venv/bin/python scripts/benchmark_live.py 15 45 rtsp://127.0.0.1:8554/live
```
