#!/usr/bin/env bash
# Entrypoint for the additive PoC stack container (colima VM).
#
#   1. Launches the AF Go control plane in background; tails its
#      log to /var/log/agentfield_cp.log for retrieval.
#   2. Polls /api/v1/health on the in-container loopback until
#      the CP is ready (max 90 s) or the CP process dies.
#   3. Editable-installs the agentfield SDK from bind-mounted /sdk
#      so on-host SDK source edits are picked up on restart.
#   4. exec's the floww_greeks bs_agent Python entrypoint, which
#      binds 127.0.0.1:8002 and registers with the in-container
#      CP via the AGENTFIELD_SERVER env var.

set -euo pipefail

mkdir -p /var/log /var/agentfield/data

echo "[entrypoint] launching AF Go control plane on :8080"
af server --backend-only --port 8080 --open=false \
    >/var/log/agentfield_cp.log 2>&1 &
CP_PID=$!
echo "[entrypoint] CP_PID=$CP_PID"

HEALTH_URL="http://127.0.0.1:8080/api/v1/health"
for i in $(seq 1 90); do
  if curl -fs "$HEALTH_URL" >/dev/null 2>&1; then
    echo "[entrypoint] CP healthy after ${i}s on $HEALTH_URL"
    break
  fi
  if ! kill -0 $CP_PID 2>/dev/null; then
    echo "[entrypoint] FATAL: CP process died"
    tail -100 /var/log/agentfield_cp.log >&2
    exit 1
  fi
  sleep 1
done

echo "[entrypoint] pip install -e /sdk"
pip install -e /sdk --quiet

echo "[entrypoint] launching floww_greeks bs_agent on :8002"
exec python /floww/integrations/agentfield/bs_agent.py
