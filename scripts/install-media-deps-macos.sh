#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This installer is for macOS." >&2
  exit 1
fi

command -v brew >/dev/null 2>&1 || {
  echo "Homebrew is required: https://brew.sh" >&2
  exit 1
}

# GStreamer supplies RTSP ingest/publishing, codecs, and VideoToolbox.
brew install gstreamer

gst-inspect-1.0 rtspsrc >/dev/null
gst-inspect-1.0 vtdec_hw >/dev/null
gst-inspect-1.0 vtenc_h264_hw >/dev/null
gst-inspect-1.0 webrtcbin >/dev/null
gst-inspect-1.0 rtspclientsink >/dev/null

echo "macOS media dependencies are ready."
