# Security Fixes — 2026-07-03

Applied against audit report `reports/audit_security_2026-07-02.md`.
All 6 issues closed. No live API key values were modified.

---

## FIX C-01 — Hardcoded JWT secret removed ✅

**File:** `backend/routes/alphapod_compat.py`

**What changed:**
- Added `import os` and `HTTPException` to top-level imports
- Replaced `hmac.new(b"floww-dev-secret", ...)` with env-var read:
  ```python
  secret = os.environ.get("JWT_SECRET_KEY", "").encode()
  if not secret:
      raise HTTPException(status_code=503, detail="JWT secret not configured ...")
  ```
- The `/api/auth/dev-token` endpoint now fails loudly (503) when `JWT_SECRET_KEY` is unset
- Added `JWT_SECRET_KEY=` placeholder to `backend/.env` with generation instructions

**Action required:** Set `JWT_SECRET_KEY` in `backend/.env` (and in production secrets) before the dev-token endpoint will work:
```
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## FIX C-02 — Sensitive Alpaca GET routes now require auth ✅

**File:** `backend/routes/alpaca.py`

**What changed:**
- Added `from auth import require_api_key` import
- Added `_: bool = Depends(require_api_key)` to:
  - `GET /api/alpaca/account`
  - `GET /api/alpaca/positions`
  - `GET /api/alpaca/orders`

**Also added to `backend/auth.py`:** new exported `require_api_key()` function — identical
to `_require_admin_auth` in admin.py but lives in auth.py for reuse. Unlike `verify_api_key`,
it checks ALL HTTP methods (no PROTECTED_METHODS skip), making it correct for GET routes.

---

## FIX C-03 — Weak dev API key documented ✅

**File:** `backend/.env`

**What changed:**
- Added comment above `API_SECRET_KEY=dev-local-testing-key`:
  ```
  # CHANGE THIS IN PRODUCTION — generate with: python3 -c "import secrets; print(secrets.token_hex(32))"
  ```
- The dev key value itself was not changed (live local dev credential)

**Note:** `auth.py` already fails closed (503) when `API_SECRET_KEY` is empty,
so misconfigured prod deployments are already caught.

---

## FIX H-02 — Broken prod Docker build fixed ✅

**File:** `Dockerfile.backend`

**Root cause:** `docker-compose.prod.yml` specified `target: production` but the
Dockerfile had no named stage.

**Fix:** Added `AS production` to the base image line:
```dockerfile
FROM python:3.11-slim AS production
```

The existing single-stage build is already production-hardened (non-root user,
healthcheck, warning-level logging). No new stage was needed — just a name.

---

## FIX H-03 — GET /api/errors/summary now requires auth ✅

**File:** `backend/routes/admin.py`

**What changed:**
- Added `_: bool = Depends(_require_admin_auth)` to `errors_summary()`:
  ```python
  @router.get("/errors/summary")
  async def errors_summary(_: bool = Depends(_require_admin_auth)):
  ```

The `_require_admin_auth` dependency was already defined in the same file and used
on all other admin GET routes — `errors/summary` was the only one that missed it.

---

## FIX H-04 — Grafana hardcoded admin password removed ✅

**Files:** `docker-compose.observability.yml`, `docker-compose.prod.yml`, root `.env`

**What changed:**

`docker-compose.observability.yml` (was fully hardcoded):
```yaml
# Before
- GF_SECURITY_ADMIN_PASSWORD=admin
# After
- GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:-admin}
```

`docker-compose.prod.yml` (was using wrong var name `GRAFANA_PASSWORD`):
```yaml
# Before
- GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD:-admin}
# After
- GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:-admin}
```

Root `.env` — added placeholder:
```
# Grafana admin password — CHANGE THIS IN PRODUCTION
GRAFANA_ADMIN_PASSWORD=
```

**Action required:** Set `GRAFANA_ADMIN_PASSWORD` in the root `.env` (and in production
secrets) before deploying observability stack:
```
python3 -c "import secrets; print(secrets.token_hex(16))"
```

---

## Verification commands

```bash
# C-01: hardcoded secret gone
grep -n "floww-dev-secret" backend/routes/alphapod_compat.py
# → should print nothing

# C-01: env var pattern present
grep -n "JWT_SECRET_KEY" backend/routes/alphapod_compat.py backend/.env

# C-02: auth on Alpaca GET routes
grep -n "require_api_key\|Depends" backend/routes/alpaca.py

# H-03: auth on errors/summary
grep -n "errors/summary" backend/routes/admin.py

# H-02: Dockerfile stage name
head -1 Dockerfile.backend

# H-04: Grafana env var
grep "GF_SECURITY_ADMIN_PASSWORD" docker-compose.observability.yml docker-compose.prod.yml
```

---

## Files changed summary

| File | Fix |
|------|-----|
| `backend/routes/alphapod_compat.py` | C-01: env-var JWT secret, fail-loud on missing |
| `backend/auth.py` | C-02: added `require_api_key()` exported function |
| `backend/routes/alpaca.py` | C-02: `Depends(require_api_key)` on 3 GET routes |
| `backend/routes/admin.py` | H-03: `Depends(_require_admin_auth)` on errors/summary |
| `backend/.env` | C-01+C-03: JWT_SECRET_KEY placeholder, API key comment |
| `Dockerfile.backend` | H-02: `AS production` stage name added |
| `docker-compose.observability.yml` | H-04: Grafana password reads from env |
| `docker-compose.prod.yml` | H-04: aligned to GRAFANA_ADMIN_PASSWORD var name |
| `.env` (root) | H-04: GRAFANA_ADMIN_PASSWORD placeholder added |
