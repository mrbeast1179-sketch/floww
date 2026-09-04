#!/bin/bash
# Restart Floww backend + static proxy cleanly
set -e

PROJ="/Users/nav/Documents/GitHub/floww"
PROXY="/Users/nav/.hermes/scripts/static_proxy.py"

echo "=== Killing existing processes ==="
pkill -f "uvicorn server:app" 2>/dev/null || true
pkill -f "static_proxy.py" 2>/dev/null || true
sleep 2

echo "=== Starting backend on :8000 ==="
cd "$PROJ"
python3 -m uvicorn server:app --host 127.0.0.1 --port 8000 --workers 1 2>&1 &
BACKEND_PID=$!
echo "backend PID: $BACKEND_PID"

echo "=== Starting proxy on :3000 ==="
python3 "$PROXY" --build "$PROJ/frontend/build" 2>&1 &
PROXY_PID=$!
echo "proxy PID: $PROXY_PID"

echo "=== Waiting for startup ==="
sleep 5

echo "=== Health checks ==="
echo -n "backend health: "
curl -s --connect-timeout 3 --max-time 5 http://127.0.0.1:8000/api/health 2>&1 || echo "FAILED"
echo ""
echo -n "proxy health: "
curl -s --connect-timeout 3 --max-time 5 http://localhost:3000/api/health 2>&1 || echo "FAILED"
echo ""

echo "=== Done ==="
