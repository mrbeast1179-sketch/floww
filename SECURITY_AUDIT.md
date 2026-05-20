# SECURITY AUDIT REPORT — Floww / Confluence Decoder

**Audit Date:** 2026-07-09
**Auditor:** OWL (red-team audit pass)
**Scope:** Pre-live-trading security gate — all attack surfaces before Schwab data + paper-trade money switch flips.
**Repo:** `git@github.com:JattMoosewala5911/floww.git`
**Truth Audit:** GREEN (14/14 pass) — verified before audit.

---

## SEVERITY KEY

| Severity | Meaning |
|:---------|:--------|
| **CRITICAL** | Exploitable now; gates live-trading switch |
| **HIGH** | Exploitable under common conditions; fix before production |
| **MEDIUM** | Defense-in-depth gap; fix in next sprint |
| **LOW** | Best-practice recommendation |

---

## SUMMARY

| Severity | Count |
|:---------|------:|
| CRITICAL | 5 |
| HIGH | 6 |
| MEDIUM | 5 |
| LOW | 4 |

**Live-trading gate: BLOCKED until all CRITICAL findings are resolved.**

---

## CRITICAL FINDINGS

### C-01: .env File World-Readable (644 Permissions)
- **Severity:** CRITICAL
- **Location:** `backend/.env` (file permissions)
- **Description:** The `.env` file containing 12 secrets (MongoDB credentials, API keys for Polygon, Finnhub, Alpha Vantage, Alpaca, Schwab, etc.) has permissions `644` (rw-r--r--). Any user on the system can read it. On a shared machine or if the Mac has multiple user accounts, this is a full credential compromise.
- **Recommended Fix:**
  ```bash
  chmod 600 /Users/nav/Documents/GitHub/floww/backend/.env
  ```
  Add to a pre-commit hook or startup script to enforce.

### C-02: Auth Bypass When API_SECRET_KEY Is Unset
- **Severity:** CRITICAL
- **Location:** `backend/auth.py:63-65`
- **Description:** If `API_SECRET_KEY` is not set in the environment (or `.env`), the auth middleware allows ALL mutating requests through: `if not expected_key: return True`. This means if the `.env` variable is renamed, misspelled, or the file fails to load, every POST/PUT/DELETE/PATCH route becomes unauthenticated — including Alpaca order execution, portfolio modifications, paper trading, ML model promotion, and live trading controls.
- **Recommended Fix:** Fail closed. If `API_SECRET_KEY` is not set, refuse to start the server or reject all mutating requests:
  ```python
  # auth.py — fail closed
  expected_key = get_api_key()
  if not expected_key:
      logger.critical("API_SECRET_KEY not set — mutating routes disabled")
      raise HTTPException(status_code=503, detail="Authentication not configured")
  ```

### C-03: WebSocket Endpoints Completely Unauthenticated
- **Severity:** CRITICAL
- **Location:** `backend/server.py:2297-2355` (`/ws/gex/{ticker}`), `backend/server.py:2561-2574` (`/ws/{topic}`)
- **Description:** Both WebSocket endpoints accept connections with zero authentication. The `/ws/{topic}` endpoint (added in Project Oracle Phase 4) streams live market data including ticks, flow, toxicity, and analytics. Anyone on the LAN (or internet if port-forwarded) can subscribe to real-time Schwab data. The `/ws/gex/{ticker}` endpoint streams live GEX levels. No token, no API key, no handshake.
- **Recommended Fix:** Add token-based auth via query parameter on connection:
  ```python
  @app.websocket("/ws/{topic}")
  async def websocket_endpoint(websocket: WebSocket, topic: str):
      token = websocket.query_params.get("token", "")
      expected = os.environ.get("WS_API_TOKEN", "")
      if expected and token != expected:
          await websocket.close(code=4001, reason="Unauthorized")
          return
      await ws_manager.connect(websocket, [topic])
      ...
  ```

### C-04: Dash UI at /dashboard/ Has No Access Control
- **Severity:** CRITICAL
- **Location:** `backend/server.py:2577-2583`, `backend/services/dash_ui.py:638`
- **Description:** The Dash/Plotly UI mounted at `/dashboard/` displays live market data, GEX heatmaps, flow, toxicity gauges, and portfolio information. There is no authentication, no session check, no HTTP basic auth. Anyone who can reach `localhost:8000` (or the machine's IP) sees all data. The Dash app is mounted via WSGIMiddleware which bypasses FastAPI's auth middleware entirely.
- **Recommended Fix:** Add a FastAPI middleware or dependency that checks for a session cookie or basic auth before the WSGIMiddleware handles the request:
  ```python
  @app.middleware("http")
  async def dash_auth_middleware(request: Request, call_next):
      if request.url.path.startswith("/dashboard/"):
          token = request.cookies.get("session_token", "")
          if not token or token != os.environ.get("DASH_SESSION_TOKEN", ""):
              from starlette.responses import RedirectResponse
              return RedirectResponse(url="/login")
      return await call_next(request)
  ```

### C-05: CORS `allow_origins=["*"]` Default with No Production Enforcement
- **Severity:** CRITICAL
- **Location:** `backend/server.py:2361`
- **Description:** `CORS_ORIGINS` env var defaults to `"*"` if not set. While `allow_credentials=False` prevents credentialed cross-origin requests, the `*` origin still allows any website to make unauthenticated cross-origin requests to the API. If any route returns sensitive data (and many GET routes do — portfolio, positions, Schwab data), any malicious site can read it. Additionally, `allow_methods=["*"]` and `allow_headers=["*"]` maximize the attack surface.
- **Recommended Fix:**
  ```python
  allowed_origins = os.environ.get("CORS_ORIGINS", "")
  if not allowed_origins:
      raise RuntimeError("CORS_ORIGINS must be set in production — refusing to start with wildcard")
  app.add_middleware(
      CORSMiddleware,
      allow_credentials=False,
      allow_origins=[o.strip() for o in allowed_origins.split(",") if o.strip()],
      allow_methods=["GET", "POST", "PUT", "DELETE"],
      allow_headers=["Authorization", "Content-Type", "X-API-Key"],
  )
  ```

---

## HIGH FINDINGS

### H-01: Middleware Ordering — CORS Added After Routes
- **Severity:** HIGH
- **Location:** `backend/server.py:2358` (add_middleware) vs `backend/server.py:2450+` (include_router)
- **Description:** `app.add_middleware(CORSMiddleware, ...)` is called at line 2358, but `app.include_router(...)` calls start at line 2450. In FastAPI/Starlette, middleware added via `add_middleware` wraps around route handlers, but the order matters for middleware stacking. The `@app.middleware("http")` decorators (rate_limit at line 93, performance at line 176, security_headers at line 2367, auth at line 2391) are registered as decorators and execute in registration order. The CORS middleware being added via `add_middleware` after the decorator-based middleware means CORS headers may not be applied consistently to error responses from the auth/rate-limit middleware.
- **Recommended Fix:** Move `app.add_middleware(CORSMiddleware, ...)` to immediately after `app = FastAPI(...)` (line 83), before any routes or other middleware registration.

### H-02: Rate Limiter Trusts Spoofable Client IP
- **Severity:** HIGH
- **Location:** `backend/server.py:100`
- **Description:** The rate limiter uses `request.client.host` which is the direct TCP peer address. If the server is behind a reverse proxy (nginx, Caddy, Cloudflare), this is the proxy's IP, making rate limiting useless (all users share one bucket). Even without a proxy, `X-Forwarded-For` headers are not checked, but the bigger issue is that the in-memory `_rate_limits` dict is per-worker — uvicorn with `--workers N` means N independent rate limiters, each allowing `RATE_LIMIT` requests/min.
- **Recommended Fix:** Use a Redis-backed rate limiter (e.g., `slowapi` with Redis storage) for production. At minimum, document that single-worker mode is required for rate limiting to work.

### H-03: POST Routes Accepting Raw Dict[str, Any] Without Pydantic Validation
- **Severity:** HIGH
- **Location:** `backend/routes/alerts.py:35`, `backend/routes/gemini.py:13,27,41,59`
- **Description:** Five POST route handlers accept `Dict[str, Any]` directly as request body:
  - `POST /api/alerts/snapshot` — `snapshot: Dict[str, Any]`
  - `POST /api/ai/analyze-trade` — `trade: Dict[str, Any]`
  - `POST /api/ai/analyze-regime` — `regime_data: Dict[str, Any]`
  - `POST /api/ai/summarize-day` — `trades: List[Dict[str, Any]]`
  - `POST /api/ai/explain-signal` — `signal: Dict[str, Any]`
  
  These bypass Pydantic validation entirely. An attacker can send arbitrary keys/values, including nested objects, extremely large payloads, or unexpected types that may cause downstream errors or injection.
- **Recommended Fix:** Define Pydantic models for each:
  ```python
  class AlertSnapshotRequest(BaseModel):
      ticker: str = Field(max_length=10)
      spot_price: float = Field(ge=0)
      gamma_flip: float
      call_wall: float
      put_wall: float
      max_pain: float
      max_gamma_strike: float
      total_gex: float
      net_gex: float
      regime: str = Field(max_length=50)
      gex_by_strike: Dict[str, float] = Field(default_factory=dict)
  ```

### H-04: Schwab OAuth Token File Stored with Insufficient Path Validation
- **Severity:** HIGH
- **Location:** `backend/schwab.py:30,58-63`
- **Description:** The Schwab token file (containing `access_token` and `refresh_token`) defaults to `~/.hermes/schwab_token.json`. While `os.chmod(0o600)` is correctly applied on save (line 63), the parent directory `~/.hermes/` may have permissive permissions. If the directory is world-readable, an attacker could replace the token file before the chmod applies (race condition on first save). Also, the token is loaded into memory (`self._token`) and persists for the lifetime of the process.
- **Recommended Fix:** Ensure `~/.hermes/` has `0700` permissions. Consider encrypting the token file at rest. Clear `self._token` from memory on shutdown.

### H-05: No CSRF Protection on State-Changing Routes
- **Severity:** HIGH
- **Location:** All POST/PUT/DELETE routes (37 POST + 3 DELETE routes)
- **Description:** The API uses `X-API-Key` header for auth, which provides some CSRF protection for API clients (browsers don't automatically add custom headers). However, the Dash UI at `/dashboard/` makes same-origin requests which WOULD include cookies if any were set. There's no CSRF token mechanism, no `SameSite` cookie policy, and no `Origin` header validation. If the Dash UI ever sets cookies, it's vulnerable to CSRF.
- **Recommended Fix:** Add `SameSite=Strict` on any cookies. Validate `Origin` header on mutating requests. Add CSRF tokens for the Dash UI forms.

### H-06: pymongo 4.5.0 — CVE-2024-5629
- **Severity:** HIGH
- **Location:** `backend/.venv` (pymongo 4.5.0)
- **Description:** pymongo 4.5.0 is vulnerable to CVE-2024-5629. Fixed in 4.6.3.
- **Recommended Fix:** `backend/.venv/bin/pip install --upgrade pymongo>=4.6.3`

---

## MEDIUM FINDINGS

### M-01: pip 24.0 — Multiple CVEs (CVE-2025-8869, CVE-2026-1703, CVE-2026-3219, CVE-2026-6357)
- **Severity:** MEDIUM
- **Location:** `backend/.venv` (pip 24.0)
- **Description:** pip 24.0 has 4 known vulnerabilities. While pip is a build-time tool, CVE-2026-3219 and CVE-2026-6357 could affect package installation integrity.
- **Recommended Fix:** `backend/.venv/bin/pip install --upgrade pip>=26.1`

### M-02: npm Frontend Vulnerabilities (nth-check, @eslint/plugin-kit, @tootallnate/once)
- **Severity:** MEDIUM
- **Location:** `frontend/` (npm dependencies)
- **Description:** `npm audit` reports:
  - `nth-check` (< 2.0.1) — High severity, inefficient regex complexity (ReDoS)
  - `@eslint/plugin-kit` (< 0.3.4) — ReDoS via ConfigCommentParser
  - `@tootallnate/once` (< 3.0.1) — Incorrect control Flow Scoping (transitive via jsdom → jest)
  
  The nth-check and eslint issues are in dev dependencies (react-scripts, jest). The jest issues only affect test runtime.
- **Recommended Fix:** Run `npm audit fix` for the `@tootallnate/once` fix. For nth-check and eslint, accept risk (dev-only) or upgrade react-scripts.

### M-03: No Request Size Limits
- **Severity:** MEDIUM
- **Location:** `backend/server.py` (global config)
- **Description:** No `client_max_size` or equivalent is configured. An attacker can send arbitrarily large request bodies to any POST endpoint, causing memory exhaustion.
- **Recommended Fix:** Add a middleware to limit request body size:
  ```python
  @app.middleware("http")
  async def limit_body_size(request: Request, call_next):
      if request.method in ("POST", "PUT", "PATCH"):
          body = await request.body()
          if len(body) > 1_000_000:  # 1MB limit
              return JSONResponse(status_code=413, content={"error": "Payload too large"})
      return await call_next(request)
  ```

### M-04: No API Versioning Prefix on All Routes
- **Severity:** MEDIUM
- **Location:** `backend/server.py` (route wiring)
- **Description:** Some routes use `/api/` prefix (e.g., `/api/alerts`, `/api/portfolio`) while others don't (e.g., `/schwab/`, `/live/`, `/memory/`, `/portfolio/`). This inconsistency makes it hard to apply policies (rate limiting, auth, CORS) at a prefix level and complicates future API versioning.
- **Recommended Fix:** Standardize all routes under `/api/v1/` prefix. Add a global APIRouter with that prefix.

### M-05: Security Headers Only Added After Response (Not on Error Responses)
- **Severity:** MEDIUM
- **Location:** `backend/server.py:2367-2386`
- **Description:** The `security_headers_middleware` adds headers via `response.headers[...]` after `call_next(request)`. If an upstream middleware (rate_limit, auth) returns an error response directly, the security headers middleware still processes it (since it's after call_next). However, if the auth middleware raises an unhandled exception, security headers won't be added. The HSTS header is only set when `ENVIRONMENT == "production"`, but there's no validation that this is set.
- **Recommended Fix:** Add security headers in the exception handlers as well, or use a separate middleware that wraps the entire request.

---

## LOW FINDINGS

### L-01: No Audit Logging for Security Events
- **Severity:** LOW
- **Location:** `backend/auth.py`, `backend/server.py`
- **Description:** Failed auth attempts are logged (`logger.warning`), but there's no structured audit log for security events (auth failures, rate limit hits, token refreshes). This makes incident response difficult.
- **Recommended Fix:** Add a dedicated security audit logger that writes to a separate file with structured JSON.

### L-02: No robots.txt or security.txt
- **Severity:** LOW
- **Location:** N/A
- **Description:** No `robots.txt` to discourage crawling, no `security.txt` for responsible disclosure.
- **Recommended Fix:** Add static files at `/robots.txt` and `/.well-known/security.txt`.

### L-03: No Per-User Rate Limiting
- **Severity:** LOW
- **Location:** `backend/server.py:88-130`
- **Description:** Rate limiting is per-IP only. Authenticated users sharing an IP (NAT, VPN) share a rate limit, and there's no per-user bucket.
- **Recommended Fix:** Add per-user rate limiting behind the auth layer using the API key as the bucket key.

### L-04: Missing HSTS in Non-Production Environments
- **Severity:** LOW
- **Location:** `backend/server.py:2376-2377`
- **Description:** HSTS header is only set when `ENVIRONMENT == "production"`. If `ENVIRONMENT` is unset (default), no HSTS is sent even if the server is accidentally exposed to the internet.
- **Recommended Fix:** Always set HSTS; make `ENVIRONMENT` required at startup.

---

## PREVIOUSLY FIXED (from 2026-05-17 audit)

1. ✅ .env removed from git history (git-filter-repo)
2. ✅ CORS configured with `allow_credentials=False`
3. ✅ X-API-Key auth on mutating routes
4. ✅ Deque-based sliding window rate limiter
5. ✅ Pydantic models on most endpoints
6. ✅ Parameterized MongoDB queries (no string concatenation)
7. ✅ No hardcoded secrets in source code

---

## DEPENDENCY VULNERABILITY SUMMARY

### Python (pip-audit)
| Package | Version | CVE | Fix Version |
|:--------|:--------|:----|:------------|
| pip | 24.0 | CVE-2025-8869 | 25.3 |
| pip | 24.0 | CVE-2026-1703 | 26.0 |
| pip | 24.0 | CVE-2026-3219 | — |
| pip | 24.0 | CVE-2026-6357 | 26.1 |
| pymongo | 4.5.0 | CVE-2024-5629 | 4.6.3 |

### JavaScript (npm audit)
| Package | Severity | Issue |
|:--------|:---------|:------|
| nth-check | HIGH | ReDoS (dev-dependency via react-scripts) |
| @eslint/plugin-kit | MEDIUM | ReDoS (dev-dependency) |
| @tootallnate/once | MEDIUM | Control flow scoping (transitive via jest) |

---

## LIVE-TRADING GATE DECISION

**STATUS: BLOCKED**

**Blockers (all CRITICAL findings must be resolved):**
1. C-01: Fix `.env` file permissions to `0600`
2. C-02: Fail-closed auth when `API_SECRET_KEY` is unset
3. C-03: Add token auth to WebSocket endpoints
4. C-04: Add access control to `/dashboard/`
5. C-05: Enforce explicit CORS origins in production

**Recommended order of operations:**
1. Fix C-01 (chmod — 1 minute)
2. Fix C-02 (auth.py — code change + test)
3. Fix C-05 (CORS — code change + env var)
4. Fix C-03 (WS auth — code change)
5. Fix C-04 (Dash auth — code change)
6. Re-run truth audit
7. Re-run this audit to confirm fixes
8. Unblock live-trading switch

---

*Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>*
