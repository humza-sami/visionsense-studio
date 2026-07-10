"""Zone files: where a client's drawn areas/lines live and how rules load them.

One JSON file per camera under ``<site>/zones/``. Coordinates are normalized to
[0,1] against a reference snapshot of that camera, so they survive resolution
changes (mainstream vs substream) — see the platform architecture doc, §3.3/§5.

Schema::

    {
      "reference": {"width": 1280, "height": 720, "snapshot": "gate_ref.jpg"},
      "zones": [
        {"name": "entry_line",      "type": "line",    "points": [[0.1,0.6],[0.9,0.6]]},
        {"name": "cooler_area",     "type": "polygon", "points": [[...], ...]}
      ]
    }

Rules reference a zone as ``"zones/gate.json#entry_line"`` (path relative to
the site directory, fragment = zone name).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Zone:
    name: str
    type: str                       # "polygon" | "line"
    points: tuple[tuple[float, float], ...]
    source_file: str = ""

    def __post_init__(self) -> None:
        if self.type not in ("polygon", "line"):
            raise ValueError(f"zone '{self.name}': unknown type '{self.type}'")
        if self.type == "line" and len(self.points) != 2:
            raise ValueError(f"line zone '{self.name}' needs exactly 2 points, got {len(self.points)}")
        if self.type == "polygon" and len(self.points) < 3:
            raise ValueError(f"polygon zone '{self.name}' needs >= 3 points, got {len(self.points)}")
        for x, y in self.points:
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError(
                    f"zone '{self.name}': point ({x}, {y}) outside [0,1] — zones must be "
                    "stored normalized, never in pixels")


def load_zone_file(path: str | Path) -> dict[str, Zone]:
    """Load every zone in one camera's zone file, keyed by zone name."""
    path = Path(path)
    doc = json.loads(path.read_text())
    zones: dict[str, Zone] = {}
    for z in doc.get("zones", []):
        zone = Zone(
            name=z["name"],
            type=z["type"],
            points=tuple((float(p[0]), float(p[1])) for p in z["points"]),
            source_file=str(path),
        )
        if zone.name in zones:
            raise ValueError(f"{path}: duplicate zone name '{zone.name}'")
        zones[zone.name] = zone
    return zones


def resolve_zone(ref: str, base_dir: str | Path) -> Zone:
    """Resolve a ``"zones/gate.json#entry_line"`` reference from site.yaml."""
    if "#" not in ref:
        raise ValueError(
            f"zone reference '{ref}' must be '<file>#<zone_name>' "
            "(e.g. zones/gate.json#entry_line)")
    file_part, zone_name = ref.rsplit("#", 1)
    path = Path(base_dir) / file_part
    zones = load_zone_file(path)
    if zone_name not in zones:
        raise ValueError(
            f"{path}: no zone named '{zone_name}' (has: {', '.join(sorted(zones))})")
    return zones[zone_name]
