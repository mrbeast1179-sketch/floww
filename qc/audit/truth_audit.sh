#!/usr/bin/env bash
# qc/audit/truth_audit.sh
# Verifies that the latest commit's claims match actual code state.
# Returns 0 if claims match, 1 if they don't.
# Designed to run in CI (no interactive input).

set -u

# Note (2026-05-18): `set -euo pipefail` was previously in effect but caused
# the audit to silently exit early. `grep -rn ... | grep -v ... | wc -l`
# inside a command substitution returns non-zero when the grep finds nothing,
# and with pipefail+errexit that aborted the script before any check could
# run — the audit was "passing" by never finishing. With just `set -u`, all
# rules execute and the exit code reflects real findings.

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

PASS=0
FAIL=0
WARN=0

check() {
    local description="$1"
    local result="$2"  # "pass" or "fail"
    if [ "$result" = "pass" ]; then
        echo "  PASS: $description"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $description"
        FAIL=$((FAIL + 1))
    fi
}

# warn() surfaces a rule violation visibly without failing the audit. Use it
# for rules that flag legacy artifacts already on disk that the project
# intends to clean up. Promote specific warn() calls to check(..., "fail")
# once the legacy cohort is resolved.
warn() {
    local description="$1"
    echo "  WARN: $description"
    WARN=$((WARN + 1))
}

# Get the latest commit message
COMMIT_MSG=$(git log -1 --pretty=%B 2>/dev/null || echo "")
if [ -z "$COMMIT_MSG" ]; then
    echo "truth_audit: no commits found, skipping"
    exit 0
fi

echo "=== Truth Audit ==="
echo "Commit: $(git log -1 --oneline)"
echo "Message: $(echo "$COMMIT_MSG" | head -1)"
echo ""

# --- Rule 1: No synthetic data in any commit touching ML ---
if echo "$COMMIT_MSG" | grep -qiE "ml|model|train|synthetic|data.*gen"; then
    SYNTHETIC_REFS=$(grep -rn "np\.random\." backend/ml*.py 2>/dev/null | grep -v "__pycache__" | wc -l)
    if [ "$SYNTHETIC_REFS" -gt 0 ]; then
        check "ML commit must not contain np.random data generation" "fail"
        grep -rn "np\.random\." backend/ml*.py 2>/dev/null | head -5
    else
        check "ML commit contains no np.random data generation" "pass"
    fi
fi

# --- Rule 2: If commit claims "refactor", server.py must not have grown ---
if echo "$COMMIT_MSG" | grep -qiE "refactor|Phase A"; then
    SERVER_LINES=$(wc -l < backend/server.py 2>/dev/null || echo 0)
    if [ "$SERVER_LINES" -gt 3532 ]; then
        check "Refactor commit: server.py must not grow (currently $SERVER_LINES lines, baseline 3532)" "fail"
    else
        check "Refactor commit: server.py did not grow ($SERVER_LINES lines)" "pass"
    fi
fi

# --- Rule 3: If commit claims VEX/DEX/Vega, grep must find it ---
if echo "$COMMIT_MSG" | grep -qiE "vex|vanna.*exposure|calc_vex"; then
    if grep -rn "def calc_vex" backend/ 2>/dev/null | grep -v "__pycache__" | grep -q .; then
        check "VEX commit: def calc_vex found in codebase" "pass"
    else
        check "VEX commit: def calc_vex NOT found in codebase" "fail"
    fi
fi

if echo "$COMMIT_MSG" | grep -qiE "dex|delta.*exposure|calc_dex"; then
    if grep -rn "def calc_dex" backend/ 2>/dev/null | grep -v "__pycache__" | grep -q .; then
        check "DEX commit: def calc_dex found in codebase" "pass"
    else
        check "DEX commit: def calc_dex NOT found in codebase" "fail"
    fi
fi

if echo "$COMMIT_MSG" | grep -qiE "vega.*total|total.*vega|calc_vega_total"; then
    if grep -rn "def calc_vega_total" backend/ 2>/dev/null | grep -v "__pycache__" | grep -q .; then
        check "Vega-Total commit: def calc_vega_total found in codebase" "pass"
    else
        check "Vega-Total commit: def calc_vega_total NOT found in codebase" "fail"
    fi
fi

# --- Rule 4: If commit claims "quarantine", models must be in _quarantine/ ---
if echo "$COMMIT_MSG" | grep -qiE "quarantine|degenerate"; then
    QUARANTINE_COUNT=$(ls models/_quarantine/*.joblib 2>/dev/null | wc -l)
    LIVE_COUNT=$(ls models/*.joblib 2>/dev/null | wc -l)
    if [ "$QUARANTINE_COUNT" -gt 0 ] && [ "$LIVE_COUNT" -eq 0 ]; then
        check "Quarantine commit: models in _quarantine/ ($QUARANTINE_COUNT files), none in models/" "pass"
    else
        check "Quarantine commit: expected models in _quarantine/, found $QUARANTINE_COUNT quarantined, $LIVE_COUNT live" "fail"
    fi
fi

# --- Rule 5: If commit claims "ML" or "model", DegenerateModelError must exist ---
if echo "$COMMIT_MSG" | grep -qiE "ml|model.*guard|degenerate|training.*guard"; then
    if grep -rn "class DegenerateModelError\|DegenerateModelError" backend/ml_pipeline.py 2>/dev/null | grep -q .; then
        check "ML guard commit: DegenerateModelError found in ml_pipeline.py" "pass"
    else
        check "ML guard commit: DegenerateModelError NOT found in ml_pipeline.py" "fail"
    fi
fi

# --- Rule 6: If commit claims "CI" or "audit", truth_audit.sh must exist and be executable ---
if echo "$COMMIT_MSG" | grep -qiE "ci|audit|hook|pre-commit"; then
    if [ -x "qc/audit/truth_audit.sh" ]; then
        check "CI commit: qc/audit/truth_audit.sh exists and is executable" "pass"
    else
        check "CI commit: qc/audit/truth_audit.sh missing or not executable" "fail"
    fi
fi

# --- Rule 7: If commit claims "MongoDB" or "load", verify pymongo/motor imports ---
if echo "$COMMIT_MSG" | grep -qiE "mongo|load.*dataset|backfill"; then
    if grep -rn "motor\|pymongo\|MongoClient" scripts/*.py backend/scripts/*.py 2>/dev/null | grep -q .; then
        check "MongoDB commit: motor/pymongo imports found" "pass"
    else
        check "MongoDB commit: motor/pymongo imports NOT found" "fail"
    fi
fi

# --- Rule 8: Universal — no .env file in repo ---
if [ -f ".env" ] && [ -z "$(git check-ignore .env 2>/dev/null)" ]; then
    check ".env file is git-ignored" "fail"
else
    check ".env file is git-ignored or absent" "pass"
fi

# --- Rule 9: Universal (WARN) — no live model has Sharpe > MAX_PLAUSIBLE ---
# Catches "model shipped without the gate" scenarios at the artifact level.
# Currently a warning so legacy artifacts surface without blocking CI.
# Promote to check(..., "fail") once flagged models are quarantined.
MAX_PLAUSIBLE_DAILY_SHARPE=10
SUSPECT_META_FILES=""
for meta in models/*_meta_v*.json; do
    [ -f "$meta" ] || continue
    sharpe=$(python3 -c "
import json
try:
    d = json.load(open('$meta'))
    print(d.get('sharpe', 0))
except Exception:
    print(0)
" 2>/dev/null)
    flag=$(python3 -c "print('1' if float('$sharpe') > $MAX_PLAUSIBLE_DAILY_SHARPE else '0')" 2>/dev/null)
    if [ "$flag" = "1" ]; then
        SUSPECT_META_FILES="$SUSPECT_META_FILES $meta(sharpe=$sharpe)"
    fi
done
if [ -n "$SUSPECT_META_FILES" ]; then
    warn "live model with Sharpe > $MAX_PLAUSIBLE_DAILY_SHARPE (likely in-sample):$SUSPECT_META_FILES"
else
    check "Universal: no live model has Sharpe > $MAX_PLAUSIBLE_DAILY_SHARPE" "pass"
fi

# --- Rule 10: Universal (WARN) — no SHIPped training report has empty baselines ---
# The empty-baselines + SHIP combo was the smoking gun for the prior auto-pass bug.
# Currently a warning so 12+ legacy reports surface without blocking CI.
BAD_REPORTS=""
for report in reports/training_*.json; do
    [ -f "$report" ] || continue
    is_bad=$(python3 -c "
import json
try:
    d = json.load(open('$report'))
    bad = d.get('verdict', '') == 'SHIP' and d.get('baselines', None) == {}
    print('1' if bad else '0')
except Exception:
    print('0')
" 2>/dev/null)
    if [ "$is_bad" = "1" ]; then
        BAD_REPORTS="$BAD_REPORTS $(basename $report)"
    fi
done
if [ -n "$BAD_REPORTS" ]; then
    warn "training report with verdict=SHIP and baselines={} (auto-pass bug):$BAD_REPORTS"
else
    check "Universal: no SHIPped training report has empty baselines" "pass"
fi

# --- Summary ---
echo ""
if [ "$WARN" -gt 0 ]; then
    echo "=== Results: $PASS passed, $FAIL failed, $WARN warnings ==="
else
    echo "=== Results: $PASS passed, $FAIL failed ==="
fi

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "TRUTH AUDIT FAILED — commit claims do not match code state."
    echo "Fix the issues above, or update the commit message to match reality."
    exit 1
fi

if [ "$WARN" -gt 0 ]; then
    echo "TRUTH AUDIT PASSED with $WARN warnings — see notes above."
else
    echo "TRUTH AUDIT PASSED — all claims verified."
fi
exit 0
