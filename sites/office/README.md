# Site: office client — 16 cameras, presence + desk occupancy

Real deployment. One Dahua NVR with **16 × 4MP (2560×1440) HEVC mainstreams @
25 fps** (probed 10 Jul 2026), processed at **full resolution** through
**YOLO26-xlarge at 5 detections/s per camera** on one RTX 3070 Ti.

| Question the client asked | Rule | Where |
|---|---|---|
| How many people are in the room? | `headcount` (built-in, whole frame, median-smoothed) | one per camera |
| Who is seated at a desk and working? | `desk_occupancy` — per-desk polygons, session + daily timers; "working" = seated ≥ 2 min | [apps/desk_occupancy.py](apps/desk_occupancy.py) |

## Capacity (why this fits on one 3070 Ti)

- Decode: 16 × 2560×1440×25 ≈ **1.47 Gpx/s** — fits one Ampere NVDEC.
  Measured live (10 Jul): 3 full-res HEVC cams = 8% decoder → 16 ≈ **43%**
  (HEVC decodes cheaper than the H.264 wall we benchmarked).
- Compute: measured 3 cams × 5 det/s xlarge = 22% GPU → 16 cams ≈ **80–100%**.
  Workable but tight; if on-site soak shows saturation, drop to `detect_fps: 4`
  or `model: yolo26l` (both one-line changes).
- **Measured limit during off-site testing: the NVR's internet uplink.** One
  4MP mainstream ≈ 6 Mbps; the uplink delivers ~20 Mbps → only ~3 full-res
  cameras over WAN. The checked-in site config is now restored for the on-site
  LAN path with all 16 cameras enabled. If streams starve again from off-site,
  suspect the network before the server.

## Setup / operate

```bash
export OFFICE_NVR_TMPL='rtsp://USER:PASS@NVR_HOST:554/cam/realmonitor?channel={ch}&subtype=0'

frameinsight validate sites/office        # config check, no GPU
frameinsight studio  sites/office         # http://<box>:8765 — draw desk zones,
                                          # then watch live with boxes + timers
bash scripts/run_edge.sh sites/office     # the pipeline itself (container)
```

Workflow: open Studio → pick a camera → **Zones tab** → "New snapshot" → "+
Desk area" → click the corners of each chair/desk → save (names desk1, desk2, …
are what `desk_occupancy` picks up). Restart the pipeline to apply. Then the
**Live tab** shows the camera with detection boxes, each desk polygon colored
by state (grey empty / yellow present / purple working), the session timer on
the desk, and per-desk today totals in the side panel.

Notes:
- Desk timers are **zone-based, not track-ID-based**: tracker ID churn while
  someone sits still does not reset a timer (`empty_grace_s` bridges
  occlusions; sessions survive ID swaps — tested).
- Anchor is the **box center** (a seated person's feet are under the desk).
- "Working" is presence-based (seated ≥ `working_after_s`). It cannot see
  whether someone is typing or day-dreaming — that would need a pose model.
- cam01 ships with 10 desk polygons pre-drawn from the reference snapshot as a
  starting point — adjust them in Studio to match the real chairs.
