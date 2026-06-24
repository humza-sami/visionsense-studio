# Production Media Architecture

## Goal

Use one VisionSense application on Apple Silicon macOS and Ubuntu 24.04 with
an NVIDIA GTX 1660, while using each platform's hardware media and inference
engines.

## Process boundaries

```text
React dashboard
    │ REST / WebSocket / native MJPEG (WebRTC next)
FastAPI control plane
    │ local HTTP control API
Native C++ media agent
    ├── macOS: GStreamer applemedia / VideoToolbox + CoreML
    └── Linux: GStreamer nvcodec / NVDEC/NVENC + TensorRT
```

FastAPI remains responsible for camera configuration, applications, alerts,
SQLite persistence, and stream proxying. The native agent owns RTSP sessions,
hardware decode, scaling, JPEG output, lifecycle metrics, and reconnects.
WebRTC and zero-copy inference delivery remain the next transport/runtime
milestones.

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
5. Native JPEG frames are proxied to the browser without Python decoding.
6. If AI is enabled, that camera switches to the inference worker.

## Target pipelines

macOS:

```text
rtspsrc → depay → parse → vtdec → videoscale → tee
    ├── vtenc_h264 → WebRTC
    └── CoreML inference sampler
```

Ubuntu/NVIDIA:

```text
rtspsrc → depay → parse → nvh265dec/nvh264dec → cudaconvertscale → tee
    ├── nvh264enc → WebRTC
    └── CUDA/TensorRT inference sampler
```

## Delivery phases

1. ✅ Capability/control API scaffold.
2. ✅ GStreamer RTSP lifecycle and native browser stream.
3. ✅ SQLite persistence, watchdogs, metrics, and installers.
4. In progress: WebRTC signaling and React player.
5. ONNX model runtime with CoreML and TensorRT providers.
6. Automated soak and recovery qualification.

## Current measured result (M4 Mac Mini)

For two NVR `subtype=0` streams, the source reports 2560×1440. The media agent
hardware-decodes them, scales dashboard output to 1280×720, and delivers
approximately 21–24 FPS per camera. FastAPI remains around 0.2–0.3% CPU because
it no longer opens or JPEG-encodes non-AI RTSP streams.
