#!/usr/bin/env bash
# deploy/free/smoke.sh — post-deploy verification. Run on the server (or any
# box that can reach the domain). Exits non-zero on first failure.
#
# Usage: DOMAIN=confluencedecoder.duckdns.org bash deploy/free/smoke.sh

set -euo pipefail
DOMAIN="${DOMAIN:?set DOMAIN=your.domain}"
SCHEME="${SCHEME:-https}"
BASE="${SCHEME}://${DOMAIN}"
# -k when hitting a self-signed local stack: CURL_OPTS="-k"
CURL_OPTS="${CURL_OPTS:-}"

pass=0; fail=0
# Cold-start tolerance: the first /health hit after `docker compose up` may
# land while uvicorn is still importing pandas/numba and JIT-compiling
# (numba @njit first-call compilation alone can take 30-60s+). Wait for
# liveness before running checks, and give every request a generous cap so a
# slow cold endpoint fails with 000 rather than hanging forever.
echo "── Waiting for backend warm-up (numba JIT cold start can take ~90s) ──"
for i in $(seq 1 18); do   # up to ~3 minutes
    code=$(curl $CURL_OPTS -s -o /dev/null -w '%{http_code}' --max-time 120 "${BASE}/health" || echo 000)
    if [ "$code" = "200" ]; then echo "  ok   warm-up -> 200 (attempt ${i})"; break; fi
    echo "  ...  attempt ${i}: ${code}; retrying in 10s"; sleep 10
done

check() { # check <name> <url> <expect_code>
    local name="$1" url="$2" expect="$3" got
    got=$(curl $CURL_OPTS -s -o /dev/null -w '%{http_code}' --max-time 120 "$url" || echo 000)
    if [ "$got" = "$expect" ]; then
        echo "  ok   $name -> $got"; pass=$((pass+1))
    else
        echo "  FAIL $name -> $got (want $expect)  $url"; fail=$((fail+1))
    fi
}

echo "── Smoke: ${DOMAIN} ──"
check "liveness /health"        "${BASE}/health"            200
check "deep health"             "${BASE}/api/health"        200
check "SPA index"               "${BASE}/"                  200
check "SPA deep link"           "${BASE}/flowseeker"        200
check "briefing SPY"            "${BASE}/api/briefing/SPY"  200

# Content sanity, not just status codes
spot=$(curl $CURL_OPTS -sf --max-time 60 "${BASE}/api/briefing/SPY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
m = d.get('metrics') or {}
v = d.get('spot') or d.get('price') or m.get('spot') or m.get('price') or ''
print(v)" 2>/dev/null || true)
if [ -n "$spot" ]; then
    echo "  ok   briefing SPY spot=${spot}"; pass=$((pass+1))
else
    echo "  WARN briefing SPY returned no spot field (data provider may be rate-limited)"
fi

echo ""
echo "passed=${pass} failed=${fail}"
[ "$fail" -eq 0 ]
