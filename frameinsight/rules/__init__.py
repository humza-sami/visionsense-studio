"""Kernel registry: built-in kernels plus per-site plugins.

Built-ins cover the recurring CCTV asks (see docs/builder-spec.md). A site that
needs something new drops a ~30-line kernel in ``<site>/apps/`` and registers
it with :func:`register_kernel` — the runtime, sinks, and dashboards need no
changes (architecture doc §4).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from .base import Rule
from .headcount import Headcount
from .line_crossing import LineCrossing
from .zone_dwell import ZoneDwell
from .zone_intrusion import ZoneIntrusion

import logging

log = logging.getLogger("frameinsight.rules")

KERNELS: dict[str, type[Rule]] = {}
_BUILTIN_KINDS: frozenset[str] = frozenset()  # sealed below, after built-ins register


def register_kernel(cls: type[Rule]) -> type[Rule]:
    """Class decorator: make a kernel available under its ``KIND`` name.

    A plugin may be re-registered (site apps get re-imported when a second
    dispatcher is built in the same process) — last registration wins. Plugins
    can never shadow a built-in kernel.
    """
    kind = getattr(cls, "KIND", None)
    if not kind or kind == "base":
        raise ValueError(f"{cls.__name__}: set a unique KIND class attribute")
    existing = KERNELS.get(kind)
    if existing is not None and existing is not cls:
        if kind in _BUILTIN_KINDS:
            raise ValueError(
                f"{cls.__name__}: kind '{kind}' is a built-in kernel — pick another name")
        log.warning("kernel kind '%s' re-registered (%s replaces %s)",
                    kind, cls.__name__, existing.__name__)
    KERNELS[kind] = cls
    return cls


for _cls in (LineCrossing, ZoneDwell, Headcount, ZoneIntrusion):
    register_kernel(_cls)
_BUILTIN_KINDS = frozenset(KERNELS)


def load_plugins(apps_dir: str | Path) -> list[str]:
    """Import every ``*.py`` in a site's apps/ dir so its kernels register.

    Returns the module names loaded. Missing dir is fine (site has no custom
    apps).
    """
    apps_dir = Path(apps_dir)
    loaded: list[str] = []
    if not apps_dir.is_dir():
        return loaded
    for py in sorted(apps_dir.glob("*.py")):
        mod_name = f"frameinsight_site_apps.{py.stem}"
        spec = importlib.util.spec_from_file_location(mod_name, py)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        loaded.append(mod_name)
    return loaded


__all__ = [
    "Rule", "KERNELS", "register_kernel", "load_plugins",
    "LineCrossing", "ZoneDwell", "Headcount", "ZoneIntrusion",
]
