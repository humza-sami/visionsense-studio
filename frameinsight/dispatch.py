"""Dispatcher — routes each camera's detections to that camera's rule kernels.

This is the seam between the GPU pipeline and business logic (architecture doc
§3.4): the pipeline knows nothing about apps; kernels know nothing about
GStreamer. The same dispatcher is driven by the live DeepStream probe
(:mod:`frameinsight.runtime`) and by recorded detections
(:mod:`frameinsight.replay`) — which is why every kernel is testable without
a GPU.

Also owns crash-safety for rule state: kernels' ``snapshot_state()`` is written
to ``<site>/state/<scope>.json`` periodically and restored on startup, so a
process restart doesn't zero the day's counters (architecture doc §8).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from .rules import KERNELS, load_plugins
from .rules.base import Rule
from .siteconfig import SiteConfig
from .sinks import EventSink
from .types import Detection
from .zones import resolve_zone

log = logging.getLogger("frameinsight.dispatch")


class Dispatcher:
    def __init__(
        self,
        site: SiteConfig,
        sink: EventSink,
        cameras: list[str] | None = None,
        *,
        scope: str = "all",
        snapshot_every_s: float = 30.0,
    ) -> None:
        """``cameras`` limits the dispatcher to one group's cameras (each
        pipeline process builds only the rules it feeds). ``scope`` names the
        state file — use the group name so processes don't clobber each other.
        """
        self.site = site
        self.sink = sink
        self.scope = scope
        self.snapshot_every_s = snapshot_every_s
        self._state_path = site.base_dir / site.state_dir / f"{scope}.json"
        self._next_snapshot = time.monotonic() + snapshot_every_s

        load_plugins(site.base_dir / site.apps_dir)

        wanted = set(cameras) if cameras is not None else set(site.cameras)
        self.rules_by_cam: dict[str, list[Rule]] = {c: [] for c in wanted}
        for binding in site.rules:
            if binding.camera not in wanted:
                continue
            cls = KERNELS.get(binding.kernel)
            if cls is None:
                raise ValueError(
                    f"rule '{binding.name}': unknown kernel '{binding.kernel}' "
                    f"(built-ins + plugins: {', '.join(sorted(KERNELS))})")
            zone = (resolve_zone(binding.zone, site.base_dir)
                    if binding.zone else None)
            rule = cls(site=site.site, cam_id=binding.camera, name=binding.name,
                       emit=sink.write, zone=zone, **binding.params)
            self.rules_by_cam[binding.camera].append(rule)

        self._restore()
        n_rules = sum(len(r) for r in self.rules_by_cam.values())
        log.info("dispatcher[%s]: %d rule(s) across %d camera(s)",
                 scope, n_rules, len(wanted))

    # -- hot path --------------------------------------------------------------

    def process_frame(self, cam_id: str, ts: float,
                      detections: list[Detection]) -> None:
        for rule in self.rules_by_cam.get(cam_id, ()):
            try:
                rule.process_frame(ts, detections)
            except Exception:
                # One buggy kernel must not take down the pipeline or its
                # neighbours — log loudly and keep going.
                log.exception("kernel '%s' failed on %s frame", rule.name, cam_id)
        now = time.monotonic()
        if now >= self._next_snapshot:
            self._next_snapshot = now + self.snapshot_every_s
            self.snapshot()

    # -- crash-safe rule state ---------------------------------------------------

    def snapshot(self) -> None:
        state = {
            rule.name: rule.snapshot_state()
            for rules in self.rules_by_cam.values() for rule in rules
        }
        state = {k: v for k, v in state.items() if v}
        if not state:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=1))
        tmp.replace(self._state_path)  # atomic — never a half-written file

    def _restore(self) -> None:
        if not self._state_path.is_file():
            return
        try:
            state = json.loads(self._state_path.read_text())
        except json.JSONDecodeError:
            log.warning("state file %s unreadable — starting fresh", self._state_path)
            return
        for rules in self.rules_by_cam.values():
            for rule in rules:
                if rule.name in state:
                    rule.restore_state(state[rule.name])
        log.info("restored state for %d rule(s) from %s", len(state), self._state_path)

    def close(self) -> None:
        self.snapshot()
