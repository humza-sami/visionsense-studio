"""Vertical-package capacity benchmark — the quoting tool.

Runs the sales packages (restaurant / market / industry) at small/standard/large
site sizes on THIS box, reusing run_scenario from benchmark_mixed. Each scenario
runs in its own subprocess for clean VRAM; failures (e.g. CUDA OOM) are recorded
as a CSV row instead of aborting the sweep — OOM is a quoting data point
("this package size needs a bigger GPU"), not an error.

Group fps targets come from the use-case corpus (data/usecases/catalog.yaml):
alert-grade rules 1-2 fps, tills/theft 5-10 fps, footfall 8 fps, danger zones 15 fps.

  python scripts/benchmark_verticals.py [scenario|all] [seconds] [relay_url] [csv]
"""
from __future__ import annotations

import csv
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, os.getcwd())

# groups: (label, cam_count, model_key, input_fps, target_det_fps)
SCENARIOS = {
    # ── RESTAURANT: tables/turnover (n@1) + till/queue/theft (s@5) + kitchen hygiene/fire (m@1)
    "restaurant_S06": [("tables", 2, "n", 25, 1.0), ("till_queue", 2, "s", 25, 5.0), ("kitchen", 2, "m", 25, 1.0)],
    "restaurant_M10": [("tables", 4, "n", 25, 1.0), ("till_queue", 3, "s", 25, 5.0), ("kitchen", 3, "m", 25, 1.0)],
    "restaurant_L14": [("tables", 6, "n", 25, 1.0), ("till_queue", 4, "s", 25, 5.0), ("kitchen", 4, "m", 25, 1.0)],
    # ── MARKET/RETAIL: footfall lines (s@8) + aisle dwell/heatmap (n@3) + theft at exits (l@10)
    "market_S08": [("footfall", 2, "s", 25, 8.0), ("aisles", 4, "n", 25, 3.0), ("theft", 2, "l", 25, 10.0)],
    "market_M12": [("footfall", 3, "s", 25, 8.0), ("aisles", 6, "n", 25, 3.0), ("theft", 3, "l", 25, 10.0)],
    "market_L16": [("footfall", 3, "s", 25, 8.0), ("aisles", 9, "n", 25, 3.0), ("theft", 4, "l", 25, 10.0)],
    # ── INDUSTRY: PPE compliance (m@1) + danger-zone fast alerts (n@15) + fire/smoke (l@1)
    "industry_S08": [("ppe", 4, "m", 25, 1.0), ("danger_zone", 2, "n", 25, 15.0), ("fire", 2, "l", 25, 1.0)],
    "industry_M14": [("ppe", 8, "m", 25, 1.0), ("danger_zone", 3, "n", 25, 15.0), ("fire", 3, "l", 25, 1.0)],
    "industry_L18": [("ppe", 10, "m", 25, 1.0), ("danger_zone", 4, "n", 25, 15.0), ("fire", 4, "l", 25, 1.0)],
}


def append_failure_row(csv_path: str, name: str, groups, err: str) -> None:
    from benchmark_mixed import COLUMNS
    total = sum(g[1] for g in groups)
    row = {c: 0 for c in COLUMNS}
    row.update({"scenario": name, "total_cameras": total, "groups": str(groups),
                "notes": f"FAILED: {err[:160]}"})
    new = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerow(row)


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    secs = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    url = sys.argv[3] if len(sys.argv) > 3 else "rtsp://127.0.0.1:8554/live"
    csv_path = sys.argv[4] if len(sys.argv) > 4 else "benchmark_verticals.csv"

    if which != "all":
        from benchmark_mixed import run_scenario
        try:
            run_scenario(which, SCENARIOS[which], secs, url, csv_path)
        except Exception as e:  # OOM etc. — record and exit clean so the sweep continues
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
    print(f"\nvertical capacity CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
