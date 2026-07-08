# DeepStream Evaluation — Why, What It Changes, and the Go/No-Go Spike

*Written 2026-07-04. Context: our measured walls on the RTX 3070 Ti 8 GB
([quote-sheet.md](quote-sheet.md)): 32-camera VRAM wall (~190 MB/cam), host-CPU wall
(~1.4%/cam of 8 cores), and the Python scheduler ceiling (achieved ~3.8 fps at target 5
with the GPU 60% idle). DeepStream attacks all three at once.*

## 1. Where our ~190 MB/camera actually goes (memory anatomy)

Per-camera path today: independent GStreamer pipeline → NVDEC decode → nvvideoconvert →
**download to CPU BGR** → numpy buffer → (per tick) letterbox → **re-upload to GPU** →
TensorRT. The VRAM cost per camera decomposes as:

| # | Component | Size | Avoidable? |
|---|---|---|---|
| a | H.265 reference frames (DPB, 6–8 NV12 surfaces @ 0.58 MB for 704×576) | ~5 MB | **No — physics.** P/B frames need their reference chain; you cannot "decode 5 of 25 fps". I-frame-only decode gives 0.5–1 fps (GOP rate), not a chosen fps, and saves compute, not pool memory. |
| b | Default-sized surface pools: decoder extra surfaces + nvvideoconvert BGRx pool (1.55 MB/surface) + appsink queues — allocated at connect, per pipeline | tens of MB | Yes — trim `num-extra-surfaces`, or share pools |
| c | Per-decoder-instance driver state (bitstream staging, parser, sync) × 32 independent instances | tens of MB | Yes — fewer, shared instances |
| d | Inference-side staging: per-camera letterbox tensors, PyTorch caching-allocator retention, batch activations scaling with camera count | ~50–100 MB spread | Yes — GPU-resident zero-copy input, preallocated bindings |
| e | 2 MB CUDA allocation granularity + fragmentation across many small pools | slack | Yes — consolidation |

**Conclusion: ~5 MB is physics; ~185 MB is architecture.** Not a language issue — the
allocations live in driver/GStreamer C code regardless of whether Python or Rust
orchestrates. Detection fps changes none of it: **memory is set by pool allocation at
connect time; compute is set by detection rate.** (Hence 36 cams OOM'd at startup before
any inference.)

## 2. What DeepStream changes (why it runs many more cameras)

| Our wall (measured) | DeepStream mechanism |
|---|---|
| ~190 MB VRAM/cam → 32-cam wall | `NvBufSurface` zero-copy path (decode→`nvstreammux`→`nvinfer`→`nvtracker`, frames never leave VRAM); one **shared, explicitly-sized** batch pool instead of N private default-sized pools → ~20–40 MB/cam |
| CPU 1.4%/cam (NV12→BGR + PCIe round-trip) → 16-core host at 100 cams | No CPU touch in the frame path at all; conversion on GPU only where needed |
| Python serial loop → achieved 3.8/5 fps with GPU idle | Pipeline graph runs in C threads; Python (`pyservicemaker`) receives only metadata callbacks |
| Per-camera CPU ByteTrack | GPU multi-stream `nvtracker` (NvSORT / NvDCF) |

**Capacity estimate for our 3070 Ti, honestly derived** (NVIDIA publishes single-stream
peak fps, not stream counts — so we use our own ladder): yolo26n measured ~270–295 total
fps at batch 8–16 → at 2 fps/cam that is ~135 cams of compute. With memory at
~30–40 MB/cam the VRAM wall moves past 150 substreams and NVDEC (~200 substreams/decoder)
is fine. Realistic with margins: **60–100 substream cameras per 8 GB card ≈ 3× current
capacity, ÷3 cost-per-camera.**

## 3. What it costs / what it does NOT touch

Costs: DS 9.0 platform pin (Ubuntu 24.04, driver 590+, CUDA 13.1, TRT 10.14.1);
custom YOLO26 bbox parser (.so); new debugging surface; container-based deploys.
Dev-cost mitigation: NVIDIA's **DeepStream coding-agent skill**
(github NVIDIA-AI-IOT/deepstream_coding_agent; docs: DS_AI_Agent) generates
pyservicemaker pipelines, nvinfer configs, and custom parsers — install into
`~/.claude/skills/`.

**Untouched:** everything above the PERCEIVE+TRACK line — rule kernels, event schema,
Redis, sync-agent, WhatsApp, dashboard, fleet, site-as-code. DeepStream emits tracked
detections via pad probe → same `Event` objects into Redis. This is an engine swap inside
`vision-core` (architecture.md §4), which is exactly why the platform/apps split exists.

## 4. The spike (2 weeks, go/no-go)

1. Run DS 9.0 NGC container on the lab box; install both NVIDIA skills.
2. Onboard yolo26n via `deepstream-import-vision-model` (ONNX → engine → parser →
   benchmark report).
3. Replay our MediaMTX 704×576 H.265 substreams at **32 → 64 → 96** streams,
   `nvstreammux` batch 16–32, det interval matched to 2 fps/cam.
4. Measure: VRAM/cam slope, achieved det fps/cam, GPU/NVDEC/CPU util — append to
   `artifacts/benchmarks/` next to the existing CSVs for apples-to-apples.
5. Wire one pad-probe → Redis `Event` bridge; run the existing `zone_state` logic
   against it to prove the kernel layer is engine-agnostic.

**Gate: ≥ 60 cameras @ 2 fps yolo26n on the 8 GB card with stable 24 h soak.**
- Pass → DeepStream becomes vision-core v2 for new installs (architecture.md phase
  ordering updated; old stack maintained for existing sites until parity).
- Fail → keep current stack + quick wins (GPU-side color convert, pool trimming,
  preview decoupling → ~50 cams) and re-evaluate at DS 9.x.

## 5. Scheduler note (independent of engine choice)

Over-budget compute degrades all camera groups uniformly today
(`achieved ≈ target × budget/demand`). Safety-critical groups (danger-zone, conveyor QC,
weapon) need a **guaranteed-floor priority tier** so degradation eats analytics groups
first. Applies to both the current stack and any DeepStream port (per-group
`interval`/drop policy in nvinfer or upstream sampling).
