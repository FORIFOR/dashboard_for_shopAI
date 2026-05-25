#!/usr/bin/env bash
# Install the ShopAI GPU exporter as a systemd service on the GPU PC (192.168.0.15).
# Needs root. saiteku cannot run non-interactive sudo, so run this yourself from
# the Claude Code prompt with the ! prefix, e.g.:
#     ! sudo bash ~/Project/shopai-dashboard/gpu-exporter/install_systemd_service.sh
set -euo pipefail

DIR="/home/saiteku/Project/shopai-dashboard/gpu-exporter"
UNIT="/etc/systemd/system/shopai-gpu-exporter.service"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

# Ensure the venv exists (create as the saiteku user, not root).
if [[ ! -x "$DIR/.venv/bin/python" ]]; then
  echo "Creating venv..."
  sudo -u saiteku python3 -m venv "$DIR/.venv"
  sudo -u saiteku "$DIR/.venv/bin/pip" install -q --upgrade pip
  sudo -u saiteku "$DIR/.venv/bin/pip" install -q -r "$DIR/requirements.txt"
fi

install -m 0644 "$DIR/shopai-gpu-exporter.service" "$UNIT"
systemctl daemon-reload
systemctl enable --now shopai-gpu-exporter.service
sleep 2
systemctl --no-pager --full status shopai-gpu-exporter.service | head -20
echo "---"
echo "Verify: curl http://127.0.0.1:9401/metrics | grep '^shopai_gpu'"
