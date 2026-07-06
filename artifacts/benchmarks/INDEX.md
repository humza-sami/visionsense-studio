# Benchmark dump index — RTX 3070 Ti 8 GB · TensorRT @640 · 704×576 H.265 substreams

All capacity tests run on this box, consolidated 2026-07-04. Reproduce commands are in
each script's docstring; relay setup is in `docs/quote-sheet.md`.

| File | What it measures | Script | Date |
|---|---|---|---|
| `model_ladder.csv` | Pure inference throughput per model (n/s/m/l/x) × batch (1/4/8/16): ms/frame, fps, VRAM | `scripts/bench_infer_ladder.py` | 2026-07 |
| `benchmark_results.csv` | Single-model live pipeline runs (capture+decode+track+preview) at 5/10/15 cams, per-model | `scripts/benchmark_live.py` | 2026-07-02 |
| `combinations.csv` | First 4 mixed-workload scenarios (S1–S4), incl. the S1 m+l 15-cam OOM | `scripts/benchmark_mixed.py` | 2026-07 |
| `benchmark_verticals.csv` | Sales packages (restaurant/market/industry × S/M/L site) — the quoting sweep | `scripts/benchmark_verticals.py` | 2026-07-04 |
| `benchmark_stress.csv` | Stress matrix: per-size camera ceilings (n20/24, s16/20, m12/16, l10/12, x4/8) + x mixes + 4/5-engine stacking OOMs | `scripts/benchmark_stress.py` | 2026-07-04 |
| `benchmark_scale.csv` | Camera-count ladder @2 fps nano (28✅ 32✅ 36❌ 40❌) — the capture-vs-detect-fps proof | `scripts/benchmark_scale.py` | 2026-07-04 |
| `decomposition_matrix.csv` | All 100 catalog use cases × kernels × primitives × models × fps hints | `scripts/validate_usecases.py` | 2026-07-04 |
| `BENCHMARK.md` | Narrative results: 15-cam real-NVR run, x-large UI runs, limits analysis | — | snapshot |

Headline numbers → `docs/quote-sheet.md`. Calibrated sizing model → `data/calibration.json`
(validated against S1 OOM, industry_M14 OOM, and nano ceiling). GPU tier database →
`data/gpus.json`.

Known harness caveats (do not mistake for hardware limits):
- `stress_s20` IndexError = small engine's TensorRT batch profile (≤16), not VRAM; the
  production pipeline chunks batches by `max_batch` (`src/pipeline.py`), the bench harness
  doesn't.
- Achieved det-fps saturates ~3.8 when targeting 5 (and ~75 % of any fast target) with GPU
  ≤ 62 % — the serial single-thread scheduler in the bench loop, not the GPU.
