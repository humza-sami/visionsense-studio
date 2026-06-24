"""Pydantic data models for cameras and pipeline configuration."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ── Sub-models ────────────────────────────────────────────────────────────────

class CameraSource(BaseModel):
    type: Literal["rtsp", "webcam", "usb"] = "webcam"
    url: Optional[str] = None          # for rtsp
    device_index: Optional[int] = 0    # for webcam / usb


class TrackingConfig(BaseModel):
    enabled: bool = False
    tracker: Literal["bytetrack", "botsort"] = "bytetrack"


class Thresholds(BaseModel):
    confidence: float = Field(default=0.35, ge=0.0, le=1.0)
    iou: float = Field(default=0.5, ge=0.0, le=1.0)


class PipelineFeatures(BaseModel):
    boxes: bool = True
    masks: bool = False
    keypoints: bool = False
    labels: bool = True
    trails: bool = False
    obb: bool = False
    semantic: bool = False


class ApplicationConfig(BaseModel):
    """A single business-logic application attached to a camera."""
    type: str  # head_count | customer_in_out | manager_presence | mobile_usage |
               # ppe | heatmap | speed | intrusion | blur
    enabled: bool = False
    config: Dict[str, Any] = Field(default_factory=dict)


class PipelineConfig(BaseModel):
    model: str = "yolov8n.pt"
    task: Literal["detect", "segment", "pose", "obb", "classify", "semantic"] = "detect"
    open_vocab_prompt: List[str] = Field(default_factory=list)
    tracking: TrackingConfig = Field(default_factory=TrackingConfig)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    features: PipelineFeatures = Field(default_factory=PipelineFeatures)
    applications: List[ApplicationConfig] = Field(default_factory=list)
    frame_skip: int = Field(default=1, ge=1, le=60)


# ── Top-level Camera model ────────────────────────────────────────────────────

class Camera(BaseModel):
    id: str
    name: str
    source: CameraSource
    status: Literal["idle", "connecting", "live", "error", "stopped"] = "idle"
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    error_message: Optional[str] = None


# ── Request bodies ────────────────────────────────────────────────────────────

class CreateCameraRequest(BaseModel):
    name: str
    source: CameraSource
    pipeline: Optional[PipelineConfig] = None


class PatchPipelineRequest(BaseModel):
    """Partial update for pipeline — any field may be omitted."""
    model: Optional[str] = None
    task: Optional[Literal["detect", "segment", "pose", "obb", "classify", "semantic"]] = None
    open_vocab_prompt: Optional[List[str]] = None
    tracking: Optional[TrackingConfig] = None
    thresholds: Optional[Thresholds] = None
    features: Optional[PipelineFeatures] = None
    applications: Optional[List[ApplicationConfig]] = None
    frame_skip: Optional[int] = None


class ProbeRequest(BaseModel):
    template: str           # e.g. "rtsp://user:pass@host/cam?channel={channel}&subtype=1"
    range_start: int = 1
    range_end: int = 16
    username: Optional[str] = None
    password: Optional[str] = None
    subtype: int = 1        # 0=main stream, 1=sub stream


class ProbeResponse(BaseModel):
    alive: List[int]


# ── Telemetry ─────────────────────────────────────────────────────────────────

class Alert(BaseModel):
    type: str
    ts: float
    detail: str


class TelemetryMessage(BaseModel):
    cam_id: str
    fps: float
    inference_ms: float
    counts: Dict[str, int] = Field(default_factory=dict)
    application_outputs: Dict[str, Any] = Field(default_factory=dict)
    alerts: List[Alert] = Field(default_factory=list)
