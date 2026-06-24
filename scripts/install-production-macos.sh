#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_SOURCE="${ROOT_DIR}/deploy/launchd/com.xronai.visionsense-media-agent.plist"
PLIST_TARGET="${HOME}/Library/LaunchAgents/com.xronai.visionsense-media-agent.plist"

"${ROOT_DIR}/scripts/install-media-deps-macos.sh"
"${ROOT_DIR}/scripts/build-media-agent.sh"

mkdir -p "${HOME}/Library/LaunchAgents" "${HOME}/Library/Logs"
sed \
  -e "s|__PROJECT_DIR__|${ROOT_DIR}|g" \
  -e "s|__HOME__|${HOME}|g" \
  "${PLIST_SOURCE}" > "${PLIST_TARGET}"

launchctl bootout "gui/${UID}" "${PLIST_TARGET}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/${UID}" "${PLIST_TARGET}"
launchctl enable "gui/${UID}/com.xronai.visionsense-media-agent"

docker compose -f "${ROOT_DIR}/docker-compose.mac.yml" up -d --build
echo "VisionSense is available at http://localhost:3000"
