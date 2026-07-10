"""FrameInsight — multi-camera video-analytics backend on NVIDIA DeepStream.

The package splits into two halves that never mix:

- GPU side (``frameinsight.runtime``): builds one DeepStream pipeline per
  (model, detect_fps) group from ``site.yaml`` and converts DeepStream object
  metadata into plain :class:`~frameinsight.types.Detection` objects.
  Importing it requires ``pyservicemaker`` (only inside the DeepStream container).

- CPU side (everything else): rule kernels, zones, dispatch, and event sinks.
  Pure Python — runs on any machine, which is what makes kernels testable and
  replayable without a GPU.
"""

__version__ = "0.1.0"

from .types import Detection, Event  # noqa: F401
