#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"${ROOT_DIR}/scripts/install-media-deps-ubuntu.sh"
"${ROOT_DIR}/scripts/build-media-agent.sh"

if ! id visionsense >/dev/null 2>&1; then
  sudo useradd --system --home /opt/visionsense-studio --shell /usr/sbin/nologin visionsense
fi

sudo mkdir -p /opt/visionsense-studio
sudo rsync -a --delete \
  --exclude .git \
  --exclude frontend/node_modules \
  "${ROOT_DIR}/" /opt/visionsense-studio/
sudo chown -R visionsense:visionsense /opt/visionsense-studio
sudo install -m 0644 \
  "${ROOT_DIR}/deploy/systemd/visionsense-media-agent.service" \
  /etc/systemd/system/visionsense-media-agent.service
sudo systemctl daemon-reload
sudo systemctl enable --now visionsense-media-agent

sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
docker compose -f /opt/visionsense-studio/docker-compose.yml up -d --build

echo "VisionSense is available at http://localhost:3000"
