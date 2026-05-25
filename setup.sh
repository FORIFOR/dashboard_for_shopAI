#!/usr/bin/env bash
# ShopAI dashboard — one-command setup. Safe to re-run (idempotent).
#
#   ./setup.sh                 # auto-detect role, then confirm
#   ./setup.sh gpu-pc          # this machine = GPU PC (192.168.0.15)
#   ./setup.sh backend-vm      # this machine = Backend VM (192.168.0.6)
#   NONINTERACTIVE=1 ./setup.sh gpu-pc
#
# It only does what a normal user can; anything needing root is printed for you
# to run with sudo (saiteku cannot run non-interactive sudo).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

c_g=$'\033[32m'; c_y=$'\033[33m'; c_r=$'\033[31m'; c_b=$'\033[36m'; c_0=$'\033[0m'
info() { printf '%s[ info ]%s %s\n' "$c_b" "$c_0" "$*"; }
ok()   { printf '%s[  ok  ]%s %s\n' "$c_g" "$c_0" "$*"; }
warn() { printf '%s[ warn ]%s %s\n' "$c_y" "$c_0" "$*"; }
err()  { printf '%s[ FAIL ]%s %s\n' "$c_r" "$c_0" "$*" >&2; }
need() { command -v "$1" >/dev/null 2>&1 || { err "missing prerequisite: $1"; return 1; }; ok "found $1"; }

gen_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | cut -c1-24
  else
    python3 -c 'import secrets;print(secrets.token_urlsafe(18))'
  fi
}

# ---------------------------------------------------------------- GPU PC ----
setup_gpu_pc() {
  info "Role: GPU PC — nvidia-smi GPU exporter + vLLM metrics check"
  local fail=0
  need nvidia-smi || fail=1
  need python3 || fail=1
  need curl || fail=1
  [ "$fail" = 0 ] || { err "Install the missing prerequisites and re-run."; return 1; }

  info "Creating venv and installing prometheus-client..."
  [ -x gpu-exporter/.venv/bin/python ] || python3 -m venv gpu-exporter/.venv
  gpu-exporter/.venv/bin/pip install -q --upgrade pip
  gpu-exporter/.venv/bin/pip install -q -r gpu-exporter/requirements.txt
  ok "venv ready"

  info "Phase 2 — checking vLLM metrics on :8000"
  bash scripts/verify_vllm_metrics.sh 127.0.0.1:8000 \
    || warn "vLLM not reachable on :8000. Start it (~/shopai-llm-server) before relying on LLM panels."

  info "Phase 3 — GPU exporter"
  if [ "$(id -u)" = 0 ]; then
    bash gpu-exporter/install_systemd_service.sh
  else
    warn "Installing the systemd service needs root. Run this yourself (use ! in Claude Code):"
    printf '       %ssudo bash %s/gpu-exporter/install_systemd_service.sh%s\n' "$c_y" "$ROOT" "$c_0"
    info "Running a 5s foreground test so you can confirm it works now..."
    GPU_EXPORTER_PORT=9401 timeout 5 gpu-exporter/.venv/bin/python gpu-exporter/gpu_exporter.py \
      >/tmp/shopai-gpu-setup-test.log 2>&1 &
    local pid=$!
    sleep 2
    bash scripts/verify_gpu_metrics.sh 127.0.0.1:9401 \
      || warn "exporter test did not pass; see /tmp/shopai-gpu-setup-test.log"
    wait "$pid" 2>/dev/null
  fi

  echo
  ok "GPU PC setup done."
  info "Open the firewall for the Backend VM if one is active:"
  printf '       %ssudo ufw allow from 192.168.0.6 to any port 9401 proto tcp%s\n' "$c_y" "$c_0"
}

# ------------------------------------------------------------ Backend VM ----
ensure_env() {
  if [ ! -f .env ]; then
    cp .env.example .env
    local ga db; ga="$(gen_secret)"; db="$(gen_secret)"
    sed -i "s|^GRAFANA_ADMIN_PASSWORD=.*|GRAFANA_ADMIN_PASSWORD=${ga}|" .env
    sed -i "s|^SHOPAI_DASHBOARD_DB_PASSWORD=.*|SHOPAI_DASHBOARD_DB_PASSWORD=${db}|" .env
    warn "Created .env with generated Grafana-admin and dashboard-DB passwords."
    warn "You MUST edit .env and set POSTGRES_PASSWORD to your existing ShopAI DB password."
  else
    ok ".env already exists (left untouched)"
  fi
}

ensure_network_in_env() {
  local net="${SHOPAI_NETWORK:-}"
  if [ -z "$net" ]; then
    net="$($DOCKER network ls --format '{{.Name}}' 2>/dev/null | grep -E '_default$' | head -1)"
  fi
  if [ -z "$net" ]; then
    err "Could not auto-detect the backend's docker network."
    err "List them with: $DOCKER network ls   then re-run:  SHOPAI_NETWORK=<name> ./setup.sh backend-vm"
    return 1
  fi
  ok "Backend docker network: $net"
  if grep -q '^SHOPAI_NETWORK=' .env 2>/dev/null; then
    sed -i "s|^SHOPAI_NETWORK=.*|SHOPAI_NETWORK=${net}|" .env
  else
    printf '\n# docker network of the backend compose project (auto-detected)\nSHOPAI_NETWORK=%s\n' "$net" >> .env
  fi
}

setup_backend_vm() {
  info "Role: Backend VM — Prometheus + Grafana + exporters"
  local fail=0
  need docker || fail=1
  need curl || fail=1
  need python3 || fail=1
  [ "$fail" = 0 ] || { err "Install the missing prerequisites and re-run."; return 1; }

  # docker compose v2 or v1?
  if docker compose version >/dev/null 2>&1; then DC="docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then DC="docker-compose"
  else err "neither 'docker compose' nor 'docker-compose' is available"; return 1; fi
  ok "compose command: $DC"

  # sudo needed for docker?
  if docker ps >/dev/null 2>&1; then SUDO=""; DOCKER="docker"
  else SUDO="sudo"; DOCKER="sudo docker"; warn "docker needs sudo on this host — using sudo for docker commands"; fi

  ensure_env
  ensure_network_in_env || return 1

  warn "Read-only Grafana DB user: run ONCE if not done yet (needs DB access):"
  printf '       %spsql "postgresql://shopai@localhost:5432/shopai" -v pw=\"'"'"'<SHOPAI_DASHBOARD_DB_PASSWORD from .env>'"'"'\" -f sql/grafana_readonly_user.sql%s\n' "$c_y" "$c_0"

  info "Validating compose config..."
  $SUDO $DC --env-file .env -f docker-compose.monitoring.yml config -q \
    && ok "compose config valid" || { err "compose config invalid — fix .env / network and re-run"; return 1; }

  info "Starting the monitoring stack..."
  $SUDO $DC --env-file .env -f docker-compose.monitoring.yml up -d || { err "compose up failed"; return 1; }

  info "Waiting for Prometheus to scrape (12s)..."
  sleep 12
  info "Phase 4 — checking scrape targets"
  bash scripts/verify_prometheus_targets.sh localhost:9090 \
    || warn "Some targets are not UP yet. Re-run: scripts/verify_prometheus_targets.sh (backend may need the /metrics wiring; vLLM/GPU must be reachable across the LAN)."

  local host; host="$(hostname -I 2>/dev/null | awk '{print $1}')"
  echo
  ok "Backend VM setup done."
  info "Grafana:    http://${host:-192.168.0.6}:3000   (admin / GRAFANA_ADMIN_PASSWORD in .env)"
  info "Prometheus: http://${host:-192.168.0.6}:9090/targets"
  warn "Keep Grafana/Prometheus on the LAN or VPN only — do NOT expose to the internet."
}

# ------------------------------------------------------------------ main ----
case "${1:-}" in
  -h|--help)
    grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
esac

role="${1:-}"
if [ -z "$role" ]; then
  if command -v nvidia-smi >/dev/null 2>&1; then detected="gpu-pc"; else detected="backend-vm"; fi
  if [ "${NONINTERACTIVE:-0}" = 1 ]; then
    role="$detected"; info "Auto-selected role: $role"
  else
    read -rp "Detected role: ${detected}. Enter to accept, or type gpu-pc / backend-vm: " ans
    role="${ans:-$detected}"
  fi
fi

case "$role" in
  gpu-pc)     setup_gpu_pc ;;
  backend-vm) setup_backend_vm ;;
  *) err "unknown role '$role' (expected gpu-pc or backend-vm)"; exit 2 ;;
esac
