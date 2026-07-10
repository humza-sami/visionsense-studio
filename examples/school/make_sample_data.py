"""Generate sample_data/school_day.jsonl — a deterministic 2-minute synthetic
recording of all 7 school cameras, in the replay format (one frame per line).

What it stages (so you know what the replay should report):

  gate    5 kids ENTER (t≈5,15,25,40,60), 2 kids EXIT (t≈70,90)
  cooler  kid 101 dwells ~25s, kid 102 ~40s, kid 103 walks through (no visit),
          kids 104–108 crowd the cooler t=78–96 (5 > limit 4 → alert)
  class1  24 students inside the room polygon + 2 people in the corridor
          (excluded by the zone), with detector flicker the median smooths out
  class2–5  18 / 30 / 22 / 27 students, whole-frame counting

Run:  python examples/school/make_sample_data.py
Then: frameinsight replay examples/school examples/school/sample_data/school_day.jsonl --console
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).parent / "sample_data" / "school_day.jsonl"
DURATION = 120.0
FAST_DT = 0.2     # gate + cooler sampled at 5 fps
SLOW_DT = 1.0     # classrooms sampled at 1 fps


def obj(tid: int, fx: float, fy: float, conf: float = 0.85,
        w: float = 0.04, h: float = 0.14) -> dict:
    """Object whose foot (bottom-center) is at (fx, fy)."""
    return {"id": tid, "cls": "person",
            "conf": round(conf, 2),
            "bbox": [round(fx - w / 2, 4), round(fy - h, 4), w, h]}


def walker(t: float, start: float, dur: float, y0: float, y1: float) -> float | None:
    """Foot y of a kid walking y0→y1 during [start, start+dur], else None."""
    if start <= t <= start + dur:
        return y0 + (y1 - y0) * (t - start) / dur
    return None


def gate_frame(t: float) -> list[dict]:
    objs = []
    # Entering: walk down the image (y 0.30 → 0.80) across the line at y=0.55.
    for tid, start, x in [(1, 5, 0.35), (2, 15, 0.50), (3, 25, 0.62),
                          (4, 40, 0.44), (5, 60, 0.55)]:
        y = walker(t, start, 4.0, 0.30, 0.80)
        if y is not None:
            objs.append(obj(tid, x, y))
    # Exiting: walk up.
    for tid, start, x in [(6, 70, 0.40), (7, 90, 0.58)]:
        y = walker(t, start, 4.0, 0.80, 0.30)
        if y is not None:
            objs.append(obj(tid, x, y))
    return objs


def cooler_frame(t: float) -> list[dict]:
    objs = []
    # Dwellers: approach (2s), stand in the zone, leave (2s).
    for tid, arrive, leave, x in [(101, 10, 35, 0.45), (102, 30, 70, 0.58)]:
        if arrive - 2 <= t < arrive:
            objs.append(obj(tid, 0.15 + (x - 0.15) * (t - arrive + 2) / 2, 0.60))
        elif arrive <= t <= leave:
            objs.append(obj(tid, x, 0.60))
        elif leave < t <= leave + 2:
            objs.append(obj(tid, x + (0.90 - x) * (t - leave) / 2, 0.60))
    # Walkthrough: crosses the zone in 2 s — should NOT count as a visit.
    if 50 <= t <= 52:
        objs.append(obj(103, 0.20 + 0.60 * (t - 50) / 2, 0.55))
    # Crowd: 5 kids simultaneously (limit is 4) from t=78 to 96.
    if 78 <= t <= 96:
        for i in range(5):
            objs.append(obj(104 + i, 0.38 + i * 0.06, 0.55 + (i % 2) * 0.12))
    return objs


def classroom_frame(t: float, cam_index: int, count: int,
                    with_corridor: bool) -> list[dict]:
    objs = []
    ti = int(t)
    # Deterministic detector flicker: some seconds miss 2 kids, some double-count 1.
    n = count
    if (ti + cam_index * 3) % 17 == 0:
        n -= 2
    elif (ti + cam_index * 5) % 23 == 0:
        n += 1
    # Seated grid inside the room polygon (x 0.05–0.85, y 0.35–0.95).
    cols = 8
    for i in range(n):
        fx = 0.06 + (i % cols) * 0.10
        fy = 0.38 + (i // cols) * 0.14
        objs.append(obj(2000 + cam_index * 100 + i, fx, min(fy, 0.95), conf=0.65))
    # class1 only: two people in the corridor (x≈0.95) — outside the room zone.
    if with_corridor:
        objs.append(obj(2900, 0.95, 0.70, conf=0.9))
        objs.append(obj(2901, 0.96, 0.85, conf=0.9))
    return objs


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frames: list[tuple[float, str, list[dict]]] = []

    t = 0.0
    while t <= DURATION:
        frames.append((round(t, 1), "gate", gate_frame(t)))
        frames.append((round(t, 1), "cooler", cooler_frame(t)))
        t = round(t + FAST_DT, 10)

    classes = [("class1", 24, True), ("class2", 18, False), ("class3", 30, False),
               ("class4", 22, False), ("class5", 27, False)]
    t = 0.0
    while t <= DURATION:
        for i, (cam, count, corridor) in enumerate(classes):
            frames.append((round(t, 1), cam, classroom_frame(t, i, count, corridor)))
        t = round(t + SLOW_DT, 10)

    frames.sort(key=lambda f: f[0])
    with open(OUT, "w") as fh:
        for ts, cam, objs in frames:
            fh.write(json.dumps({"cam": cam, "ts": ts, "objects": objs},
                                separators=(",", ":")) + "\n")
    print(f"wrote {len(frames)} frames to {OUT}")


if __name__ == "__main__":
    main()
