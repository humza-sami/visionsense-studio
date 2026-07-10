# FrameInsight — Application Developer Usage Guide

**Audience:** application engineers building client deployments (sites) on the
FrameInsight engine. You configure cameras, draw zones, bind rules, and write
custom rule kernels. You never modify the engine.

Everything in this guide runs **without a GPU** except the final "run live"
step. That is the whole point of the design: your development loop is
`edit → replay → pytest`, on your laptop, in seconds.

---

## Table of contents

1. [The mental model](#1-the-mental-model)
2. [Setup](#2-setup)
3. [Anatomy of a site](#3-anatomy-of-a-site)
4. [site.yaml — complete reference](#4-siteyaml--complete-reference)
5. [Zones — drawing, format, semantics](#5-zones--drawing-format-semantics)
6. [Built-in kernels — complete reference](#6-built-in-kernels--complete-reference)
7. [Custom kernels — the full API](#7-custom-kernels--the-full-api)
8. [Worked examples](#8-worked-examples)
9. [Testing: replay + pytest](#9-testing-replay--pytest)
10. [Zone Studio](#10-zone-studio)
11. [Running live on the edge box](#11-running-live-on-the-edge-box)
12. [Events, sinks, and querying results](#12-events-sinks-and-querying-results)
13. [State files](#13-state-files)
14. [Upgrading the engine version](#14-upgrading-the-engine-version)
15. [Troubleshooting](#15-troubleshooting)
16. [Cheat sheet](#16-cheat-sheet)

---

## 1. The mental model

The engine (this repo, released as a Docker image + pip package) does the
expensive work once per camera: decode the RTSP stream on the GPU, run YOLO
object detection, track objects across frames. What comes out is a stream of
small facts:

```
Detection(cam_id="reception", ts=1783508492.4, track_id=17,
          class_name="person", confidence=0.83,
          bbox=(0.41, 0.22, 0.06, 0.31))   # (x, y, w, h), normalized 0..1
```

Your business logic ("rule kernels") consumes that stream and produces
**events**:

```
Event(site="cubicle-office", cam_id="reception", rule="room_entry_counter",
      kind="line_crossed", severity="info", track_id=17,
      data={"direction": "in", "totals": {"in": 14, "out": 9}})
```

Events go to **sinks** (console, JSONL file, SQLite, Supabase) and from there
to dashboards and reports.

```
                    THE ENGINE (never yours to modify)
 RTSP ─► NVDEC ─► YOLO/TensorRT ─► tracker ─► Detection stream
                                                    │
                    YOUR SITE (config + small code) ▼
        site.yaml  ─────────►  dispatcher ─► rule kernels ─► Events ─► sinks
        zones/*.json                          (built-in or
        apps/*.py  ──────────────────────────  your apps/)
```

Three consequences you should internalize:

- **Adding a rule costs microseconds, not GPU.** Ten rules on one camera reuse
  the same detections. Never think "this extra analysis is expensive".
- **Kernels never see pixels.** If your idea requires looking at the image
  (color, faces, text), it needs a model change — talk to the engine team.
- **Everything is replayable.** Any kernel that works on a recorded JSONL file
  works identically live, because both paths feed the same dispatcher.

### Golden rules (the four things that get PRs rejected)

1. Never modify engine code or pin a site to a git *branch* — tags only.
2. Never commit credentials. Camera URLs are `${ENV_VAR}` references.
3. Never import pyservicemaker / GStreamer / OpenCV / network clients in a
   kernel. Detections in, events out.
4. Every custom kernel ships with a pytest and a replay recording.

---

## 2. Setup

### Laptop (development — no GPU, no cameras)

```bash
pip install "git+https://github.com/frameinsight/core@v0.2.0#egg=frameinsight[studio]"

frameinsight --help
frameinsight kernels          # lists built-in kernels
```

Requires Python ≥ 3.10. The `[studio]` extra adds Zone Studio (FastAPI +
uvicorn); skip it if you only need replay/tests.

### Starting a new site repo

```bash
git clone https://github.com/frameinsight/core /tmp/core   # only to copy the template
cp -r /tmp/core/templates/site-template ./<client>-site
cd <client>-site
git init && git add -A && git commit -m "New site from template (core v0.2.0)"
gh repo create frameinsight/<client>-site --private --source . --push
```

### Edge box (deployment — prepared once by ops)

The box has: NVIDIA driver 590+, Docker + NVIDIA Container Toolkit, model
packs with prebuilt TensorRT engines at `/opt/frameinsight/models`, and access
to `ghcr.io/frameinsight/edge` (`docker login ghcr.io` with an org token).
You interact with it only through your site repo's `./fi.sh`.

---

## 3. Anatomy of a site

```
<client>-site/
├── site.yaml            THE deployment description (section 4)
├── zones/
│   └── <cam>.json       drawn areas/lines per camera, normalized (section 5)
├── apps/
│   └── *.py             custom kernels — only when built-ins don't cover it (section 7)
├── recordings/
│   └── *.jsonl          replay data = your regression suite (section 9)
├── tests/
│   └── test_*.py        pytest for custom kernels (section 9)
├── fi.sh                runs any frameinsight command in the PINNED engine image
├── .env.example         which env vars this site needs (copy to .env on the box)
├── .gitignore           ignores .env, events/, state/
└── README.md
```

Generated at runtime (git-ignored):

```
events/                  events.jsonl, events.db — the site's output
state/                   <group>.json rule-state snapshots; live/<cam>.json live feed
```

---

## 4. site.yaml — complete reference

Validate any time with `frameinsight validate <site-dir>` — it checks
everything below and fails with plain-English messages.

```yaml
# ── identity ─────────────────────────────────────────────────────────────────
site: cubicle-office            # REQUIRED. Goes into every event as `site`.

# ── engine paths / global knobs (all optional, defaults shown) ───────────────
models_dir: /models             # where model packs are mounted in the container
apps_dir: apps                  # plugin dir, relative to the site dir
state_dir: state                # rule-state + live-state dir
heartbeat_s: 60                 # health event period
streammux: {width: 1280, height: 720}   # the pipeline's working resolution.
                                # All bbox/zone coordinates are normalized, so
                                # changing this does NOT invalidate zones.

# ── cameras ──────────────────────────────────────────────────────────────────
url_template: ${OFFICE_NVR_TMPL}    # optional; used by cameras with `channel:`.
                                    # The env var's VALUE contains {ch}, e.g.
                                    # rtsp://u:p@10.0.0.5:554/cam/realmonitor?channel={ch}&subtype=1

cameras:
  reception: {channel: 1, fps: 30}          # via url_template
  parking:   {url: "rtsp://${PARK_CAM_URL}", fps: 25}   # or explicit url
  # fps = the camera's real stream rate. Used to compute frame decimation.

# ── groups: one GPU pipeline per group ───────────────────────────────────────
# WHY groups exist: a pipeline has ONE model and ONE detection rate. Cameras
# needing fast reactions (counting, alerts) go in a 10 det/s group; slow
# analytics (headcounts) are fine at 1-2 det/s and cost almost nothing.
# RULES: every camera used by a rule must be in EXACTLY one group.
groups:
  - name: fast                  # REQUIRED, unique
    model: yolo26s              # REQUIRED: yolo26n|s|m|l|x (pack must exist in models_dir)
    detect_fps: 10              # detections/second the rules receive (default 5).
                                # Implemented as source-side frame decimation:
                                # every frame your kernel sees IS an inferred frame.
    tracker: NvDCF              # NvSORT (default, cheap) | NvDCF (holds IDs through
                                # occlusion — use for gates/crowds) | IOU
    cameras: [reception]
  - name: slow
    model: yolo26m
    detect_fps: 2
    cameras: [parking]

# ── rules: bind kernels to cameras ───────────────────────────────────────────
rules:
  - name: room_entry_counter    # unique; appears in every event as `rule`
    camera: reception           # must exist AND be in a group
    kernel: line_crossing       # built-in KIND or a KIND from apps/*.py
    zone: zones/reception.json#door_line    # "<file>#<zone_name>", optional if
                                            # the kernel accepts no/optional zone
    params:                     # kernel params — validated at load; a typo'd
      classes: [person]         # param name FAILS validation (fail-fast)
      min_conf: 0.5
      label_left: in
      label_right: out
      summary_every_s: 60

# ── sinks: where events go (all events go to ALL sinks) ─────────────────────
sinks:
  - {type: console}                              # stdout, one JSON per line
  - {type: jsonl,  path: events/events.jsonl}    # append-only, crash-safe
  - {type: sqlite, path: events/events.db}       # queryable locally
  - {type: supabase, table: events,              # batched cloud sync
     url_env: SUPABASE_URL, key_env: SUPABASE_SERVICE_KEY,
     batch: 50, flush_s: 5}
```

**Validation catches:** unknown camera in a group or rule · camera in two
groups · camera in no group but used by a rule · `detect_fps` > camera fps ·
duplicate rule names · unknown kernel KIND · missing zone file or zone name ·
unknown kernel params · missing `url`/`channel`. Missing env vars are a
*warning* at validate time (so you can validate on a laptop) and a *hard
error* at run time.

**Credential resolution order:** env var is expanded first, then `{ch}` is
replaced with the camera's channel — so the `{ch}` placeholder lives inside
your env var's value.

---

## 5. Zones — drawing, format, semantics

### The two zone types

| Type | Points | Used by |
|---|---|---|
| `polygon` | ≥ 3 | zone_dwell, headcount, zone_intrusion, most custom kernels |
| `line` | exactly 2, **directed** a→b | line_crossing |

### The file format (`zones/<cam>.json`)

```json
{
  "reference": {
    "width": 1280, "height": 720,
    "snapshot": "reception_ref.jpg",
    "note": "Drawn 2026-07-10. Door line directed left->right: walking INTO the room crosses to the LEFT side = 'in'."
  },
  "zones": [
    {"name": "door_line",    "type": "line",    "points": [[0.15, 0.55], [0.85, 0.55]]},
    {"name": "waiting_area", "type": "polygon", "points": [[0.30, 0.40], [0.72, 0.40], [0.78, 0.85], [0.25, 0.85]]}
  ]
}
```

Rules reference a zone as `zones/reception.json#waiting_area`.

### Non-negotiable semantics

- **Coordinates are normalized to [0, 1].** The loader rejects pixel values.
  This makes zones survive stream-resolution changes (mainstream ↔ substream).
- **Floor rules test the FEET anchor** — `Detection.foot` = bottom-center of
  the box — not the box center. A person's box center crosses a painted floor
  line long before they do. Draw polygons on the *floor* as seen in the image.
- **Lines are directed.** Crossing to the line's left (relative to the a→b
  drawing direction) emits `label_left`; to the right, `label_right`. If a
  live test shows in/out swapped, swap the labels in site.yaml — don't redraw.
- **Keep the reference snapshot.** When a camera gets bumped, it's your only
  way to see that zones no longer match reality.

### How to create zones

Preferred: **Zone Studio** (section 10) — draw with the mouse, it writes this
exact format. By hand also works; the engine can't tell the difference. To
convert pixel coordinates from any image tool: `x_norm = x_px / image_width`,
`y_norm = y_px / image_height`.

---

## 6. Built-in kernels — complete reference

List what your installed engine + your site's plugins provide:

```bash
frameinsight kernels <site-dir>
```

Every kernel accepts the **standard guards** (from the base class) *in
addition to* its own params:

| Param | Default | What it does / why it exists |
|---|---|---|
| `classes` | `[person]` | Detector classes the rule sees. Everything else is filtered out before your kernel runs. |
| `min_conf` | `0.5` | Confidence floor. Kills flicker boxes. |
| `sustain_s` | `0.0` | Condition must hold this long before it counts. Kills one-frame blips. |
| `cooldown_s` | `10.0` | Minimum gap between repeated alerts from the same cause. Kills alert storms. |
| `lost_timeout_s` | `3.0` | Track unseen this long ⇒ treated as gone (`on_track_lost` fires). |

### 6.1 `line_crossing` — directional entry/exit counting

Zone: **line** (required). Counts a track when its feet cross the line
segment between two processed frames — walking around the line's endpoint
does *not* count, and per-track `recross_cooldown_s` stops jitter from
double-counting.

| Param | Default | Meaning |
|---|---|---|
| `label_left` | `"in"` | Name for crossings to the line's left side |
| `label_right` | `"out"` | Name for crossings to the right |
| `recross_cooldown_s` | `2.0` | Same track can't count twice within this window |
| `summary_every_s` | `60.0` | Period of the totals event |

Events:
- `line_crossed` `{direction, totals:{<left>: n, <right>: m}}` — per crossing, has `track_id`
- `count_summary` `{<left>: n, <right>: m, window_s}` — periodic totals

State survives restarts (the day's totals restore from the state snapshot).

### 6.2 `zone_dwell` — how long each person stays in an area

Zone: **polygon** (required). Per-track state machine:
outside → (feet inside, sustained `sustain_s`) → **visit starts** →
(feet outside for `exit_grace_s`, or track lost) → **visit ends**.
`exit_grace_s` bridges short occlusions so one visit doesn't fragment into
many; visits shorter than `min_dwell_s` (walk-throughs) are dropped entirely.

| Param | Default | Meaning |
|---|---|---|
| `min_dwell_s` | `3.0` | Shorter visits are ignored (not real visits) |
| `exit_grace_s` | `2.0` | Brief exits/occlusions inside one visit are bridged |
| `summary_every_s` | `60.0` | Period of the occupancy summary |

Events:
- `dwell_started` — visit began (has `track_id`)
- `dwell_completed` `{dwell_s}` — visit ended
- `occupancy` `{current, visits, avg_dwell_s, max_dwell_s}` — periodic

Use for: water coolers, waiting areas, counters, promo zones, desks, tables.

### 6.3 `headcount` — smoothed people count

Zone: **polygon, optional** (omit to count the whole frame). Reports the
**median** of per-frame counts over `window_s` — single-frame detector flicker
cannot move the reported number. Track IDs not required.

| Param | Default | Meaning |
|---|---|---|
| `report_every_s` | `30.0` | Reporting period |
| `window_s` | `10.0` | Smoothing window for the median |
| `max_count` | `0` | If > 0: `overcrowded` alert when smoothed count exceeds it |

Events:
- `headcount` `{count, min, max, samples}` — periodic
- `overcrowded` `{count, limit}` — severity=alert, rate-limited by `cooldown_s`

Also publishes `live_state` (`{current, raw_last}`) for the live UI.

### 6.4 `zone_intrusion` — restricted-area alert

Zone: **polygon** (required). A track whose feet stay inside for `sustain_s`
raises **one** alert (per `cooldown_s`); leaving emits an end event with the
total duration.

Events:
- `intrusion` `{confidence}` — severity=alert, has `track_id`
- `intrusion_end` `{duration_s}`

Use for: after-hours areas, machine cages, chemical storage, staff-only zones.

---

## 7. Custom kernels — the full API

Write a custom kernel **only** when configuring built-ins can't express the
requirement. It's one file in `apps/`, typically 20–40 lines.

### 7.1 Skeleton

```python
# apps/my_rule.py
from frameinsight.geometry import point_in_polygon   # + side_of_line, boxes_iou, segments_intersect
from frameinsight.rules import register_kernel
from frameinsight.rules.base import Rule


@register_kernel                    # ← registers KIND so site.yaml can bind it
class MyRule(Rule):
    KIND = "my_rule"                # ← unique name; cannot shadow a built-in

    def configure(self, *, my_param: float = 10.0, **params):
        """Consume YOUR params. Always call super().configure(**params) —
        it rejects unknown leftovers, so typos in site.yaml fail at load."""
        super().configure(**params)
        if self.zone is None or self.zone.type != "polygon":
            raise ValueError(f"rule '{self.name}': needs a polygon zone")
        self.my_param = float(my_param)
        self._state = {}            # whatever per-track/per-rule state you need

    def on_frame(self, ts, detections):
        """Called once per processed frame (at the group's detect_fps).
        `detections` is ALREADY filtered by classes + min_conf."""
        ...

    def on_track_lost(self, ts, track_id):
        """A track hasn't been seen for lost_timeout_s. Clean up its state,
        close any open visit, etc."""
        self._state.pop(track_id, None)

    def live_state(self):
        """OPTIONAL: tiny JSON dict of what's true right now (occupancy,
        timers). Published to state/live/<cam>.json ~5×/s for the live UI."""
        return {}

    def snapshot_state(self):
        """OPTIONAL but recommended when you keep counters/timers: JSON-safe
        dict persisted every ~30 s and across restarts."""
        return {}

    def restore_state(self, state):
        """Inverse of snapshot_state, called once at startup."""
```

### 7.2 What you get from the base class

**Attributes** (set from site.yaml, available after `configure`):
`self.site`, `self.cam_id`, `self.name` (rule instance name), `self.zone`
(a `Zone` with `.type` and `.points`, or `None`), `self.classes`,
`self.min_conf`, `self.sustain_s`, `self.cooldown_s`, `self.lost_timeout_s`.

**Helpers:**

```python
self.emit(ts, kind, data=None, *, severity="info", track_id=None)
# Creates the Event and sends it to every sink. kind is YOUR machine-readable
# name ("visitor_waiting_too_long"). severity: "info" or "alert".

self.cooled_down(ts, key="")        # -> bool
# True if cooldown_s has passed for this key (e.g. str(track_id)).
# CONSUMES the cooldown when it returns True — call it exactly at emit time:
#     if condition and self.cooled_down(ts, str(d.track_id)):
#         self.emit(...)
```

**Detection objects** (what `on_frame` receives):

```python
d.cam_id       # str
d.ts           # float epoch seconds (same value as on_frame's ts)
d.track_id     # int, persistent per camera; d.is_tracked is False if untracked
d.class_name   # "person", "car", ... (COCO labels)
d.confidence   # float 0..1
d.bbox         # (x, y, w, h) normalized 0..1, top-left origin
d.center       # (cx, cy) box center
d.foot         # (cx, y+h) bottom-center — USE THIS for floor zones
```

### 7.3 Hard rules

- **No pixels, no video, no GStreamer, no network, no blocking I/O.** A kernel
  that takes milliseconds per frame slows every rule on that camera.
- **Time comes from `ts`, never `time.time()`** — otherwise your kernel breaks
  under replay and in tests.
- **Expect track IDs to churn.** Occlusions swap/split IDs. Design with
  `sustain_s`, grace windows, and cooldowns; never assume an ID lives forever.
- **Expect sampled frames.** At `detect_fps: 2`, a person can appear for 0.4 s
  and never be seen. If your rule needs to catch fast events, its camera
  belongs in a faster group.
- **State must be JSON-safe** in `snapshot_state` (str keys, plain values).

### 7.4 Kernel-vs-config decision table

| Requirement | Answer |
|---|---|
| Count people through a door | built-in `line_crossing` |
| How long people stay somewhere / live occupancy | built-in `zone_dwell` |
| How many people are in a room | built-in `headcount` |
| Alert when someone enters an area | built-in `zone_intrusion` |
| Alert when someone *stays too long* | custom (section 8.1) |
| Only alert outside working hours | custom wrapper (section 8.2) |
| Two object classes too close (forklift + person) | custom, `boxes_iou`/distance on centers |
| Anything needing colors, faces, text, PPE | **model change → engine team**, not a kernel |

---

## 8. Worked examples

### 8.1 Waiting too long (per-track timer + alert)

Client ask: *"Alert if a visitor waits at reception > 5 minutes."*

```python
# apps/reception_wait.py
from frameinsight.geometry import point_in_polygon
from frameinsight.rules import register_kernel
from frameinsight.rules.base import Rule


@register_kernel
class ReceptionWait(Rule):
    KIND = "reception_wait"

    def configure(self, *, max_wait_minutes: float = 5, **params):
        super().configure(**params)
        if self.zone is None or self.zone.type != "polygon":
            raise ValueError(f"rule '{self.name}': needs a polygon zone")
        self.max_wait_s = max_wait_minutes * 60
        self._since = {}                      # track_id -> entered ts

    def on_frame(self, ts, detections):
        poly = list(self.zone.points)
        for d in detections:
            if not point_in_polygon(d.foot, poly):
                self._since.pop(d.track_id, None)
                continue
            started = self._since.setdefault(d.track_id, ts)
            if ts - started > self.max_wait_s and self.cooled_down(ts, str(d.track_id)):
                self.emit(ts, "visitor_waiting_too_long",
                          {"waited_min": round((ts - started) / 60, 1)},
                          severity="alert", track_id=d.track_id)

    def on_track_lost(self, ts, track_id):
        self._since.pop(track_id, None)

    def live_state(self):                     # live UI shows current waiters
        return {"waiting_now": len(self._since)}

    def snapshot_state(self):                 # survive restarts mid-wait
        return {"since": {str(k): v for k, v in self._since.items()}}

    def restore_state(self, state):
        self._since = {int(k): v for k, v in state.get("since", {}).items()}
```

```yaml
  - name: waiting_alert
    camera: reception
    kernel: reception_wait
    zone: zones/reception.json#waiting_area
    params: {classes: [person], min_conf: 0.5, max_wait_minutes: 5, cooldown_s: 600}
```

### 8.2 Time-windowed rule (after-hours only)

Client ask: *"Presence in the store room is fine 9:00–18:00, alert otherwise."*
Pattern: convert `ts` to local time inside the kernel; the condition simply
includes the clock.

```python
# apps/after_hours.py
import datetime
from zoneinfo import ZoneInfo
from frameinsight.geometry import point_in_polygon
from frameinsight.rules import register_kernel
from frameinsight.rules.base import Rule

TZ = ZoneInfo("Asia/Karachi")


@register_kernel
class AfterHours(Rule):
    KIND = "after_hours"

    def configure(self, *, open_hour: int = 9, close_hour: int = 18, **params):
        super().configure(**params)
        if self.zone is None or self.zone.type != "polygon":
            raise ValueError(f"rule '{self.name}': needs a polygon zone")
        self.open_hour, self.close_hour = int(open_hour), int(close_hour)
        self._inside_since = {}

    def _is_closed(self, ts):
        h = datetime.datetime.fromtimestamp(ts, TZ).hour
        return not (self.open_hour <= h < self.close_hour)

    def on_frame(self, ts, detections):
        if not self._is_closed(ts):
            self._inside_since.clear()
            return
        poly = list(self.zone.points)
        for d in detections:
            if not point_in_polygon(d.foot, poly):
                self._inside_since.pop(d.track_id, None)
                continue
            first = self._inside_since.setdefault(d.track_id, ts)
            if ts - first >= self.sustain_s and self.cooled_down(ts, str(d.track_id)):
                self.emit(ts, "after_hours_presence",
                          {"confidence": round(d.confidence, 2)},
                          severity="alert", track_id=d.track_id)

    def on_track_lost(self, ts, track_id):
        self._inside_since.pop(track_id, None)
```

```yaml
    params: {classes: [person], min_conf: 0.6, sustain_s: 5,
             cooldown_s: 900, open_hour: 9, close_hour: 18}
```

### 8.3 Two-class proximity (forklift ↔ pedestrian near-miss)

Pattern: frame-level rule over *pairs* of detections; no zone needed.

```python
# apps/near_miss.py
import math
from frameinsight.rules import register_kernel
from frameinsight.rules.base import Rule


@register_kernel
class NearMiss(Rule):
    KIND = "near_miss"

    def configure(self, *, class_a: str = "person", class_b: str = "truck",
                  max_gap: float = 0.06, **params):
        # note: put BOTH classes in site.yaml `classes:` so the filter passes them
        super().configure(**params)
        self.class_a, self.class_b = class_a, class_b
        self.max_gap = float(max_gap)   # normalized distance between feet points

    def on_frame(self, ts, detections):
        people = [d for d in detections if d.class_name == self.class_a]
        machines = [d for d in detections if d.class_name == self.class_b]
        for p in people:
            for m in machines:
                gap = math.dist(p.foot, m.foot)
                if gap < self.max_gap and self.cooled_down(ts, f"{p.track_id}:{m.track_id}"):
                    self.emit(ts, "near_miss",
                              {"gap": round(gap, 3)},
                              severity="alert", track_id=p.track_id)
```

```yaml
    params: {classes: [person, truck], min_conf: 0.5, max_gap: 0.06, cooldown_s: 60}
```

Caveat to state honestly to the client: normalized 2-D distance is a proxy —
0.06 near the camera is more meters than 0.06 far away. For a fixed camera
you tune `max_gap` per camera; true metric distance needs calibration.

---

## 9. Testing: replay + pytest

### 9.1 The replay format (one frame per line, JSONL)

```json
{"cam": "reception", "ts": 12.4, "objects": [
  {"id": 17, "cls": "person", "conf": 0.83, "bbox": [0.41, 0.22, 0.06, 0.31]}
]}
```

- `ts` — relative seconds (replay rebases to now) or absolute epoch.
- `bbox` — `(x, y, w, h)` normalized, same convention as live.
- `id` — track ID; keep it stable while "the same person" is present.
- Blank lines and `#` comments are allowed.

Run it:

```bash
frameinsight replay <site-dir> recordings/scenario.jsonl --console
frameinsight replay <site-dir> recordings/scenario.jsonl            # to real sinks
frameinsight replay <site-dir> recordings/scenario.jsonl --speed 1  # real-time pace
```

### 9.2 Crafting a recording

Write a 20-line generator per scenario (see
`examples/school/make_sample_data.py` in core for a full one):

```python
# recordings/make_waiting_scenario.py
import json

def obj(tid, fx, fy, w=0.05, h=0.2):
    """Object whose FEET are at (fx, fy)."""
    return {"id": tid, "cls": "person", "conf": 0.9,
            "bbox": [round(fx - w/2, 4), round(fy - h, 4), w, h]}

frames = []
t = 0.0
while t <= 380:                       # person waits 380 s in the waiting area
    frames.append({"cam": "reception", "ts": round(t, 1),
                   "objects": [obj(1, 0.5, 0.6)]})
    t += 0.5                          # ~2 fps is plenty for a dwell scenario

with open("recordings/waiting_6min.jsonl", "w") as fh:
    for f in frames:
        fh.write(json.dumps(f) + "\n")
```

Expected result of the replay: exactly one `visitor_waiting_too_long` at
t≈300 s, silenced afterwards by the cooldown. Make the negative scenario too
(waits 2 min → zero alerts). **Commit both.** They are your regression suite —
every engine upgrade re-runs them.

You can also record *real* detections from a running site (ask ops to enable
the detection recorder sink) — real data beats synthetic for tuning
`min_conf` and grace windows.

### 9.3 pytest for kernels (no site.yaml needed)

```python
# tests/test_reception_wait.py
import importlib.util, sys
from pathlib import Path
from frameinsight.types import Detection
from frameinsight.zones import Zone

# import the plugin so it registers
spec = importlib.util.spec_from_file_location(
    "site_apps.reception_wait", Path(__file__).parent.parent / "apps/reception_wait.py")
mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

from frameinsight.rules import KERNELS

AREA = Zone(name="waiting_area", type="polygon",
            points=((0.3, 0.4), (0.7, 0.4), (0.7, 0.9), (0.3, 0.9)))

def det(ts, tid, fx, fy):
    return Detection(cam_id="reception", ts=ts, track_id=tid,
                     class_name="person", confidence=0.9,
                     bbox=(fx - 0.025, fy - 0.2, 0.05, 0.2))

def make(events, **params):
    return KERNELS["reception_wait"](
        site="t", cam_id="reception", name="t", emit=events.append,
        zone=AREA, classes=["person"], min_conf=0.5, cooldown_s=600, **params)

def test_alert_fires_after_threshold():
    events = []
    rule = make(events, max_wait_minutes=5)
    for t in range(0, 320, 2):                       # waits 320 s
        rule.process_frame(float(t), [det(float(t), 1, 0.5, 0.6)])
    alerts = [e for e in events if e.kind == "visitor_waiting_too_long"]
    assert len(alerts) == 1                          # once, then cooldown holds
    assert alerts[0].severity == "alert"

def test_short_wait_is_silent():
    events = []
    rule = make(events, max_wait_minutes=5)
    for t in range(0, 120, 2):                       # only 2 minutes
        rule.process_frame(float(t), [det(float(t), 2, 0.5, 0.6)])
    assert not [e for e in events if e.kind == "visitor_waiting_too_long"]
```

Drive `rule.process_frame(...)` (not `on_frame`) — that path applies the
class/confidence filters and the track-lost pruning, exactly like production.

---

## 10. Zone Studio

The local web UI for zones and live verification. Needs the `[studio]` extra
and (for the live tab) ffmpeg — both are in the edge image.

```bash
./fi.sh studio /site --host 0.0.0.0        # on the edge box → http://<box>:8765
frameinsight studio <site-dir>             # laptop, if it can reach the cameras
```

- **Zones tab** — pick a camera, grab a fresh snapshot, draw polygons and
  lines with the mouse, name them, save. Writes normalized coordinates into
  `zones/<cam>.json` — identical to hand-written files.
- **Live tab** — one camera at a time with detection boxes, your zones,
  occupancy/timers overlaid. The overlay comes from `state/live/<cam>.json`
  which the running pipeline publishes ~5×/s — Studio never touches the GPU
  pipeline itself.

**Security:** Studio has no auth and can see cameras and edit zones. Bind it
to the site LAN / Tailscale only; never expose the port to the internet.

After drawing: `frameinsight validate .` then commit the zone files.

---

## 11. Running live on the edge box

```bash
git clone https://github.com/frameinsight/<client>-site && cd <client>-site
cp .env.example .env && $EDITOR .env       # camera credentials (git-ignored)

./fi.sh validate /site                     # always validate on the box first
./fi.sh run /site                          # all groups, supervised
./fi.sh run /site -g fast                  # one group only (debugging)
./fi.sh studio /site --host 0.0.0.0        # zones + live view
```

What `run` does: one OS process per site.yaml group, each owning one
DeepStream pipeline (`nvurisrcbin×N → nvstreammux → nvinfer → nvtracker →
probe`). A crashed group restarts alone after 10 s; the others keep running.
RTSP drops auto-reconnect. The runtime also emits health events (section 12).

`fi.sh` pins the engine version (`IMAGE=ghcr.io/frameinsight/edge:vX.Y.Z`),
mounts the site at `/site` and model packs at `/models`, applies the required
`--ulimit nofile=65536` and `--network host`, and reads `.env`.

Permanent service (ops usually owns this):

```ini
# /etc/systemd/system/frameinsight-<client>.service
[Unit]
Description=FrameInsight edge — <client>
After=docker.service network-online.target
[Service]
WorkingDirectory=/opt/sites/<client>-site
ExecStart=/opt/sites/<client>-site/fi.sh run /site
Restart=always
RestartSec=15
[Install]
WantedBy=multi-user.target
```

---

## 12. Events, sinks, and querying results

### Event envelope (every event, every sink)

```json
{"ts": 1783508492.4, "site": "cubicle-office", "cam_id": "reception",
 "rule": "room_entry_counter", "kind": "line_crossed", "severity": "info",
 "track_id": 17, "data": {"direction": "in", "totals": {"in": 14, "out": 9}}}
```

### System events (emitted by the runtime itself, `rule: "_system"`)

| kind | severity | When |
|---|---|---|
| `heartbeat` | info | Every `heartbeat_s`: per-camera frame counts + last-frame age (`cam_id: "_server"`) |
| `camera_stalled` | alert | A camera produced no frames for ~1.5× the heartbeat period (re-alerts at most every 5 min) |

Your dashboards get camera health for free — don't build it into kernels.

### Sink reference

| type | Options | Notes |
|---|---|---|
| `console` | — | One JSON line per event on stdout (⇒ `docker logs`) |
| `jsonl` | `path` | Append-only; survives crashes; the local source of truth |
| `sqlite` | `path` | Table `events(ts, site, cam_id, rule, kind, severity, track_id, data)` |
| `supabase` | `table`, `url_env`, `key_env`, `batch` (50), `flush_s` (5) | Batched background POSTs; bounded queue; a dead uplink never blocks the pipeline |

Paths are relative to the site dir. All sinks receive all events; a failing
sink is logged and skipped.

### Handy SQLite queries (`sqlite3 events/events.db`)

```sql
-- entries today
SELECT COUNT(*) FROM events
WHERE kind='line_crossed' AND json_extract(data,'$.direction')='in'
  AND ts > strftime('%s','now','start of day');

-- entries per hour
SELECT strftime('%H', ts, 'unixepoch', 'localtime') h, COUNT(*)
FROM events WHERE kind='line_crossed' GROUP BY h ORDER BY h;

-- average dwell (zone_dwell rules)
SELECT rule, ROUND(AVG(json_extract(data,'$.dwell_s')),1) avg_s, COUNT(*) visits
FROM events WHERE kind='dwell_completed' GROUP BY rule;

-- open alert stream
SELECT datetime(ts,'unixepoch','localtime'), cam_id, kind, data
FROM events WHERE severity='alert' ORDER BY ts DESC LIMIT 20;
```

---

## 13. State files

| File | Written by | Purpose |
|---|---|---|
| `state/<group>.json` | dispatcher, every ~30 s, atomic | Rule `snapshot_state()` — counters/timers survive restarts. Delete it to reset counters. |
| `state/live/<cam>.json` | runtime, ~5×/s, atomic | Latest detections + each rule's `live_state()` — consumed by Zone Studio's live tab (or any local UI). |

Both are git-ignored. Never commit them.

---

## 14. Upgrading the engine version

1. Read core's `CHANGELOG.md` between your pinned tag and the target.
2. Bump the pin: `IMAGE=` in `fi.sh` and your laptop's pip install.
3. `frameinsight validate .` — schema still accepted?
4. `pytest` + replay **all** recordings — same events out?
5. Deploy (git pull on the box, restart the service).

Rollback = revert the pin. That's the entire risk surface, which is why sites
pin tags and never branches.

---

## 15. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `validate` fails: *unknown params ['max_wait_mins']* | Typo'd kernel param in site.yaml — check the kernel's `configure` signature |
| `validate` fails: *camera 'x' is in no group* | Add it to a group; rules only run on decoded cameras |
| `error: environment variable OFFICE_NVR_TMPL is not set` at run | `.env` missing on the box, or var name mismatch with site.yaml |
| Rule never fires in replay | 1) `classes`/`min_conf` filtering everything (drop `min_conf` to 0.1 to test) 2) zone tests the **feet** point — is `bbox` placed so feet land inside? 3) `sustain_s` longer than the scenario |
| Line counter counts double | Increase `recross_cooldown_s`; check the person isn't oscillating across a line drawn on a busy pixel edge |
| in/out swapped | Swap `label_left`/`label_right` (line direction is a→b as drawn) |
| Dwell visits fragment into many | Increase `exit_grace_s`; consider `tracker: NvDCF` for that group |
| Headcount jumps around | Increase `window_s`; it reports a median, so widen the window |
| Fast walkers occasionally missed | Group's `detect_fps` too low for that camera — move it to a faster group |
| `camera_stalled` alerts | Camera/NVR/network issue — check RTSP with `ffplay`, check `.env` URL |
| Events missing after crash | They aren't — check `events/events.jsonl` (append-only); SQLite/Supabase catch up on restart |
| Studio live tab: video but no boxes | The pipeline isn't running (`./fi.sh run /site`) — boxes come from `state/live/*.json` |

---

## 16. Cheat sheet

```bash
# dev loop (laptop)
frameinsight validate .
frameinsight replay . recordings/x.jsonl --console
pytest
frameinsight kernels .

# deploy loop (edge box)
git pull && ./fi.sh validate /site
sudo systemctl restart frameinsight-<client>    # or ./fi.sh run /site
./fi.sh studio /site --host 0.0.0.0             # zones + live view :8765

# results
sqlite3 events/events.db "SELECT ..."
tail -f events/events.jsonl | jq .
```

**Standard guards:** `classes` · `min_conf` · `sustain_s` · `cooldown_s` · `lost_timeout_s`
**Kernel hooks:** `configure` · `on_frame` · `on_track_lost` · `live_state` · `snapshot_state`/`restore_state`
**Helpers:** `self.emit(ts, kind, data, severity=, track_id=)` · `self.cooled_down(ts, key)` · `d.foot` · `point_in_polygon`
**Never:** engine edits · credentials in files · pixels in kernels · branch pins · `time.time()` in kernels
