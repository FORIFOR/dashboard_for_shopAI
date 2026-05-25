#!/usr/bin/env python3
"""nvidia-smi based Prometheus exporter for the ShopAI GPU PC (192.168.0.15).

Primary GPU exporter for ShopAI. We use nvidia-smi rather than DCGM because:
  - DCGM Exporter needs a privileged container (docker + SYS_ADMIN), and docker
    on this host requires sudo; and
  - on GeForce (RTX 5070 Ti) DCGM does not reliably expose every field.
nvidia-smi returns utilization / VRAM / temperature / power / clocks directly,
with no container, so it is the dependable choice here. The DCGM path is kept as
an alternative in run_dcgm_exporter.sh.

Exposes (one time series per physical GPU, labelled gpu="<index>" name="<model>"):
  shopai_gpu_utilization_percent
  shopai_gpu_memory_used_mib
  shopai_gpu_memory_total_mib
  shopai_gpu_temperature_celsius
  shopai_gpu_power_draw_watts
  shopai_gpu_clock_mhz
  shopai_gpu_scrape_success     (1 ok / 0 last poll failed)
  shopai_gpu_exporter_up        (constant 1 — liveness)

Config via env: GPU_EXPORTER_PORT (default 9401), GPU_EXPORTER_INTERVAL (2 s).
"""

import os
import subprocess
import sys
import time

from prometheus_client import Gauge, start_http_server

PORT = int(os.environ.get("GPU_EXPORTER_PORT", "9401"))
INTERVAL = float(os.environ.get("GPU_EXPORTER_INTERVAL", "2"))

_LABELS = ["gpu", "name"]
GPU_UTIL = Gauge("shopai_gpu_utilization_percent", "GPU utilization percent", _LABELS)
GPU_MEMORY_USED = Gauge("shopai_gpu_memory_used_mib", "GPU memory used MiB", _LABELS)
GPU_MEMORY_TOTAL = Gauge("shopai_gpu_memory_total_mib", "GPU memory total MiB", _LABELS)
GPU_TEMPERATURE = Gauge("shopai_gpu_temperature_celsius", "GPU temperature", _LABELS)
GPU_POWER_DRAW = Gauge("shopai_gpu_power_draw_watts", "GPU power draw", _LABELS)
GPU_CLOCK = Gauge("shopai_gpu_clock_mhz", "GPU graphics clock MHz", _LABELS)
SCRAPE_SUCCESS = Gauge("shopai_gpu_scrape_success", "1 if last nvidia-smi poll succeeded")
EXPORTER_UP = Gauge("shopai_gpu_exporter_up", "Exporter liveness (always 1)")

_QUERY = (
    "index,name,utilization.gpu,memory.used,memory.total,"
    "temperature.gpu,power.draw,clocks.current.graphics"
)


def _to_float(value: str) -> float:
    value = value.strip()
    # nvidia-smi prints "[N/A]" / "[Not Supported]" for unsupported fields.
    if not value or value.startswith("[") or value.lower() == "n/a":
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def update_metrics() -> None:
    output = subprocess.check_output(
        ["nvidia-smi", f"--query-gpu={_QUERY}", "--format=csv,noheader,nounits"],
        text=True,
        timeout=10,
    ).strip()

    for line in output.splitlines():
        fields = line.split(",")
        if len(fields) < 8:
            continue
        index = fields[0].strip()
        name = fields[1].strip()
        util, used, total, temp, power, clock = (
            _to_float(fields[i]) for i in range(2, 8)
        )
        labels = {"gpu": index, "name": name}
        GPU_UTIL.labels(**labels).set(util)
        GPU_MEMORY_USED.labels(**labels).set(used)
        GPU_MEMORY_TOTAL.labels(**labels).set(total)
        GPU_TEMPERATURE.labels(**labels).set(temp)
        GPU_POWER_DRAW.labels(**labels).set(power)
        GPU_CLOCK.labels(**labels).set(clock)


def main() -> None:
    start_http_server(PORT)
    EXPORTER_UP.set(1)
    print(f"shopai-gpu-exporter listening on :{PORT} (interval {INTERVAL}s)", flush=True)
    while True:
        try:
            update_metrics()
            SCRAPE_SUCCESS.set(1)
        except Exception as exc:  # keep serving last-known values on failure
            SCRAPE_SUCCESS.set(0)
            print(f"nvidia-smi poll failed: {exc}", file=sys.stderr, flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
