"""Business-logic base. One stateful handler instance per camera. Handlers consume
tracked detections (with IDs persistent over time) and emit Events.
"""
from __future__ import annotations

from src.config import CameraConfig
from src.events.schemas import Event
from src.types import Track
from src.zones import Zone

# COCO ids used across handlers.
PERSON = 0
CARRY_ITEMS = {24, 26, 28, 63, 67}  # backpack, handbag, suitcase, laptop, cell phone


class LogicHandler:
    name = "base"

    def __init__(self, cam: CameraConfig, zones: list[Zone]) -> None:
        self.cam = cam
        self.zones = zones

    def process(self, tracks: list[Track]) -> list[Event]:
        raise NotImplementedError
