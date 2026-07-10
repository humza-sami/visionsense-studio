"""DeepStream runtime — one GPU pipeline per site.yaml group.

Pipeline shape (all GPU-resident, zero-copy)::

    nvurisrcbin ×N  →  nvstreammux  →  nvinfer  →  nvtracker  →  probe → fakesink
    (NVDEC decode)     (batch N cams)  (TensorRT)   (track IDs)    │
                                                                   └─ Detection → Dispatcher → kernels → sinks

Requires ``pyservicemaker`` — i.e. run inside the DeepStream 9.0 container
(see README / docker/Dockerfile). Everything DeepStream-specific stays in this
module; nothing else in the package imports it.

Key facts baked in from the benchmarks (docs/deepstream-benchmark-report.md):

- ``interval`` on nvinfer skips whole batches; per-camera rates are done with
  one pipeline **per group**, never per-camera intervals.
- RTSP sources need ``live-source=1`` on the mux and ``sync=0`` on the sink.
- Engines must be prebuilt (scripts/build_engine_from_onnx.py) — building
  TensorRT engines under live decode load once crashed the GPU driver.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from .dispatch import Dispatcher
from .siteconfig import Group, SiteConfig
from .sinks import EventSink
from .types import Detection, Event

log = logging.getLogger("frameinsight.runtime")

DS_ROOT = "/opt/nvidia/deepstream/deepstream"
TRACKER_LIB = f"{DS_ROOT}/lib/libnvds_nvmultiobjecttracker.so"
TRACKER_CONFIGS = {
    "NvSORT": f"{DS_ROOT}/samples/configs/deepstream-app/config_tracker_NvSORT.yml",
    "NvDCF": f"{DS_ROOT}/samples/configs/deepstream-app/config_tracker_NvDCF_perf.yml",
    "IOU": f"{DS_ROOT}/samples/configs/deepstream-app/config_tracker_IOU.yml",
}


def load_labels(models_dir: str) -> list[str]:
    path = Path(models_dir) / "labels.txt"
    return [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]


def nvinfer_interval(cam_fps: float, detect_fps: float) -> int:
    """nvinfer runs 1 batch then skips ``interval`` batches: effective rate is
    fps/(interval+1). interval=2 at 30 fps ≈ 10 detections/s."""
    if detect_fps <= 0:
        return 0
    return max(0, round(cam_fps / detect_fps) - 1)


class GroupRuntime:
    """Owns one DeepStream pipeline and its dispatcher."""

    def __init__(self, site: SiteConfig, group: Group, sink: EventSink) -> None:
        self.site = site
        self.group = group
        self.sink = sink
        self.dispatcher = Dispatcher(site, sink, cameras=group.cameras,
                                     scope=group.name)
        self.labels = load_labels(site.models_dir)
        # streammux assigns source_id by pad order == the order we add sources.
        self.cam_order = list(group.cameras)
        self._frames_seen: dict[str, int] = {c: 0 for c in self.cam_order}
        self._last_frame: dict[str, float] = {}
        self._stall_alerted: dict[str, float] = {}
        self._stop = threading.Event()

    # -- probe ------------------------------------------------------------------

    def _make_probe(self):
        from pyservicemaker import BatchMetadataOperator, Probe

        rt = self

        class MetaProbe(BatchMetadataOperator):
            def handle_metadata(self, batch_meta):
                ts = time.time()
                for frame in batch_meta.frame_items:
                    sid = frame.source_id
                    if sid >= len(rt.cam_order):
                        continue
                    cam_id = rt.cam_order[sid]
                    pw = frame.pipeline_width or 1
                    ph = frame.pipeline_height or 1
                    dets: list[Detection] = []
                    for obj in frame.object_items:
                        r = obj.rect_params
                        cls_id = obj.class_id
                        name = (rt.labels[cls_id]
                                if 0 <= cls_id < len(rt.labels) else str(cls_id))
                        dets.append(Detection(
                            cam_id=cam_id,
                            ts=ts,
                            track_id=obj.object_id,
                            class_name=name,
                            confidence=obj.confidence,
                            bbox=(r.left / pw, r.top / ph,
                                  r.width / pw, r.height / ph),
                        ))
                    rt._frames_seen[cam_id] += 1
                    rt._last_frame[cam_id] = ts
                    rt.dispatcher.process_frame(cam_id, ts, dets)

        return Probe("frameinsight-probe", MetaProbe())

    # -- pipeline ----------------------------------------------------------------

    def build(self):
        from pyservicemaker import Pipeline

        g = self.group
        pgie_cfg = f"{self.site.models_dir}/app_configs/pgie_{g.model}.txt"
        if not Path(pgie_cfg).is_file():
            raise FileNotFoundError(
                f"no nvinfer config for model '{g.model}' at {pgie_cfg} "
                f"(is models/deepstream mounted at {self.site.models_dir}?)")
        tracker_cfg = TRACKER_CONFIGS.get(g.tracker)
        if tracker_cfg is None:
            raise ValueError(f"group '{g.name}': unknown tracker '{g.tracker}' "
                             f"(have: {', '.join(TRACKER_CONFIGS)})")

        n = len(g.cameras)
        max_fps = max(self.site.cameras[c].fps for c in g.cameras)
        interval = nvinfer_interval(max_fps, g.detect_fps)
        log.info("group '%s': %d cam(s), model=%s, detect_fps=%s → interval=%d",
                 g.name, n, g.model, g.detect_fps, interval)

        pipeline = Pipeline(f"frameinsight-{self.site.site}-{g.name}")
        for i, cam_id in enumerate(self.cam_order):
            pipeline.add("nvurisrcbin", f"src{i}", {
                "uri": self.site.cameras[cam_id].resolved_url(),
                "rtsp-reconnect-interval": 10,
            })
        pipeline.add("nvstreammux", "mux", {
            "batch-size": n,
            "width": self.site.streammux["width"],
            "height": self.site.streammux["height"],
            "live-source": 1,
            "batched-push-timeout": 40000,
        })
        pipeline.add("nvinfer", "pgie", {
            "config-file-path": pgie_cfg,
            "batch-size": n,
            "interval": interval,
        })
        pipeline.add("nvtracker", "tracker", {
            "ll-lib-file": TRACKER_LIB,
            "ll-config-file": tracker_cfg,
            "tracker-width": 640,
            "tracker-height": 384,
        })
        pipeline.add("fakesink", "sink", {"sync": 0, "async": 0})

        for i in range(n):
            pipeline.link((f"src{i}", "mux"), ("", "sink_%u"))
        pipeline.link("mux", "pgie", "tracker", "sink")
        pipeline.attach("tracker", self._make_probe())
        return pipeline

    # -- health ------------------------------------------------------------------

    def _heartbeat_loop(self) -> None:
        """Server + camera health (architecture doc §7): every heartbeat_s emit
        per-camera frame ages, and raise camera_stalled when a feed goes quiet."""
        period = self.site.heartbeat_s
        stall_after = max(15.0, 3 * period / 2)
        while not self._stop.wait(period):
            now = time.time()
            cams = {}
            for cam in self.cam_order:
                last = self._last_frame.get(cam)
                age = round(now - last, 1) if last else None
                cams[cam] = {"frames": self._frames_seen[cam], "last_frame_age_s": age}
                stalled = last is None or now - last > stall_after
                if stalled and now - self._stall_alerted.get(cam, 0.0) > 300:
                    self._stall_alerted[cam] = now
                    self.sink.write(Event(
                        site=self.site.site, cam_id=cam, rule="_system",
                        kind="camera_stalled", severity="alert", ts=now,
                        data={"last_frame_age_s": age, "group": self.group.name}))
            self.sink.write(Event(
                site=self.site.site, cam_id="_server", rule="_system",
                kind="heartbeat", ts=now,
                data={"group": self.group.name, "cameras": cams}))

    # -- lifecycle ---------------------------------------------------------------

    def run(self) -> None:
        pipeline = self.build()
        hb = threading.Thread(target=self._heartbeat_loop, daemon=True,
                              name=f"heartbeat-{self.group.name}")
        hb.start()
        try:
            pipeline.start().wait()
        finally:
            self._stop.set()
            self.dispatcher.close()
            self.sink.close()


def run_group(site: SiteConfig, group_name: str, sink: EventSink) -> None:
    for group in site.groups:
        if group.name == group_name:
            GroupRuntime(site, group, sink).run()
            return
    raise ValueError(f"no group named '{group_name}' "
                     f"(have: {', '.join(g.name for g in site.groups)})")
