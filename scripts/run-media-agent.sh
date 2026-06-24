#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BINARY="${ROOT_DIR}/media-agent/build/visionsense-media-agent"

if [[ ! -x "${BINARY}" ]]; then
  "${ROOT_DIR}/scripts/build-media-agent.sh"
fi

exec "${BINARY}" --port "${VS_MEDIA_AGENT_PORT:-9010}"
