# DeepStream YOLO26 — parser, configs & how to run

Production inference path (evaluated & benchmarked July 2026). DeepStream keeps every
frame on the GPU (zero-copy decode → infer → track), which is why the same RTX 3070 Ti
8 GB that maxed ~32 cameras on our Python stack runs **50 real 720p cameras through
YOLO26-xlarge at 30 fps** — the bottleneck is the video decoder (NVDEC), not the AI.
Full results: [`docs/deepstream-benchmark-report.md`](../../docs/deepstream-benchmark-report.md).

## Files

| Path | What it is |
|---|---|
| `parser/nvdsinfer_yolo26.cpp` | Custom bbox parser. YOLO26 is NMS-free (output `[batch,300,6]` = final boxes), so it just thresholds + copies. Build with `cluster-mode=4`. |
| `app_configs/pgie_yolo26{n,s,m,l,x}.txt` | nvinfer config per model size (FP16, 640×640, letterbox, this parser). |
| `app_configs/live_x50.txt` | Reference 50-camera tiled live-demo pipeline (tiled display + OSD). |
| `labels.txt` | 80 COCO class names. |
| `yolo26{n,s,m,l,x}/*.onnx` | ONNX weights (git-ignored; export with `scripts/export_model.py`). |
| `*.engine` | TensorRT FP16 engines (git-ignored; built on first run or via `trtexec`). |

## Prerequisites

- NVIDIA driver 590+, DeepStream 9.0 container (`nvcr.io/nvidia/deepstream:9.0-triton-multiarch`)
- Docker + NVIDIA Container Toolkit
- ONNX weights present in `yolo26<size>/`

## Build the parser (once, inside the container)

```bash
docker run --rm --gpus all -v $PWD/models/deepstream:/models \
  nvcr.io/nvidia/deepstream:9.0-triton-multiarch bash -c \
  "g++ -shared -fPIC -o /models/parser/libnvdsparser_yolo26.so \
   /models/parser/nvdsinfer_yolo26.cpp \
   -I/opt/nvidia/deepstream/deepstream/sources/includes -I/usr/local/cuda/include"
```

## Build a TensorRT engine (once per model, gentle on the driver)

Build with `trtexec` **without streams attached** — building under live load once crashed
the driver's GSP firmware.

```bash
docker run --rm --gpus all -v $PWD/models/deepstream:/models \
  nvcr.io/nvidia/deepstream:9.0-triton-multiarch bash -c \
  "trtexec --onnx=/models/yolo26x/yolo26x.onnx \
   --saveEngine=/models/yolo26x/yolo26x.onnx_b16_gpu0_fp16.engine \
   --fp16 --optShapes=images:16x3x640x640 --maxShapes=images:16x3x640x640"
```

## Benchmark harnesses (in `scripts/`)

| Script | Purpose |
|---|---|
| `benchmark_deepstream.py` | Per-model camera ladder, synthetic + real-NVR modes, crash-safe (per-rung logs, resumable state). |
| `benchmark_nvr_ceiling.py` | Rich-metric ceiling test (p50/p95 latency, dropped frames, read errors, NIC, 4-way bottleneck classification). `SRC=nvr` (real NVR) or `SRC=local` (loopback relay). |
| `start_multipath_relay.sh` | 12-publisher loopback RTSP relay (removes source bottleneck for pure server tests). |
| `run_live_x50.sh` | Launch the 50-camera live demo. |

## Key measured facts (RTX 3070 Ti 8 GB, 720p H.264, FP16, ~2.5 fps detection)

- **Decoder (NVDEC) is the wall:** ~64× 720p30 streams saturate one Ampere decoder
  (~1.8 Gpx/s). Halving resolution (→ 704×576) roughly doubles camera capacity.
- **Compute rarely binds** at alert-grade fps: 15×xlarge + 25×small = 40 cams ran full
  30 fps at **14 % GPU**, 65 % NVDEC, 4.3 GB VRAM.
- **VRAM:** ~1.5 GB base + FP16 engine per distinct model + ~30 MB/camera at 720p.

These anchors calibrate [`frameinsight_estimator.html`](../../frameinsight_estimator.html).

## Building applications on top

The pipeline emits per-frame metadata — class, bounding box, confidence, and a persistent
**track ID** — via a pad probe. Business apps (dwell time on a chair, phone-usage
duration, zone intrusion, footfall) are small rule functions on that metadata stream; the
expensive work (decode + inference + tracking) is already done on GPU. See the 10 rule
kernels in [`docs/builder-spec.md`](../../docs/builder-spec.md).
