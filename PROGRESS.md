## [2026-06-24] - Initial Project Scaffold + Complete App Build
**Agent:** claude-sonnet-4-6

### What Changed
* Created full project structure: backend/ (FastAPI+YOLO) and frontend/ (React+shadcn+Zustand) via parallel agents
* Root files: docker-compose.yml (NVIDIA GPU), docker-compose.mac.yml (CPU/Mac), nginx.conf, .gitignore

### Handoff Notes (read this first, next agent)
* Backend API contract: REST at /api/cameras, MJPEG at /stream/{cam_id}, WS at /ws/telemetry
* Frontend runs on :5173 (dev) / :3000 (Docker); backend on :8000; Vite proxy handles CORS in dev
* YOLO models auto-download from ultralytics on first use; GPU=CUDA, Mac=CPU (set DEVICE=cpu env var)

## [2026-06-24] - Complete FastAPI Backend Implementation
**Agent:** claude-sonnet-4-6

### What Changed
* Built all 13 Python modules under backend/app/ — models, core (camera_manager, inference_engine, solutions), api (cameras, stream, websocket), main.py, config.py
* 9 solutions implemented: HeadCount, CustomerInOut, ManagerPresence, MobileUsage, PPEDetection, Heatmap, IntrusionAlarm, PrivacyBlur, SpeedEstimation — each with ultralytics wrapper + custom fallback

### Handoff Notes (read this first, next agent)
* Start backend: `cd backend && uvicorn app.main:app --reload --port 8000`; all API contracts match the spec exactly
* Cameras stored in-memory (no DB); restart clears all camera state — intentional for demo use

## [2026-06-24] - Complete React Frontend Implementation
**Agent:** claude-sonnet-4-6

### What Changed
* Created all 40+ frontend files: shadcn/ui components (button, card, badge, switch, slider, input, label, tabs, select, scroll-area, separator, toast, tooltip, dialog, progress, alert, accordion), Zustand store, REST API client, WebSocket hook with exponential backoff, all TypeScript types
* SplashPage (animated eye logo + progress bar), SetupPage (3-step wizard with RTSP single URL / NVR channel auto-probe / webcam device picker), DashboardPage (3-column layout with WS status, grid size switcher), LeftSidebar (cameras, telemetry, alerts, sliders, controls), RightSidebar (feature toggles + 9 application toggles + custom vocab), CameraFeed (MJPEG via `<img>`, status overlays, count badges, alert indicators), CameraGrid

### Handoff Notes (read this first, next agent)
* Build passes clean — `cd frontend && npm run build` outputs to `dist/`; dark class applied in App.tsx root div
* Backend URL default is `http://localhost:8000`; persisted in localStorage via Zustand persist middleware

## [2026-06-24] - shadcn b0 Theme Applied
**Agent:** claude-sonnet-4-6

### What Changed
* Applied `npx shadcn@latest apply --preset b0` — components.json updated to style: radix-nova / baseColor: neutral
* index.css replaced with oklch color vars (b0 palette, light+dark), Inter Variable font, Tailwind v3 compatible (no v4 @theme/@custom-variant imports)
* tailwind.config.ts updated: all color tokens use `var(--color)` not `hsl(var(--color))` to match oklch full-value vars; added sidebar/chart color tokens

### Handoff Notes (read this first, next agent)
* Do NOT revert index.css to hsl vars — the whole color system is oklch now; `var(--background)` gives a full color value
* Dark mode is active via `className="dark"` in App.tsx; dashboard always renders dark

## [2026-06-24] - Bug Fixes + Full b0 Color Sweep
**Agent:** claude-sonnet-4-6
* Fixed 422 on POST /api/cameras: frame_skip was 0, backend constraint is ge=1, changed to 1; Fixed React Error #31: /api/models returns objects not strings, getModels() now maps to name strings; Added text-foreground + color-scheme:dark to fix dark inputs; Removed all indigo/red/green/amber/hardcoded-hex colors from 12 files — only b0 semantic tokens remain (primary, secondary, muted, destructive, foreground, border, card, background)

## [2026-06-24] - Cross-Platform Native Media Architecture Started
**Agent:** Codex (GPT-5)

### Objective
Replace the CPU-heavy OpenCV/MJPEG path with a production media layer that
uses Apple VideoToolbox/CoreML on macOS and NVDEC/NVENC/TensorRT on Ubuntu
24.04 with NVIDIA GPUs.

### Completed
* Added `docs/MEDIA_ARCHITECTURE.md` with process boundaries, target GStreamer
  pipelines, hardware backends, lifecycle, and phased delivery plan.
* Added a portable C++20 `media-agent/` project with CMake packaging and a
  Clang fallback build for development machines without CMake.
* Added runtime capability detection:
  * macOS: VideoToolbox + CoreML.
  * Linux/NVIDIA: NVCodec + TensorRT when NVIDIA runtime support is present.
  * Explicit software fallback reporting.
* Added native control endpoints:
  * `GET /health`
  * `GET /v1/capabilities`
* Added FastAPI media-agent client and `GET /api/system/capabilities`.
* Added Mac and NVIDIA Compose configuration for the media-agent host URL.
* Updated `start.sh` to build/start the native agent automatically on macOS.
* Verified on the M4 Mac Mini:
  * platform: Darwin/arm64
  * video backend: VideoToolbox
  * inference backend: CoreML
  * H.264/H.265 hardware decode and encode detected
* Installed GStreamer 1.28.4 with bundled RTSP, WebRTC, and codec plugins.
* Verified a live NVR stream through the native hardware pipeline:
  `rtspsrc → rtph265depay → h265parse → vtdec_hw → fakesink`.
* Added repeatable media dependency installers for macOS and Ubuntu/NVIDIA.

### Current Limitations
* AI-enabled cameras temporarily switch to the existing Ultralytics worker.
  Ubuntu uses CUDA (`VS_YOLO_DEVICE=0`); native CoreML/TensorRT adapters remain
  the next inference milestone.

### Next Milestones
1. Add ONNX Runtime inference adapters: CoreML and TensorRT/CUDA.
2. Run long-duration stream recovery and resource soak tests.

## [2026-06-24] - Native Two-Camera Runtime + Persistence
**Agent:** Codex (GPT-5)

### Completed
* Implemented real GStreamer RTSP lifecycle management in the C++ media agent:
  * `POST /v1/pipelines/{camera_id}`
  * `DELETE /v1/pipelines/{camera_id}`
  * `GET /v1/pipelines`
  * `GET /v1/streams/{camera_id}` native MJPEG output
* Added per-pipeline state, FPS, frame count, resolution, error, and restart
  metrics.
* Added a GStreamer watchdog that restarts failed/EOS RTSP sessions.
* Moved non-AI RTSP playback off Python/OpenCV:
  * VideoToolbox hardware decode on Apple Silicon.
  * NVDEC-compatible GStreamer path on Ubuntu/NVIDIA.
  * FastAPI only proxies the native stream and remains nearly idle.
* Added an output ceiling of 1280×720 for dashboard tiles. The tested NVR
  `subtype=0` source identifies itself as 2560×1440, despite being described
  as 720p.
* Enforced two-camera paging:
  * only the visible pair is active;
  * moving Next/Previous tears down the old pair;
  * sidebar camera selection jumps to the matching pair;
  * spotlight has Back, Escape, and double-click exit.
* AI remains disabled by default. Enabling a feature/application on a selected
  camera switches that camera to the inference worker; disabling all AI
  switches it back to native playback.
* Added SQLite persistence and a Docker data volume. Camera definitions now
  survive backend/container restarts.
* Re-probed and persisted all 16 currently available NVR channels.
* Splash bootstrap now goes directly to the dashboard when saved cameras exist.
* Added Mac launchd and Ubuntu systemd production service definitions,
  production installers, and a diagnostics script.
* Corrected NVIDIA Compose inference configuration to
  `VS_YOLO_DEVICE=0`, enabled compute/video driver capabilities, and added
  shared memory.

### Verified
* 16 camera definitions survived a backend container rebuild.
* Page 1 opened exactly two native pipelines; page 2 removed those two and
  opened exactly the next two.
* After the 720p output ceiling, two active streams sustained approximately
  21–24 FPS each in the final health check.
* FastAPI CPU during native playback: approximately 0.2%.
* Enabling an AI feature removed that camera from the native playback set and
  started the inference worker; disabling it restored the native pipeline.
* Frontend production build, Python compile, C++ build, Compose validation, and
  whitespace checks pass.

### Remaining Product Work
1. WebRTC/WHEP transport to eliminate JPEG encoding and reduce latency/bandwidth.
2. Native inference adapters:
   * macOS: ONNX Runtime CoreML execution provider.
   * Ubuntu GTX 1660: TensorRT/CUDA execution provider.
3. Authentication, encrypted RTSP credential storage, and role-based access.
4. Automated 8–24 hour disconnect/reconnect and memory-growth soak suite.

## [2026-06-24] - RTSP Jitter and False FPS Fix
**Agent:** Codex (GPT-5)

### Root Cause
* The UI showed 23–25 FPS because the metric averaged all frames since pipeline
  startup. It hid delivery gaps of 0.2–1.8 seconds followed by catch-up bursts.
* FastAPI added essentially no jitter; the same burst pattern was measured
  directly from the native agent.
* The remote RTSP stream needed a larger jitter buffer, and the GStreamer
  appsink had clock synchronization disabled.

### Fix
* Increased the RTSP jitter buffer from 100 ms to 500 ms and stopped dropping
  late packets.
* Added `videorate` with a fixed 15 FPS dashboard output.
* Enabled appsink clock synchronization, preventing catch-up frames from being
  emitted in bursts.
* Reduced native JPEG quality from 75 to 65 to lower browser decode and network
  load without changing the 1280×720 output size.
* Changed FPS reporting to a rolling three-second measurement.
* Added automatic frontend stream reconnection after a camera/agent interruption.
* Camera-page activation now reconciles against the media agent's actual
  pipeline list, removing orphaned streams left by a backend container restart.

### Verified
* Native agent: approximately 15.1 FPS, 66 ms average frame spacing,
  71 ms p95, and 73 ms maximum during the sample.
* FastAPI/browser endpoint: approximately 15.0 FPS, 66.7 ms average,
  71.5 ms p95, and 98 ms maximum.
* Before the fix, measured maximum gaps were 0.5–1.8 seconds.

## [2026-06-24] - Bounded Playback Queue
**Agent:** Codex (GPT-5)

### Completed
* Added a native per-camera 30-frame ring buffer (two seconds at 15 FPS).
* New viewers start five frames behind live, providing approximately 330 ms of
  protection from short network and encoding bursts.
* Each browser connection consumes queued frames at a clocked 15 FPS.
* Slow clients are automatically advanced near live instead of accumulating
  unlimited latency.
* Queue depth and client-drop counters are exposed by `GET /v1/pipelines`.
* Added a no-frame watchdog: a pipeline that remains connected but produces no
  frames for five seconds is restarted automatically.
* The queue is bounded, so memory usage cannot grow with stream duration.

### Verified
* Both native and FastAPI endpoints measured 14.99 FPS.
* Average frame spacing: 66.7 ms.
* p95 spacing: 70.7 ms.
* Maximum measured spacing: approximately 77 ms.
* Both active pipelines maintained a full 30-frame bounded buffer.

### Clean Restart Test
* Rebuilt and restarted the native media agent, FastAPI backend, and frontend.
* Activated only Office Channels 1 and 2.
* Both queues reached their 30-frame target after five seconds.
* Concurrent 180-frame samples:
  * Channel 1 native: 14.99 FPS, 70.5 ms p95, 72.0 ms maximum gap.
  * Channel 1 backend: 15.00 FPS, 71.5 ms p95, 81.2 ms maximum gap.
  * Channel 2 native: 14.99 FPS, 70.4 ms p95, 72.9 ms maximum gap.
  * Channel 2 backend: 14.99 FPS, 71.2 ms p95, 80.2 ms maximum gap.
* No pipeline restarts and no client frames dropped during the test.
* Runtime usage:
  * media agent: approximately 19% CPU and 277 MB RSS;
  * FastAPI: approximately 1.5% CPU and 67 MB;
  * frontend nginx: effectively 0% CPU and 8 MB.

## [2026-06-24] - Production H.264 WebRTC Delivery
**Agent:** Codex (GPT-5)

### Architecture
* Added pinned MediaMTX `v1.19.1` to both macOS and Ubuntu/NVIDIA Compose
  profiles.
* Replaced browser-primary MJPEG with:
  * hardware RTSP decode;
  * a clocked 1280×720, 25 FPS raw stage;
  * VideoToolbox H.264 on macOS or NVENC H.264 on Ubuntu;
  * local RTSP publishing to MediaMTX, the transport recommended by MediaMTX
    for GStreamer publishers;
  * WHEP/WebRTC playback in native browser `<video>` elements.
* Kept the existing bounded 15 FPS MJPEG branch as a compatibility fallback.
  WebRTC retries continue quietly behind the fallback and automatically replace
  it when a newly activated path becomes available.
* AI remains off by default. These transport changes do not start inference.

### Production Reliability
* Pinned the media-server image instead of using `latest`.
* MediaMTX starts before the native agent and uses restart policies.
* Added RTSP, WHEP HTTP, and ICE/UDP ports to Compose.
* Added Mac and Ubuntu dependency checks for `rtspclientsink`.
* The media agent exposes transport and WHEP URL metadata with each pipeline.
* Fixed the frontend fallback timeout so successful WebRTC playback is not
  replaced after eight seconds.
* Fixed the camera-page startup race: initial WHEP 404 responses now retry until
  the publisher is registered.
* Added explicit active-camera ownership in the backend so telemetry retry logic
  cannot resurrect a camera from the previous page.

### Verified
* Synthetic 1280×720 H.264 publishing established a MediaMTX peer at 25 FPS.
* Real Office Channels 1 and 2 measured approximately 25.1 FPS each with zero
  pipeline restarts.
* Browser verification after 12 seconds:
  * two native `<video>` elements;
  * both `readyState=4`, playing, 1280×720;
  * no MJPEG image elements or fallback labels;
  * no browser console warnings or errors.
* Page 1 → Page 2 transition:
  * old WebRTC readers and RTSP publishers closed;
  * initial WHEP requests safely fell back while channels 3 and 4 started;
  * background retries upgraded both tiles to WebRTC;
  * exactly the two requested native pipelines remained after an additional
    six-second race check;
  * channels 3 and 4 measured approximately 24.5–24.8 FPS with zero restarts.
* Runtime sample for two live WebRTC streams:
  * native media agent: approximately 20% CPU, 348 MB RSS;
  * MediaMTX: approximately 3.7% CPU, 44 MB;
  * frontend nginx: effectively 0% CPU, 8 MB.

### Deployment Note
* Local browser use works with the default additional ICE host `127.0.0.1`.
* For another device on the LAN, set `VS_WEBRTC_ADDITIONAL_HOSTS` to the Mac or
  Ubuntu server's LAN IP before running Compose.

## [2026-06-24] - Decoupled Smooth AI Overlay
**Agent:** Codex (GPT-5)

### Root Cause
* Enabling any AI toggle previously stopped the native VideoToolbox/WebRTC
  pipeline and replaced it with a synchronous Python/OpenCV/YOLO/MJPEG worker.
* The Mac Docker image contains CPU-only PyTorch. Docker cannot expose Apple's
  Metal/MPS device, so model inference limited the entire video stream to
  approximately 6–7 FPS.

### Completed
* Native H.264 WebRTC now remains active when AI is enabled or disabled.
* Added a single-camera AI sidecar with separate capture and inference threads:
  * capture continuously drains RTSP;
  * inference always takes the newest frame;
  * stale frames are overwritten instead of queued;
  * slow inference can no longer add video latency.
* Removed server-side JPEG encoding and annotation rendering from the RTSP AI
  path.
* Reduced the Mac CPU inference input to a bounded 512-pixel YOLO size while
  preserving 1280×720 browser video.
* Added normalized detection metadata to WebSocket telemetry.
* Added browser-side SVG boxes and labels over the live WebRTC `<video>`.
* Split telemetry into `video_fps`, `ai_fps`, and `inference_ms`.
* Added deterministic ownership for the single AI slot.
* Background dashboard tabs no longer fight the visible operator tab for the
  global two-camera decoder allocation.

### Verified
* AI off → on → off → on did not recreate or restart the native pipeline:
  * frame counter increased continuously from 1195 to 1550;
  * restart count remained zero;
  * video remained approximately 25.0 FPS.
* Current Mac Docker CPU sidecar:
  * approximately 15–17 AI FPS;
  * approximately 51–55 ms inference latency at 512 input size;
  * detections delivered through WebSocket.
* Browser grid:
  * two 1280×720 WebRTC videos, `readyState=4`, playing;
  * no MJPEG image elements;
  * live overlay boxes and labels.
* Browser spotlight:
  * one 1280×720 WebRTC video remained playing;
  * browser-rendered AI overlay remained active;
  * no warnings or errors.

### Next Acceleration Milestone
* Video output is already a stable 25 FPS. AI metadata currently runs at
  approximately 15–17 FPS because the Mac Docker container is CPU-only.
* A native macOS CoreML/Metal inference service is the next step for using the
  M4 GPU/Neural Engine; Ubuntu continues toward TensorRT/CUDA on the GTX 1660.

## [2026-06-24] - Upgrade to YOLO26 (latest Ultralytics model)
**Agent:** claude-sonnet-4-6
* Default model changed from `yolov8n.pt` → `yolo26n.pt` in config.py and camera.py; `_BUILTIN_MODELS` in cameras.py now leads with the full YOLO26 family (n/s/m/l/x + seg/pose/obb/cls variants); frontend fallback list updated to YOLO26 variants; ultralytics pinned to >=8.4.0
* **Handoff:** Run `pip install -U ultralytics` in the backend container before starting — `yolo26n.pt` auto-downloads on first inference call; existing cameras in SQLite still reference `yolov8n.pt` and will continue to work.

## [2026-06-24] - Fix invisible boxes + add Pose/Trails client-side rendering
**Agent:** claude-sonnet-4-6
* Root cause of invisible boxes: SVG `strokeWidth="0.003"` with `vectorEffect="non-scaling-stroke"` = literally 0.003 screen pixels. Fixed to `strokeWidth="2"` + vectorEffect. Pose skeleton and trails now rendered as SVG client-side (not OpenCV). Backend auto-switches model: keypoints→yolo26n-pose.pt, masks→yolo26n-seg.pt, obb→yolo26n-obb.pt. Frontend hot-swapped via docker cp without full image rebuild.
* **Handoff:** User must hard-refresh browser (Cmd+Shift+R) to load new JS. Only ONE feature type at a time makes sense (detect OR pose OR segment — not all together, different models). yolo26n.pt already cached; pose/seg models download on first use (~5-15MB each).

## [2026-06-25] - Fix AI not starting on camera toggle (force=True)
**Agent:** claude-sonnet-4-6
* Root cause: `start()` called `_start_ai_worker(force=False)` — silently blocked if another camera held the AI slot. Fixed lines 477+480 to `force=True`. Frontend container was serving June 24 build; rebuilt with `docker compose build frontend && up -d frontend`.
* **Handoff:** AI confirmed working: WebSocket sends `ai_enabled=true`, 15+ detections/frame at 2-3 AI fps. User must hard-refresh browser (Cmd+Shift+R at localhost:3000). cam_695c3fef has `boxes=true` in DB — toggle Detect on any camera while viewing page 1 to test.

## [2026-06-25] - Remove Docker; fully native Mac stack
**Agent:** claude-sonnet-4-6
* Stopped all Docker containers. Backend now runs natively in `backend/.venv` (Python 3.13 + PyTorch MPS). Frontend built to `frontend/dist` and served directly by FastAPI SPA mount — no Nginx needed. mediamtx 1.19.1 downloaded as native ARM64 binary to `bin/mediamtx`. `start.sh` completely rewritten: Docker-free, auto-setups venv + frontend build + mediamtx on first run, starts all services natively. Single URL: http://localhost:8000 (serves both app and API). Backend uses `VS_YOLO_DEVICE=mps` directly — host-inference sidecar no longer needed.
* **Handoff:** Run `./start.sh` from project root to launch everything. Backend DB at `backend/data/visionsense.db`. Logs: `/tmp/vs-mediamtx.log`, `/tmp/vs-backend.log`. If frontend changes, run `cd frontend && npm run build` to rebuild dist. `host-inference/` still exists but is unused — backend uses MPS natively now.

## [2026-06-25] - Model switch fix: warmup on pipeline change + preload all at startup
**Agent:** claude-sonnet-4-6
* Added `POST /warmup` to host server — pre-loads model into MPS cache without a frame. Backend `patch_pipeline` calls warmup as a fire-and-forget async task whenever `model` or `features` changes. Inference timeout raised 15s→120s (covers download+JIT). Added startup preloader: background thread downloads all size×variant combos (N/S/M/L × detect/seg/pose/obb = 16 models) when server starts. Size list configurable via `PRELOAD_SIZES` env var (default: n,s,m,l; x excluded). Server starts immediately; preload runs behind it.
* **Handoff:** Model switch now: (1) UI sends PATCH → backend triggers warmup → host loads model in 5-30s. (2) AI worker's next frame arrives → model already cached → inference is instant. If warmup hasn't finished, inference call blocks (up to 120s) until model loads. Preload log visible in `/tmp/host-inference.log`. To include X model at startup: `PRELOAD_SIZES=n,s,m,l,x .venv/bin/python3 server.py`.

## [2026-06-25] - Host MPS inference sidecar (10x faster than Docker CPU)
**Agent:** claude-sonnet-4-6
* Created `host-inference/server.py` (FastAPI, port 9020) running on Mac host with MPS (Metal). Backend sends JPEG frames via `POST /infer` to `host.docker.internal:9020` instead of running YOLO locally. Added `VS_REMOTE_INFERENCE_URL` to `config.py` + `docker-compose.mac.yml`. Falls back to local CPU if host unreachable. Measured: yolo26n-seg MPS=11ms vs CPU=60ms (5x), M model ~30ms vs 325ms (10x).
* **Handoff:** Host server runs as a background process — start with `cd host-inference && ./start.sh`. Venv at `host-inference/.venv`. Server must be running BEFORE enabling AI on any camera (backend falls back to slow CPU otherwise). Model files download to `~/Library/Caches/torch/hub` on first use. To disable and revert to Docker CPU, remove `VS_REMOTE_INFERENCE_URL` from docker-compose.mac.yml and rebuild.

## [2026-06-25] - Fix segment visualization: send polygon data + SVG polygon overlay
**Agent:** claude-sonnet-4-6
* Backend `_extract_detections` now includes `segments: [[x,y],...]` from `results.masks.xyn` (normalized polygon, downsampled to max 80 pts). Frontend `Detection` type gains `segments` field. `DetectionOverlay` renders `<polygon>` with 25% fill + colored stroke when `showSegments=true`. `CameraFeed` passes `showSegments={features.masks || features.semantic}`. Backend hot-patched via docker cp; frontend rebuilt.
* **Handoff:** Segment masks now render as colored SVG polygons over the WebRTC feed. Hard-refresh browser (Cmd+Shift+R). If polygons appear jagged, adjust downsample step in `_extract_detections` (line: `step = max(1, len(poly) // 80)`). Semantic still shows same polygon overlay — true per-pixel semantic coloring requires render=True on frames.

## [2026-06-25] - Right sidebar redesign: Controls, Feature dropdown, Class filter
**Agent:** claude-sonnet-4-6
* Moved Controls (Confidence/IOU/ModelSize) from LeftSidebar to top of RightSidebar; Feature toggles replaced with single Mode dropdown (None/Detect/Segment/Pose/OBB/Semantic) + Labels/Trails/Track chips; Applications section now collapsible; COCO-80 class filter added (search+tags, frontend-only filtering of detections). `classFilters` added to Zustand store; `CameraFeed.tsx` filters detections before passing to overlay. Fixed `showBoxes` to exclude semantic.
* **Handoff:** All changes are frontend-only. RightSidebar.tsx is now self-contained (no sub-components needed). FeatureToggles.tsx and ApplicationToggles.tsx are still on disk but not used — safe to delete. Class filter is UI-state only (not persisted to backend or localStorage).

## [2026-06-25] - Auto model variant selection + size-only UI
**Agent:** claude-sonnet-4-6
* `_effective_model()` now accepts bare size names (`yolo26n`, `yolo26m` etc.) — strips any suffix then appends correct variant based on features: boxes→.pt, masks/semantic→-seg.pt, keypoints→-pose.pt, obb→-obb.pt. `/api/models` now returns 5 size objects (N/S/M/L/X) instead of full model filenames. DB migrated: all 16 cameras updated from `yolo26n.pt` → `yolo26n`.
* **Handoff:** Frontend shows N/S/M/L/X pill buttons instead of model dropdown. Selecting "N" stores `yolo26n`; backend picks `yolo26n.pt` or `yolo26n-pose.pt` etc. automatically. cam_695c3fef now has `model=yolo26m` with `boxes=true` — AI running at ~3fps CPU.

## [2026-06-25] - Fix native WebRTC video feed (NVR HEVC → H.264 bridge)
**Agent:** claude-sonnet-4-6
* Root cause: NVR sends HEVC only; Chrome needs H.264; mediamtx needed `paths: all_others:` to accept RTSP publishers. Created two-stage FFmpeg bridge in `backend/app/core/ffmpeg_bridge.py` — Stage 1 copies HEVC from NVR to `{cam_id}_raw` (stable). Stage 2 transcodes HEVC → H.264 with libx264, retrying every 1.5s until it catches an IDR frame. AI worker reads from mediamtx H.264 (not NVR directly). `media_agent_client.py` delegates to `ffmpeg_bridge.py`. WHEP confirmed working with H.264 SDP answer.
* **Handoff:** Video appears ~5-15s after camera starts (stage 2 retries). `start.sh` now writes mediamtx.yml with `paths: all_others:`. If video disappears briefly, stage 2 is restarting (self-heals in ~5s). C++ media agent unused for video.

## [2026-06-25] - Box alignment fix + full-resolution inference + detection lag fix
**Agent:** claude-sonnet-4-6
* `OverlayCanvas.tsx`: replaced flat `x * clientWidth` mapping with object-cover-aware transform (computes scale+crop offset from `videoEl.videoWidth/Height` vs `clientWidth/Height`) — boxes/keypoints/segments now align correctly with video regardless of container aspect ratio.
* `inference_engine.py`: `imgsz` now dynamically set to `ceil(max(h,w)/32)*32` (native frame resolution, no downscale). `websocket.py` + `camera_manager.py`: detection push bypasses 200ms timer — inference thread calls callback immediately, asyncio queue wakes broadcaster, overlay lag reduced from ~200ms to ~5ms.
* **Handoff:** `useStore.ts` `updateTelemetry` now merges (not replaces) so fast detection pushes (detections/trails/ai_fps) and slow polls (video_fps/status) coexist without wiping each other. Live Counts section removed from LeftSidebar.
