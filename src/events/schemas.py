"""Event schema emitted by business logic and published to subscribers (§5.11)."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Event:
    cam: str
    type: str                       # e.g. "headcount", "theft_suspected", "desk_active"
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
