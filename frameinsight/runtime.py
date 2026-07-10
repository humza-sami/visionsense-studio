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

import json
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


def source_drop_interval(cam_fps: float, detect_fps: float) -> int:
    """Per-source decimation: nvurisrcbin's ``drop-frame-interval=N`` keeps
    1 frame in N after decode (N<=1 keeps all). We decimate at the source and
    run nvinfer with interval=0 so **every frame the rules see is an inferred
    frame** — measured: with nvinfer interval>0, objects only exist on inferred
    frames (NvSORT does not propagate on skipped frames), which poisons
    frame-level kernels (a 25 fps stream of mostly-empty frames drives a
    headcount median to zero) and phase-aliases any fixed-rate sampler.
    Decode still runs at full fps on NVDEC; only downstream work drops."""
    if detect_fps <= 0:
        return 0
    return max(1, round(cam_fps / detect_fps))


class LiveStateWriter:
    """Publishes each camera's latest detections + rule live-state to
    ``<site>/state/live/<cam>.json`` a few times per second (atomic replace).

    This file is the contract with the local live-view UI (Zone Studio): the
    UI overlays these normalized boxes on the video and shows the timers —
    no video path between the pipeline and the UI, just this tiny JSON.
    """

    def __init__(self, site: SiteConfig, hz: float = 5.0) -> None:
        self.dir = site.base_dir / site.state_dir / "live"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._min_gap = 1.0 / hz
        self._last_write: dict[str, float] = {}

    def publish(self, cam_id: str, ts: float, detections: list[Detection],
                rules: dict) -> None:
        if ts - self._last_write.get(cam_id, 0.0) < self._min_gap:
            return
        self._last_write[cam_id] = ts
        doc = {
            "cam": cam_id,
            "ts": round(ts, 3),
            "detections": [
                {"id": d.track_id if d.is_tracked else None,
                 "cls": d.class_name,
                 "conf": round(d.confidence, 3),
                 "bbox": [round(v, 4) for v in d.bbox]}
                for d in detections
            ],
            "rules": rules,
        }
        tmp = self.dir / f".{cam_id}.tmp"
        tmp.write_text(json.dumps(doc, separators=(",", ":")))
        tmp.replace(self.dir / f"{cam_id}.json")


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
        self.live = LiveStateWriter(site)

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
                    rt.live.publish(cam_id, ts, dets,
                                    rt.dispatcher.live_state(cam_id))

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

        pipeline = Pipeline(f"frameinsight-{self.site.site}-{g.name}")
        for i, cam_id in enumerate(self.cam_order):
            cam = self.site.cameras[cam_id]
            drop = source_drop_interval(cam.fps, g.detect_fps)
            log.info("group '%s': %s decode %sfps → keep 1/%d → %.3g det/s",
                     g.name, cam_id, cam.fps, drop, cam.fps / drop)
            pipeline.add("nvurisrcbin", f"src{i}", {
                "uri": cam.resolved_url(),
                "rtsp-reconnect-interval": 10,
                "drop-frame-interval": drop,
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
            "interval": 0,   # every downstream frame is inferred (see above)
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
