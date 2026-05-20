# NEXT_TASKS.md

## Security Audit Complete (2026-07-09)

### CRITICAL Findings (5 — must fix before live trading):
1. C-01: .env file permissions 644 → 600
2. C-02: Auth bypass when API_SECRET_KEY unset — fail closed
3. C-03: WebSocket endpoints unauthenticated — add token auth
4. C-04: Dash UI /dashboard/ no access control — add auth
5. C-05: CORS defaults to wildcard — enforce explicit origins

### HIGH Findings (6):
1. H-01: Middleware ordering — move CORS add_middleware before routes
2. H-02: Rate limiter trusts spoofable IP — document or use Redis
3. H-03: POST routes accept Dict[str, Any] — add Pydantic models
4. H-04: Schwab token file path validation — ensure dir permissions
5. H-05: No CSRF protection — add SameSite cookies + Origin validation
6. H-06: pymongo 4.5.0 CVE — upgrade to 4.6.3

### Immediate Next Steps:
1. Fix all 5 CRITICAL findings
2. Run `bash qc/audit/security_regression.sh` to verify
3. Run `bash qc/audit/truth_audit.sh` to confirm no regressions
4. Re-run security audit to confirm all CRITICAL resolved
5. Unblock live-trading switch
