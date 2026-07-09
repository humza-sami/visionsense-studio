# FrameInsight Platform Architecture

*The centralized, reusable product design: one edge runtime for every client, config-driven
apps, Supabase cloud, two dashboards, and full remote fleet operations. Written 2026-07-10.
Grounded in the measured DeepStream results
([deepstream-benchmark-report.md](deepstream-benchmark-report.md)) and the rule-kernel
analysis ([builder-spec.md](builder-spec.md)).*

---

## 1. The thesis

> **Ship the same product to every client; only data differs.**

One versioned Docker image — the **FrameInsight Edge Runtime** — runs at every site
(restaurant, factory, retail store). A client is a **folder of config files** (cameras,
zones, app rules), not a codebase. Events flow to one multi-tenant Supabase; one online
dashboard serves every client; one fleet screen serves FrameInsight ops.

Consequences:
- A bug fix is **one image update rolled out to the whole fleet from the office** — no
  site visits to read logs.
- A new client is **~1 day of configuration**, zero platform code.
- A new *application* for an existing client is usually **one YAML file**, deployed
  remotely in minutes (and billable as an add-on).

## 2. The five layers

```
┌─ 1 · EDGE RUNTIME (GPU box, on-site) ─────────────────────── 100% reused ─┐
│   DeepStream: NVDEC decode → YOLO (TensorRT FP16) → NvSORT tracking       │
│   → metadata probe → RULES ENGINE (kernels + plugins) → events            │
│   + local SQLite buffer + snapshot store + health agent + updater         │
├─ 2 · ON-SITE DASHBOARD (served by the box) ────────────────  100% reused  │
│   live tiles with boxes (WebRTC via mediamtx), event feed, camera status  │
├─ 3 · SYNC AGENT (box → cloud) ─────────────────────────────  100% reused  │
│   alerts immediately · aggregates per minute/hour · heartbeat per 60 s    │
│   store-and-forward through internet outages                              │
├─ 4 · CLOUD (Supabase + Next.js) ───────────────────────────  100% reused  │
│   multi-tenant Postgres+RLS, Auth, Storage, Realtime, Edge Functions      │
│   client dashboard (analytics/reports) + FrameInsight fleet-ops screen    │
├─ 5 · PER-CLIENT (the only "written each time" part)                       │
│   sites/<client>/: site.yaml · zones/*.json · apps/*.yaml · plugins/ (rare)│
└────────────────────────────────────────────────────────────────────────────┘
```

## 3. Layer 1 — Edge Runtime (`frameinsight/edge:<semver>` Docker image)

Contents of the image (identical at every site):

| Component | Role | Stack |
|---|---|---|
| **Pipeline builder** | Reads `site.yaml`, constructs the DeepStream graph at startup (N cameras → per-group model → tracker → probe). No hand-written pipeline per client. | Python `pyservicemaker` |
| **Model packs** | Versioned folders: ONNX + labels + parser + pgie template. `yolo26-base`, `fire-v2`, `ppe-v1`, HuggingFace onboards via the same format (Inference Builder MCP scaffolds config/parser). TensorRT engines build **on-site on first boot** (engines are GPU-specific). | ONNX/TensorRT + C++ parser |
| **Rules engine** | Runs stock kernels + site plugins against the metadata stream (§4). | Python |
| **Local buffer** | Events + snapshots in SQLite ring (≈7 days). Box is fully functional offline. | SQLite |
| **Health agent** | Samples GPU/VRAM/temp/NVDEC/CPU/disk + per-camera state; feeds heartbeats. | Python |
| **Updater** | Pulls signed images per update channel (beta/stable), health-checks, auto-rolls back. | Watchtower v1 → Go agent later |

Mixed model groups (e.g. 10×xlarge + 20×small) run as **two pipeline processes sharing
the GPU** — validated pattern (see the mixed benchmark: 40 cams full 30 fps, 14 % GPU).

Deployment = `docker compose up` with the client's config folder mounted.

## 4. The plugin protocol (maximum-reuse mechanism)

The whole "SDK" is a ~30-line contract every dev codes against. Platform owns plumbing;
plugins own logic.

```python
@dataclass
class Detection:                 # handed to rules per frame, per object
    cam_id: str
    class_id: int                # 0=person, 67=cell phone, …
    bbox: tuple                  # (left, top, w, h)
    confidence: float
    track_id: int                # persistent per object — enables all time-based rules

class Rule(ABC):
    """One business rule. Stateful. Instantiated per camera from apps/*.yaml."""
    def __init__(self, cam_id: str, zones: list[Zone], params: dict): ...
    @abstractmethod
    def on_frame(self, dets: list[Detection], ts: float) -> list[Event]: ...

@dataclass
class Event:                     # the ONLY thing that leaves the rules engine
    type: str                    # "zone_intrusion", "chair_dwell", "fire"
    severity: str                # info | alert | critical
    cam_id: str; ts: float
    payload: dict
    snapshot: bool = False
```

- The runtime ships **10 stock kernels** on this protocol (presence/absence, count, dwell,
  proximity, line-cross, vanish, …) — per [builder-spec.md](builder-spec.md) these cover
  ~90 % of the 100-app catalog.
- **An app is YAML**, not code:

```yaml
# sites/restaurant-lahore/apps/kitchen_phone.yaml
rule: proximity
cameras: [cam03, cam04]
params: {class_a: person, class_b: cell_phone, max_dist_px: 120, sustain_s: 30}
emit:  {type: phone_in_kitchen, severity: alert, snapshot: true}
```

- Truly novel logic = one `Rule` subclass in `sites/<client>/plugins/`, auto-loaded.
  Nothing else in the stack changes.

**Framework-or-SDK answer:** build a *thin internal platform*. The `Rule`/`Event` protocol
is the SDK surface; resist adding abstraction beyond it.

## 5. Layer 3 — Sync cadence (edge → Supabase)

| Data | Cadence | Notes |
|---|---|---|
| Alert events | immediate | + snapshot to Supabase Storage; Edge Function → WhatsApp |
| Aggregates (counts, dwell sums) | 1-min batches → hourly rollups | cheap analytics later |
| Health heartbeat | 60 s | one upsert per box |
| Raw per-frame detections | **never leave the box** | SQLite ring ~7 days; keeps cloud cost + privacy clean |

Store-and-forward: outage → queue locally → replay on reconnect. Detection never blocks
on the network.

## 6. Layer 4 — Cloud on Supabase

Use all five Supabase products:

- **Postgres + RLS** — multi-tenant day one: every row carries `org_id`; RLS makes
  cross-client reads impossible; a `frameinsight_staff` role sees all orgs (fleet view).
- **Auth** — client logins for the online dashboard.
- **Storage** — alert snapshots (images, never video).
- **Realtime** — live alert feed on the dashboard, zero extra infra.
- **Edge Functions + pg_cron** — WhatsApp dispatch, nightly report PDFs, and
  *"box silent > 5 min → page FrameInsight ops."*

**Core schema (7 tables):**

```
orgs(id, name, plan)
sites(id, org_id, name, tz)
boxes(id, site_id, version, last_seen, gpu_model)
cameras(id, site_id, name, rtsp_meta, status, link_quality)
events(id, site_id, cam_id, type, severity, ts, payload jsonb, snapshot_url)
rollups_hourly(site_id, cam_id, metric, hour, value)          -- analytics fuel
health_heartbeats(box_id, ts, gpu_pct, vram_gb, temp_c, nvdec_pct,
                  cpu_pct, disk_free_gb, cams_up, cams_total)
```

**Online dashboard** (Next.js + Supabase client): per-client analytics (footfall trends,
compliance scorecards, dwell reports — the monthly-billable product) plus the **health
page**: server last-ping, GPU/VRAM/temp, cameras up (e.g. 23/24), per-camera link quality.

**Camera "internet strength"** is measured on the box as RTSP stability — fps steadiness,
reconnect count, frame latency — classified `good / degraded / down`. This is the metric
that predicts client complaints, and it's free to collect from the pipeline.

## 7. Layer 5 — What a client actually is

```
sites/restaurant-lahore/          ← a git folder. This IS the client.
  site.yaml                       cameras, RTSP URLs, model groups, schedules
  zones/cam03.json                polygons drawn at install (counter, kitchen, exit)
  apps/*.yaml                     purchased rules + thresholds
  plugins/                        usually empty (novel rules only)
  models.lock                     pinned model-pack versions
```

“Site-as-code”: every remote fix is a reviewed commit with history. Dev protocol:
**platform changes → the image (semver); client changes → their folder (git).**

## 8. Remote operations (the original pain, solved end-to-end)

1. **Know first** — heartbeat gap or camera flap triggers pg_cron → WhatsApp to ops,
   before the client calls.
2. **Reach the box** — Tailscale (outbound-only) → SSH from the office; structured JSONL
   logs on disk; recent error lines ride along with heartbeats.
3. **Fix once, ship fleet-wide** — CI builds `edge:x.y.z` → beta channel (office box + one
   friendly site) → stable; updater health-checks and auto-rolls back on failure.
4. **Config-only fixes** — edit the site folder; box pulls; rules hot-reload. Minutes.

## 9. Stack summary (per the dev guide)

| Piece | Choice | Why |
|---|---|---|
| Edge pipeline | DeepStream + `pyservicemaker` (Python) | graph runs in C/CUDA; Python only builds it |
| Bbox parsers | C++ (only forced-C++ spot) | runs per detection |
| Rules engine / plugins | Python | metadata-only arithmetic; readability wins |
| On-site API/dashboard | FastAPI + one web page; mediamtx for WebRTC live view | DeepStream RTSP-out drops overlays (measured) |
| Sync/health agents | Python; updater → Go later | IO-bound |
| Cloud | Supabase (PG+RLS, Auth, Storage, Realtime, Functions) | five products, one bill |
| Online dashboard | Next.js + Supabase client | the sellable subscription surface |

## 10. Build order

1. **Edge runtime skeleton** — pipeline-from-`site.yaml` + probe → Rule engine with 2
   kernels (zone presence, dwell). *After this, the next client is config-only.*
2. **Sync agent + Supabase schema + heartbeats** — events and health flowing.
3. **On-site dashboard** — live tiles + event feed.
4. **Online dashboard** — analytics + the health page; RLS multi-tenancy.
5. **Reports + WhatsApp** — the monthly-billable layer (Edge Functions + pg_cron).
6. Later: Go updater with signed staged rollouts; model-pack OTA; app marketplace flips.

## 11. Scale ceilings (so nothing surprises us)

- **Per box:** decoder-bound ~64× 720p cameras (measured); mixed models share one GPU as
  two processes; bigger sites = multi-decoder GPU or second box.
- **Fleet:** boxes are independent — one site failing affects one site.
- **Cloud:** single Supabase carries hundreds of sites if raw detections stay on-box;
  `events` is the only fast-growing table → partition by month + archive to Storage.
- **Team:** the protocol keeps new devs productive in days: learn `Rule`, `Event`,
  `site.yaml` — not GStreamer.
