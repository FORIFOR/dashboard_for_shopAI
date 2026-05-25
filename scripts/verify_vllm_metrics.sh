#!/usr/bin/env bash
# Phase 2 check: vLLM exposes the metrics the dashboards depend on.
# Usage: scripts/verify_vllm_metrics.sh [host:port]   (default 192.168.0.15:8000)
set -uo pipefail
TARGET="${1:-192.168.0.15:8000}"
URL="http://${TARGET}/metrics"

echo "Scraping ${URL}"
BODY="$(curl -s --max-time 8 "$URL")" || { echo "FAIL: cannot reach $URL"; exit 1; }

REQUIRED=(
  vllm:num_requests_running
  vllm:num_requests_waiting
  vllm:kv_cache_usage_perc
  vllm:time_to_first_token_seconds
  vllm:e2e_request_latency_seconds
  vllm:inter_token_latency_seconds
  vllm:generation_tokens_total
  vllm:prefix_cache_hits_total
  vllm:prefix_cache_queries_total
  vllm:request_success_total
)
rc=0
for m in "${REQUIRED[@]}"; do
  if grep -q "^${m}" <<<"$BODY"; then echo "  ok   $m"; else echo "  MISS $m"; rc=1; fi
done
[[ $rc -eq 0 ]] && echo "PASS: all required vLLM metrics present" || echo "FAIL: missing metrics above"
exit $rc
