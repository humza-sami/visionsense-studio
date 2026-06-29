"""ROI / zone helpers (§5.9). Load per-camera polygons and test membership."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np


@dataclass
class Zone:
    name: str
    type: str
    polygon: list[list[int]]

    def __post_init__(self) -> None:
        self._np = np.array(self.polygon, dtype=np.int32)

    def contains(self, point: tuple[float, float]) -> bool:
        return cv2.pointPolygonTest(self._np, (float(point[0]), float(point[1])), False) >= 0


def load_zones(zones_file: Optional[str]) -> list[Zone]:
    if not zones_file:
        return []
    path = Path(zones_file)
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return [
        Zone(name=z["name"], type=z.get("type", "interest"), polygon=z["polygon"])
        for z in data.get("zones", [])
    ]


def in_any(point: tuple[float, float], zones: list[Zone], zone_type: Optional[str] = None) -> bool:
    for z in zones:
        if zone_type and z.type != zone_type:
            continue
        if z.contains(point):
            return True
    return False
