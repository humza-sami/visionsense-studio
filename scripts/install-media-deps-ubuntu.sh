#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This installer is for Ubuntu/Linux." >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y \
  build-essential \
  cmake \
  pkg-config \
  rsync \
  gstreamer1.0-tools \
  gstreamer1.0-libav \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly \
  libgstreamer1.0-dev \
  libgstreamer-plugins-base1.0-dev \
  libgstreamer-plugins-bad1.0-dev

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "Install the Ubuntu NVIDIA driver before continuing." >&2
  exit 2
fi

if ! command -v nvidia-ctk >/dev/null 2>&1; then
  echo "Install NVIDIA Container Toolkit:" >&2
  echo "https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html" >&2
  exit 3
fi

gst-inspect-1.0 rtspsrc >/dev/null
gst-inspect-1.0 webrtcbin >/dev/null
gst-inspect-1.0 rtspclientsink >/dev/null
gst-inspect-1.0 nvh265dec >/dev/null
gst-inspect-1.0 nvh264enc >/dev/null

echo "Ubuntu media dependencies and NVIDIA NVCodec plugins are ready."
