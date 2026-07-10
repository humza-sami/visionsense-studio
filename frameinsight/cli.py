"""frameinsight CLI.

    frameinsight validate <site>            check site.yaml + zones + rules (no GPU)
    frameinsight replay   <site> <file>     run recorded detections through the rules (no GPU)
    frameinsight run      <site>            run live: one DeepStream pipeline per group
    frameinsight run      <site> -g NAME    run a single group (what the supervisor spawns)
    frameinsight kernels  [<site>]          list available rule kernels
"""

from __future__ import annotations

import argparse
import logging
import multiprocessing
import sys
import time

from .siteconfig import SiteConfig, env_refs, load_site


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr)


# -- validate ------------------------------------------------------------------

def cmd_validate(args: argparse.Namespace) -> int:
    import os

    from .dispatch import Dispatcher
    from .sinks import CompositeSink

    site = load_site(args.site)  # raises with a problem list if invalid
    # Building the dispatcher exercises zone files, kernel names, and params.
    dispatcher = Dispatcher(site, CompositeSink([]), snapshot_every_s=float("inf"))

    print(f"site: {site.site}")
    print(f"cameras ({len(site.cameras)}):")
    missing_env: set[str] = set()
    for cam in site.cameras.values():
        raw = cam.raw_url()
        missing_env.update(v for v in env_refs(raw) if os.environ.get(v) is None)
        grp = site.group_for(cam.cam_id)
        n_rules = len(dispatcher.rules_by_cam.get(cam.cam_id, ()))
        print(f"  {cam.cam_id:<12} fps={cam.fps:<5g} group={grp.name if grp else '-':<12} "
              f"rules={n_rules}")
    print(f"groups ({len(site.groups)}):")
    for g in site.groups:
        print(f"  {g.name:<12} model={g.model:<9} detect_fps={g.detect_fps:<5g} "
              f"tracker={g.tracker:<7} cameras={len(g.cameras)}")
    print(f"rules ({len(site.rules)}):")
    for r in site.rules:
        zone = r.zone or "-"
        print(f"  {r.name:<20} {r.kernel:<15} cam={r.camera:<12} zone={zone}")
    ungrouped = [c for c in site.cameras if site.group_for(c) is None]
    if ungrouped:
        print(f"warning: cameras in no group (never processed): {', '.join(ungrouped)}")
    if missing_env:
        print(f"warning: env vars not set (needed to run live): {', '.join(sorted(missing_env))}")
    print("OK")
    return 0


# -- replay --------------------------------------------------------------------

def cmd_replay(args: argparse.Namespace) -> int:
    from .replay import replay
    from .sinks import build_sinks

    site = load_site(args.site)
    sink = build_sinks(site.sinks if not args.console else [{"type": "console"}],
                       base_dir=site.base_dir)
    t0 = time.monotonic()
    frames = replay(site, sink, args.events, speed=args.speed)
    sink.close()
    print(f"replayed {frames} frames in {time.monotonic() - t0:.2f}s", file=sys.stderr)
    return 0


# -- run -----------------------------------------------------------------------

def _run_one_group(site_path: str, group_name: str, verbose: bool) -> None:
    _setup_logging(verbose)
    from .runtime import run_group
    from .sinks import build_sinks

    site = load_site(site_path)
    sink = build_sinks(site.sinks, base_dir=site.base_dir)
    run_group(site, group_name, sink)


def cmd_run(args: argparse.Namespace) -> int:
    site = load_site(args.site)
    if args.group:
        _run_one_group(args.site, args.group, args.verbose)
        return 0

    # Supervisor: one process per group (one DeepStream pipeline each — the
    # measured-safe pattern is a handful of pipelines sharing the GPU, not one
    # giant mixed pipeline). A crashed group restarts alone; the others keep
    # running.
    procs: dict[str, multiprocessing.Process] = {}

    def spawn(name: str) -> None:
        p = multiprocessing.Process(
            target=_run_one_group, args=(args.site, name, args.verbose),
            name=f"group-{name}")
        p.start()
        procs[name] = p

    for g in site.groups:
        spawn(g.name)
    print(f"started {len(procs)} pipeline group(s): {', '.join(procs)}", file=sys.stderr)
    try:
        while True:
            time.sleep(5)
            for name, p in list(procs.items()):
                if not p.is_alive():
                    print(f"group '{name}' exited (code {p.exitcode}) — restarting in 10s",
                          file=sys.stderr)
                    time.sleep(10)
                    spawn(name)
    except KeyboardInterrupt:
        print("stopping...", file=sys.stderr)
        for p in procs.values():
            p.terminate()
        for p in procs.values():
            p.join(timeout=10)
    return 0


# -- kernels ---------------------------------------------------------------------

def cmd_kernels(args: argparse.Namespace) -> int:
    from .rules import KERNELS, load_plugins

    if args.site:
        site = load_site(args.site)
        load_plugins(site.base_dir / site.apps_dir)
    for kind in sorted(KERNELS):
        cls = KERNELS[kind]
        origin = "built-in" if cls.__module__.startswith("frameinsight.") else "plugin"
        doc = cls.__doc__ or sys.modules[cls.__module__].__doc__ or ""
        summary = doc.strip().splitlines()[0] if doc.strip() else ""
        print(f"{kind:<18} [{origin:<8}] {summary}")
    return 0


# -- studio --------------------------------------------------------------------

def cmd_studio(args: argparse.Namespace) -> int:
    try:
        from .studio.server import run
    except ImportError as e:
        print(f"error: studio needs fastapi+uvicorn — pip install 'frameinsight[studio]' ({e})",
              file=sys.stderr)
        return 2
    run(args.site, host=args.host, port=args.port)
    return 0


# -- entry ---------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="frameinsight",
        description="FrameInsight video-analytics backend (DeepStream edge runtime)")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("validate", help="check a site config without running it")
    p.add_argument("site", help="site directory (containing site.yaml)")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("replay", help="run recorded detections through the rules (no GPU)")
    p.add_argument("site")
    p.add_argument("events", help="JSONL detections file")
    p.add_argument("--speed", type=float, default=0.0,
                   help="0 = as fast as possible (default), 1 = real time")
    p.add_argument("--console", action="store_true",
                   help="print events to stdout instead of the site's sinks")
    p.set_defaults(fn=cmd_replay)

    p = sub.add_parser("run", help="run live pipelines (inside the DeepStream container)")
    p.add_argument("site")
    p.add_argument("-g", "--group", help="run only this group (no supervisor)")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("kernels", help="list available rule kernels")
    p.add_argument("site", nargs="?", help="also load this site's plugins")
    p.set_defaults(fn=cmd_kernels)

    p = sub.add_parser("studio",
                       help="local web UI: draw zones + live view (needs ffmpeg)")
    p.add_argument("site")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="0.0.0.0")
    p.set_defaults(fn=cmd_studio)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    try:
        return args.fn(args)
    except (ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
