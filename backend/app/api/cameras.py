"""
Camera CRUD and control endpoints.

Routes:
    GET    /api/cameras              → list cameras
    POST   /api/cameras              → create camera
    DELETE /api/cameras/{cam_id}     → remove camera
    POST   /api/cameras/{cam_id}/start
    POST   /api/cameras/{cam_id}/stop
    PATCH  /api/cameras/{cam_id}/pipeline
    POST   /api/cameras/probe        → channel-range prober
    GET    /api/devices              → list USB/webcam devices
    GET    /api/models               → list available YOLO model files
"""
from __future__ import annotations

import concurrent.futures
import glob
import logging
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
from fastapi import APIRouter, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.core.camera_manager import camera_manager
from app.models.camera import (
    Camera,
    ActivateCamerasRequest,
    CreateCameraRequest,
    PatchPipelineRequest,
    PipelineConfig,
    ProbeRequest,
    ProbeResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["cameras"])


# ── Camera CRUD ───────────────────────────────────────────────────────────────

@router.get("/cameras", response_model=List[Camera])
async def list_cameras():
    return camera_manager.list()


@router.post("/cameras", response_model=Camera, status_code=status.HTTP_201_CREATED)
async def create_camera(body: CreateCameraRequest):
    camera = camera_manager.create(
        name=body.name,
        source=body.source,
        pipeline=body.pipeline,
    )
    return camera


@router.delete("/cameras/{cam_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(cam_id: str):
    success = camera_manager.delete(cam_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' not found")


# ── Camera control ────────────────────────────────────────────────────────────

@router.post("/cameras/{cam_id}/start", response_model=Camera)
async def start_camera(cam_id: str):
    camera = camera_manager.get(cam_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' not found")
    success = camera_manager.start(cam_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to start camera worker")
    return camera_manager.get(cam_id)


@router.post("/cameras/{cam_id}/stop", response_model=Camera)
async def stop_camera(cam_id: str):
    camera = camera_manager.get(cam_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' not found")
    camera_manager.stop(cam_id)
    cam = camera_manager.get(cam_id)
    cam.status = "stopped"
    return cam


@router.post("/cameras/activate", response_model=List[Camera])
async def activate_cameras(body: ActivateCamerasRequest):
    """Run only the requested two-camera page and release all other streams."""
    try:
        return await run_in_threadpool(camera_manager.activate_only, body.camera_ids)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Camera '{exc.args[0]}' not found")


@router.patch("/cameras/{cam_id}/pipeline", response_model=Camera)
async def patch_pipeline(cam_id: str, body: PatchPipelineRequest):
    camera = camera_manager.get(cam_id)
    if camera is None:
        raise HTTPException(status_code=404, detail=f"Camera '{cam_id}' not found")

    # Merge patch fields into current pipeline
    current = camera.pipeline.model_dump()
    patch = body.model_dump(exclude_unset=True)
    merged = {**current, **patch}
    new_pipeline = PipelineConfig(**merged)

    success = camera_manager.update_pipeline(cam_id, new_pipeline)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update pipeline")
    return camera_manager.get(cam_id)


# ── Channel probing ───────────────────────────────────────────────────────────

def _probe_channel(template: str, channel: int, timeout_s: float) -> Optional[int]:
    """
    Try to open a single RTSP channel.
    Returns channel number if alive, else None.
    Runs in a thread-pool thread.
    """
    url = template.replace("{channel}", str(channel))
    try:
        # VideoCapture can block before OpenCV applies its timeout properties.
        # ffprobe gives us a real process-level timeout, so a dead channel
        # cannot leave the Add Camera UI waiting indefinitely.
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-rtsp_transport", "tcp",
                "-select_streams", "v:0",
                "-show_entries", "stream=index",
                "-of", "csv=p=0",
                url,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout_s,
            check=False,
            text=True,
        )
        return channel if result.returncode == 0 and result.stdout.strip() else None
    except (subprocess.TimeoutExpired, OSError):
        return None


@router.post("/cameras/probe", response_model=ProbeResponse)
async def probe_channels(body: ProbeRequest):
    """
    Probe a range of NVR channels in parallel.

    The template must contain ``{channel}`` which is replaced per-channel, e.g.:
        rtsp://user:pass@host/cam/realmonitor?channel={channel}&subtype=1
    """
    template = body.template
    if "{channel}" not in template:
        raise HTTPException(
            status_code=422,
            detail="template must contain the literal string {channel}",
        )

    # Optionally inject credentials into the URL
    if body.username and body.password:
        # Only inject if not already in the URL
        if "@" not in template:
            template = re.sub(
                r"^(rtsp://)",
                f"rtsp://{body.username}:{body.password}@",
                template,
            )

    # Replace subtype placeholder if present
    if "{subtype}" in template:
        template = template.replace("{subtype}", str(body.subtype))

    channel_range = range(body.range_start, body.range_end + 1)
    timeout = settings.probe_timeout_s
    max_workers = min(settings.probe_max_workers, len(channel_range))

    alive: List[int] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_probe_channel, template, ch, timeout): ch
            for ch in channel_range
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result is not None:
                alive.append(result)

    alive.sort()
    logger.info(f"Probe complete: {len(alive)}/{len(channel_range)} channels alive")
    return ProbeResponse(alive=alive)


# ── Device enumeration ────────────────────────────────────────────────────────

@router.get("/devices")
async def list_devices() -> List[Dict[str, Any]]:
    """
    Enumerate available USB / webcam / V4L2 devices.

    On Linux: scans /dev/video*.
    On macOS/Windows: tries VideoCapture(0..9) and returns opening ones.
    """
    devices: List[Dict[str, Any]] = []
    system = platform.system()

    if system == "Linux":
        video_devs = sorted(glob.glob("/dev/video*"))
        for dev_path in video_devs:
            try:
                idx = int(re.search(r"\d+$", dev_path).group())
            except Exception:
                continue
            cap = cv2.VideoCapture(dev_path)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                devices.append({
                    "index": idx,
                    "path": dev_path,
                    "label": f"Camera {idx} ({w}x{h})",
                })
                cap.release()
    else:
        # macOS / Windows: try indices 0–9
        for idx in range(10):
            cap = cv2.VideoCapture(idx)
            if cap.isOpened():
                ret, _ = cap.read()
                if ret:
                    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    devices.append({
                        "index": idx,
                        "path": str(idx),
                        "label": f"Camera {idx} ({w}x{h})",
                    })
                cap.release()

    return devices


# ── Model discovery ───────────────────────────────────────────────────────────

# Well-known ultralytics model names (auto-downloaded if used)
_BUILTIN_MODELS = [
    # YOLOv8
    "yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt",
    "yolov8n-seg.pt", "yolov8s-seg.pt", "yolov8m-seg.pt",
    "yolov8n-pose.pt", "yolov8s-pose.pt",
    "yolov8n-obb.pt", "yolov8s-obb.pt",
    "yolov8n-cls.pt", "yolov8s-cls.pt",
    # YOLOv9
    "yolov9c.pt", "yolov9e.pt",
    # YOLOv10
    "yolov10n.pt", "yolov10s.pt", "yolov10m.pt",
    # YOLO11
    "yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolo11l.pt", "yolo11x.pt",
    "yolo11n-seg.pt", "yolo11s-seg.pt",
    "yolo11n-pose.pt", "yolo11s-pose.pt",
    # YOLO-World / YOLOE (open vocab)
    "yolov8s-worldv2.pt",
    "yoloe-11s-seg.pt",
]


@router.get("/models")
async def list_models() -> List[Dict[str, Any]]:
    """
    Return:
    - Built-in ultralytics model names (always available, auto-downloaded on first use)
    - Any .pt files found in the configured weights directory
    """
    models: List[Dict[str, Any]] = []

    # Scan local weights dir
    local_files: set = set()
    weights_dir = settings.models_dir
    if weights_dir.exists():
        for pt in sorted(weights_dir.glob("*.pt")):
            local_files.add(pt.name)
            models.append({
                "name": pt.name,
                "path": str(pt),
                "source": "local",
                "size_mb": round(pt.stat().st_size / 1_048_576, 1),
            })

    # Also check ultralytics default download dir
    ult_dir = Path.home() / ".ultralytics" / "assets"
    if ult_dir.exists():
        for pt in sorted(ult_dir.glob("*.pt")):
            if pt.name not in local_files:
                local_files.add(pt.name)
                models.append({
                    "name": pt.name,
                    "path": str(pt),
                    "source": "ultralytics_cache",
                    "size_mb": round(pt.stat().st_size / 1_048_576, 1),
                })

    # Append built-ins not already present
    existing_names = {m["name"] for m in models}
    for name in _BUILTIN_MODELS:
        if name not in existing_names:
            models.append({
                "name": name,
                "path": name,  # ultralytics will auto-download
                "source": "builtin",
                "size_mb": None,
            })

    return models
