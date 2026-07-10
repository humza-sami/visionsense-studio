"""Rule kernel protocol — the ~30-line contract every app implements.

A kernel is a small state machine fed one camera's detections, frame by frame,
that emits :class:`~frameinsight.types.Event` objects. It never touches pixels
or GStreamer.

Standard parameters (accepted by **every** kernel — enforced here, see the
architecture doc §4.3; each exists because skipping it caused a real failure):

- ``classes``      which detector classes the rule cares about
- ``min_conf``     confidence floor (kills flicker-boxes)
- ``sustain_s``    condition must hold this long before it counts (kills blips)
- ``cooldown_s``   minimum gap between repeated alerts from the same cause
- ``lost_timeout_s`` a track unseen for this long is treated as gone
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from ..types import Detection, Event
from ..zones import Zone

EmitFn = Callable[[Event], None]


class Rule:
    """Base class for all kernels. Subclass and override the ``on_*`` hooks."""

    KIND = "base"

    def __init__(
        self,
        *,
        site: str,
        cam_id: str,
        name: str,
        emit: EmitFn,
        zone: Zone | None = None,
        classes: Iterable[str] = ("person",),
        min_conf: float = 0.5,
        sustain_s: float = 0.0,
        cooldown_s: float = 10.0,
        lost_timeout_s: float = 3.0,
        **params: Any,
    ) -> None:
        self.site = site
        self.cam_id = cam_id
        self.name = name
        self.zone = zone
        self.classes = frozenset(classes)
        self.min_conf = float(min_conf)
        self.sustain_s = float(sustain_s)
        self.cooldown_s = float(cooldown_s)
        self.lost_timeout_s = float(lost_timeout_s)
        self._emit = emit
        self._last_seen: dict[int, float] = {}      # track_id -> last frame ts
        self._last_alert: dict[str, float] = {}     # alert key -> last emit ts
        self.configure(**params)

    # -- hooks for subclasses -------------------------------------------------

    def configure(self, **params: Any) -> None:
        """Consume kernel-specific params. Default: reject unknown ones."""
        if params:
            raise TypeError(f"{type(self).__name__}: unknown params {sorted(params)}")

    def on_frame(self, ts: float, detections: list[Detection]) -> None:
        """Called once per processed frame with the *filtered* detections."""
        raise NotImplementedError

    def on_track_lost(self, ts: float, track_id: int) -> None:
        """Called when a track exceeds ``lost_timeout_s`` without being seen."""

    # -- state persistence (crash-safety; see architecture doc §8) ------------

    def snapshot_state(self) -> dict[str, Any]:
        """JSON-safe state to survive a process restart. Override to add more."""
        return {}

    def restore_state(self, state: dict[str, Any]) -> None:
        """Inverse of :meth:`snapshot_state`."""

    # -- plumbing (called by the dispatcher) ----------------------------------

    def process_frame(self, ts: float, detections: list[Detection]) -> None:
        kept = [
            d for d in detections
            if d.class_name in self.classes and d.confidence >= self.min_conf
        ]
        for d in kept:
            if d.is_tracked:
                self._last_seen[d.track_id] = ts
        self.on_frame(ts, kept)
        self._prune_lost(ts)

    def _prune_lost(self, ts: float) -> None:
        gone = [tid for tid, seen in self._last_seen.items()
                if ts - seen > self.lost_timeout_s]
        for tid in gone:
            del self._last_seen[tid]
            self.on_track_lost(ts, tid)

    # -- helpers for subclasses -----------------------------------------------

    def emit(
        self,
        ts: float,
        kind: str,
        data: dict[str, Any] | None = None,
        *,
        severity: str = "info",
        track_id: int | None = None,
    ) -> None:
        self._emit(Event(
            site=self.site, cam_id=self.cam_id, rule=self.name,
            kind=kind, severity=severity, ts=ts,
            track_id=track_id, data=data or {},
        ))

    def cooled_down(self, ts: float, key: str = "") -> bool:
        """True if ``cooldown_s`` has passed since the last alert for ``key``.

        Calling this *consumes* the cooldown (records ``ts``) when it returns
        True, so use it exactly at the point of emitting.
        """
        last = self._last_alert.get(key)
        if last is not None and ts - last < self.cooldown_s:
            return False
        self._last_alert[key] = ts
        return True
