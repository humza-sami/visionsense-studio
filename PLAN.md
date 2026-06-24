# VisionSense Studio — Build Plan & Architecture

A live-demo platform for pitching AI-on-CCTV to clients. The user supplies an RTSP/webcam/USB feed; the system applies Ultralytics YOLO models in real time and visualizes the result so a prospect can see what their "real product" would look like.

This document is written to be handed directly to an AI coding agent. It defines the architecture, the data model, the screen flow, and an ordered build roadmap that de-risks the hardest unknowns first.

---

## 1. The architecture reality (read this first)

React + shadcn is the **face** of the product. It cannot do the actual work, because:

- **Browsers cannot consume RTSP.** There is no native RTSP support in any browser.
- **Browsers cannot run Ultralytics YOLO.** Inference (especially multi-stream) needs Python + a GPU.

So VisionSense Studio is a **two-process system**: a Python backend that ingests cameras and runs YOLO, and a React frontend that controls it and displays annotated video. They communicate over HTTP (video) and WebSocket (telemetry/events).

```
                          VisionSense Studio
 ┌──────────────────────────────────────────────────────────────────────┐
 │                                                                        │
 │   ┌───────────────────────┐         ┌──────────────────────────────┐  │
 │   │   FRONTEND (React)    │  HTTP   │      BACKEND (Python)        │   │
 │   │  Vite + shadcn/ui     │◄───────►│       FastAPI (async)        │   │
 │   │                       │   WS    │                              │   │
 │   │  • Splash / Setup     │         │  ┌────────────────────────┐  │   │
 │   │  • Camera grid        │         │  │   Camera Manager       │  │   │
 │   │  • Left sidebar:      │         │  │  (one worker / camera) │  │   │
 │   │    telemetry+controls │         │  └───────────┬────────────┘  │   │
 │   │  • Right sidebar:     │         │              │ frames        │   │
 │   │    Apps + Features    │         │  ┌───────────▼────────────┐  │   │
 │   └───────────┬───────────┘         │  │   Inference Engine     │  │   │
 │               │                     │  │  Ultralytics YOLO      │  │   │
 │   annotated   │  MJPEG / WS         │  │  detect/seg/pose/obb/  │  │   │
 │   video  ◄────┘                     │  │  cls/sem + track       │  │   │
 │                                     │  └───────────┬────────────┘  │   │
 │                                     │              │ results       │   │
 │                                     │  ┌───────────▼────────────┐  │   │
 │                                     │  │   Solutions Layer      │  │   │
 │                                     │  │  counting, in/out,     │  │   │
 │                                     │  │  heatmap, ROI, PPE...  │  │   │
 │                                     │  └────────────────────────┘  │   │
 │                                     │              ▲               │   │
 │                                     └──────────────┼───────────────┘   │
 │                                                    │ RTSP / USB / V4L2 │
 └────────────────────────────────────────────────────┼──────────────────┘
                                                       │
                                            ┌──────────▼──────────┐
                                            │  IP Cameras / NVR   │
                                            │  Webcam / USB cam   │
                                            └─────────────────────┘
```

**Packaging for demos:** build it as a web app (FastAPI serves the compiled React SPA), then optionally wrap it in **Tauri** (lightweight) or **Electron** for the polished "double-click → our logo → app" desktop experience you described. Start web-first; add the desktop wrapper in a later phase so it doesn't slow the core build.

---

## 2. Recommended stack

| Layer | Choice | Why |
|---|---|---|
| Frontend framework | React + Vite | Fast, your stated preference |
| UI components | shadcn/ui + Tailwind | Your provided theme drops straight in |
| Frontend state | Zustand | Lightweight; good for "active camera / active apps" state |
| Data fetching | TanStack Query | Camera lists, config, status polling |
| Live data channel | Native WebSocket client | Detections, counts, alerts, FPS |
| Backend | FastAPI (async) | First-class WebSockets, great for ML serving |
| Inference | Ultralytics (`ultralytics` pip pkg) | All YOLO tasks + ready-made solutions |
| Capture/decode | OpenCV (`cv2.VideoCapture`) + FFmpeg | RTSP, USB, V4L2 |
| Camera discovery | `onvif-zeep` + WS-Discovery | Auto-enumerate channels/streams |
| Annotated video transport | **MJPEG** (multipart/x-mixed-replace) for v1 | Simplest path that "looks like the real product"; WebRTC is the future upgrade |
| GPU | NVIDIA + CUDA (or CPU fallback with `yolo26n`) | Demo laptops should ship with a GPU if possible |
| Desktop wrapper (later) | Tauri or Electron | Native splash + offline demo build |

**Model lineup (from the current Ultralytics release, YOLO26):** sizes `n/s/m/l/x` across `detect / segment / pose / obb / classify` plus `semantic` (Cityscapes) and `cls` (ImageNet). For demos, default to **`yolo26n` / `yolo26s`** — speed matters more than peak accuracy when a prospect is watching latency.

---

## 3. Camera ingestion & the channel auto-load question

Your two example URLs are classic Dahua/Hikvision NVR patterns:

```
rtsp://test:welcome%40123@103.83.89.187:554/cam/realmonitor?channel=1&subtype=0
rtsp://admin:552050gmb@172.20.17.40:554/cam/realmonitor?channel=16&subtype=0
```

- `channel=N` → which camera on the NVR
- `subtype=0` → **main stream** (high-res, heavy)
- `subtype=1` → **sub stream** (low-res, light) ← use this for multi-camera grids
- `%40` in the password is URL-encoded `@` — handle encoding/decoding carefully in the setup form

**Yes, you can load all cameras automatically.** Three approaches, in order of robustness:

**A. ONVIF discovery (best, do this in a later phase).** Most NVRs/IP cameras support ONVIF. WS-Discovery scans the subnet and finds devices automatically; the ONVIF Media service then returns exact stream URIs, resolutions, and channel counts. No guessing.

**B. Channel-template probing (pragmatic, matches your URLs — build this first).** In setup, the user provides a base URL with a `{channel}` token plus a range:

```
Template: rtsp://admin:pass@172.20.17.40:554/cam/realmonitor?channel={channel}&subtype=1
Range:    1 – 16
```

The backend opens each channel in parallel (e.g. `ThreadPoolExecutor`) with a 2–3 second connection timeout, keeps the channels that connect, and discards dead ones. The survivors become the camera grid — no manual one-by-one entry. Use `subtype=1` for the grid to conserve bandwidth and GPU.

**C. Vendor HTTP API (optional).** Dahua CGI / Hikvision ISAPI can report the exact channel count if you want to skip probing a fixed range.

**Setup wizard must support three input modes:**
1. **RTSP** — single URL, or template + range (method B above)
2. **Webcam** — browser `getUserMedia` for the local cam, *or* backend `VideoCapture(0)` (prefer backend so it goes through the same pipeline)
3. **USB / V4L2** — backend enumerates `/dev/video*` (Linux) or DirectShow devices (Windows)

All three normalize to the same internal `Camera` object so the rest of the system doesn't care about the source.

---

## 4. The core concept: Features vs Applications

This is the heart of the product, so make the abstraction clean. There are two layers, and they map almost exactly onto Ultralytics' own structure (`tasks/` and `solutions/`).

### Features = primitives (the raw YOLO output)

These answer "**what does the model see?**" They are toggleable overlay layers on a camera:

| Feature | Ultralytics task | What it shows |
|---|---|---|
| Detect | detect | Bounding boxes + labels |
| Segment | segment | Instance masks |
| Classify | classify | Frame-level class label |
| Pose | pose | Skeleton keypoints |
| OBB | obb | Oriented (rotated) boxes |
| Semantic | semantic | Per-pixel scene segmentation |
| Track | track (ByteTrack/BoT-SORT) | Persistent IDs + motion trails |

Track is special — it's a modifier that sits on top of detect/segment/pose and gives every object a stable ID across frames. It's the foundation for any counting/duration application.

### Applications = solutions (business logic built on primitives)

These answer "**what business question does this solve?**" Each is a primitive + logic + configuration (ROI zones, counting lines, timers). Crucially, **most already exist in `ultralytics/solutions/` — wrap them, don't reimplement.**

| Your Application | Built from | Ultralytics solution to wrap | Notes |
|---|---|---|---|
| Head count | Detect(person) + count-in-frame | `object_counter` / `region_counter` | Easiest. Great first app. |
| Customer In/Out | Detect(person) + Track + line crossing | `object_counter` (line mode) | Needs tracking. The classic CCTV demo. |
| Manager presence in seat | Detect(person) inside a seat polygon + presence timer | `region_counter` + custom timer | User draws the seat ROI in the UI. |
| Manager mobile-usage duration | Detect(person + cell phone) co-occurrence, or pose (hand-near-head) + duration timer | custom (no direct solution) | **Hardest — see §6.** Phone is small and often occluded. |
| Safety equipment / PPE | Detect(helmet/vest) per person + compliance check | custom + PPE model or open-vocab | **Needs the right model — see §5.** |

**Free wins to show off** (already shipped as solutions — toggle them on to impress):
`heatmap` (foot-traffic heatmap), `speed_estimation` (vehicle speed), `security_alarm` (intrusion in a zone → alert), `queue_management`, `parking_management`, `distance_calculation`, `trackzone`, `vision_eye`, `analytics` (live charts), and **`object_blurrer`** (face/person blur — directly relevant to Pakistani privacy concerns and a strong trust signal in a pitch).

The right sidebar, then, has two groups: **Features** (per-camera overlay toggles) and **Applications** (per-camera logic toggles). Activating an Application auto-enables the Features it depends on (e.g. Customer In/Out auto-turns-on Detect + Track).

---

## 5. Model strategy & the PPE caveat (important for demo credibility)

COCO-pretrained YOLO knows **80 classes** — including `person`, `cell phone`, `car`, `truck`, `backpack`, etc. It does **not** know `hardhat`, `safety vest`, `fire`, `smoke`, `forklift`, or a license plate. If a client asks for PPE detection and you point a COCO model at workers, it will detect the people but not the helmets — an awkward moment in a live pitch.

Three ways to handle arbitrary client requests:

1. **Open-vocabulary models (the strategic unlock).** **YOLOE** and **YOLO-World** detect classes from a *text prompt* with zero training. At the meeting, the user types the target — `"hardhat"`, `"safety vest"`, `"forklift"`, `"fire extinguisher"` — and the model detects it live. This directly solves "we can't build all apps beforehand." Make a prompt box a first-class UI element.

2. **Pre-finetuned client-ready models.** Keep a small swappable library for the common high-value asks: PPE (the repo already ships a `construction-ppe` dataset, so a PPE-trained YOLO is straightforward to produce), fire/smoke, ANPR/number plates. Load on demand per camera.

3. **COCO models for the fast common cases.** Person counting, vehicle counting, phone detection — `yolo26n`/`yolo26s` handle these instantly with no setup.

**Recommended default:** COCO `yolo26s` for speed, with a one-click switch to **YOLOE/YOLO-World** when the client wants something custom. That combination covers ~everything a prospect will throw at you.

---

## 6. Honest take on the hard parts

State these expectations to your agent up front so it doesn't over-promise in the build:

- **Multi-stream real-time inference is GPU-heavy.** A demo laptop will *not* run 16 streams at full inference simultaneously. Mitigation (build this in from the start): **selective inference** — run full YOLO only on the *spotlighted/selected* camera and any camera with an active Application; show the rest of the grid as raw or low-FPS thumbnails. Use sub-streams, small models, and frame-skipping (process every Nth frame).
- **"Manager mobile-usage duration" is the trickiest Application.** Phones are small, often held below the desk or occluded by a hand. A reliable demo-grade version: detect `person` + `cell phone` and flag usage when a phone box overlaps/neighbors a person box, then accumulate duration via tracking. A pose-based variant (wrist keypoint near the head) can supplement it. Be candid that accuracy here is lower than person-counting; frame it as "indicative," not forensic.
- **MJPEG latency** is ~200–500 ms — perfectly fine for "look how it'll work" demos, but not "production real-time." WebRTC is the upgrade path when you need it.
- **PPE/custom classes** depend entirely on the model (see §5). Don't let the agent assume COCO covers them.

---

## 7. Data model

A clean schema your agent can implement directly. Each camera carries its own pipeline config, so cameras are independent.

```jsonc
// Camera
{
  "id": "cam_01",
  "name": "Entrance",
  "source": {
    "type": "rtsp | webcam | usb",
    "url": "rtsp://.../channel=1&subtype=1",   // for rtsp
    "device_index": 0                            // for webcam/usb
  },
  "status": "connecting | live | error | stopped",
  "pipeline": {
    "model": "yolo26s.pt",                        // or yolo26s-seg.pt, yoloe-..., etc.
    "task": "detect | segment | pose | obb | classify | semantic",
    "open_vocab_prompt": ["hardhat", "vest"],     // only for YOLOE/YOLO-World
    "tracking": { "enabled": true, "tracker": "bytetrack | botsort" },
    "thresholds": { "confidence": 0.35, "iou": 0.5 },
    "features": {                                 // overlay toggles (the primitives)
      "boxes": true, "masks": false, "keypoints": false,
      "labels": true, "trails": true, "obb": false, "semantic": false
    },
    "applications": [                             // the business-logic solutions
      {
        "type": "customer_in_out",
        "config": { "line": [[x1,y1],[x2,y2]] }
      },
      {
        "type": "manager_presence",
        "config": { "zone": [[x,y],[x,y],[x,y],[x,y]] }
      }
    ],
    "inference_mode": "full | spotlight_only | every_nth_frame",
    "frame_skip": 2
  }
}
```

```jsonc
// Live telemetry pushed over WebSocket (per camera, ~1–5 Hz)
{
  "cam_id": "cam_01",
  "fps": 24.3,
  "inference_ms": 18,
  "counts": { "person": 7 },
  "application_outputs": {
    "customer_in_out": { "in": 142, "out": 138, "current": 4 },
    "manager_presence": { "present": true, "duration_s": 1830 }
  },
  "alerts": [
    { "type": "ppe_violation", "ts": 1719230000, "detail": "no helmet" }
  ]
}
```

---

## 8. UI / screen flow

### Startup sequence
1. **Splash** — your logo + loading animation while the backend warms up (loads default model, checks GPU).
2. **Setup or Skip** — a card with two choices.
3. **Setup wizard** (if chosen) — pick input mode (RTSP / Webcam / USB) → for RTSP, single URL *or* template+range → optional "Auto-detect channels" → preview thumbnails of connected cameras → confirm.
4. **Skip** → straight to an empty Dashboard with a "+ Add Camera" prompt in the center.

### Dashboard layout (three columns)

**Center — live views.** Single spotlight view or an N×N grid of camera feeds (annotated MJPEG `<img>` per camera). Clicking a tile spotlights it (and triggers full inference on it). An overlay drawing tool lets the user draw counting lines and ROI zones directly on a feed — these write into that camera's `pipeline.applications[].config`.

**Left sidebar — system controls & telemetry** (your "important fields"; here's a concrete proposal):
- Active camera count + per-camera health/status dots
- Global model selector + confidence/IoU sliders
- System FPS and inference latency
- Aggregate counters (total people, total in/out)
- **Live alerts/events feed** (intrusion, PPE violation, etc.) — scrolling list, very demo-friendly
- Snapshot / start-recording / export buttons
- Settings (theme, GPU/CPU, grid size)

**Right sidebar — Applications & Features** (per the selected camera, as you described):
- **Features** group: toggle switches for Detect, Segment, Classify, Pose, OBB, Semantic, Track
- **Applications** group: toggle switches for Head Count, Customer In/Out, Manager Presence, Mobile Usage, PPE/Safety, plus the "free win" solutions (Heatmap, Speed, Intrusion Alarm, Privacy Blur…)
- A **custom-detection prompt box** (text input → YOLOE/YOLO-World) so a client can request "detect X" live

Enabling an Application auto-enables its required Features and surfaces its config controls (e.g. "draw the counting line").

---

## 9. Build roadmap (ordered to de-risk the hardest unknowns first)

**Phase 0 — Prove the pipeline (the critical milestone).**
Scaffold FastAPI + React(Vite)+shadcn. Build the splash → setup/skip flow. Get **one webcam → backend → YOLO detect → MJPEG → rendered in React** working end to end. *Nothing else matters until this round-trip works.* Acceptance: a person stands in front of the laptop webcam and sees a green box with "person 0.91" in the React UI, latency under ~0.5 s.

**Phase 1 — Camera manager + setup wizard.** Single RTSP stream working. Setup wizard for all three input modes (RTSP / Webcam / USB). Normalize to the `Camera` object. Connection status + error handling (bad URL, timeout, wrong credentials).

**Phase 2 — Multi-camera + channel auto-load.** N×N grid. Channel-template probing (§3, method B) with parallel connect + timeout. Sub-stream handling. **Selective/spotlight inference** so the grid stays performant.

**Phase 3 — Features layer.** The 7 YOLO modes as per-camera overlay toggles. Model swapping per camera. Confidence/IoU sliders. Tracking (ByteTrack) as a modifier.

**Phase 4 — Applications layer.** Wrap Ultralytics solutions: Head Count, Customer In/Out (line crossing), Manager Presence (ROI + timer), Heatmap, Intrusion Alarm, Privacy Blur. Build the ROI/line drawing tool. Add the YOLOE/YOLO-World custom-prompt box. Tackle Mobile-Usage last (it's the hardest — §6).

**Phase 5 — Telemetry, alerts & polish.** Left-sidebar telemetry + scrolling alerts feed over WebSocket. Snapshot/record/export. Apply your shadcn theme thoroughly. Wrap in Tauri/Electron for the native desktop demo build with your logo splash.

**Phase 6 — Robustness & extras.** ONVIF auto-discovery (§3, method A). Performance tuning (frame-skip tuning, model size auto-selection by hardware). A swappable library of client-ready models (PPE, fire/smoke, ANPR).

---

## 10. First-week target for the coding agent

Don't build features — **build the spine.** Deliver Phase 0 plus a single RTSP stream (Phase 1 partial). Concretely:

- FastAPI service that opens a webcam *and* one RTSP URL, runs `yolo26n` detect, and serves annotated MJPEG at `/stream/{cam_id}`
- React app: splash → setup/skip → dashboard with one live annotated feed in the center and a Detect/Track toggle in the right sidebar
- WebSocket pushing `{ fps, inference_ms, counts }` to a basic left-sidebar readout

Once that spine is alive, every Feature and Application is an incremental addition on a proven pipeline — which is exactly how you avoid the trap of building a beautiful React UI that can't actually talk to a camera.