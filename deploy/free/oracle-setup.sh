#!/usr/bin/env bash
# deploy/free/oracle-setup.sh — Oracle Cloud Always Free (ARM A1) bootstrap.
# Run ONCE on a fresh Ubuntu 22.04+/24.04 VM as the default user (ubuntu/opc), via sudo.
#
# Usage:
#   scp -i <key> deploy/free/{oracle-setup.sh,deploy_key_ed25519,server-setup.sh} ubuntu@<VM_IP>:~/
#   ssh -i <key> ubuntu@<VM_IP>
#   chmod 600 ~/deploy_key_ed25519 && sudo bash ~/oracle-setup.sh
#
# The script stops once to let you fill secrets, then re-runs to build & start.

set -euo pipefail

APP_DIR="/opt/floww"
REPO_SSH="git@github.com:mrbeast1179-sketch/floww.git"
DEPLOY_KEY_SRC="$HOME/deploy_key_ed25519"

[ "$(id -u)" -eq 0 ] || { echo "run with sudo"; exit 1; }
[ -f "$DEPLOY_KEY_SRC" ] || { echo "missing $DEPLOY_KEY_SRC — scp deploy/free/deploy_key_ed25519 up first"; exit 1; }

echo "── 1. System packages ──"
apt-get update -qq
apt-get install -y -qq ca-certificates curl git ufw

echo "── 2. Docker ──"
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

echo "── 4. Install read-only GitHub deploy key ──"
install -m 600 -o root -g root "$DEPLOY_KEY_SRC" /root/.ssh/floww_deploy_key
grep -q "github.com" /root/.ssh/config 2>/dev/null || cat >> /root/.ssh/config <<'EOF'
Host github.com
    IdentityFile /root/.ssh/floww_deploy_key
    StrictHostKeyChecking accept-new
EOF
chmod 600 /root/.ssh/config

echo "── 5. Clone repo ──"
if [ ! -d "$APP_DIR" ]; then
    git clone "$REPO_SSH" "$APP_DIR"
fi
cd "$APP_DIR"

echo "── 6. Secrets file ──"
if [ ! -s deploy/free/.env.prod ] || grep -q "your.domain.com" deploy/free/.env.prod; then
    cp -n deploy/free/.env.prod.template deploy/free/.env.prod || true
    chmod 600 deploy/free/.env.prod
    echo "!! EDIT $APP_DIR/deploy/free/.env.prod — set:"
    echo "!!   DOMAIN=confluencedecoder.duckdns.org"
    echo "!!   ADMIN_EMAIL, CORS_ORIGINS=https://confluencedecoder.duckdns.org"
    echo "!!   fresh API_SECRET_KEY + JWT_SECRET_KEY (python3 -c \"import secrets; print(secrets.token_hex(32))\")"
    echo "!!   data provider keys from local backend/.env"
    echo "!! Then re-run: sudo bash $APP_DIR/deploy/free/oracle-setup.sh"
    exit 1
fi

echo "── 7. Build frontend ──"
cd frontend
npm ci --legacy-peer-deps
npm run build
cd ..

echo "── 8. Start stack ──"
docker compose -f deploy/free/docker-compose.yml --env-file deploy/free/.env.prod up -d --build

echo ""
echo "Waiting for backend health..."
for i in $(seq 1 30); do
    if curl -sf http://localhost/api/health >/dev/null 2>&1; then
        DOMAIN=$(grep '^DOMAIN=' deploy/free/.env.prod | cut -d= -f2)
        echo "✅ Confluence Decoder LIVE on https://${DOMAIN}"
        echo "   Don't forget: update DuckDNS to point at THIS VM's public IP:"
        echo "   curl https://www.duckdns.org/update?domains=confluencedecoder&token=<TOKEN>&ip=$(curl -s ifconfig.me)"
        exit 0
    fi
    sleep 5
done
echo "⚠ Backend not healthy yet — check: docker compose -f deploy/free/docker-compose.yml logs backend"
exit 1
