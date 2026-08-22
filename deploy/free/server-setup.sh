#!/usr/bin/env bash
# deploy/free/server-setup.sh
# Run ONCE on a fresh Ubuntu 22.04+/Debian ARM VM (as root or with sudo).
# Installs Docker, hardens the firewall, clones the repo, and starts the stack.

set -euo pipefail

REPO_URL="https://github.com/mrbeast1179-sketch/floww.git"
APP_DIR="/opt/floww"

echo "── 1. System packages ──"
apt-get update -qq
apt-get install -y -qq ca-certificates curl git ufw

echo "── 2. Docker (official convenience script) ──"
if ! command -v docker >/dev/null; then
    curl -fsSL https://get.docker.com | sh
fi
docker --version
docker compose version

echo "── 3. Firewall: only SSH + web ──"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "── 4. Clone repo ──"
if [ ! -d "$APP_DIR" ]; then
    git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

echo "── 5. Secrets file ──"
if [ ! -f deploy/free/.env.prod ]; then
    cp deploy/free/.env.prod.template deploy/free/.env.prod
    chmod 600 deploy/free/.env.prod
    echo "!! EDIT $APP_DIR/deploy/free/.env.prod — fill in DOMAIN + API keys, then re-run this script."
    exit 1
fi

echo "── 6. Build frontend (needs ~2GB RAM; ARM free VMs have it) ──"
cd frontend
npm ci --legacy-peer-deps
npm run build
cd ..

echo "── 7. Start stack ──"
docker compose -f deploy/free/docker-compose.yml --env-file deploy/free/.env.prod up -d --build

echo ""
echo "Waiting for backend health..."
for i in $(seq 1 30); do
    if curl -sf http://localhost/api/health >/dev/null 2>&1; then
        echo "✅ Confluence Decoder LIVE on https://${DOMAIN:-your.domain}"
        exit 0
    fi
    sleep 5
done
echo "⚠ Backend not healthy yet — check: docker compose -f deploy/free/docker-compose.yml logs backend"
exit 1
