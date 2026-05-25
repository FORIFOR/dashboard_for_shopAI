#!/usr/bin/env bash
# Phase 3 check: the GPU exporter exposes RTX 5070 Ti metrics.
# Usage: scripts/verify_gpu_metrics.sh [host:port]   (default 192.168.0.15:9401)
set -uo pipefail
TARGET="${1:-192.168.0.15:9401}"
URL="http://${TARGET}/metrics"

echo "Scraping ${URL}"
BODY="$(curl -s --max-time 8 "$URL")" || { echo "FAIL: cannot reach $URL"; exit 1; }

REQUIRED=(
  shopai_gpu_utilization_percent
  shopai_gpu_memory_used_mib
  shopai_gpu_memory_total_mib
  shopai_gpu_temperature_celsius
  shopai_gpu_power_draw_watts
  shopai_gpu_scrape_success
)
rc=0
for m in "${REQUIRED[@]}"; do
  if grep -q "^${m}" <<<"$BODY"; then echo "  ok   $m"; else echo "  MISS $m"; rc=1; fi
done
grep -q '^shopai_gpu_scrape_success 1' <<<"$BODY" || { echo "  WARN: last nvidia-smi poll failed"; rc=1; }
[[ $rc -eq 0 ]] && echo "PASS: GPU exporter healthy" || echo "FAIL: see above"
exit $rc
