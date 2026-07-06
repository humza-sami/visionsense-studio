# VisionSense Studio — What We're Building, Selling, and Have Proven

*Single entry point for the project. Updated 2026-07-04. Detail lives in the linked docs;
this file is the story.*

---

## 1. What we are doing

We turn **existing CCTV cameras into business intelligence and safety systems** using
computer vision — no new cameras, no cloud dependency, one GPU server on the client's
premises.

The core insight our whole product rests on: **every sellable camera-AI application is the
same four-stage pipeline** — only the rules and alerts differ:

```
PERCEIVE (YOLO26 detection) → TRACK (ByteTrack IDs) → CONDITION (business rules) → EMIT (alert/report)
```

The software ([src/](src/)) is a decoupled producer–consumer backend: per-camera capture
threads with NVDEC hardware decode → latest-frame buffer → motion gate → **one shared
batched TensorRT inference** → per-camera tracking → pluggable logic handlers → events
(WhatsApp alerts, dashboards, reports) + live MJPEG preview. Runs on a single consumer
GPU. Dev on macOS, deploy on Ubuntu/NVIDIA with zero code changes ([README.md](README.md),
[PLAN.md](PLAN.md)).

**The moat is not the model** — "person detected" is a commodity. The moat is the rules
engine: *"counter unmanned > 5 min during business hours, excluding prayer break, WhatsApp
the owner with a snapshot."* We build that engine once and configure it per client.

## 2. Our services (what we sell)

Full catalog: **100 applications across 13 verticals**, every one decomposed and validated
in [data/usecases/catalog.yaml](data/usecases/catalog.yaml) (machine-readable) and
[docs/builder-spec.md](docs/builder-spec.md) (analysis). All 100 reduce to **10 reusable
rule kernels** — a new client app is configuration, not new engineering.

**Cross-vertical modules (the menu every client picks 4–6 from):**
face attendance · zone intrusion + after-hours alerts · ALPR (gates/parking/pumps) ·
theft/object-removal · PPE & uniform compliance · fire/smoke visual detection ·
phone-usage detection · presence/idle dashboards · footfall + heatmaps + queue analytics ·
weapon detection · fall/man-down · abandoned objects — all delivered with **WhatsApp
snapshot alerts** (the feature owners love most).

**Vertical packages (measured, quotable):**

| Package | Typical apps | Models |
|---|---|---|
| **Restaurant / QSR** | table turnover, queue, kitchen hygiene, fire, till monitoring | n + s + m |
| **Market / Retail** | footfall, aisle heatmaps, exit theft, counter coverage, phone usage | n + s + l |
| **Industry / Safety** | PPE compliance, danger zones, fire/smoke, man-down, line manning | m + n + l |
| **Banks / Offices** | queue SLA, covered-face, weapon (x-large on critical cams), attendance | s + x |
| **Residential / Societies** | gate ALPR, guard patrol verification, perimeter, night loitering | n + custom |

Readiness: **34/100 apps ship day-one** with the pretrained detector; **52/100** with
face-ID/pose/OCR added; the rest need custom training — backlog ranked by revenue unlock
in [docs/builder-spec.md](docs/builder-spec.md) §5 (license plates first, then a single
multi-class PPE dataset that unlocks factory + food + hospital at once).

## 3. What we want to do (roadmap)

1. **Build the rules-engine "builder"** ([docs/builder-spec.md](docs/builder-spec.md)) —
   replace hand-written per-app handlers with 10 generic kernels + YAML config.
   Order: kernel base class (shared debounce/schedule/cooldown) → `zone_state` kernel
   (covers 72% of catalog) → WhatsApp alert sink (77/100 apps) → aggregation/reports →
   geometry kernels → face-ID → PPE classifier → pose/correlation.
2. **Fix the software scheduler ceiling** — detection saturates ~3.8 fps/cam with the GPU
   62% idle (serial Python loop). Optimization: GPU-side color convert, decouple preview,
   parallel group scheduling. This raises both fps and cameras-per-box **for free**.
3. **Custom model training** — license plates (Pakistani format + OCR), PPE pack,
   fire/smoke, shelf gaps. Roboflow-style datasets fine-tuned on client footage.
4. **Standardize quote hardware** — reference builds below; validate the 12 GB tier
   (RTX 3060) with the same benchmark suite when the card arrives.
5. **Scale the sales motion** — marketing team quotes from the calculator (link below)
   without engineering involvement.

## 4. Testing results & analysis (what we proved)

**Test rig:** RTX 3070 Ti 8 GB · 8-core CPU · 16 GB RAM · TensorRT @640 · real NVR-style
704×576 H.265 @ 25 fps streams. **47 scenario runs across 5 campaigns**, all dumps indexed
in [artifacts/benchmarks/INDEX.md](artifacts/benchmarks/INDEX.md).

**Headline findings:**

| Finding | Number | Consequence |
|---|---|---|
| VRAM is the only real limit | GPU compute never exceeded 62%, NVDEC ≤ 16%, CPU ≤ 45% | count memory, not FLOPs, when quoting |
| Per-camera VRAM cost | **~190 MB/cam** (decode surfaces, regardless of detection fps) | sizing formula: 1.3 GB base + engine contexts + 190 MB × cams + 1 GB spare |
| Single-model ceilings (8 GB) | **n 24+ · s ~20 · m 16 · l 12 · x 8** | m×16 is compute-bound (98% peak) — the only compute wall we found |
| Multi-model ceiling | **max 3 model types per 8 GB box** — every 4- and 5-engine mix OOM'd at load | 4+ model sites need 12 GB or rule consolidation |
| Camera wall at low fps | **32 cams @ 2 fps pass (7.4 GB); 36 OOM** | capture fps ≠ detect fps; 100-cam site = 4× 8 GB boxes or 1× 24 GB GPU |
| Vertical packages | restaurant 14 ✅ · market 12 ✅ (16 tight) · industry 8 ✅ / 14 ❌ | quote sheet: [docs/quote-sheet.md](docs/quote-sheet.md) |
| x-large is cheap on few cams | bank pkg (s×6 + x×2 weapon @ 8 fps) = **3.7 GB** | premium accuracy on 2–4 critical cams is a safe upsell |
| Scheduler artifact | fast targets reach ~75% (GPU idle) | guarantee 1–3 fps in contracts; 5+ fps after optimization (roadmap #2) |
| Cost model validated | predicted all 3 OOMs + nano ceiling correctly ([data/calibration.json](data/calibration.json)) | calculator extrapolations to other GPUs are trustworthy |

**Analysis in one paragraph:** the 8 GB consumer card is a memory-shaped box, not a
compute-shaped one. Alert-grade analytics (1–3 fps) are nearly free in compute, so profit
per box is maximized by (a) packing cameras up to the VRAM wall, (b) keeping model count
≤ 3 per box (consolidating rules onto shared models is the single biggest capacity lever),
and (c) selling accuracy where risk concentrates — the x-large model on 2–4 critical
cameras costs ~1.5 GB, not 4 GB. Fault-isolation and the host-CPU wall make several
mid-size boxes better than one giant GPU for 50+ camera sites.

## 5. Where everything lives

| Artifact | What it is |
|---|---|
| **[Capacity report + quote calculator](https://claude.ai/code/artifact/94d6c1fe-f1ff-48ec-937e-477241d34fb4)** | Shareable page for the marketing team: full report, GPU/CPU/RAM/storage/PSU calculator, reference builds (₨175k starter → ₨1.1M 100-cam), used/Jetson/Intel-Arc alternatives |
| [docs/quote-sheet.md](docs/quote-sheet.md) | Measured quoting rules & tables (engineering source of truth) |
| [docs/architecture.md](docs/architecture.md) | **Complete product architecture**: edge/cloud/control planes, tech stack & languages, platform-vs-apps model, remote fleet management, SaaS subscription design |
| [docs/builder-spec.md](docs/builder-spec.md) | Rules-engine architecture: 10 kernels, rule schema, build order |
| [data/usecases/catalog.yaml](data/usecases/catalog.yaml) | All 100 use cases, machine-readable (builder acceptance tests) |
| [artifacts/benchmarks/](artifacts/benchmarks/) | Every test dump, indexed ([INDEX.md](artifacts/benchmarks/INDEX.md)) |
| [BENCHMARK.md](BENCHMARK.md) | Original benchmark narrative incl. real 15-camera NVR run |
| [gpu_calculator.html](gpu_calculator.html) | Internal engineering-grade sizing tool |
| [README.md](README.md) / [PLAN.md](PLAN.md) / [STATUS.md](STATUS.md) / [PROGRESS.md](PROGRESS.md) | Code architecture · build plan · box status · work log |
