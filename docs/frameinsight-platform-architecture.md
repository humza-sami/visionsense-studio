# FrameInsight Platform — Architecture & Engineering Guide

*The complete design for devs: one reusable edge runtime, config-driven per-client apps,
Supabase cloud, dashboards, fleet operations — plus the detailed mechanics (zones,
per-camera rates, model onboarding) and the production practices we hold every deployment
to. Grounded in measured results ([deepstream-benchmark-report.md](deepstream-benchmark-report.md))
and the kernel analysis ([builder-spec.md](builder-spec.md)). Updated 2026-07-10.*

---

## 1. Thesis and principles

> **Ship the same product to every client; only data differs.**

One versioned Docker image — the **FrameInsight Edge Runtime** — runs at every site.
A client is a **folder of config files** (cameras, zones, app rules), not a codebase.
Events flow to one multi-tenant Supabase; one online dashboard serves every client; one
fleet screen serves FrameInsight ops.

Non-negotiable principles (each one earned by a measured failure):

1. **Never touch pixels in app code.** Decode, inference, tracking stay inside DeepStream's
   GPU plugins. App code sees only metadata (class, bbox, confidence, track ID). Our old
   Python stack broke this rule and walled at 32 cameras; DeepStream keeping frames
   GPU-resident runs 64+ on the same GPU.
2. **Platform changes go in the image (semver). Client changes go in their folder (git).**
   Any change that doesn't fit one of those two boxes is a design smell.
3. **The box works offline.** Detection, rules, local alerts, on-site dashboard — all
   function with the internet down. Cloud sync is store-and-forward, never in the
   detection path.
4. **Raw video and per-frame detections never leave the site.** Cloud gets events,
   aggregates, heartbeats, and alert snapshots. This is our privacy pitch, our bandwidth
   budget, and our Supabase bill, all at once.
5. **No secrets in code or configs — ever.** Camera/NVR credentials come from environment
   (`NVR_TMPL` etc.). We caught real credentials hours before a public push once; the rule
   exists because of that day.

---

## 2. System overview

```
┌─ 1 · EDGE RUNTIME (GPU box, on-site) ─────────────────────── 100% reused ─┐
│   DeepStream: NVDEC decode → YOLO/TAO (TensorRT FP16) → NvSORT/NvDCF      │
│   → metadata probe → RULES ENGINE (kernels + site plugins) → events       │
│   + SQLite buffer + snapshot store + health agent + updater               │
├─ 2 · ON-SITE DASHBOARD (served by the box) ────────────────  100% reused  │
│   live tiles with boxes (WebRTC via mediamtx), event feed, camera status, │
│   ZONE EDITOR (draw polygons on live snapshot)                            │
├─ 3 · SYNC AGENT (box → cloud) ─────────────────────────────  100% reused  │
│   alerts immediately · aggregates per min/hour · heartbeat / 60 s         │
│   store-and-forward across outages                                        │
├─ 4 · CLOUD (Supabase + Next.js) ───────────────────────────  100% reused  │
│   multi-tenant Postgres+RLS, Auth, Storage, Realtime, Edge Functions      │
│   client dashboard (analytics/reports) + FrameInsight fleet-ops screen    │
├─ 5 · PER-CLIENT (the only “written each time” part)                       │
│   sites/<client>/: site.yaml · zones/*.json · apps/*.yaml · plugins/(rare)│
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Edge Runtime in depth

### 3.1 The Docker image (`frameinsight/edge:<semver>`)

| Component | Role | Stack |
|---|---|---|
| Pipeline builder | Reads `site.yaml`, constructs DeepStream graph(s) at startup | Python `pyservicemaker` |
| Model packs | Versioned model folders (§7) | ONNX/TensorRT + C++ parser |
| Rules engine | Kernels + site plugins on the metadata stream (§4–5) | Python |
| Local buffer | Events + snapshots, SQLite ring ≈7 days | SQLite |
| Health agent | GPU/VRAM/temp/NVDEC/CPU/disk + per-camera state + camera-move check | Python |
| Updater | Signed image pulls per channel (beta/stable), health-check, auto-rollback | Watchtower v1 → Go agent |

Deployment = `docker compose up` with the client folder mounted. Engines are **built
on-site on first boot** (TensorRT engines are GPU-specific; never copy engines between
machines).

### 3.2 `site.yaml` — the group is a *(model, detect_fps, cameras)* triple

Detection rate is a property of the **app**, not the camera: intrusion needs 8–10 det/s,
dwell/occupancy is fine at 1–2. Cameras are therefore grouped by *(model, rate)* and the
builder spawns **one pipeline process per group** (processes share the GPU — validated:
two concurrent pipelines, 40 cams, full 30 fps, 14 % GPU):

```yaml
# sites/restaurant-lahore/site.yaml
org: restaurant-lahore
mux: {width: 1280, height: 720}          # THE coordinate space (see 3.3)
groups:
  - name: fast_alerts                     # intrusion, exit theft
    model: yolo26s
    detect_fps: 10                        # → nvinfer interval=2 at 30fps input
    cameras: [cam01, cam07]
  - name: slow_analytics                  # dwell, tables, occupancy
    model: yolo26s
    detect_fps: 1                         # → interval=29
    cameras: [cam02, cam03, cam04]
cameras:
  cam01: {rtsp: "${NVR_TMPL:ch=1}", note: "main entrance"}
  cam02: {rtsp: "${NVR_TMPL:ch=2}", note: "dining left"}
```

**Why groups, precisely:** `nvinfer`'s `interval` property skips whole *batches*, and a
batch contains frames from all cameras in that pipeline — so one nvinfer cannot give
camera A 10 det/s and camera B 1 det/s. The three real mechanisms:

| Mechanism | How | Cost / flaw | Use |
|---|---|---|---|
| **1. Rate groups → separate pipelines** (default) | one process per (model, rate) | same model in two groups = engine VRAM paid twice (~0.5 GB for `s`); more processes to watch. Keep ≤ 2–3 groups/box | the architecture |
| **2. Per-source decimation** | `drop-frame-interval` on the source/decoder drops all but every Nth frame of that camera post-decode | NVDEC load barely drops (reference frames must decode anyway); tracker + live view of that cam get choppy | fine-tuning inside a group |
| **3. Detect at max rate, subsample in rules** | rules ignore ticks they don't need | pays GPU for discarded detections | interim only, while compute is far from the wall |

### 3.3 Coordinate spaces — read this before writing any geometry

`nvstreammux` rescales every camera to one resolution (`mux.width × mux.height`). All
bounding boxes in metadata (`NvDsObjectMeta.rect_params`) are **in mux space** — not in
the camera's native resolution. Therefore:

- **Zones are stored normalized (0–1)** and converted to pixels once at load:
  `poly_px = polygon_norm × (mux_w, mux_h)`. Pixel-stored zones silently break when a
  camera is swapped 720p→1080p or mux resolution changes. Design the bug out.
- Every zone file stores a **reference snapshot** of the camera at draw time — the anchor
  for camera-move detection (§8.1).

```json
// sites/restaurant-lahore/zones/cam01.json
{
  "reference": {"w": 1280, "h": 720, "snapshot": "cam01_ref.jpg", "taken": "2026-07-10"},
  "zones": [
    {"name": "restricted_area",
     "polygon_norm": [[0.12,0.40],[0.55,0.38],[0.60,0.95],[0.10,0.97]]}
  ]
}
```

### 3.4 The probe and per-camera dispatch

One shared pipeline serves fifty different per-camera app configs because every frame in
a batch carries its `source_id`. The pipeline knows nothing about apps; the registry
knows nothing about GStreamer. **That seam is the reusability story.**

```python
# startup: wire rules per camera from apps/*.yaml
registry: dict[str, list[Rule]] = defaultdict(list)
for spec in load_app_specs("sites/<client>/apps/*.yaml"):
    for cam_id in spec.cameras:
        zones = load_zones(f"zones/{cam_id}.json", wanted=spec.params.get("zone"))
        registry[cam_id].append(KERNELS[spec.rule](cam_id, zones, spec.params, spec.emit))

# per frame: attached after nvtracker
def on_batch(pad, info):
    batch = pyds.gst_buffer_get_nvds_batch_meta(hash(info.get_buffer()))
    for frame in iter_frames(batch):
        cam_id = source_map[frame.source_id]          # pad index → "cam01"
        dets = [Detection(cam_id, o.class_id,
                          (o.rect_params.left, o.rect_params.top,
                           o.rect_params.width, o.rect_params.height),
                          o.confidence, o.object_id)
                for o in iter_objects(frame)]
        for rule in registry.get(cam_id, []):
            for event in rule.on_frame(dets, frame_ts(frame)):
                event_bus.publish(event)              # Redis → sync-agent → Supabase
    return Gst.PadProbeReturn.OK
```

---

## 4. The plugin protocol (the entire “SDK” — keep it this small)

```python
@dataclass
class Detection:
    cam_id: str
    class_id: int              # 0=person, 56=chair, 67=cell phone …
    bbox: tuple                # (left, top, w, h) in MUX SPACE
    confidence: float
    track_id: int              # persistent per object — enables all time-based rules

class Rule(ABC):
    """One business rule. Stateful. Instantiated per camera from apps/*.yaml."""
    def __init__(self, cam_id: str, zones: dict[str, Zone], params: dict, emit: dict): ...
    @abstractmethod
    def on_frame(self, dets: list[Detection], ts: float) -> list[Event]: ...
    def snapshot_state(self) -> dict: return {}       # optional: persisted every ~30 s
    def restore_state(self, s: dict): pass

@dataclass
class Event:
    type: str                  # "zone_intrusion", "chair_dwell", "fire"
    severity: str              # info | alert | critical
    cam_id: str; ts: float
    payload: dict
    snapshot: bool = False     # attach JPEG evidence?
```

- Runtime ships the **stock kernels** (presence/absence, count, dwell, proximity,
  line-cross, vanish, …) — they cover ~90 % of the app catalog.
- **An app is YAML** (a kernel + parameters + cameras). Novel logic = one `Rule` subclass
  in `sites/<client>/plugins/`, auto-loaded. Nothing else changes.
- **Every kernel takes the four standard parameters** (§4.3). A kernel PR without them is
  incomplete.

### 4.1 Worked kernel: ZoneIntrusion (camera 1: “alert if someone enters this area”)

The naive version is three lines; the production version has four extra mechanisms, each
of which exists because the naive one fails in the field:

```python
class ZoneIntrusion(Rule):
    def __init__(self, cam_id, zones, params, emit):
        self.poly       = zones[params["zone"]].as_pixels(MUX_W, MUX_H)
        self.min_conf   = params.get("min_conf", 0.5)     # (1) phantom filter
        self.sustain_s  = params.get("sustain_s", 1.0)    # (2) debounce
        self.cooldown_s = params.get("cooldown_s", 60)    # (3) one intruder = one alert
        self._inside_since: dict[int, float] = {}
        self._last_alert:   dict[int, float] = {}

    def on_frame(self, dets, ts):
        events, seen = [], set()
        persons = [d for d in dets if d.class_id == 0 and d.confidence >= self.min_conf]
        for p in persons:
            foot = (p.bbox[0] + p.bbox[2]/2, p.bbox[1] + p.bbox[3])   # (4) feet anchor
            if point_in_polygon(foot, self.poly):
                seen.add(p.track_id)
                t0 = self._inside_since.setdefault(p.track_id, ts)
                if ts - t0 >= self.sustain_s and \
                   ts - self._last_alert.get(p.track_id, 0) >= self.cooldown_s:
                    self._last_alert[p.track_id] = ts
                    events.append(Event("zone_intrusion", "alert", self.cam_id, ts,
                                        {"track": p.track_id}, snapshot=True))
        for tid in list(self._inside_since):
            if tid not in seen: del self._inside_since[tid]
        return events
```

1. **Confidence floor** — dusk/noise produces 0.3-confidence phantoms; without a floor you
   WhatsApp the owner at 3 a.m. about a shadow.
2. **Sustain** — bboxes flicker across zone edges frame-to-frame; require continuous
   presence before firing.
3. **Cooldown per track** — one intruder must produce one alert, not thirty per second.
4. **Bottom-center (“feet”) anchor** — zones are drawn on the *floor* but bboxes are 2D
   rectangles: a person standing *behind* a zone has a bbox whose center overlaps it while
   their feet don't. Testing the feet point approximates “standing on that floor area.”
   Getting this wrong breaks every floor-zone rule under perspective.

### 4.2 Worked kernel: ChairDwell (camera 2: “how long was the person on the chair”)

Two designs; choose per situation, and say the honest limits out loud:

- **Design A — dwell in a drawn area (default).** Client draws a polygon around the
  table+chair *place*. Feet-in-polygon starts a per-`track_id` timer, with **hysteresis**:
  enter after ≥2 s inside, leave only after ≥5 s outside — so a waiter briefly occluding
  the guest doesn't split one 30-minute sit into six. Emit `chair_dwell {track, seconds}`
  on exit + periodic progress events for live dashboards. *No chair detection at all* —
  fewer detections, fewer failure modes. Right for fixed furniture (99 % of cases).
- **Design B — person-bbox ∩ chair-bbox (COCO 56) overlap.** Handles moved furniture, but:
  a person standing *in front of* a chair overlaps it (2D can't tell “on” from “before”),
  and the sitting person *occludes the chair*, making chair detections vanish mid-sit.
- **If the client needs true posture** (“sitting” vs “standing at the desk”), bbox
  geometry is not honest — that's a pose model as secondary inference (§7.4). Don't
  oversell rectangles.

### 4.3 Standard rule parameters (mandatory on every kernel)

| Param | Default | Prevents |
|---|---|---|
| `min_conf` | 0.5 | phantom detections firing rules |
| `sustain_s` | rule-specific | edge-flicker false positives |
| `hysteresis_exit_s` | > enter | occlusion splitting one visit into many |
| `cooldown_s` | 60 | alert storms from one incident |

---

## 5. Inputs: the zone lifecycle

1. **Draw** — install day, on-site dashboard → camera live snapshot → canvas polygon
   editor → name the zone. Installer draws *with the camera's perspective in mind* (train
   this: a floor zone drawn as seen by the camera, not as a top-down map).
2. **Store** — normalized polygons + reference snapshot → `sites/<client>/zones/camXX.json`
   via edge-api → committed to the site's git folder (every zone change is a reviewed,
   revertible commit).
3. **Load** — rules engine converts to mux-space pixels at startup.
4. **Hot-reload** — config-only changes (zones, thresholds, new app YAML) reload without
   restarting pipelines. Remote fix in minutes.
5. **Guard** — health agent periodically compares the current frame against the reference
   snapshot (§8.1) and pauses affected rules + alerts ops if the camera moved.

---

## 6. Models

### 6.1 Model-pack format (one format for every source)

```
packs/peoplenet-v2.6/
  model.onnx (or .etlt)      weights
  labels.txt                 class names
  parser.cpp / parser.so     output→bbox translator (if not a stock one)
  pgie.template.txt          nvinfer config template (normalization, dims, cluster-mode)
  pack.yaml                  version, source (NGC/HF/custom), license note, sha256
```

Engines (`*.engine`) are **never** in the pack — always built on the target GPU, offline
via `trtexec` (a build under live pipeline load once crashed the driver's GSP firmware;
we don't do that anymore).

### 6.2 Onboarding YOLO / HuggingFace models — normalization is the silent killer

A wrong `net-scale-factor`/`offsets` gives you a *working pipeline with garbage
confidences* — no error anywhere. Rules:

- Ultralytics YOLO: `net-scale-factor=1/255`, **no** offsets, RGB (`model-color-format=0`),
  `maintain-aspect-ratio=1` + `symmetric-padding=1` (must match training letterbox).
- YOLO26 is NMS-free (`[batch,300,6]` output) → our tiny copy-parser + `cluster-mode=4`.
- HF/other models: derive normalization from the model card *before* the first run; the
  Inference Builder MCP ships a normalization reference/calculator for exactly this.
- **Acceptance test for every onboarded model:** run one annotated frame and eyeball the
  boxes before any benchmark or deployment. A pipeline that runs is not a pipeline that
  detects.

### 6.3 NVIDIA model zoo (NGC / TAO) — yes, and often better than COCO YOLO

These are trained on **CCTV-angle** footage, unlike COCO's eye-level photos:

| Model | Use | Note |
|---|---|---|
| PeopleNet | person/bag/face from surveillance viewpoints | usually beats COCO-YOLO-person on ceiling cams |
| TrafficCamNet | vehicles from traffic-cam angles | gates, parking |
| LPDNet + LPRNet | plate detection + reading | the ANPR pipeline, pre-built |
| ReIdentificationNet | person re-ID embeddings | cross-camera “same person” |
| PoseClassificationNet / bodypose | posture | the honest fix for “actually sitting?” |
| RT-DETR warehouse | warehouse objects | Inference Builder MCP's own example |

Integration is the same pack format: `nvinfer` consumes TAO models natively; parsers come
from NVIDIA's `deepstream_tao_apps`; the MCP's `prepare_model_repository` downloads NGC
models + configs directly. **Cautions:** every distinct model costs engine VRAM and
possibly its own pipeline group — prefer one general detector + rules, add specialists
(plates, pose, fire) only where they clearly win; and check each model's NVIDIA license
for commercial terms before it ships in a quote.

### 6.4 Secondary inference (SGIE) — chaining, not mixing

An SGIE runs a *second model on the crops of the first* (detect person → classify
posture; detect car → read plate). That's how pose/plate/attribute models attach. It is
**not** the tool for running different models on different cameras — that's groups (§3.2).

---

## 7. Sync and cloud (Supabase)

### 7.1 Cadences

| Data | Cadence | Path |
|---|---|---|
| Alert events | immediate | insert + snapshot → Storage; Edge Function → WhatsApp |
| Aggregates (counts, dwell sums) | 1-min batches → hourly rollups | cheap analytics forever |
| Health heartbeat | 60 s | one upsert per box |
| Raw per-frame detections | **never leave the box** | SQLite ring ≈7 days |

Store-and-forward: outage → queue in SQLite → replay on reconnect. Detection never blocks
on the network.

### 7.2 Schema (7 tables) and tenancy

```
orgs(id, name, plan)
sites(id, org_id, name, tz)
boxes(id, site_id, version, last_seen, gpu_model)
cameras(id, site_id, name, status, link_quality)
events(id, site_id, cam_id, type, severity, ts, payload jsonb, snapshot_url)
rollups_hourly(site_id, cam_id, metric, hour, value)
health_heartbeats(box_id, ts, gpu_pct, vram_gb, temp_c, nvdec_pct, cpu_pct,
                  disk_free_gb, cams_up, cams_total)
```

Every row carries `org_id`-lineage; **RLS** makes cross-client reads impossible; a
`frameinsight_staff` role sees all orgs (fleet view). `events` is the only fast-growing
table → partition by month, archive old partitions to Storage.

### 7.3 Dashboards

- **On-site** (served by the box, works offline): live tiles with boxes (WebRTC via
  mediamtx — DeepStream's own RTSP-out drops OSD overlays; measured, don't use it for
  client-facing view), event feed, camera status, zone editor.
- **Online** (Next.js + Supabase): analytics and reports (the monthly-billable product) +
  the health page per site: last ping, GPU/VRAM/temp, cameras up (23/24), per-camera link
  quality. *Camera “internet strength” = RTSP stability measured on the box* (fps
  steadiness, reconnect count, frame latency) → `good / degraded / down`. It's free to
  collect and it's the metric that predicts client complaints.

---

## 8. Known failure modes and mandatory mitigations

| # | Failure | Why it's nasty | Mitigation (required, not optional) |
|---|---|---|---|
| 8.1 | **Camera moved/zoomed** | zones silently point at wrong floor; data goes quietly wrong | reference snapshot at draw time; health agent runs periodic frame-vs-reference similarity; below threshold → pause affected rules + alert ops (“re-draw zones”) |
| 8.2 | **2D bbox ≈ 3D reality** | perspective/occlusion make zone tests approximate | feet anchor for floor zones; sustain windows; installer training; sell trends & alerts, never cm-truth |
| 8.3 | **Track-ID switches** | occlusion → new ID → dwell timers split/reset | hysteresis absorbs short breaks; re-association pass (new ID near a just-lost ID within N s + high IoU → inherit timers); NvDCF tracker on dwell-critical cams; report dwell as ±, design analytics on aggregates |
| 8.4 | **Sampling misses fast events** | at 1 det/s a person can cross a small zone unseen between ticks | detection rate is an *app* property: intrusion 8–10/s, dwell 1–2/s; enforce via groups (§3.2) |
| 8.5 | **Zone drawing is manual labor** | doesn't amortize at 100+ sites | accept now; templates + assisted drawing later; budget it per install |
| 8.6 | **Rule state lives in RAM** | reboot at minute 20 of a sit → timer lost | kernels implement `snapshot_state()`; engine persists to SQLite every ~30 s and restores on boot |
| 8.7 | **fd exhaustion at scale** | 64+ RTSP sources exceed default 1024 fds → GstPoll assertion crash | `ulimit nofile=65536` in every container spec (measured, fixed once, keep forever) |
| 8.8 | **Engine build under load** | crashed GSP firmware once (full driver wedge, reboot) | engines built offline via `trtexec`, never inside a live pipeline |

---

## 9. Production best-practices checklist

### 9.1 Accuracy

- **ROI inference (`nvdspreprocess`) where the zone is the job.** For door/gate/zone
  cameras, define per-stream ROIs so the model runs **only on the marked region** instead
  of the full frame (`input-tensor-from-meta=1` on nvinfer). Double win: less compute *and*
  better accuracy — the zone fills more of the model's 640×640 input, so small/far objects
  land more pixels. Use on: entrances, tills, gates. Don't use where context matters
  (whole-floor occupancy).
- **Substream choice**: analytics run on substreams; 704×576 class substreams roughly
  double camera capacity vs 720p (the decoder is pixel-bound — our #1 measured finding).
  But mind small objects: if the target is tiny (far plates), ROI-inference on the main
  stream for *that camera* beats full-frame on a substream.
- **Match preprocessing to training** (§6.2): normalization, letterbox, color order.
  Verify with an annotated-frame eyeball test on every model onboarding.
- **Class filtering at the source**: `filter-out-class-ids` / per-class thresholds in the
  pgie config so rules never see classes they don't use.
- **Model choice per job**: smallest model that meets the app's accuracy = most cameras.
  CCTV-tuned zoo models (PeopleNet) over COCO YOLO for ceiling-angle person detection.
  Specialists (pose, plates) via SGIE only where bbox geometry is dishonest.
- **Per-camera tuning knobs live in YAML** (`min_conf`, thresholds) — never hardcode; day-2
  tuning must be a config commit, not a release.

### 9.2 Performance

- **FP16 always** (`network-mode=2`); INT8 (`=1`) with a calibration set when a model
  group is genuinely compute-bound (xlarge fleets).
- **`interval` per group**: alert-grade = 8–10 det/s only where needed; analytics at 1–2.
  Compute demand scales linearly with det_fps — this is the cheapest capacity lever.
- **Batching**: `nvstreammux batch-size` = cameras in the group; `nvinfer batch-size`
  sized to the engine profile (we ship b16/b32 engines).
- **Know the wall**: decoder ≈ 64 × 720p30 per NVDEC (measured). Past it: multi-NVDEC GPU
  (4090/5090/L4) or a second box. Compute is almost never the limit for n/s models.
- **≤ 2–3 pipeline processes per box** (groups); same model across groups costs its engine
  VRAM per process.

### 9.3 Reliability

- **Crash-safe by construction** (proven pattern from our benchmark harness): every
  component writes its state/results the moment they exist; per-process logs stream to
  disk as JSONL; a supervisor restarts unhealthy pipelines; GPU health is checked before
  (re)starts so a dead driver produces a clear alert, not junk.
- **Watchdogs + heartbeats**: pipeline emits a liveness tick; health agent escalates
  missing ticks locally (restart) and to cloud (ops alert) — “box silent > 5 min” pages
  *us*, not the client.
- **Timestamps**: rules use frame timestamps (NTP-synced hosts, `chronyd` on the box) —
  wall-clock drift corrupts dwell math and cross-camera correlation.
- **Update discipline**: beta channel (office box + one friendly site) soaks every image
  before stable; updater health-checks after pull and auto-rolls back on failure.

### 9.4 Security

- Secrets only via env/secret store; repo-wide secret scan in CI (we once caught real NVR
  credentials pre-push — the scan is not optional).
- Outbound-only connectivity (Tailscale for ops SSH; no inbound ports at client sites).
- Signed images; boxes refuse unsigned updates.
- Snapshots in Supabase Storage under per-org paths + RLS; no video in the cloud, ever.

### 9.5 Testing

- **Recorded-clip regression**: every kernel has a test that replays a recorded clip
  (via the MediaMTX relay harness) and asserts expected events. Rules are pure functions
  of (detections, time) — test them without a GPU by feeding synthetic `Detection` lists.
- **Capacity claims come from the benchmark harness** (`scripts/benchmark_*.py`), never
  from hand-waving; new GPU model = rerun the ladder before quoting it.

---

## 10. Fleet operations (the “no more site visits” loop)

1. **Know first** — heartbeat gap / camera flap / camera-moved → pg_cron → WhatsApp to ops.
2. **Reach** — Tailscale SSH from the office; JSONL logs on disk; recent error lines ride
   along with heartbeats for zero-SSH triage.
3. **Fix once, ship fleet-wide** — CI builds `edge:x.y.z` → beta → stable; auto-rollback.
4. **Config fixes** — edit `sites/<client>/`, box pulls, rules hot-reload. Minutes.

---

## 11. Repo layout and build order

```
frameinsight/
  edge/                # the runtime (one docker image)
    core/              pipeline builder (pyservicemaker), probe, dispatch
    rules/             kernel library + plugin loader (the Rule/Event protocol)
    api/               on-site dashboard + zone editor + local API (FastAPI)
    sync/              supabase sync agent (store-and-forward)
    health/            health agent (incl. camera-move check)
  cloud/
    supabase/          migrations, RLS policies, edge functions
    dashboard/         Next.js online dashboard (+ fleet ops view)
  packs/               model packs (yolo26-base, peoplenet, fire-v2, …)
  sites/               per-client config — “site-as-code”
    <client>/          site.yaml · zones/ · apps/ · plugins/ · models.lock
```

**Build order:** ① runtime skeleton — pipeline-from-`site.yaml` + probe + 2 kernels
(ZoneIntrusion, ChairDwell) running against the real NVR *(after this, the next client is
config-only)* → ② sync agent + Supabase schema + heartbeats → ③ on-site dashboard + zone
editor → ④ online dashboard + health page → ⑤ reports + WhatsApp (the billable layer) →
⑥ Go updater, model-pack OTA, assisted zone drawing.

## 12. Scale ceilings (measured, so nobody re-litigates them)

- **Per box**: ~64 × 720p cameras (single-NVDEC GPUs, decoder-bound); mixed models/rates as
  2–3 processes on one GPU; xlarge is the only compute-bound model at alert-grade rates.
- **Fleet**: boxes are independent — one site failing affects one site.
- **Cloud**: one Supabase carries hundreds of sites *because raw detections stay on-box*;
  partition `events` monthly.
- **Team**: a new dev learns `Rule`, `Event`, `site.yaml` — not GStreamer. That's the
  protocol doing its job.
