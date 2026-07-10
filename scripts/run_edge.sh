#!/usr/bin/env bash
# Run a FrameInsight site live inside the DeepStream container.
#
#   bash scripts/run_edge.sh <site-dir> [group]
#   bash scripts/run_edge.sh examples/school
#   bash scripts/run_edge.sh examples/school entrances     # one group only
#
# The site dir must be inside this repo (the repo is mounted at /workspace).
# Camera credentials come from the environment (e.g. SCHOOL_NVR_TMPL) — they
# are passed through to the container, never written to files.
set -euo pipefail

SITE="${1:?usage: run_edge.sh <site-dir> [group]}"
GROUP="${2:-}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="${FRAMEINSIGHT_IMAGE:-frameinsight/edge:0.1.0}"

# Use sudo when the user isn't in the docker group.
DOCKER="docker"
if ! docker ps >/dev/null 2>&1; then
    DOCKER="sudo docker"
fi
# TTY only when attached to a terminal (works under supervisors/systemd too).
TTY=""
[ -t 1 ] && TTY="-it"

if ! $DOCKER image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "building $IMAGE ..." >&2
    $DOCKER build -t "$IMAGE" -f "$REPO/docker/Dockerfile" "$REPO"
fi

# Engines must be prebuilt (building TensorRT engines under live decode load
# once crashed the GPU driver — see models/deepstream/README.md).
if ! ls "$REPO"/models/deepstream/*/*.engine >/dev/null 2>&1; then
    echo "warning: no TensorRT engines under models/deepstream/*/ —" >&2
    echo "         prebuild them first (models/deepstream/README.md)" >&2
fi

# --ulimit nofile: each RTSP source costs several fds; the default 1024 dies
# around 64 streams (measured). --network host: RTSP + local dashboards.
exec $DOCKER run --rm $TTY --gpus all --network host \
    --ulimit nofile=65536:65536 \
    -e NVR_TMPL -e SCHOOL_NVR_TMPL -e OFFICE_NVR_TMPL \
    -e SUPABASE_URL -e SUPABASE_SERVICE_KEY \
    -v "$REPO/models/deepstream:/models" \
    -v "$REPO:/workspace" -w /workspace \
    "$IMAGE" run "/workspace/$SITE" ${GROUP:+-g "$GROUP"}
