#!/usr/bin/env bash
# ALTERNATIVE GPU exporter: NVIDIA DCGM Exporter (container, :9400).
# Try this only if you prefer DCGM over the nvidia-smi exporter. Needs docker,
# which requires sudo on this host. Run from the Claude Code prompt with !:
#     ! sudo bash ~/Project/shopai-dashboard/gpu-exporter/run_dcgm_exporter.sh
#
# NOTE: On GeForce (RTX 5070 Ti) DCGM may not return every field (e.g. some
# clock/power metrics). If DCGM_FI_DEV_GPU_UTIL / _FB_USED / _GPU_TEMP /
# _POWER_USAGE are missing or zero, stay on the nvidia-smi exporter (:9401) and
# point the prometheus job at it instead.
set -euo pipefail

IMAGE="nvcr.io/nvidia/k8s/dcgm-exporter:4.5.3-4.8.2-distroless"

docker rm -f shopai-dcgm-exporter 2>/dev/null || true
docker run -d \
  --name shopai-dcgm-exporter \
  --restart unless-stopped \
  --gpus all \
  --cap-add SYS_ADMIN \
  -p 9400:9400 \
  "$IMAGE"

echo "Waiting for DCGM exporter..."
sleep 8
echo "--- expected fields ---"
curl -s http://127.0.0.1:9400/metrics | grep -E \
  'DCGM_FI_DEV_(GPU_UTIL|FB_USED|FB_FREE|GPU_TEMP|POWER_USAGE)' | head -20 \
  || echo "DCGM returned no matching fields — prefer the nvidia-smi exporter (:9401)."
