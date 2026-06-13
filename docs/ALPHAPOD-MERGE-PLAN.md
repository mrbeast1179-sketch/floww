# MASTER PLAN: Merge AlphaPod Clone with floww Backend

## Goal
Replace the floww frontend (CRA React app in `/Users/nav/Documents/GitHub/floww/frontend/`) with the AlphaPod-cloned SPA from `/Users/nav/GitHub/hub-alphapodtrading/`, while keeping the floww FastAPI backend (port 8000) and preserving Trinity + Heatseeker functionality.

## Current State

### floww project (`/Users/nav/Documents/GitHub/floww/`)
- **Backend**: FastAPI on port 8000 with routes like `/api/heatseeker/*`, `/api/chain/*`, `/api/advanced/*`, `/api/ml/*`, etc.
- **Frontend**: CRA (craco) React app on port 3000 — currently has AlphaPod-style UI we just built
- **Key pages**: Trinity (legacy options flow), Heatseeker (GEX heatmap), Skylit, Flowseeker, Portfolio, Journal, SwarmSPX
- **Data sources**: Databento, Polygon, yfinance — our own data, NOT AlphaPod's

### AlphaPod clone (`/Users/nav/GitHub/hub-alphapodtrading/`)
- **Server**: Python ThreadingHTTPServer on port 3456 that serves a Vite-built React SPA
- **API proxy**: `/api/*` → `https://api.alphapodtrading.com/api/*` with JWT auth
- **Pages**: Flow Alerts, Alpha Flow, Daily Report, SPX GEX, Ticker Analysis, Earnings + mock pages
- **Auth**: JWT via POST /api/auth/dev-token (email + tier)

## Architecture Decision

**Use the AlphaPod clone as the MAIN frontend, but modify it to:**

1. **Replace the API proxy** — Instead of proxying to `https://api.alphapodtrading.com`, proxy to our local floww backend at `http://localhost:8000`
2. **Add Trinity and Heatseeker routes** — These are our unique features that don't exist on AlphaPod
3. **Keep the AlphaPod sign-in page** — But make it optional (allow bypass for local dev)
4. **Merge the static assets** — Copy the AlphaPod `assets/`, `fonts/`, `index.html` into the floww project

## Step-by-Step Plan

### Phase 1: Set up the AlphaPod SPA as the floww frontend
1. Copy `index.html`, `assets/`, `fonts/`, `favicon.svg` from hub-alphapodtrading to floww's frontend public directory
2. Modify `server.py` in hub-alphapodtrading to:
   - Change API_BASE from `https://api.alphapodtrading.com` to `http://localhost:8000`
   - Remove the JWT auth (our backend doesn't need it for most endpoints)
   - Keep the SPA routing and static file serving
3. Test that the AlphaPod SPA loads and can call our backend

### Phase 2: Add Trinity and Heatseeker to the AlphaPod SPA
1. Add new routes to the AlphaPod SPA: `/trinity` and `/heatseeker`
2. These routes should render our existing Trinity and Heatseeker components
3. The AlphaPod SPA needs to be modified to include our custom components
4. Since the SPA is minified/bundled, we need to either:
   a. Add a script tag that loads our components separately, OR
   b. Rebuild the SPA with our components included

### Phase 3: API compatibility layer
1. The AlphaPod frontend expects specific API response shapes from `/api/alerts`, `/api/alpha-flow`, etc.
2. Our floww backend has different endpoints and response shapes
3. Create an API compatibility layer in the FastAPI backend that:
   - Maps AlphaPod-style endpoints to floww endpoints
   - Transforms response shapes to match what the AlphaPod frontend expects
4. Key mappings:
   - `/api/alerts` → our existing `/api/alerts` (may need shape adjustment)
   - `/api/alpha-flow` → create new endpoint that returns floww data in AlphaPod format
   - `/api/deep-dive/{ticker}` → map to our `/api/chain/{ticker}` + `/api/advanced/{ticker}`
   - `/api/gex/spx` → map to our GEX calculations

### Phase 4: Auth flow
1. Keep the AlphaPod sign-in page for visual consistency
2. Make it a "dev login" that sets a dummy token
3. Our backend doesn't require auth for read endpoints
4. The sign-in just stores a token and redirects to the main app

### Phase 5: Testing
1. Start floww backend: `cd backend && source venv/bin/activate && python -m uvicorn server:app --port 8000`
2. Start AlphaPod SPA server: `cd /Users/nav/GitHub/hub-alphapodtrading && python3 server.py`
3. Open http://localhost:3456
4. Sign in with demo@alphapod.dev / pro
5. Verify all pages load and show real data
6. Verify Trinity and Heatseeker work

## Important Notes
- The AlphaPod SPA is a Vite-built app with minified JS bundles
- We CANNOT easily modify the React components without rebuilding
- Instead, we should use the server.py approach: serve the AlphaPod SPA, and add our custom pages as separate HTML/JS that loads alongside
- The key insight: we can add `<script>` tags to index.html that load additional code
- Or better: we can create a hybrid approach where the AlphaPod SPA handles most pages, and we embed our Trinity/Heatseeker as iframes or separate routes

## Recommended Approach (Simplest)
1. Use the hub-alphapodtrading server.py as-is, but change API_BASE to `http://localhost:8000`
2. Add API compatibility endpoints to floww's backend
3. For Trinity/Heatseeker: add new routes to server.py that serve our existing CRA-built pages as iframes or embedded apps
4. The AlphaPod SPA gets a "Trinity" and "Heatseeker" nav item that opens our legacy app in an iframe or new tab

## Files to Modify
- `/Users/nav/GitHub/hub-alphapodtrading/server.py` — Change API_BASE, add Trinity/Heatseeker routes
- `/Users/nav/Documents/GitHub/floww/backend/server.py` — Add AlphaPod-compatible API endpoints
- `/Users/nav/GitHub/hub-alphapodtrading/index.html` — Add nav items for Trinity/Heatseeker

## Verification
```bash
# Terminal 1
cd /Users/nav/Documents/GitHub/floww/backend && source venv/bin/activate && python -m uvicorn server:app --port 8000

# Terminal 2
cd /Users/nav/GitHub/hub-alphapodtrading && python3 server.py

# Terminal 3 - Test
curl -s http://localhost:3456/ | head -20
curl -s -X POST http://localhost:3456/api/auth/dev-token -H "Content-Type: application/json" -d '{"email":"demo@alphapod.dev","tier":"pro"}'
```
