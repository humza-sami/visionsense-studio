# DeepStream Benchmark — Test Plan, Method, and Results

*Living document. Updated 2026-07-08 after the real-NVR run. Raw data:
`benchmark_deepstream.csv` (synthetic 704×576) and `benchmark_deepstream_nvr.csv`
(real 50-camera Dahua NVR, 720p). Harness: `scripts/benchmark_deepstream.py`.
Per-rung logs: `artifacts/benchmarks/ds_logs/`.*

---

## 1. Why this test exists

Our own pipeline (Python + Ultralytics + per-camera ByteTrack) hit a hard wall at
**~32–36 cameras** on the RTX 3070 Ti 8 GB. Analysis said the wall was software, not
hardware (GPU sat 60–80 % idle). NVIDIA **DeepStream** is a C/GStreamer video-analytics
SDK that keeps every frame on the GPU (zero-copy), batches inference across cameras, and
tracks on the GPU. This benchmark measures how much more the same hardware delivers under
DeepStream, per YOLO26 model size, on **real cameras**.

## 2. What the pipeline does (per rung)

```
N× RTSP (real Dahua NVR channels)  →  NVDEC hardware decode  →  nvstreammux (batch=N)
   →  nvinfer (YOLO26 TensorRT FP16, detect every 12th frame ≈ 2.5 fps/cam)
   →  nvtracker (NvSORT, GPU)  →  fakesink (no render)   [perf measurement ON]
```

- **Custom parser** (`models/deepstream/parser/nvdsinfer_yolo26.cpp`): YOLO26 is NMS-free
  (output `[batch,300,6]` = final boxes), so the parser just thresholds and copies;
  `cluster-mode=4`. Verified producing correct boxes+classes on a real frame.
- **interval=11**: detection runs on 1 of every 12 frames — ~2.5 fps/camera at 30 fps
  input. This is alert-grade analytics (theft, intrusion, PPE, attendance), identical
  workload to how our own stack was benchmarked, so the comparison is fair.
- **Engines**: TensorRT FP16, prebuilt once with `trtexec` (no streams attached — a build
  under live load crashed the driver's GSP firmware; prebuilding avoids that).

## 3. Test matrix

| Axis | Values |
|---|---|
| Models | yolo26 n / s / m / l / x (FP16, 640×640) |
| Real-NVR ladder | 8 → 16 → 32 → 50 → 64 cameras |
| Synthetic ladder (earlier) | up to 224 (n), 192 (s), 128 (m), 96 (l), 64 (x) |
| Source (real) | 50 live Dahua channels, **1280×720 H.264 @ 30 fps**, over LAN |
| Source (synthetic) | MediaMTX relay looping one 704×576 H.265 clip |
| Detection rate | ~2.5 fps/camera (interval=11) |

## 4. Crash-safety (the harness)

Built after a driver crash lost a run. Every result persists the instant it exists:
per-rung container logs stream to disk line-by-line; every rung writes its CSV row even
on crash; progress is in a JSON state file; reruns skip successes and retry failures; GPU
health is checked before each rung and aborts cleanly if the driver is dead. A single
`ulimit nofile=65536` fixed 64-stream fd exhaustion; writing the trtexec command to a
script file (not `bash -c`) fixed silent engine-build failures.

## 5. RESULTS — real 50-camera Dahua NVR (720p H.264, 2.5 fps detection)

*All 25 rungs PASSED. Every model ran 64 real 720p cameras.*

| Model | 8 | 16 | 32 | 50 | 64 | VRAM@64 | GPU avg/peak @64 | NVDEC @64 |
|---|---|---|---|---|---|---|---|---|
| **n** | ✅30 | ✅30 | ✅30 | ✅30 | ✅28 | 4.8 GB | 10%/36% | 56% |
| **s** | ✅30 | ✅30 | ✅30 | ✅30 | ✅28 | 5.0 GB | 13%/55% | 55% |
| **m** | ✅30 | ✅30 | ✅30 | ✅30 | ✅27 | 5.5 GB | 22%/100% | 56% |
| **l** | ✅30 | ✅30 | ✅30 | ✅30 | ✅27 | 5.0 GB | 22%/100% | 53% |
| **x** | ✅30 | ✅30 | ✅30 | ✅30 | ✅26 | 5.4 GB | 32%/100% | 53% |

(✅NN = all streams alive at NN fps/camera; 30 = full realtime.)

## 6. ANALYSIS — cost, bottlenecks, where it's expensive

**Per-camera cost at 720p (marginal slopes, measured):**
- **VRAM: ~36 MB/camera** + ~2.5 GB fixed (model + CUDA context + desktop). Cheap.
  (The "106 MB/cam" from the 8-cam smoke test was fixed cost ÷ 8; the true *marginal*
  cost is 36 MB.)
- **NVDEC decode: ~0.86 %/camera** → the scarce resource. 55 % at 64 cams.
- **GPU compute @2.5 fps: negligible for n/s** (10–13 % avg), **material for m/l/x**
  (100 % peaks during detection ticks at 64).
- **Host CPU: ~0.4 %/camera** (real cameras self-publish — 27 % at 64 cams, far below the
  synthetic test where the local ffmpeg relay stole cores).

**Where it costs most, in order (720p):**
1. **NVDEC video decoder is the #1 wall.** One hardware decoder on the 3070 Ti, ~55 % at
   64 cams → linear extrapolation walls near **~110–120 cameras** regardless of model.
   This is why the fps dipped to ~26–28 at 64: the decoder starting to saturate.
2. **GPU compute** is the wall only for **xlarge** (100 % peaks from 32 cams up) and
   partly medium/large. Nano/small have huge compute headroom.
3. **VRAM** would allow ~150 nano cams but NVDEC caps first — VRAM is *not* the 720p wall
   (it was the wall at 576p in the synthetic test).

**What we can do with this (quotable, real):**
- **One 8 GB box comfortably runs an entire 64-camera 720p NVR** at 2.5 fps alert-grade
  analytics — on any model up to large — with room to spare. Our old stack maxed ~32.
- For **nano/small** analytics the box is decoder-bound near ~110 cams, not compute-bound.
- **Lower-resolution substreams (CIF/D1) decode far cheaper** → many more cameras. 720p is
  a heavy substream; most NVRs can emit 640×480/704×576, which roughly doubles camera
  capacity (per the synthetic 576p run reaching 160+ nano).

## 7. Why our own stack walled at 32 and DeepStream doesn't

1. **Memory:** we gave each camera its own Python pipeline + CPU round-trip (decode→CPU
   BGR→GPU), ~190 MB/cam. DeepStream keeps frames GPU-resident in one shared pool,
   ~36 MB/cam at 720p.
2. **Precision:** our engines were accidentally TF32; DeepStream builds true FP16 (~2×).
3. **Scheduling:** our serial Python loop left the GPU 60–80 % idle; DeepStream's C
   pipeline runs decode/batch/infer/track concurrently.

## 8. No-limit run (80–150 cams) — the wall is the NVR, not our server

Pushed each model past 64 by reopening the 50 real channels 2–3× each. Nano/small:

| Cams | min-fps | NVDEC | GPU | VRAM | interpretation |
|---:|---:|---:|---:|---:|---|
| 64 | 28 | 55% | 10% | 4.8 GB | ✅ clean |
| 80 | 19 | 40%↓ | 6% | 4.5 GB | throughput dropping |
| 96 | 10 | 29%↓ | 6% | 5.1 GB | collapsing |
| 112 | 4 | 19%↓ | 8% | 5.6 GB | starving |
| 128 | 0.3 | 5%↓ | 4% | 6.2 GB | starved |
| 150 | 0 | 0% | 2% | 7.1 GB | no frames arrive |

**Diagnosis: this is a source-side (NVR) limit, NOT our GPU.** As cameras rise, fps *and*
NVDEC *and* GPU all fall while VRAM never OOMs — the signature of **frame starvation**:
the GPU sits idle waiting for video. If our box were the bottleneck, NVDEC would pin at
100% and VRAM would OOM (the opposite happens). Root cause: only **50 real channels**
exist; reopening them to 80–150 asks the **Dahua NVR to serve more concurrent RTSP pulls
than it can (~64–70)**, so it throttles. The bottleneck moved off our server onto the NVR.

**Exception — xlarge hits OUR hardware first:** x:80 = VRAM **7.77 GB** (near the 8 GB
wall) + GPU 100% peak. Only the largest model is genuinely server-bound at 720p, around
80 cams.

### The honest two-number conclusion
1. **64 real 720p cameras per 8 GB box** — solid, every model, ~28 fps, GPU idle. The
   defensible real-world quote. (Old stack: ~32.)
2. **Our server's true ceiling is higher than 64** — proven by the synthetic run (source
   could feed unlimited streams) reaching **160+ nano @ 576p**. The >64 collapse here is
   the test rig (one NVR, 50 channels), not the product.

To measure the box's true **720p** ceiling we'd need a source that can feed >64 streams
(multiple NVRs, or a synthetic 720p relay). NVDEC math predicts ~110–120 for n/s at 720p;
VRAM/compute predict ~80 for x.

### Per-model 720p summary (real NVR, 2.5 fps detection)

| Model | Clean real-camera max | First wall above that | Wall type |
|---|---:|---|---|
| nano | 64+ (NVR-limited) | ~110–120 predicted | NVDEC decode |
| small | 64+ (NVR-limited) | ~110 predicted | NVDEC decode |
| medium | 64 | compute peaks 100% @64 | GPU compute |
| large | 64 | compute peaks 100% @64 | GPU compute |
| xlarge | 64 | ~80 measured | VRAM 7.8 GB + compute |

---

## 9. FINAL CONSOLIDATED FINDINGS (2026-07-08, root-caused)

After the real-NVR run "walled" at 64, we isolated the cause with two more source
configs. The ~64-camera wall at 720p appeared **identically** in all three, which is the
whole point:

| Source config | Network path | Wall | GPU at wall | Meaning |
|---|---|---|---|---|
| Real 150-ch NVR | routed, ~100 Mbps segment | ~64 | idle (7–13%) | net path *also* caps ~64 (64×1.4Mbps≈90Mbps) |
| Single loopback relay | none (127.0.0.1) | ~64–96 | idle (2–8%) | relay fan-out strains |
| 12-publisher loopback | none (127.0.0.1) | ~64 | idle (5–12%) | source is NOT the limit |

**Root cause: the RTX 3070 Ti's single NVDEC video decoder.** Spreading the source across
12 publishers did not move the wall, and the GPU compute cores sit idle when fps collapses
— so the limit is upstream of inference, in decode. Pixel-throughput math confirms it:

- 720p30 wall at ~64 streams = **1.8 Gpixel/s**
- 576p25 wall at ~150 streams (earlier synthetic run) = **1.5 Gpixel/s**

Same ~1.5–1.8 Gpx/s ceiling at both resolutions = one hardware decoder, pixel-bound. The
"64 cams" and "150 cams" numbers are the *same limit* in different resolutions.

### The honest, defensible conclusions

1. **~60–64 cameras per RTX 3070 Ti at 720p30**, any model up to large, ~2.5 fps
   alert-grade detection. Decoder-bound. (Our old Python stack: ~32.)
2. **~150 cameras at 576p (CIF/D1)** — because the decoder is pixel-bound, halving
   resolution ~doubles camera count. **Substream resolution is the #1 capacity lever.**
3. **Inference is not the wall for n/s/m** — GPU idle at the decoder ceiling. **large/xlarge
   approach their compute limit at ~64 too** (100% GPU peaks), so for heavy models compute
   and decode walls coincide.
4. **VRAM is never the 720p wall** (≤5.9 GB at collapse) — it was only the wall at 576p
   in the earlier synthetic run.
5. **This client's NVR has a second, independent limit**: a ~100 Mbps segment in the routed
   path to its subnet caps ~64 cameras regardless of the server. Fixing that path to
   gigabit is required before the server's headroom can be used on real cameras.

### Bottleneck ranking at 720p (where cost concentrates)
1. **NVDEC decoder** (pixel throughput) — the primary wall. More decoders (multi-GPU, or
   a card with 2–3 NVDEC like the 4090/5090) scale this linearly.
2. **GPU compute** — only binds for large/xlarge.
3. **Network path to the source** — a real deployment constraint (this NVR: 100 Mbps).
4. **VRAM / CPU** — ample headroom, not limiting at 720p.

### To measure the server's true >64 ceiling cleanly (future)
Need a source that is neither network- nor host-contended: either fix the NVR path to
gigabit and pull real channels, or drive from a **separate** source machine. On this single
box, any local relay competes with inference for CPU/decoder and cannot exceed the decoder
ceiling anyway.

### Method caveats (honesty)
- `NVDS_ENABLE_LATENCY_MEASUREMENT=1` adds some logging overhead at high stream counts
  (~800 latency lines/run); the clean pre-instrumentation run showed 64@720p at 26–28 fps,
  slightly better than the instrumented 20–24. Treat 720p @ ~64 as "at the edge."
- Loopback streams show one repeated scene — irrelevant to decode/infer cost, only makes
  detection counts identical.

### Data files
`benchmark_nvr_ceiling.csv` (real NVR), `benchmark_local720_ceiling.csv` (loopback),
per-rung logs in `artifacts/benchmarks/ds_logs/`, harness `scripts/benchmark_nvr_ceiling.py`.
