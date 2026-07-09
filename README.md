# VisionSense — DeepStream YOLO26

Multi-camera CCTV analytics on NVIDIA DeepStream. Decode → YOLO26 inference → tracking,
all GPU-resident (zero-copy), so one mid-range GPU runs far more cameras than a Python
pipeline: **50 real 720p cameras through YOLO26-xlarge at 30 fps** on an RTX 3070 Ti 8 GB.
The bottleneck is the video **decoder** (NVDEC), not the AI.

## Layout

```
models/deepstream/          production inference path
  parser/nvdsinfer_yolo26.cpp   custom NMS-free bbox parser (YOLO26 → boxes)
  app_configs/pgie_yolo26*.txt  nvinfer config per model size (FP16, 640)
  app_configs/live_x50.txt      50-camera tiled live-demo pipeline
  labels.txt                    80 COCO classes
  README.md                     build + run instructions
  yolo26{n,s,m,l,x}/            ONNX + TensorRT engines (git-ignored)

scripts/
  benchmark_deepstream.py       per-model camera ladder (synthetic + real NVR), crash-safe
  benchmark_nvr_ceiling.py      rich-metric ceiling test (latency, drops, NIC, bottleneck)
  run_live_x50.sh               launch the 50-camera live demo
  start_multipath_relay.sh      12-publisher loopback RTSP relay for pure-server tests
  export_model.py               Ultralytics → ONNX
  build_engine_from_onnx.py     ONNX → TensorRT engine
  setup_gpu.sh / gpu_resume.sh  host GPU/driver setup

deploy/
  mediamtx.yml, mediamtx_multi.yml   RTSP relay configs (benchmarks)
  live_demo/                          browser demo pages

docs/
  deepstream-benchmark-report.md   test plan, results, NVDEC root-cause analysis
  deepstream-evaluation.md         why DeepStream (vs the old Python stack)
  builder-spec.md                  the 10 rule kernels for apps built on the metadata

frameinsight_estimator.html    server-spec calculator (decode/compute/VRAM), DeepStream-calibrated
artifacts/benchmarks/          measured result CSVs
```

## Quick start

Prerequisites: NVIDIA driver 590+, Docker + NVIDIA Container Toolkit, the DeepStream 9.0
container (`nvcr.io/nvidia/deepstream:9.0-triton-multiarch`), and ONNX weights under
`models/deepstream/yolo26<size>/`.

```bash
# 1. export weights → ONNX (once)
python scripts/export_model.py            # or bring your own yolo26*.onnx

# 2. build the parser + a TensorRT engine  (see models/deepstream/README.md)

# 3. point the benchmark at a real NVR and run
export NVR_TMPL='rtsp://USER:PASS@NVR_HOST:554/cam/realmonitor?channel={ch}&subtype=1'
NVR=1 python scripts/benchmark_deepstream.py all 90

# 4. live 50-camera demo
bash scripts/run_live_x50.sh
```

Full build/run detail: [models/deepstream/README.md](models/deepstream/README.md).

## Key measured facts (RTX 3070 Ti 8 GB · 720p H.264 · FP16 · ~2.5 fps detection)

- **NVDEC decoder is the wall** — ~64× 720p30 streams saturate one Ampere decoder
  (~1.8 Gpx/s). Lower-resolution substreams (704×576) roughly double camera capacity.
- **Compute rarely binds** at alert-grade fps: 15×xlarge + 25×small = 40 cams ran full
  30 fps at 14 % GPU, 65 % NVDEC, 4.3 GB VRAM.
- **VRAM** — ~1.5 GB base + FP16 engine per distinct model + ~30 MB/camera at 720p.

These anchors calibrate [frameinsight_estimator.html](frameinsight_estimator.html).

## Building apps on top

The pipeline emits per-frame metadata (class, box, confidence, persistent track ID) via a
pad probe. Apps like dwell-time-on-chair or phone-usage duration are small rule functions
on that stream — detection runs once, rules are cheap. See the 10 kernels in
[docs/builder-spec.md](docs/builder-spec.md).

> **Note.** Camera credentials are read from the `NVR_TMPL` env var — never hardcode them.
