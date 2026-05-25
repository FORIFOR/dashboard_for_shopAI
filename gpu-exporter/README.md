# GPU exporter — runs on the GPU PC (192.168.0.15)

This is the only part of the stack that runs on this host. Prometheus on the
Backend VM scrapes it at `192.168.0.15:9401`.

## Why nvidia-smi instead of DCGM

`docker` requires sudo on this host and DCGM on GeForce (RTX 5070 Ti) does not
reliably expose every field, so the **nvidia-smi exporter is the primary path**.
DCGM is available as an alternative via `run_dcgm_exporter.sh`.

Verified on this machine — `curl http://127.0.0.1:9401/metrics` returns:

```
shopai_gpu_utilization_percent{gpu="0",name="NVIDIA GeForce RTX 5070 Ti"} ...
shopai_gpu_memory_used_mib  shopai_gpu_memory_total_mib
shopai_gpu_temperature_celsius  shopai_gpu_power_draw_watts  shopai_gpu_clock_mhz
shopai_gpu_scrape_success  shopai_gpu_exporter_up
```

## Quick test (foreground)

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
./.venv/bin/python gpu_exporter.py    # Ctrl-C to stop
curl http://127.0.0.1:9401/metrics | grep '^shopai_gpu'
```

## Install as a service (persistent, survives reboot)

`systemctl` needs root. saiteku can't run non-interactive sudo, so run this from
the Claude Code prompt with the `!` prefix:

```
! sudo bash ~/Project/shopai-dashboard/gpu-exporter/install_systemd_service.sh
```

Then `systemctl status shopai-gpu-exporter`.

## Open the firewall for the Backend VM (if a firewall is active)

```
! sudo ufw allow from 192.168.0.6 to any port 9401 proto tcp
```
