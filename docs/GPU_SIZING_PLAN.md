# GPU Sizing Study — Test Plan & Model

Goal: from measured data, derive a **GPU cost estimator** that, given an application's
camera mix (count · resolution · input fps · model · **target detection fps**), predicts
the compute + VRAM + decode needed and recommends an NVIDIA GPU.

## The cost model (what we're calibrating)

A workload is a set of **camera groups**. Each group `g` has: `count`, `resolution`,
`input_fps`, `model`, `det_fps` (how often YOLO runs per camera — the key knob).

The GPU must satisfy **three independent budgets**:

1. **Inference compute**
   `T_infer (ms/s) = Σ_g count_g · det_fps_g · ms_per_frame(model_g, imgsz, GPU)`
   A GPU delivers ~`1000 · U` ms of inference per second (U≈0.85 usable). Fits if
   `T_infer ≤ 1000·U`. `ms_per_frame` is measured per model on the 3070 Ti and scaled
   to other GPUs by their FP16/INT8 throughput ratio.

2. **VRAM**
   `VRAM = base_context + Σ_models engine_vram(model) + Σ_g count_g · vram_per_cam(resolution)`
   Measured: base+context ≈ 1.3–1.9 GB; per-camera ≈ 120–340 MB (resolution-dependent);
   engine resident size scales with model.

3. **Decode (NVDEC)**
   `Decode_load = Σ_g count_g · input_fps_g · decode_cost(resolution)` vs the GPU's NVDEC
   capacity (# decoder chips × throughput). Cheap in practice (H.265 substreams).

**Key insight already proven:** detection fps dominates compute. Attendance @ 25 fps costs
25× a fire camera @ 1 fps on the *same* model. So mixing models AND fps per group is how you
pack a box efficiently.

## Application → recommended group settings (research)

| Application | Task | Model | Input fps | Detect fps | Why |
|---|---|---|---|---|---|
| Attendance / people-counting | person | small–medium | 10–15 | 8–12 | needs smooth tracking of moving people |
| Queue / occupancy | person | small | 5–10 | 3–5 | slow-changing counts |
| Fire / smoke | fire,smoke | large/xl | 2–5 | 0.5–1 | rare event, accuracy > speed, tiny cues |
| Theft / loss-prevention | person+objects | large | 12–15 | 8–12 | fast interactions, object hand-off |
| PPE / safety compliance | person+PPE | medium | 5–10 | 2–5 | periodic checks |
| ANPR / vehicle | vehicle,plate | medium | 10–15 | 8–12 | fast-moving vehicles |
| Intrusion / perimeter | person | medium | 5–10 | 2–5 | motion-gated, event-driven |
| Parking occupancy | vehicle | small | 1–2 | 0.2–0.5 | very slow-changing |

## Tests to run

**A. Per-model inference ladder** (clean GPU cost, no preview overhead):
batched inference on 704×576 frames, batch ∈ {1,4,8,16}, for models n/s/m/l/x →
`ms_per_frame(model, batch)`. Fit amortized per-frame ms + batching gain.

**B. Per-model VRAM ladder:** VRAM vs camera count (already have n/l/x; add s/m).
Fit `base(model) + per_cam·N`.

**C. Mixed-workload scenarios** (2 models, controlled per-group det fps) → `combinations.csv`:
- **S1 Warehouse:** 10× attendance (medium, 704×576, det 10) + 5× fire (large, det 1)
- **S2 Retail:** 8× people (small, det 8) + 4× theft (large, det 10)
- **S3 Safety:** 12× PPE (medium, det 3) + 3× fire (xl, det 1)
- **S4 Mixed-fps single model:** 15× medium, 5 @ det 15 + 10 @ det 3

For each: measured GPU%, VRAM, NVDEC%, CPU%, RAM, per-group batch size + achieved fps.
Validate that measured GPU util ≈ predicted `T_infer/(1000·U)`.

## Deliverables
- `benchmark_results.csv` (single-model sweeps, existing) + `model_ladder.csv` (A/B)
- `combinations.csv` + section in `BENCHMARK.md` (C)
- `data/gpus.json` — NVIDIA GPU database (specs + relative perf)
- `gpu_calculator.html` — interactive estimator built on the fitted model
