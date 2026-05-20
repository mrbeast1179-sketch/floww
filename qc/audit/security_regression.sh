#!/usr/bin/env bash
# qc/audit/security_regression.sh
# Regression tests for CRITICAL security findings.
# Run after any security fix to verify the fix holds.
set -euo pipefail

PASS=0
FAIL=0

check() {
    local label="$1"
    shift
    if "$@" &>/dev/null; then
        echo "  PASS: $label"
        ((PASS++))
    else
        echo "  FAIL: $label"
        ((FAIL++))
    fi
}

check_not() {
    local label="$1"
    shift
    if "$@" &>/dev/null; then
        echo "  FAIL: $label (expected failure but succeeded)"
        ((FAIL++))
    else
        echo "  PASS: $label"
        ((PASS++))
    fi
}

echo "=== Security Regression Tests ==="

# C-01: .env file permissions must be 0600 or more restrictive
echo ""
echo "--- C-01: .env file permissions ---"
ENV_PERMS=$(stat -f "%Lp" /Users/nav/Documents/GitHub/floww/backend/.env 2>/dev/null || echo "000")
if [ "$ENV_PERMS" != "000" ]; then
    check ".env permissions are 0600" test "$ENV_PERMS" = "600"
else
    echo "  SKIP: .env not found"
fi

# C-02: Auth must fail closed when API_SECRET_KEY is unset
echo ""
echo "--- C-02: Auth fail-closed ---"
# Check that auth.py does NOT have the "if not expected_key: return True" bypass
# After fix, it should either raise an error or not have that code path
if grep -q "if not expected_key" /Users/nav/Documents/GitHub/floww/backend/auth.py 2>/dev/null; then
    echo "  FAIL: auth.py still has 'if not expected_key' bypass"
    ((FAIL++))
else
    echo "  PASS: auth.py does not have open bypass"
    ((PASS++))
fi

# C-03: WebSocket endpoints must require auth
echo ""
echo "--- C-03: WebSocket auth ---"
# Check that WS endpoints have auth check before accept()
WS_AUTH=$(grep -A5 "websocket_endpoint\|websocket_gex" /Users/nav/Documents/GitHub/floww/backend/server.py | grep -c "token\|auth\|api_key\|close(code=" 2>/dev/null || echo "0")
if [ "$WS_AUTH" -gt 0 ]; then
    echo "  PASS: WebSocket endpoints have auth check"
    ((PASS++))
else
    echo "  FAIL: WebSocket endpoints have no auth check"
    ((FAIL++))
fi

# C-04: Dash UI must have access control
echo ""
echo "--- C-04: Dash UI access control ---"
if grep -q "dash_auth\|DASH_SESSION\|dashboard.*auth\|dashboard.*token" /Users/nav/Documents/GitHub/floww/backend/server.py 2>/dev/null; then
    echo "  PASS: Dash UI has access control"
    ((PASS++))
else
    echo "  FAIL: Dash UI has no access control"
    ((FAIL++))
fi

# C-05: CORS must not default to wildcard in production
echo ""
echo "--- C-05: CORS no wildcard default ---"
if grep -q 'CORS_ORIGINS.*\\*' /Users/nav/Documents/GitHub/floww/backend/server.py 2>/dev/null; then
    # Check if there's a guard that prevents startup without explicit origins
    if grep -q "CORS_ORIGINS.*raise\|CORS_ORIGINS.*RuntimeError\|CORS_ORIGINS.*required" /Users/nav/Documents/GitHub/floww/backend/server.py 2>/dev/null; then
        echo "  PASS: CORS has production guard"
        ((PASS++))
    else
        echo "  FAIL: CORS defaults to wildcard without guard"
        ((FAIL++))
    fi
else
    echo "  PASS: CORS does not default to wildcard"
    ((PASS++))
fi

# H-03: POST routes should use Pydantic models (not Dict[str, Any])
echo ""
echo "--- H-03: POST routes use Pydantic models ---"
RAW_DICT_ROUTES=$(grep -c "Dict\[str, Any\]" /Users/nav/Documents/GitHub/floww/backend/routes/*.py 2>/dev/null || echo "0")
if [ "$RAW_DICT_ROUTES" -eq 0 ]; then
    echo "  PASS: No routes accept raw Dict[str, Any]"
    ((PASS++))
else
    echo "  FAIL: $RAW_DICT_ROUTES route(s) still accept raw Dict[str, Any]"
    ((FAIL++))
fi

# H-06: pymongo version
echo ""
echo "--- H-06: pymongo version ---"
PYMONGO_VER=$(/Users/nav/Documents/GitHub/floww/backend/.venv/bin/python -c "import pymongo; print(pymongo.__version__)" 2>/dev/null || echo "0.0.0")
check "pymongo >= 4.6.3" /Users/nav/Documents/GitHub/floww/backend/.venv/bin/python -c "
from packaging.version import Version
import pymongo
assert Version(pymongo.__version__) >= Version('4.6.3'), f'pymongo {pymongo.__version__} < 4.6.3'
" 2>/dev/null || true

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
    echo "SECURITY REGRESSION FAILED"
    exit 1
fi
echo "SECURITY REGRESSION PASSED"
exit 0
