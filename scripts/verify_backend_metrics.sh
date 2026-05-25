#!/usr/bin/env bash
# Phase 1 check: the FastAPI backend exposes the shopai_* metric contract.
# Run after wiring app/observability into the backend (see backend/README-integration.md).
# Usage: scripts/verify_backend_metrics.sh [host:port]   (default 192.168.0.6:8080)
set -uo pipefail
TARGET="${1:-192.168.0.6:8080}"
URL="http://${TARGET}/metrics"

echo "Scraping ${URL}"
BODY="$(curl -s --max-time 8 "$URL")" || { echo "FAIL: cannot reach $URL"; exit 1; }

REQUIRED=(
  shopai_http_requests_total
  shopai_http_request_duration_seconds
  shopai_chat_requests_total
  shopai_chat_duration_seconds
  shopai_fallback_total
  shopai_auth_rejections_total
  shopai_rag_retrieval_total
  shopai_llm_dispatch_total
  shopai_reasoning_sanitized_total
  shopai_ready_component
)
rc=0
for m in "${REQUIRED[@]}"; do
  if grep -q "^# HELP ${m}" <<<"$BODY"; then echo "  ok   $m"; else echo "  MISS $m"; rc=1; fi
done
echo "---"
echo "Tip: send a few /chat requests, then re-run — chat/route/latency series should populate."
[[ $rc -eq 0 ]] && echo "PASS: backend metric contract present" || echo "FAIL: missing metrics above"
exit $rc
