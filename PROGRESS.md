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
