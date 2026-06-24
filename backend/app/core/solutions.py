"""
Wrapper classes for Ultralytics Solutions and custom business-logic applications.

Each solution implements:
    process(frame, detections, config) -> (annotated_frame, output_dict)

Solutions are stateful (they accumulate counts, timers, heatmaps across frames).
"""
from __future__ import annotations

import time
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import cv2

logger = logging.getLogger(__name__)


# ── Base class ────────────────────────────────────────────────────────────────

class BaseSolution(ABC):
    """Abstract base for all solutions."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._output: Dict[str, Any] = {}
        self._alerts: list = []

    @abstractmethod
    def process(
        self,
        frame: np.ndarray,
        detections: Any,
        config: Dict[str, Any],
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Process one frame. Return annotated frame + output dict."""
        ...

    def reset(self) -> None:
        """Reset accumulated state."""
        self._output = {}
        self._alerts = []

    def pop_alerts(self) -> list:
        alerts = self._alerts[:]
        self._alerts = []
        return alerts


# ── Helper utilities ──────────────────────────────────────────────────────────

def _get_boxes(detections) -> List[Tuple[int, int, int, int, float, int]]:
    """Extract (x1, y1, x2, y2, conf, cls_id) from ultralytics Results."""
    results = []
    if detections is None:
        return results
    try:
        for box in detections.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            results.append((int(x1), int(y1), int(x2), int(y2), conf, cls_id))
    except Exception:
        pass
    return results


def _point_in_polygon(x: float, y: float, polygon: List[List[float]]) -> bool:
    """Ray-casting point-in-polygon test."""
    if not polygon or len(polygon) < 3:
        return False
    pts = np.array(polygon, dtype=np.float32)
    return cv2.pointPolygonTest(pts, (float(x), float(y)), False) >= 0


def _boxes_overlap(b1, b2, threshold: float = 0.0) -> bool:
    """Return True if two boxes (x1,y1,x2,y2,...) overlap by at least threshold area."""
    ix1 = max(b1[0], b2[0])
    iy1 = max(b1[1], b2[1])
    ix2 = min(b1[2], b2[2])
    iy2 = min(b1[3], b2[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return False
    intersection = (ix2 - ix1) * (iy2 - iy1)
    return intersection > threshold


# ── Head Count ────────────────────────────────────────────────────────────────

class HeadCount(BaseSolution):
    """Count unique persons visible in the current frame."""

    PERSON_CLASS = 0  # COCO class id for 'person'

    def process(self, frame, detections, config) -> Tuple[np.ndarray, Dict[str, Any]]:
        boxes = _get_boxes(detections)
        persons = [b for b in boxes if b[5] == self.PERSON_CLASS]
        count = len(persons)

        # Draw count overlay
        h, w = frame.shape[:2]
        cv2.rectangle(frame, (0, 0), (200, 50), (0, 0, 0), -1)
        cv2.putText(
            frame, f"Head Count: {count}",
            (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
            (0, 255, 100), 2, cv2.LINE_AA,
        )

        output = {"count": count}
        self._output = output
        return frame, output


# ── Customer In/Out ───────────────────────────────────────────────────────────

class CustomerInOut(BaseSolution):
    """
    Line-crossing counter using tracking IDs.

    Requires tracking to be enabled upstream.
    config["line"]: [[x1,y1],[x2,y2]]  — the counting line in pixel coords.
    """

    PERSON_CLASS = 0

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._crossed_in: set = set()
        self._crossed_out: set = set()
        self._prev_centers: Dict[int, Tuple[float, float]] = {}

        # Try to use ultralytics ObjectCounter if available
        self._ult_counter = None
        line = config.get("line")
        if line and len(line) == 2:
            try:
                from ultralytics.solutions import ObjectCounter
                self._ult_counter = ObjectCounter(
                    region=line,
                    show=False,
                )
            except Exception:
                logger.debug("ultralytics ObjectCounter not available, using custom impl")

    def _side(self, px: float, py: float, lx1: float, ly1: float, lx2: float, ly2: float) -> float:
        """Signed cross-product to determine which side of a line a point is on."""
        return (lx2 - lx1) * (py - ly1) - (ly2 - ly1) * (px - lx1)

    def process(self, frame, detections, config) -> Tuple[np.ndarray, Dict[str, Any]]:
        line = config.get("line", self.config.get("line"))

        if self._ult_counter is not None and detections is not None:
            try:
                frame = self._ult_counter.count(frame)
                counts = self._ult_counter.classwise_counts if hasattr(self._ult_counter, "classwise_counts") else {}
                in_count = getattr(self._ult_counter, "in_count", 0)
                out_count = getattr(self._ult_counter, "out_count", 0)
                output = {
                    "in": int(in_count),
                    "out": int(out_count),
                    "current": max(0, int(in_count) - int(out_count)),
                }
                self._output = output
                return frame, output
            except Exception as e:
                logger.debug(f"ObjectCounter failed: {e}, falling back")

        # Custom fallback implementation
        if not line or len(line) < 2:
            output = {"in": len(self._crossed_in), "out": len(self._crossed_out), "current": 0}
            return frame, output

        lx1, ly1 = line[0]
        lx2, ly2 = line[1]

        # Draw counting line
        cv2.line(frame, (int(lx1), int(ly1)), (int(lx2), int(ly2)), (0, 200, 255), 2)

        boxes = _get_boxes(detections) if detections else []
        persons = [b for b in boxes if b[5] == self.PERSON_CLASS]

        current_centers: Dict[int, Tuple[float, float]] = {}

        for i, b in enumerate(persons):
            cx = (b[0] + b[2]) / 2.0
            cy = (b[1] + b[3]) / 2.0

            # Use track_id if available, else fall back to index
            track_id = i
            try:
                if detections and detections.boxes.id is not None:
                    track_id = int(detections.boxes.id[i])
            except Exception:
                pass

            current_centers[track_id] = (cx, cy)

            if track_id in self._prev_centers:
                pcx, pcy = self._prev_centers[track_id]
                prev_side = self._side(pcx, pcy, lx1, ly1, lx2, ly2)
                curr_side = self._side(cx, cy, lx1, ly1, lx2, ly2)
                if prev_side < 0 and curr_side >= 0 and track_id not in self._crossed_in:
                    self._crossed_in.add(track_id)
                elif prev_side >= 0 and curr_side < 0 and track_id not in self._crossed_out:
                    self._crossed_out.add(track_id)

        self._prev_centers = current_centers

        in_c = len(self._crossed_in)
        out_c = len(self._crossed_out)
        output = {"in": in_c, "out": out_c, "current": max(0, in_c - out_c)}
        self._output = output

        # Overlay
        cv2.putText(frame, f"In: {in_c}  Out: {out_c}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
        return frame, output


# ── Manager Presence ──────────────────────────────────────────────────────────

class ManagerPresence(BaseSolution):
    """
    Track whether a person is present inside a defined ROI zone.
    config["zone"]: [[x,y], ...] polygon in pixel coords.
    """

    PERSON_CLASS = 0

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._presence_start: Optional[float] = None
        self._total_duration: float = 0.0
        self._last_seen: Optional[float] = None

    def process(self, frame, detections, config) -> Tuple[np.ndarray, Dict[str, Any]]:
        zone = config.get("zone", self.config.get("zone", []))
        boxes = _get_boxes(detections) if detections else []
        persons = [b for b in boxes if b[5] == self.PERSON_CLASS]

        present = False
        if zone and len(zone) >= 3:
            # Draw the zone polygon
            pts = np.array(zone, dtype=np.int32)
            cv2.polylines(frame, [pts], True, (255, 165, 0), 2)
            overlay = frame.copy()
            cv2.fillPoly(overlay, [pts], (255, 165, 0))
            cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)

            # Check if any person's center falls inside the zone
            for b in persons:
                cx = (b[0] + b[2]) / 2.0
                cy = (b[1] + b[3]) / 2.0
                if _point_in_polygon(cx, cy, zone):
                    present = True
                    break
        elif persons:
            # No zone configured — presence = any person visible
            present = True

        now = time.time()
        if present:
            if self._presence_start is None:
                self._presence_start = now
            self._last_seen = now
        else:
            if self._presence_start is not None:
                self._total_duration += now - self._presence_start
                self._presence_start = None

        current_session = (now - self._presence_start) if self._presence_start else 0.0
        duration_s = self._total_duration + current_session

        label = "PRESENT" if present else "ABSENT"
        color = (0, 255, 0) if present else (0, 0, 255)
        cv2.putText(frame, f"Manager: {label}  {duration_s:.0f}s",
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        output = {"present": present, "duration_s": round(duration_s, 1)}
        self._output = output
        return frame, output


# ── Mobile Usage ──────────────────────────────────────────────────────────────

class MobileUsage(BaseSolution):
    """
    Detect phone usage: flag when a 'cell phone' detection overlaps a 'person' detection.
    Accumulates duration timer.
    COCO: person=0, cell phone=67
    """

    PERSON_CLASS = 0
    PHONE_CLASS = 67

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._usage_start: Optional[float] = None
        self._total_usage: float = 0.0

    def process(self, frame, detections, config) -> Tuple[np.ndarray, Dict[str, Any]]:
        boxes = _get_boxes(detections) if detections else []
        persons = [b for b in boxes if b[5] == self.PERSON_CLASS]
        phones = [b for b in boxes if b[5] == self.PHONE_CLASS]

        using_phone = False
        for person in persons:
            for phone in phones:
                if _boxes_overlap(person, phone):
                    using_phone = True
                    # Highlight phone box
                    cv2.rectangle(frame, (phone[0], phone[1]), (phone[2], phone[3]), (0, 0, 255), 3)
                    break
            if using_phone:
                break

        now = time.time()
        if using_phone:
            if self._usage_start is None:
                self._usage_start = now
        else:
            if self._usage_start is not None:
                self._total_usage += now - self._usage_start
                self._usage_start = None

        current = (now - self._usage_start) if self._usage_start else 0.0
        total = self._total_usage + current

        color = (0, 0, 255) if using_phone else (200, 200, 200)
        status = "PHONE DETECTED" if using_phone else "No phone"
        cv2.putText(frame, f"{status} | Usage: {total:.0f}s",
                    (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        output = {"using_phone": using_phone, "usage_duration_s": round(total, 1)}
        self._output = output
        return frame, output


# ── PPE Detection ─────────────────────────────────────────────────────────────

class PPEDetection(BaseSolution):
    """
    PPE compliance check.
    Requires a PPE-trained model or open-vocab model.
    With COCO models, falls back to detecting helmets as class approximations.
    config["required"]: list of class names or ids that must be present per person.
    """

    PERSON_CLASS = 0
    # Typical PPE class names when using a PPE-finetuned model
    PPE_CLASSES = {"hardhat", "helmet", "safety vest", "vest", "glove", "goggles"}

    def process(self, frame, detections, config) -> Tuple[np.ndarray, Dict[str, Any]]:
        boxes = _get_boxes(detections) if detections else []
        violations = 0
        compliant = 0

        # Try to get class names from detections
        class_names: Dict[int, str] = {}
        if detections is not None:
            try:
                class_names = detections.names  # dict: {id: name}
            except Exception:
                pass

        ppe_ids = {cid for cid, name in class_names.items()
                   if name.lower() in self.PPE_CLASSES}
        person_boxes = [b for b in boxes if b[5] == self.PERSON_CLASS]
        ppe_boxes = [b for b in boxes if b[5] in ppe_ids]

        for person in person_boxes:
            has_ppe = any(_boxes_overlap(person, p) for p in ppe_boxes)
            if has_ppe:
                compliant += 1
                cv2.rectangle(frame, (person[0], person[1]), (person[2], person[3]),
                               (0, 255, 0), 2)
            else:
                violations += 1
                cv2.rectangle(frame, (person[0], person[1]), (person[2], person[3]),
                               (0, 0, 255), 2)
                cv2.putText(frame, "PPE!", (person[0], person[1] - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                self._alerts.append({
                    "type": "ppe_violation",
                    "ts": time.time(),
                    "detail": "PPE not detected",
                })

        output = {"violations": violations, "compliant": compliant}
        self._output = output
        return frame, output


# ── Heatmap ───────────────────────────────────────────────────────────────────

class Heatmap(BaseSolution):
    """
    Foot-traffic heatmap.
    Accumulates a per-pixel intensity map and overlays it on the frame.
    Wraps ultralytics Heatmap solution when available.
    """

    PERSON_CLASS = 0

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._heatmap: Optional[np.ndarray] = None
        self._decay = 0.95  # bleed previous frames
        self._ult_heatmap = None

        try:
            from ultralytics.solutions import Heatmap as UltHeatmap
            self._ult_heatmap = UltHeatmap(show=False, colormap=cv2.COLORMAP_JET)
        except Exception:
            logger.debug("ultralytics Heatmap not available, using custom impl")

    def process(self, frame, detections, config) -> Tuple[np.ndarray, Dict[str, Any]]:
        if self._ult_heatmap is not None:
            try:
                frame = self._ult_heatmap.generate_heatmap(frame)
                return frame, {"active": True}
            except Exception as e:
                logger.debug(f"ultralytics Heatmap failed: {e}")

        # Custom implementation
        h, w = frame.shape[:2]
        if self._heatmap is None:
            self._heatmap = np.zeros((h, w), dtype=np.float32)

        # Decay existing heat
        self._heatmap *= self._decay

        boxes = _get_boxes(detections) if detections else []
        persons = [b for b in boxes if b[5] == self.PERSON_CLASS]
        for b in persons:
            # Use foot center (bottom center of box)
            fx = int((b[0] + b[2]) / 2)
            fy = int(b[3])
            cv2.circle(self._heatmap, (fx, fy), 30, 255, -1)

        # Normalize and colorize
        norm = cv2.normalize(self._heatmap, None, 0, 255, cv2.NORM_MINMAX)
        colored = cv2.applyColorMap(norm.astype(np.uint8), cv2.COLORMAP_JET)
        alpha = 0.4
        frame = cv2.addWeighted(colored, alpha, frame, 1 - alpha, 0)

        return frame, {"active": True, "person_count": len(persons)}


# ── Intrusion Alarm ───────────────────────────────────────────────────────────

class IntrusionAlarm(BaseSolution):
    """
    Alert when any person enters a defined zone.
    config["zone"]: [[x,y], ...] polygon.
    config["cooldown_s"]: minimum seconds between repeated alerts (default 5).
    """

    PERSON_CLASS = 0

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._last_alert_time: float = 0.0

        # Try ultralytics SecurityAlarm / SpeedEstimator
        self._ult_alarm = None
        zone = config.get("zone")
        if zone:
            try:
                from ultralytics.solutions import SecurityAlarm
                self._ult_alarm = SecurityAlarm(region=zone, show=False)
            except Exception:
                logger.debug("ultralytics SecurityAlarm not available")

    def process(self, frame, detections, config) -> Tuple[np.ndarray, Dict[str, Any]]:
        zone = config.get("zone", self.config.get("zone", []))

        if self._ult_alarm is not None:
            try:
                frame = self._ult_alarm.monitor(frame)
                return frame, {"active": True}
            except Exception as e:
                logger.debug(f"ultralytics SecurityAlarm failed: {e}")

        intruders = 0
        if zone and len(zone) >= 3:
            pts = np.array(zone, dtype=np.int32)
            cv2.polylines(frame, [pts], True, (0, 0, 255), 2)

            boxes = _get_boxes(detections) if detections else []
            persons = [b for b in boxes if b[5] == self.PERSON_CLASS]
            for b in persons:
                cx = (b[0] + b[2]) / 2.0
                cy = (b[1] + b[3]) / 2.0
                if _point_in_polygon(cx, cy, zone):
                    intruders += 1
                    cv2.rectangle(frame, (b[0], b[1]), (b[2], b[3]), (0, 0, 255), 3)

        now = time.time()
        cooldown = config.get("cooldown_s", self.config.get("cooldown_s", 5.0))
        if intruders > 0 and (now - self._last_alert_time) >= cooldown:
            self._last_alert_time = now
            self._alerts.append({
                "type": "intrusion",
                "ts": now,
                "detail": f"{intruders} intruder(s) detected",
            })
            # Flash red overlay
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (frame.shape[1], frame.shape[0]), (0, 0, 255), -1)
            cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
            cv2.putText(frame, "INTRUSION!", (50, frame.shape[0] // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 2.0, (255, 255, 255), 4)

        output = {"intruders": intruders, "alert_active": intruders > 0}
        self._output = output
        return frame, output


# ── Privacy Blur ──────────────────────────────────────────────────────────────

class PrivacyBlur(BaseSolution):
    """
    Blur detected persons/faces to protect privacy.
    config["classes"]: list of class ids to blur (default: [0] = person).
    config["blur_faces_only"]: if True, try to detect and blur faces within person boxes.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        # Try ultralytics ObjectBlurrer
        self._ult_blurrer = None
        try:
            from ultralytics.solutions import ObjectBlurrer
            self._ult_blurrer = ObjectBlurrer(show=False)
        except Exception:
            logger.debug("ultralytics ObjectBlurrer not available, using custom blur")

    def process(self, frame, detections, config) -> Tuple[np.ndarray, Dict[str, Any]]:
        if self._ult_blurrer is not None:
            try:
                frame = self._ult_blurrer.blur_objects(frame)
                return frame, {"active": True}
            except Exception as e:
                logger.debug(f"ObjectBlurrer failed: {e}")

        blur_classes = set(config.get("classes", self.config.get("classes", [0])))
        boxes = _get_boxes(detections) if detections else []
        count = 0
        for b in boxes:
            if b[5] in blur_classes:
                x1, y1, x2, y2 = b[0], b[1], b[2], b[3]
                roi = frame[y1:y2, x1:x2]
                if roi.size > 0:
                    blurred = cv2.GaussianBlur(roi, (51, 51), 30)
                    frame[y1:y2, x1:x2] = blurred
                    count += 1

        output = {"blurred": count}
        self._output = output
        return frame, output


# ── Speed Estimation ──────────────────────────────────────────────────────────

class SpeedEstimation(BaseSolution):
    """
    Vehicle speed estimation.
    Uses ultralytics SpeedEstimator when available; otherwise returns placeholder.
    config["region"]: [[x,y], ...] measurement region.
    config["fps"]: camera FPS (needed for accurate speed calc).
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._ult_speed = None
        region = config.get("region")
        if region:
            try:
                from ultralytics.solutions import SpeedEstimator
                self._ult_speed = SpeedEstimator(region=region, show=False)
            except Exception:
                logger.debug("ultralytics SpeedEstimator not available")

    def process(self, frame, detections, config) -> Tuple[np.ndarray, Dict[str, Any]]:
        if self._ult_speed is not None:
            try:
                frame = self._ult_speed.estimate_speed(frame)
                return frame, {"active": True}
            except Exception as e:
                logger.debug(f"SpeedEstimator failed: {e}")

        # Minimal fallback: just label moving objects
        output = {"active": False, "note": "Speed estimation requires region config and tracking"}
        cv2.putText(frame, "Speed Est. (configure region)", (10, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 0), 1)
        return frame, output


# ── Registry ──────────────────────────────────────────────────────────────────

SOLUTION_REGISTRY: Dict[str, type] = {
    "head_count": HeadCount,
    "customer_in_out": CustomerInOut,
    "manager_presence": ManagerPresence,
    "mobile_usage": MobileUsage,
    "ppe": PPEDetection,
    "heatmap": Heatmap,
    "intrusion": IntrusionAlarm,
    "blur": PrivacyBlur,
    "speed": SpeedEstimation,
}


def create_solution(app_type: str, config: Dict[str, Any]) -> Optional[BaseSolution]:
    """Instantiate a solution by name. Returns None if unknown type."""
    cls = SOLUTION_REGISTRY.get(app_type)
    if cls is None:
        logger.warning(f"Unknown solution type: {app_type}")
        return None
    return cls(config)
