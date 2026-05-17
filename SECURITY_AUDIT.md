# SECURITY AUDIT REPORT — Confluence Decoder
## Date: 2026-05-17

## CRITICAL FIXES APPLIED

### 1. ✅ .env File Removed from Git History
- **Issue**: backend/.env was tracked in git, exposing all API keys
- **Fix**: Used git-filter-repo to remove .env from entire history
- **Status**: Fixed and force-pushed

### 2. ✅ CORS Configuration
- **Status**: Properly configured with `allow_credentials=False`
- **Origin**: Uses `CORS_ORIGINS` env var, defaults to `*` (should be restricted in production)

### 3. ✅ Authentication Middleware
- **Status**: X-API-Key header required for mutating routes
- **Public paths**: Health, data, chain, spot, advanced are public
- **Protected paths**: Portfolio, alerts, paper trading, memory, ML training

### 4. ✅ Rate Limiting
- **Status**: Deque-based sliding window with exponential backoff
- **Limit**: 60 requests/minute per IP (configurable)
- **Response**: 429 with Retry-After header

### 5. ✅ Input Validation
- **Status**: All endpoints use Pydantic models or Query parameters
- **MongoDB**: All queries use parameterized inputs (no string concatenation)

### 6. ✅ Secrets Management
- **Status**: All API keys read from environment variables
- **No hardcoded secrets** in any Python or JS files
- **Alpaca client**: Reads from ALPACA_API_KEY and ALPACA_SECRET_KEY env vars

## REMAINING RECOMMENDATIONS

### High Priority
1. **Restrict CORS origins** in production (currently defaults to `*`)
2. **Add security headers** (HSTS, X-Frame-Options, CSP)
3. **Add CSRF tokens** for state-changing operations
4. **Add request signing** for sensitive operations
5. **Rotate all API keys** that were exposed in git history

### Medium Priority
1. **Add audit logging** for all data modifications
2. **Add IP allowlisting** for admin endpoints
3. **Add API versioning** (/api/v1/ prefix)
4. **Add dependency vulnerability scanning** (safety, pip-audit)
5. **Add Content Security Policy** headers

### Low Priority
1. **Add security.txt** file
2. **Add robots.txt** to prevent crawling
3. **Add rate limiting per-user** (not just per-IP)
4. **Add request size limits**
5. **Add timeout configuration** for all external API calls