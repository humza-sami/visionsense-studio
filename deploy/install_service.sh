#!/usr/bin/env bash
# Install + enable the VisionSense systemd service so the pipeline runs on boot
# and restarts on failure. Run once (needs sudo):  bash deploy/install_service.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sudo cp "$HERE/visionsense.service" /etc/systemd/system/visionsense.service
sudo systemctl daemon-reload
sudo systemctl enable visionsense.service
sudo systemctl restart visionsense.service
sleep 3
sudo systemctl --no-pager --full status visionsense.service | head -15
echo
echo "Logs:    journalctl -u visionsense -f"
echo "Dash:    http://$(hostname -I | awk '{print $1}'):8000/"
