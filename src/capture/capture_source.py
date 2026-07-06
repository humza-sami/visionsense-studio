"""Capture-source abstraction — the macOS/Ubuntu seam for video decode.

The pipeline only ever calls `open_capture(...)` and reads frames with cv2's
VideoCapture API. The backend chosen depends on platform + config:

  • opencv    — plain cv2.VideoCapture (CPU decode). Dev default on macOS, and the
                portable fallback everywhere. Also handles webcams (url=0) and files.
  • gstreamer — cv2 + a GStreamer pipeline using NVIDIA NVDEC (nvh264dec/nvh265dec).
                PROD path on Ubuntu. Requires OpenCV BUILT WITH GStreamer support
                (the pip `opencv-python` wheel usually is NOT — see README).
  • pynvc     — PyNvVideoCodec zero-copy NVDEC. Cleanest prod path; left as a TODO
                stub here because it returns GPU tensors, not cv2 frames, and needs
                the inference path wired for DLPack. Falls back to opencv for now.

`backend: auto` picks gstreamer on Linux when a GStreamer-enabled OpenCV is
detected, otherwise opencv.
"""
from __future__ import annotations

import platform

import cv2

from src.config import CaptureConfig


def _opencv_has_gstreamer() -> bool:
    try:
        info = cv2.getBuildInformation()
    except Exception:
        return False
    for line in info.splitlines():
        if "GStreamer" in line:
            return "YES" in line.upper()
    return False


def _resolve_backend(cfg: CaptureConfig) -> str:
    if cfg.backend != "auto":
        return cfg.backend
    if platform.system() == "Linux" and _opencv_has_gstreamer():
        return "gstreamer"
    return "opencv"


def gst_nvdec_pipeline(rtsp_url: str, cfg: CaptureConfig, codec: str = "h264") -> str:
    """GStreamer string doing GPU decode via NVDEC, with drop-old (max-buffers=1).

    NOTE: element names vary by install. Desktop dGPU NVIDIA plugins expose
    nvh264dec / nvh265dec. Jetson/DeepStream use nvv4l2decoder. Verify with
    `gst-inspect-1.0 | grep nv`. Prefer the camera's H.265 substream when
    available — roughly half the NVDEC load of H.264.
    """
    depay = "rtph265depay ! h265parse" if codec == "h265" else "rtph264depay ! h264parse"
    dec = "nvh265dec" if codec == "h265" else "nvh264dec"
    # Transport: "auto"/empty → let rtspsrc negotiate (udp→tcp), which is what many
    # GStreamer-based RTSP servers (e.g. phone IP-cam apps) require. "tcp"/"udp"
    # force that protocol (tcp is steadier for Dahua/RTSP over flaky/WAN links).
    proto = "" if cfg.rtsp_transport in ("auto", "", None) else f"protocols={cfg.rtsp_transport} "
    # nvh264dec/nvh265dec (the nvcodec NVDEC plugin) output frames in CUDA device
    # memory, so a `cudadownload` is required before the CPU `videoconvert` to BGR
    # that OpenCV's appsink expects. drop=true/max-buffers=1 keeps only the latest
    # frame (drop-old). Verified: `nvh264dec` engages the GPU's NVDEC decoder.
    return (
        f"rtspsrc location={rtsp_url} latency=100 {proto}! "
        f"{depay} ! {dec} ! cudadownload ! "
        "videoconvert ! video/x-raw,format=BGR ! "
        "appsink drop=true max-buffers=1 sync=false"
    )


def open_capture(url, cfg: CaptureConfig) -> cv2.VideoCapture:
    """Open a capture for a camera URL. Returns a cv2.VideoCapture (may be closed
    if the source is unavailable — callers must check .isOpened())."""
    backend = _resolve_backend(cfg)

    # Webcam index or local file → always plain OpenCV.
    is_stream = isinstance(url, str) and url.lower().startswith(("rtsp://", "rtmp://", "http"))

    if backend == "gstreamer" and is_stream:
        pipeline = gst_nvdec_pipeline(url, cfg, codec=getattr(cfg, "codec", "h264"))
        cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if cap.isOpened():
            return cap
        # Fall through to plain OpenCV if the GStreamer pipeline failed to open.

    # Plain OpenCV path (CPU decode). Handles int webcam index, file, or rtsp.
    if is_stream:
        # Prefer TCP + small buffer for RTSP via FFmpeg backend.
        import os
        os.environ.setdefault(
            "OPENCV_FFMPEG_CAPTURE_OPTIONS",
            f"rtsp_transport;{cfg.rtsp_transport}",
        )
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    else:
        cap = cv2.VideoCapture(url)

    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # minimise latency where supported
    except Exception:
        pass
    return cap


def active_backend(cfg: CaptureConfig) -> str:
    return _resolve_backend(cfg)
