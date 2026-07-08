# VisionSense Product Architecture

*The complete software architecture: languages, frameworks, technology choices, the
platform-vs-apps model, remote fleet management, the cloud SaaS dashboard, and what we
sell as subscription. Written 2026-07-04 against the current codebase
([src/](../src/): Python · FastAPI · Redis · Ultralytics/TensorRT · ByteTrack).*

---

## 1. The product is three planes, not one program

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  EDGE PLANE (client site — one-time sale)                                   │
│  GPU box on premises. Runs capture → inference → tracking → rules → alerts. │
│  Fully functional with internet down. Video NEVER leaves the site.          │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │ outbound-only TLS (events, metrics, snapshots)
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  CLOUD PLANE (our SaaS — subscription sale)                                 │
│  Multi-tenant dashboard: analytics, reports, heatmaps, multi-branch rollup, │
│  WhatsApp alert delivery, retention tiers.                                  │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────────────┐
│  CONTROL PLANE (our office — how we operate the fleet)                      │
│  Device registry, config push, signed OTA updates, remote debugging,        │
│  health monitoring of every client box from one screen.                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

The control plane is what makes "client reports a bug Tuesday morning, fix is live at
their site Tuesday afternoon, without leaving the office" real. It is not a product the
client sees — it is *our* operating leverage, and it also powers the paid Care Plan.

## 2. Design principles (the decisions everything else follows from)

1. **One platform, many apps.** Every client runs the *identical* platform code. What
   differs per client is **data, not code**: camera list, zone polygons, rule configs
   (the 10 kernels from [builder-spec.md](builder-spec.md)), model pack, alert routing.
   "Different applications per client" = different YAML, same binaries. A bug fix is one
   image push to the whole fleet; a new app sale is a config flip.
2. **Offline-first edge.** The box must detect, alert locally, and record events with the
   internet cut. Cloud sync is store-and-forward: events queue locally and replay when the
   link returns. No cloud round-trip is ever in the detection path.
3. **Outbound-only connectivity.** The edge box opens connections out; nothing dials in.
   No port forwarding at the client site, no static IPs, works behind any router. Remote
   access rides the same outbound tunnel.
4. **Video stays on-site; events go to cloud.** The cloud receives JSON events, aggregate
   metrics, and alert snapshots (single JPEGs) — never video streams. This is
   simultaneously our privacy pitch, our bandwidth budget (~KBs/min, works on 4G), and
   our cloud-cost moat.
5. **Everything versioned, everything rollback-able.** Container images are signed and
   tagged; per-site config lives in git ("site-as-code"). Every remote change is a commit;
   every bad update auto-rolls back on failed health check.

## 3. Language, framework & technology choices

**Direct answer to "which language":** keep Python where the ecosystem is Python, add Go
for the one component that must never die, use TypeScript for the dashboard. Do not
rewrite the pipeline in C++/Rust — we measured the GPU 60–80% idle; our ceiling is a
software *scheduling* fix inside Python, not a language problem.

| Component | Language / Framework | Why (and why not the alternative) |
|---|---|---|
| **Vision pipeline** (edge) | **Python 3.11+** · Ultralytics · TensorRT · GStreamer(NVDEC) · supervision/ByteTrack | The entire CV ecosystem is Python; the hot loops already execute in C++/CUDA under the hood (TensorRT, NVDEC, NumPy). A Rust/C++ rewrite buys <10% at 10× dev cost. Fix the measured scheduler ceiling with: GPU-side preprocessing (CuPy/DALI), preview decoupled from the detect loop, one process per concern. NVIDIA DeepStream (C++) is the >100-cam-per-box escape hatch — evaluate only when a real deployment demands it. |
| **Edge API + local UI** | **Python · FastAPI** (already built) | Serves health, config, MJPEG preview, local mini-dashboard. Stays in-process with the pipeline. |
| **Edge agent** (updater, tunnel, watchdog) | **Go** (single static binary) | This is the component that must survive when everything else is broken — it re-runs containers, applies updates, opens the support tunnel. A 10 MB static binary with no Python venv to corrupt is the right tool. Alternative: plain `docker compose` + Watchtower for v1, graduate to the Go agent in phase 2. |
| **Event bus (on box)** | **Redis Streams** (already integrated) | Pipeline publishes; sync-agent and local UI consume with consumer groups; doubles as the store-and-forward buffer. NATS JetStream is the swap-in if we ever outgrow it — same pattern. |
| **Local persistence** | **SQLite** (events, WAL mode) + rotating JPEG snapshot dir | Zero-admin, one file, survives power cuts. Postgres on the edge is overkill. |
| **Packaging** | **Docker Compose** + NVIDIA Container Toolkit; images per service | One `docker compose pull && up -d` is the whole update mechanism. K3s/Kubernetes on edge boxes is complexity we don't need at 1 box/site. |
| **Cloud backend** | **Python · FastAPI** · SQLAlchemy · Pydantic | Same language as edge = shared event/config schema models (one `visionsense-schemas` package), one team, no context switch. |
| **Cloud database** | **PostgreSQL + TimescaleDB** extension | Events are a time-series; Timescale gives hypertables, compression (10–20×), `time_bucket()` for hourly rollups, and continuous aggregates for dashboards — while staying normal Postgres for tenants/users/billing. One database, both jobs. |
| **Snapshot/object storage** | **S3-compatible**: Cloudflare R2 (zero egress fees) or self-hosted MinIO on the same VPS for v1 | Alert snapshots are the bulky part; R2's free egress matters when dashboards display them. |
| **Cloud ingestion** | **HTTPS batched JSON** (v1) → MQTT (EMQX) when we need sub-second live tiles | HTTPS retry-with-backoff is firewall-proof and debuggable with curl. Don't start with a broker you have to babysit. |
| **Dashboard frontend** | **TypeScript · Next.js · Tailwind · shadcn/ui · ECharts** | The dashboard IS the subscription product — it must look sellable. Server components for report pages, ECharts for heatmaps/time-series. |
| **Alerts delivery** | **WhatsApp Business Cloud API** (Meta) via cloud plane; SMS fallback (local gateway) | Centralizing WhatsApp in the cloud plane = one business number, template management, delivery receipts, and per-tenant quota metering (it's billable!). Edge falls back to local buzzer/UI when offline. |
| **Remote access** | **Tailscale** (WireGuard mesh) on every box | SSH to any client box from the office as if it were on the LAN, no client firewall changes. Self-host Headscale later if fleet cost matters. |
| **Fleet monitoring** | **Prometheus remote-write → VictoriaMetrics + Grafana** (internal) | The pipeline's Metrics class already collects GPU/VRAM/CPU/camera-up; ship them home. One Grafana screen shows every client box; alert on "camera down > 10 min at site X" before the client calls. |
| **CI/CD** | **GitHub Actions** → GHCR container registry → staged fleet rollout (dev box → beta sites → all) | Every merged fix produces signed images; rollout is moving a git tag. |
| **Auth (cloud)** | FastAPI JWT + `fastapi-users` (v1) → Keycloak if enterprise SSO appears | Don't buy identity infrastructure before a client demands SSO. |

## 4. Edge box: service layout

```
┌── GPU box (Ubuntu, Docker Compose) ─────────────────────────────────────────┐
│                                                                             │
│  vision-core        capture(NVDEC) → latest-frame buffer → batch TensorRT   │
│  (Python)           → ByteTrack → RULE KERNELS → events → Redis Streams     │
│                                                                             │
│  edge-api           FastAPI: /health /status /events, MJPEG preview,        │
│  (Python)           local mini-dashboard, zone-drawing UI for installers    │
│                                                                             │
│  sync-agent         Redis consumer → SQLite (store&forward) → HTTPS batch   │
│  (Python)           to cloud; snapshot upload to R2; config pull + apply    │
│                                                                             │
│  edge-agent         Go static binary: watchdog (restarts unhealthy          │
│  (Go)               services), signed OTA image updates + rollback,         │
│                     Tailscale tunnel, disk janitor                          │
│                                                                             │
│  redis              event bus + buffer            sqlite: events.db         │
└─────────────────────────────────────────────────────────────────────────────┘
```

Each service is a container; `vision-core` crashing never takes down the agent that can
fix it. This maps 1:1 onto the current code: [pipeline.py](../src/pipeline.py) is
`vision-core`, [api.py](../src/api.py) is `edge-api`, [events/publisher.py](../src/events/publisher.py)
grows into `sync-agent`. The refactor is extraction, not rewrite.

## 5. The platform/app model (your "base architecture + apps on top")

Exactly right, and it's already specified: [builder-spec.md](builder-spec.md) proved all
100 catalogued applications reduce to **10 rule kernels** + temporal decorators + sinks.
So:

- **Platform (code, identical everywhere):** pipeline, the 10 kernels, sinks (WhatsApp/
  log/metric/report/signal), model runtime, sync, agent. Versioned as container images.
- **App (config, per client):** a YAML file naming a kernel, a detection class set, zones,
  thresholds, schedules, and alert routing — e.g. `counter-unmanned.yaml`,
  `ppe-compliance.yaml`. Installing an app = adding a file + `reload`. **An app is a SKU.**
- **Model packs (data, per vertical):** `coco-base` (day one), `ppe-pack`, `plates-pk`,
  `fire-smoke` — TensorRT engines + class maps, versioned and pushed OTA like images.
- **Site definition (per client, in git):**

```
sites/afzal-mart/
  site.yaml          # tenant id, box hardware, update channel (stable/beta)
  cameras.yaml       # RTSP urls, det_interval, model assignment per camera
  zones/cam03.json   # polygons drawn at install time
  apps/              # one YAML per purchased app  ← the sellable unit
  models.lock        # pinned model-pack versions
```

A new client deployment = `git init` from a vertical template (restaurant/market/industry
presets from the catalog), edit cameras, draw zones, push. A bug fix = platform image
bump, config untouched. A new app sale = one YAML in `apps/`, priced from the menu.

## 6. Cloud plane: multi-tenant SaaS

```
edge boxes ──HTTPS batches──▶ ingest-api ──▶ TimescaleDB (events hypertable,
                                  │           continuous aggregates: hourly/daily)
                                  ├──▶ R2/MinIO (snapshots)
                                  └──▶ alert-router ──▶ WhatsApp Business API / SMS

dashboard (Next.js) ◀── query-api (FastAPI) ◀── TimescaleDB + R2
control-api ──▶ device registry, config versions, OTA channels, audit log
```

- **Tenancy:** `org → site → camera → app` hierarchy; `tenant_id` on every row +
  Postgres row-level security. One database serves all clients until ~hundreds of sites.
- **Events contract** (the one schema both planes share, versioned):

```json
{ "v": 1, "tenant": "afzal-mart", "site": "gulberg", "cam": "cam03",
  "app": "counter-unmanned", "type": "zone_absence", "severity": "alert",
  "ts": "2026-07-04T14:03:22+05:00", "dedupe_key": "cam03/counter/1720089",
  "payload": { "zone": "counter", "duration_s": 320 },
  "snapshot": "r2://afzal-mart/2026/07/04/evt_8231.jpg" }
```

- **Dashboard features by tier** (see §8): live status wall, alert feed with snapshots,
  footfall/queue/heatmap analytics, attendance reports, compliance scorecards (PPE
  violations by shift — factory owners love league tables), **multi-branch comparison**
  (the chain-owner killer feature), scheduled PDF/WhatsApp weekly reports.
- **Ops reality for v1:** all of this fits one 8 GB VPS (Hetzner/Contabo) running
  Compose: FastAPI ×2, Postgres+Timescale, MinIO, Caddy. Scale later, not now.

## 7. The remote-fix story, end to end (your Tuesday-bug scenario)

1. **Detect** — often before the client does: every box streams metrics home; Grafana
   alerts us "site afzal-mart: cam07 disconnected 3×/hr" or "vision-core restart loop".
2. **Reach** — `ssh box-afzal-mart` over Tailscale from the office. Logs are structured
   JSON (`journalctl`/`docker logs`); events and config are inspectable on the box.
3. **Reproduce** — copy the site's config + a captured clip into the lab; our benchmark
   harness replays it (`scripts/` already does exactly this with MediaMTX).
4. **Fix** — patch platform code, PR, CI builds signed image `vision-core:1.4.2`.
5. **Rollout** — promote to `beta` channel (our own box + 1 friendly site), soak, then
   `stable`. Each box's edge-agent pulls, health-checks (`/health` + event heartbeat),
   and **auto-rolls back** to 1.4.1 on failure.
6. **Verify & close** — fleet screen shows all boxes green on 1.4.2; the audit log has
   who shipped what where; client gets a WhatsApp "resolved" note from support.

If it's a *config* bug (wrong zone, threshold too tight): edit the site repo, agent pulls
config, rules reload without dropping camera connections. Minutes, not a site visit.

## 8. What we sell (the money architecture)

**One-time (edge plane):** hardware box (quoted via the [calculator](https://claude.ai/code/artifact/94d6c1fe-f1ff-48ec-937e-477241d34fb4))
+ installation & zone calibration + perpetual license for the purchased app bundle.
Runs forever without us — that honesty is a sales weapon against cloud-camera rivals.

**Subscription (cloud + care):**

| Product | What they get | Anchor price (PKR) |
|---|---|---|
| **Dashboard Basic** | Live wall, alert feed, 7-day history, 1 user | 1,500 /cam/mo — but price per *site band* in practice (e.g. ≤8 cams 10k/mo) |
| **Dashboard Pro** | + analytics (footfall, heatmaps, queues), attendance & compliance reports, 90-day history, scheduled PDF/WhatsApp reports, 5 users | ~2× Basic |
| **HQ / Multi-branch** | Cross-site comparison, league tables, org roles | + per additional site |
| **Care Plan** | Remote monitoring of their box, updates, priority fix SLA, camera-down alerts *to us*, annual health report | ~15–20% of box price /yr |
| **App add-ons** | New apps enabled remotely from the 100-app menu (config flip = near-pure margin) | per app/mo or one-time |
| **Model updates** | Improved PK-plates / PPE / fire models pushed OTA | bundled in Care or standalone |
| **Alert quota** | WhatsApp templated alerts metered (Meta charges per conversation) | included allowance + top-ups |
| **Retention & API** | 1-yr archive, CSV/API export for their ERP | add-on |

Design consequence: **retention tiers, user seats, per-app enablement, alert quotas, and
multi-site rollup must be first-class columns in the tenancy model from day one** — they
are the billing levers. Add Stripe/local-bank invoicing in phase 2; invoice manually first.

## 9. Security & privacy checklist

Outbound-only TLS 1.3; per-device token (site-scoped, revocable); signed images (cosign)
— agent refuses unsigned updates; Tailscale ACLs (office → boxes, never box → box);
snapshots encrypted at rest in R2; face embeddings stay **on-site only** (cloud gets
"person #12 checked in", never biometrics) — sell this loudly; per-tenant RLS in
Postgres; audit log on every control-plane action.

## 10. Build order (pragmatic phases)

| Phase | Weeks | Deliverable |
|---|---|---|
| **1 — Productize the edge** | 1–4 | Extract `sync-agent` (Redis→SQLite→HTTPS), Compose packaging, Tailscale on the box, site-as-code repo layout, rule kernels v1 (`zone_state` + WhatsApp sink — covers 72% of catalog) |
| **2 — Minimum sellable cloud** | 5–10 | ingest-api + Timescale + R2, Next.js dashboard v1 (live wall, alerts, footfall), WhatsApp Business API, manual invoicing. **First subscription revenue.** |
| **3 — Fleet at scale** | 11–16 | Go edge-agent (signed OTA + rollback + watchdog), VictoriaMetrics+Grafana fleet screen, staged channels, remaining kernels |
| **4 — Growth features** | 17+ | Multi-branch HQ, app marketplace flips, model-pack OTA, billing automation, MQTT live tiles |

**Parallel track — DeepStream spike (2 weeks, start now):** promoted out of phase 4 after
deeper analysis — it attacks all three measured walls (VRAM/cam, host CPU, scheduler) at
once and could ~3× cameras-per-box on identical hardware. Plan and go/no-go gate:
[deepstream-evaluation.md](deepstream-evaluation.md).

**Rule for every phase:** the demo box in our office runs the exact stack a client gets —
we are client #0 of our own fleet.
