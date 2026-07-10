"""site.yaml — the one file that describes a deployment (site-as-code).

Everything client-specific lives in the site directory; the engine (this
package) is identical for every client::

    sites/<client>/
      site.yaml          cameras, groups, rules, sinks   (this module)
      zones/*.json       drawn areas/lines, normalized   (frameinsight.zones)
      apps/*.py          optional custom kernels         (frameinsight.rules)

Schema (see examples/school/site.yaml for a complete, commented example)::

    site: greenfield-school
    models_dir: /models                # model packs (container path)
    streammux: {width: 1280, height: 720}
    url_template: ${SCHOOL_NVR_TMPL}   # optional; must contain {ch}

    cameras:
      gate: {channel: 1, fps: 30}                # via url_template, or
      lobby: {url: "rtsp://...", fps: 25}        # explicit URL (may use ${ENV})

    groups:                            # one DeepStream pipeline per group
      - name: entrances
        model: yolo26s
        detect_fps: 10
        cameras: [gate, lobby]

    rules:
      - name: gate_counter
        camera: gate
        kernel: line_crossing
        zone: zones/gate.json#entry_line
        params: {classes: [person], min_conf: 0.5}

    sinks:
      - {type: console}
      - {type: jsonl, path: events/events.jsonl}

Camera URLs may reference environment variables (``${VAR}``) — credentials
never live in the file. Expansion is deferred to :meth:`Camera.resolved_url`
so ``validate`` works on a laptop without the NVR password.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_env(text: str) -> str:
    """Expand ``${VAR}`` strictly — a missing variable is a hard error."""

    def sub(m: re.Match[str]) -> str:
        val = os.environ.get(m.group(1))
        if val is None:
            raise ValueError(
                f"environment variable {m.group(1)} is not set "
                f"(referenced by site.yaml — credentials live in env, not files)")
        return val

    return _ENV_RE.sub(sub, text)


def env_refs(text: str) -> list[str]:
    return _ENV_RE.findall(text)


@dataclass
class Camera:
    cam_id: str
    url: str | None = None          # raw, may contain ${ENV}
    channel: int | None = None      # used with site url_template
    fps: float = 30.0
    _template: str | None = None

    def raw_url(self) -> str:
        if self.url:
            return self.url
        if self.channel is not None and self._template:
            return self._template.replace("{ch}", str(self.channel))
        raise ValueError(f"camera '{self.cam_id}': set either url, or channel + site url_template")

    def resolved_url(self) -> str:
        return expand_env(self.raw_url())


@dataclass
class Group:
    """One (model, detect_fps) pipeline. This is how per-camera detection rates
    work: cameras needing 10 det/s and cameras fine with 1 det/s go in
    different groups → different pipelines → different nvinfer intervals
    (nvinfer's ``interval`` skips whole batches, so it cannot differ per camera
    within one pipeline — architecture doc §3.2)."""

    name: str
    model: str                      # e.g. yolo26s → app_configs/pgie_yolo26s.txt
    cameras: list[str]
    detect_fps: float = 5.0
    tracker: str = "NvSORT"         # NvSORT (cheap) | NvDCF (occlusion-robust)


@dataclass
class RuleBinding:
    name: str
    camera: str
    kernel: str
    zone: str | None = None         # "zones/file.json#zone_name"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class SiteConfig:
    site: str
    base_dir: Path                  # directory containing site.yaml
    cameras: dict[str, Camera]
    groups: list[Group]
    rules: list[RuleBinding]
    sinks: list[dict[str, Any]]
    streammux: dict[str, int]
    models_dir: str = "/models"
    apps_dir: str = "apps"
    state_dir: str = "state"
    heartbeat_s: float = 60.0

    def group_for(self, cam_id: str) -> Group | None:
        for g in self.groups:
            if cam_id in g.cameras:
                return g
        return None

    def rules_for_camera(self, cam_id: str) -> list[RuleBinding]:
        return [r for r in self.rules if r.camera == cam_id]


def load_site(site_path: str | Path) -> SiteConfig:
    """Load and validate a site. ``site_path`` is the site dir or the yaml file."""
    path = Path(site_path)
    if path.is_dir():
        path = path / "site.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"no site.yaml at {path}")
    base_dir = path.parent
    doc = yaml.safe_load(path.read_text()) or {}

    problems: list[str] = []
    site_name = doc.get("site")
    if not site_name:
        problems.append("missing top-level 'site' name")

    template = doc.get("url_template")
    cameras: dict[str, Camera] = {}
    for cam_id, c in (doc.get("cameras") or {}).items():
        c = c or {}
        cameras[cam_id] = Camera(
            cam_id=str(cam_id),
            url=c.get("url"),
            channel=c.get("channel"),
            fps=float(c.get("fps", 30.0)),
            _template=template,
        )
        try:
            cameras[cam_id].raw_url()
        except ValueError as e:
            problems.append(str(e))
    if not cameras:
        problems.append("no cameras defined")

    groups: list[Group] = []
    seen_in_group: dict[str, str] = {}
    for g in doc.get("groups") or []:
        grp = Group(
            name=g["name"],
            model=g["model"],
            cameras=list(g.get("cameras") or []),
            detect_fps=float(g.get("detect_fps", 5.0)),
            tracker=g.get("tracker", "NvSORT"),
        )
        groups.append(grp)
        for cam in grp.cameras:
            if cam not in cameras:
                problems.append(f"group '{grp.name}': unknown camera '{cam}'")
            if cam in seen_in_group:
                problems.append(
                    f"camera '{cam}' is in groups '{seen_in_group[cam]}' and "
                    f"'{grp.name}' — a camera is decoded once, so it belongs to exactly one group")
            seen_in_group[cam] = grp.name
        for cam in grp.cameras:
            if cam in cameras and grp.detect_fps > cameras[cam].fps:
                problems.append(
                    f"group '{grp.name}': detect_fps {grp.detect_fps} exceeds "
                    f"camera '{cam}' fps {cameras[cam].fps}")

    rules: list[RuleBinding] = []
    rule_names: set[str] = set()
    for i, r in enumerate(doc.get("rules") or []):
        rb = RuleBinding(
            name=r.get("name") or f"rule{i}",
            camera=r["camera"],
            kernel=r["kernel"],
            zone=r.get("zone"),
            params=dict(r.get("params") or {}),
        )
        if rb.name in rule_names:
            problems.append(f"duplicate rule name '{rb.name}'")
        rule_names.add(rb.name)
        if rb.camera not in cameras:
            problems.append(f"rule '{rb.name}': unknown camera '{rb.camera}'")
        elif rb.camera not in seen_in_group:
            problems.append(
                f"rule '{rb.name}': camera '{rb.camera}' is in no group — it will never "
                "be decoded or inferred")
        rules.append(rb)

    if problems:
        raise ValueError(f"{path}:\n  - " + "\n  - ".join(problems))

    mux = doc.get("streammux") or {}
    return SiteConfig(
        site=str(site_name),
        base_dir=base_dir,
        cameras=cameras,
        groups=groups,
        rules=rules,
        sinks=list(doc.get("sinks") or [{"type": "console"}]),
        streammux={"width": int(mux.get("width", 1280)),
                   "height": int(mux.get("height", 720))},
        models_dir=str(doc.get("models_dir", "/models")),
        apps_dir=str(doc.get("apps_dir", "apps")),
        state_dir=str(doc.get("state_dir", "state")),
        heartbeat_s=float(doc.get("heartbeat_s", 60.0)),
    )
