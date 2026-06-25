# Production Media Architecture

## Goal

Use one VisionSense application on Apple Silicon macOS and Ubuntu 24.04 with
an NVIDIA GTX 1660, while using each platform's hardware media and inference
engines.

## Process boundaries

```text
React dashboard
    │ REST / WebSocket metadata + WHEP/WebRTC video
FastAPI control plane
    │ local HTTP control API
Native C++ media agent
    ├── macOS: GStreamer applemedia / VideoToolbox
    └── Linux: GStreamer nvcodec / NVDEC/NVENC
Bounded AI sidecar (one camera)
    ├── current Mac fallback: PyTorch CPU in Docker
    ├── target macOS: native CoreML / Metal
    └── target Linux: TensorRT / CUDA
```

FastAPI remains responsible for camera configuration, AI scheduling,
applications, alerts, SQLite persistence, and metadata. The native agent owns
RTSP sessions, hardware decode/encode, MediaMTX publishing, lifecycle metrics,
and reconnects. AI never owns the browser video transport.

## Hardware backend selection

At startup the agent reports:

- platform and architecture;
- available FFmpeg and GStreamer runtimes;
- hardware decoder and encoder availability;
- selected video backend;
- selected inference backend.

The control plane must reject an unsupported high-density configuration rather
than silently falling back to an overloaded CPU pipeline.

## Pipeline lifecycle

Only visible or analytically active cameras hold decoder resources.

1. The dashboard requests a camera page.
2. FastAPI sends the desired camera IDs to the media agent.
3. The agent tears down obsolete pipelines.
4. The agent creates the new RTSP pipelines.
5. MediaMTX delivers 25 FPS H.264 to the browser over WHEP/WebRTC.
6. If AI is enabled, one independent latest-frame sidecar samples that camera.
7. Detection metadata is sent over WebSocket and rendered over `<video>`.

## Target pipelines

macOS:

```text
rtspsrc → depay → parse → vtdec → videoscale → tee
    ├── vtenc_h264 → MediaMTX → WebRTC
    └── bounded inference sampler → CoreML (target)
```

Ubuntu/NVIDIA:

```text
rtspsrc → depay → parse → nvh265dec/nvh264dec → cudaconvertscale → tee
    ├── nvh264enc → MediaMTX → WebRTC
    └── CUDA/TensorRT inference sampler
```

## Delivery phases

1. ✅ Capability/control API scaffold.
2. ✅ GStreamer RTSP lifecycle and native browser stream.
3. ✅ SQLite persistence, watchdogs, metrics, and installers.
4. ✅ WebRTC signaling and React player.
5. ✅ Decoupled latest-frame AI sidecar and browser metadata overlays.
6. ONNX model runtime with CoreML and TensorRT providers.
7. Automated soak and recovery qualification.

## Current measured result (M4 Mac Mini)

For two NVR `subtype=0` streams, the source reports 2560×1440. The media agent
hardware-decodes them, scales dashboard output to 1280×720, and delivers
approximately 25 FPS per camera. With detection enabled on one camera, video
remains at 25 FPS while the current Docker CPU sidecar produces approximately
15–17 AI updates per second at roughly 50–70 ms per inference.
