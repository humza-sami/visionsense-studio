#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${ROOT_DIR}/media-agent/build"

if command -v cmake >/dev/null 2>&1; then
  cmake -S "${ROOT_DIR}/media-agent" -B "${BUILD_DIR}"
  cmake --build "${BUILD_DIR}" --parallel
else
  mkdir -p "${BUILD_DIR}"
  CXX="${CXX:-clang++}"
  if ! command -v pkg-config >/dev/null 2>&1 || ! pkg-config --exists gstreamer-1.0 gstreamer-app-1.0; then
    echo "GStreamer development files are required. Run scripts/install-media-deps-macos.sh or scripts/install-media-deps-ubuntu.sh." >&2
    exit 1
  fi
  read -r -a GST_CFLAGS <<< "$(pkg-config --cflags gstreamer-1.0 gstreamer-app-1.0)"
  read -r -a GST_LIBS <<< "$(pkg-config --libs gstreamer-1.0 gstreamer-app-1.0)"
  PLATFORM_DEFINE="-DVS_PLATFORM_LINUX=1"
  if [[ "$(uname -s)" == "Darwin" ]]; then
    PLATFORM_DEFINE="-DVS_PLATFORM_MACOS=1"
  fi
  "${CXX}" \
    -std=c++20 \
    -O2 \
    -Wall \
    -Wextra \
    -Wpedantic \
    "${PLATFORM_DEFINE}" \
    "${GST_CFLAGS[@]}" \
    -I"${ROOT_DIR}/media-agent/include" \
    "${ROOT_DIR}/media-agent/src/main.cpp" \
    "${ROOT_DIR}/media-agent/src/capabilities.cpp" \
    "${ROOT_DIR}/media-agent/src/http_server.cpp" \
    "${ROOT_DIR}/media-agent/src/pipeline_manager.cpp" \
    "${GST_LIBS[@]}" \
    -o "${BUILD_DIR}/visionsense-media-agent"
fi

echo "Built ${BUILD_DIR}/visionsense-media-agent"
