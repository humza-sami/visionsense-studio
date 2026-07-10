"""Custom kernel for this site: alert when too many kids crowd the cooler.

This file demonstrates the plugin protocol — drop a ~30-line Rule subclass in
the site's apps/ dir, decorate it with @register_kernel, reference its KIND
from site.yaml. No engine changes, no pipeline changes.
"""

from frameinsight.geometry import point_in_polygon
from frameinsight.rules import register_kernel
from frameinsight.rules.base import Rule


@register_kernel
class CoolerCrowding(Rule):
    KIND = "cooler_crowding"

    def configure(self, *, max_people: int = 4, **params):
        super().configure(**params)
        if self.zone is None or self.zone.type != "polygon":
            raise ValueError(f"rule '{self.name}': cooler_crowding needs a polygon zone")
        self.max_people = int(max_people)
        self._over_since = None

    def on_frame(self, ts, detections):
        poly = list(self.zone.points)
        n = sum(1 for d in detections if point_in_polygon(d.foot, poly))
        if n <= self.max_people:
            self._over_since = None
            return
        if self._over_since is None:
            self._over_since = ts
        elif ts - self._over_since >= self.sustain_s and self.cooled_down(ts):
            self.emit(ts, "cooler_crowded",
                      {"count": n, "limit": self.max_people},
                      severity="alert")
