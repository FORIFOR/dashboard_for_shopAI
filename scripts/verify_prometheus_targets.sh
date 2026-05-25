#!/usr/bin/env bash
# Phase 4 check: every Prometheus scrape target is UP.
# Usage: scripts/verify_prometheus_targets.sh [host:port]   (default localhost:9090)
set -uo pipefail
TARGET="${1:-localhost:9090}"
URL="http://${TARGET}/api/v1/targets"

echo "Querying ${URL}"
JSON="$(curl -s --max-time 8 "$URL")" || { echo "FAIL: cannot reach $URL"; exit 1; }

# Pretty-print job -> health using python (no jq dependency).
python3 - "$JSON" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
active = data.get("data", {}).get("activeTargets", [])
if not active:
    print("No active targets."); sys.exit(1)
bad = 0
for t in active:
    job = t["labels"].get("job", "?")
    inst = t["labels"].get("instance", "?")
    health = t["health"]
    mark = "ok  " if health == "up" else "DOWN"
    if health != "up":
        bad += 1
    err = (" — " + t.get("lastError", "")) if t.get("lastError") else ""
    print(f"  {mark} {job:18} {inst}{err}")
print("PASS: all targets up" if bad == 0 else f"FAIL: {bad} target(s) down")
sys.exit(0 if bad == 0 else 1)
PY
