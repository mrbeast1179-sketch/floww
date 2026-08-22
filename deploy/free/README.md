# Going Live Free — Confluence Decoder

Goal: host the Decoder (FastAPI + React + Mongo) for free so friends can hit
it from a public URL. Everything here is $0 forever-tier.

## Why not Azure credit?
You CAN use the Azure for Students B1s free VM (750 hrs/mo, doesn't touch the
$200 credit) — instructions below work there identically. Save the $200 for
GPU/AI experiments. The truly-free-forever alternative is **Oracle Cloud ARM
Always Free** (4 cores / 24GB RAM — overkill in a good way).

## The one big caveat: yfinance on cloud IPs
Yahoo rate-limits datacenter IPs. On your Mac it works; on Azure/Oracle it may
start returning 429s under load. Mitigations already in the stack:
- Backend caches per-ticker responses (friends-scale traffic ≈ fine)
- Finnhub/AlphaVantage/Polygon keys are configured as fallbacks
  (`FLOWW_DATA_SOURCE`, `services/data_fallback.py`)
If yfinance gets blocked hard on the VM, set `FLOWW_DATA_SOURCE` to finnhub
and/or add a cheap Polygon starter later.

## What gets deployed
```
Internet ──► Caddy (:80/:443, auto-HTTPS, free Let's Encrypt)
              ├─ /*            → frontend/build static files
              ├─ /api/*        → FastAPI backend :8000
              ├─ /ws/*         → FastAPI websockets (GEX live stream)
              └─ /dashboard/*  → Dash UI
FastAPI ────► MongoDB container (internal only)
```
Single docker-compose file: `deploy/free/docker-compose.yml`.

## Steps (30–45 min)

### A. Get a VM (pick one)
1. **Azure for Students** (you have this): portal.azure.com → Create VM →
   size **B1s or B2ats_v2** (ARM if available), Ubuntu 24.04, allow ports 22/80/443.
   This uses the FREE 750 hrs/mo allowance, NOT the $200 credit.
2. **Oracle Always Free** (better specs, $0 forever): signup needs a card for
   verification but never charges on the Always Free tier.

### B. DNS (free)
Cheapest path that works with Let's Encrypt: buy nothing — use **DuckDNS**
(duckdns.org, free subdomains like `confluencedecoder.duckdns.org`) OR point a
domain you own at the VM IP. Add an A record → VM public IP.

### C. Provision the server
```bash
ssh azureuser@<VM_IP>
curl -fsSL https://raw.githubusercontent.com/mrbeast1179-sketch/floww/main/deploy/free/server-setup.sh | bash
# It will stop once and ask you to fill secrets:
nano /opt/floww/deploy/free/.env.prod    # DOMAIN, ADMIN_EMAIL, API keys
bash /opt/floww/deploy/free/server-setup.sh   # resumes, builds, starts
```

### D. Verify
```bash
curl https://your.domain/api/health
curl -s "https://your.domain/api/briefing/SPY" | head -c 200
open https://your.domain
```

## Secrets you must copy to the server
From local `backend/.env`: FINNHUB_API_KEY, ALPHA_VANTAGE_KEY,
POLYGON_API_KEY, DATABENTO_API_KEY, OPENROUTER_API_KEY, CVSERVER_API_KEY,
FLASHALPHA_API_KEY + generate fresh API_SECRET_KEY / JWT_SECRET_KEY.
The template lists all of them: `deploy/free/.env.prod.template`.

## Local ML models
`backend/models/` (71MB of .joblib artifacts) is IN git, so `git clone` on the
server brings the models automatically. Nothing extra to upload.

## Maintenance
```bash
cd /opt/floww
git pull
docker compose -f deploy/free/docker-compose.yml --env-file deploy/free/.env.prod up -d --build backend
docker compose -f deploy/free/docker-compose.yml logs -f --tail=100 backend
```
Disk watch: Mongo grows slowly (11MB now). `df -h` monthly is enough.

## Known gaps / honest notes
- `/health` (no prefix) returns 404 in current build — healthcheck and Caddy
  probes use `/api/health` instead. Fixing the route is optional cleanup.
- ~~Frontend hardcoded `http://localhost:8000` fetch bases~~ FIXED at
  `af4e254`: all 14 components resolve same-origin at runtime. No
  REACT_APP_* build args needed — one build works on localhost AND prod.
- Schwab WebSocket streamer won't run on server unless you copy its token env;
  stack falls back to yfinance/polling providers without it.
