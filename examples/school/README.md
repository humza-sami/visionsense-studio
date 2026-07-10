# Example site: Greenfield School

A complete FrameInsight deployment for a school with **7 RTSP cameras on one
NVR**, implementing three applications on a single detection pipeline:

| Camera(s) | Application | Kernel |
|---|---|---|
| `gate` | How many kids **enter / exit** the school gate | `line_crossing` (built-in) |
| `cooler` | How many kids are **around the water cooler** + **average stay time** | `zone_dwell` (built-in) |
| `cooler` | Alert when **too many kids crowd** the cooler | `cooler_crowding` ([apps/cooler_crowding.py](apps/cooler_crowding.py) — custom, ~30 lines) |
| `class1`–`class5` | **Headcount of each classroom** every 30 s | `headcount` (built-in) |

Everything site-specific is in this directory; the engine is stock:

```
site.yaml                  cameras, pipeline groups, rule bindings, sinks
zones/gate.json            gate line (directed: crossing downward = "enter")
zones/cooler.json          floor polygon in front of the cooler
zones/class1.json          room polygon (excludes the corridor seen through the door)
apps/cooler_crowding.py    the one custom kernel this site needed
make_sample_data.py        generates the synthetic recording below
sample_data/school_day.jsonl   2 minutes of staged detections for replay
```

## Try it without a GPU (30 seconds)

```bash
pip install -e .                       # from the repo root, once
frameinsight validate examples/school  # checks cameras/groups/zones/rules
frameinsight replay examples/school examples/school/sample_data/school_day.jsonl --console
```

The replay pushes a staged 2-minute "school day" through the real rule code.
You should see, among the events:

- `line_crossed` ×7 on `gate` — 5 `enter`, 2 `exit`, with running totals
- `dwell_completed` on `cooler` — kid 101 ≈ 27 s, kid 102 ≈ 42 s, and **no**
  event for kid 103 who just walked through (below `min_dwell_s`)
- `cooler_crowded` ×1 — 5 kids > limit 4, sustained 10 s, then silenced by cooldown
- `occupancy` on `cooler` — live count + `avg_dwell_s` (the "average kid stay time")
- `headcount` per classroom — 24 / 18 / 30 / 22 / 27; `class1`'s two corridor
  passers-by are excluded by the room polygon, and single-frame detector
  flicker (staged into the data) never changes the reported median

Drop `--console` to write to the site's real sinks instead
(`events/school.jsonl` + `events/school.db`).

## Run it live

```bash
export SCHOOL_NVR_TMPL='rtsp://USER:PASS@NVR_HOST:554/cam/realmonitor?channel={ch}&subtype=1'
bash scripts/run_edge.sh examples/school        # inside the DeepStream container
```

This starts **two pipelines** (see `groups:` in site.yaml):

- `entrances` — gate + cooler through **yolo26s at 10 det/s** (fast reactions,
  NvDCF tracker because kids occlude each other at the gate)
- `classrooms` — 5 rooms through **yolo26m at 1 det/s** (headcounts move
  slowly; this leaves the GPU nearly idle)

That split is *the* mechanism for per-camera detection rates: nvinfer's
`interval` skips whole batches, so different rates require different pipelines
(architecture doc §3.2). On the benchmarked RTX 3070 Ti this site uses a small
fraction of one GPU — the decoder wall is ~64×720p cameras, and compute at
these rates is trivial.

## Adapting this example to a real school

1. Point `url_template`/`channel` at the real NVR (credentials in env only).
2. Grab a reference snapshot per camera (`ffmpeg -i <rtsp> -frames:v 1 ref.jpg`),
   draw the zones on it, store **normalized** coordinates in `zones/*.json`.
3. Check the gate line's direction against the snapshot: walking *into* the
   school must land on the line's **left** side (or swap `label_left`/`label_right`).
4. Tune per-rule thresholds (`min_dwell_s`, `report_every_s`, `max_people`)
   with the client — they're business decisions, not engineering ones.
5. "Kids" are detected as COCO class `person` — YOLO26 does not distinguish
   children from adults. If staff must be excluded (e.g. from headcounts),
   that needs a secondary classifier (uniform color) or scheduled time windows.
