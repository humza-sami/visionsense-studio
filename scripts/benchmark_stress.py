"""GPU stress matrix — single-model ceilings for EVERY model size (n/s/m/l/x) and
multi-model mixes including x-large, scaled until they fail. Complements
benchmark_verticals.py (sales packages) with the raw capacity boundaries.

OOM is an expected outcome and is recorded as a CSV row (that's the ceiling).
NOTE: models/yolo26x.engine has a small batch profile — x groups stay <= 4 cams.

  python scripts/benchmark_stress.py [scenario|all] [seconds] [relay_url] [csv]
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.getcwd())

# groups: (label, cam_count, model_key, input_fps, target_det_fps)
SCENARIOS = {
    # ── single-model camera ceilings @ 5 fps detection ──
    "stress_n20": [("nano", 20, "n", 25, 5.0)],
    "stress_n24": [("nano", 24, "n", 25, 5.0)],
    "stress_s16": [("small", 16, "s", 25, 5.0)],
    "stress_s20": [("small", 20, "s", 25, 5.0)],
    "stress_m12": [("medium", 12, "m", 25, 5.0)],
    "stress_m16": [("medium", 16, "m", 25, 5.0)],
    "stress_l10": [("large", 10, "l", 25, 5.0)],
    "stress_l12": [("large", 12, "l", 25, 5.0)],
    "stress_x4":  [("xlarge", 4, "x", 25, 5.0)],
    # x-only accuracy box: two x groups (shared engine), batches of 4
    "stress_x8_dual": [("critical", 4, "x", 25, 2.0), ("fire", 4, "x", 25, 1.0)],
    # ── mixes including x-large (weapon / critical-zone patterns) ──
    "stress_bank8_sx":     [("queue", 6, "s", 25, 2.0), ("weapon", 2, "x", 25, 8.0)],
    "stress_accuracy8_mx": [("ppe", 6, "m", 25, 2.0), ("critical", 2, "x", 25, 1.0)],
    # ── many-model mixes: where does engine-context stacking break? ──
    "stress_mix4_12": [("a", 3, "n", 25, 5.0), ("b", 3, "s", 25, 5.0),
                       ("c", 3, "m", 25, 2.0), ("d", 3, "l", 25, 2.0)],
    "stress_mix4_16": [("a", 4, "n", 25, 5.0), ("b", 4, "s", 25, 5.0),
                       ("c", 4, "m", 25, 2.0), ("d", 4, "l", 25, 2.0)],
    "stress_mix5_10": [("a", 2, "n", 25, 2.0), ("b", 2, "s", 25, 2.0),
                       ("c", 2, "m", 25, 2.0), ("d", 2, "l", 25, 2.0),
                       ("e", 2, "x", 25, 1.0)],
}


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    secs = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    url = sys.argv[3] if len(sys.argv) > 3 else "rtsp://127.0.0.1:8554/live"
    csv_path = sys.argv[4] if len(sys.argv) > 4 else "benchmark_stress.csv"

    if which != "all":
        from benchmark_mixed import run_scenario
        from benchmark_verticals import append_failure_row
        try:
            run_scenario(which, SCENARIOS[which], secs, url, csv_path)
        except Exception as e:
            append_failure_row(csv_path, which, SCENARIOS[which], f"{type(e).__name__}: {e}")
            print(f"[{which}] FAILED: {e}")
        sys.stdout.flush()
        os._exit(0)

    if os.path.exists(csv_path):
        os.remove(csv_path)
    for nm in SCENARIOS:
        subprocess.run([sys.executable, __file__, nm, str(secs), url, csv_path],
                       env={**os.environ, "PYTHONPATH": os.getcwd()})
        time.sleep(4)
    print(f"\nstress matrix CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
