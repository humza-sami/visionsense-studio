# VisionSense Native Media Agent

The media agent is the cross-platform hardware boundary for camera ingest,
decode/encode, WebRTC publishing, and inference frame delivery.

The React UI and FastAPI control plane use one API regardless of platform:

- macOS: VideoToolbox decode/encode; CoreML inference.
- Ubuntu + NVIDIA: NVDEC/NVENC; TensorRT/CUDA inference.
- Unsupported hosts: software fallback with reduced capacity.

## Production media path

The current runtime uses one hardware-accelerated decode per active camera:

```text
NVR RTSP
  → GStreamer jitter buffer
  → VideoToolbox (macOS) or NVDEC (Ubuntu)
  → clocked 1280×720 / 25 FPS
  → VideoToolbox or NVENC H.264
  → local RTSP publish to MediaMTX
  → WHEP/WebRTC to the browser
```

The same decoded frames are teed into a bounded 15 FPS MJPEG branch. The
frontend displays that branch only while WebRTC is unavailable and retries
WHEP in the background.

The agent exposes:

- `GET /health`
- `GET /v1/capabilities`
- `POST /v1/pipelines/{camera_id}`
- `DELETE /v1/pipelines/{camera_id}`
- `GET /v1/pipelines`
- `GET /v1/streams/{camera_id}` (compatibility fallback)

## Build

```bash
./scripts/install-media-deps-macos.sh  # macOS, one time
# or: ./scripts/install-media-deps-ubuntu.sh

cmake -S media-agent -B media-agent/build
cmake --build media-agent/build
media-agent/build/visionsense-media-agent --probe
```

Run the control API:

```bash
VS_MEDIA_PUBLISH_BASE=rtsp://127.0.0.1:8554 \
VS_WEBRTC_PUBLIC_BASE=http://localhost:8889 \
  media-agent/build/visionsense-media-agent --port 9010
```

MediaMTX is pinned and started by the Docker Compose files. For a browser on
another machine, set `VS_WEBRTC_ADDITIONAL_HOSTS` to the server's LAN IP before
starting Compose.

Only the visible camera pair should be active. This bounds decoder, encoder,
network, and browser resource use independently of the number of configured
cameras.
