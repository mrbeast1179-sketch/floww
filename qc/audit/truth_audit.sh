#!/usr/bin/env bash
# qc/audit/truth_audit.sh
# Verifies that the latest commit's claims match actual code state.
# Returns 0 if claims match, 1 if they don't.
# Designed to run in CI (no interactive input).

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

PASS=0
FAIL=0

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
    SYNTHETIC_REFS=$(grep -rn "np\.random\." backend/ml*.py 2>/dev/null | grep -v "__pycache__" | wc -l || true)
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
if echo "$COMMIT_MSG" | grep -qiE "ml|model.*guard|degenerate|training.*guard|quality.*gate" && ! echo "$COMMIT_MSG" | grep -qiE "model.*path|model.*naming|model.*file"; then
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

# --- Rule 9: Model audit — no model with Sharpe > 5 or empty baselines ---
# Check all model meta JSON files for suspicious claims
for meta in models/*_meta_*.json; do
    [ -f "$meta" ] || continue
    # Skip quarantined models
    [[ "$meta" == *"_quarantine"* ]] && continue
    # Check for empty baselines
    if grep -q '"baselines": {}' "$meta" 2>/dev/null; then
        check "Model $meta: empty baselines dict (unverified)" "fail"
    else
        check "Model $meta: baselines present" "pass"
    fi
    # Check for Sharpe > 5 (suspicious for daily direction)
    sharpe=$(python3 -c "import json; d=json.load(open('$meta')); print(d.get('sharpe', 0))" 2>/dev/null || echo 0)
    if [ "$(echo "$sharpe > 5" | bc -l 2>/dev/null || echo 0)" -eq 1 ]; then
        check "Model $meta: Sharpe $sharpe > 5 (suspicious)" "fail"
    else
        check "Model $meta: Sharpe $sharpe (reasonable)" "pass"
    fi
done

# --- Rule 10: No model trained on too few samples ---
# Flag models with fewer than 50 training samples
for meta in models/*_meta_*.json; do
    [ -f "$meta" ] || continue
    [[ "$meta" == *"_quarantine"* ]] && continue
    n_samples=$(python3 -c "import json; d=json.load(open('$meta')); print(d.get('n_samples', 0))" 2>/dev/null || echo 0)
    if [ "$n_samples" -lt 50 ] 2>/dev/null; then
        check "Model $meta: only $n_samples training samples (suspicious)" "fail"
    else
        check "Model $meta: $n_samples training samples (ok)" "pass"
    fi
done

# --- Rule 11: Feature-to-sample ratio check ---
# Flag models with more features than 20% of samples
for meta in models/*_meta_*.json; do
    [ -f "$meta" ] || continue
    [[ "$meta" == *"_quarantine"* ]] && continue
    n_samples=$(python3 -c "import json; d=json.load(open('$meta')); print(d.get('n_samples', 0))" 2>/dev/null || echo 0)
    n_features=$(python3 -c "import json; d=json.load(open('$meta')); print(d.get('n_features_used', d.get('n_features', 0)))" 2>/dev/null || echo 0)
    if [ "$n_samples" -gt 0 ] 2>/dev/null && [ "$n_features" -gt 0 ] 2>/dev/null; then
        ratio=$(python3 -c "print($n_features / $n_samples)" 2>/dev/null || echo 0)
        if [ "$(echo "$ratio > 0.2" | bc -l 2>/dev/null || echo 0)" -eq 1 ]; then
            check "Model $meta: feature/sample ratio $ratio > 0.2 ($n_features features / $n_samples samples)" "fail"
        else
            check "Model $meta: feature/sample ratio $ratio (ok)" "pass"
        fi
    fi
done

# --- Rule 12: No model with accuracy > 95% on daily direction ---
# Daily direction prediction > 95% is almost certainly overfit
for meta in models/*_meta_*.json; do
    [ -f "$meta" ] || continue
    [[ "$meta" == *"_quarantine"* ]] && continue
    acc=$(python3 -c "import json; d=json.load(open('$meta')); print(d.get('metrics', {}).get('accuracy', d.get('accuracy', 0)))" 2>/dev/null || echo 0)
    if [ "$(echo "$acc > 0.95" | bc -l 2>/dev/null || echo 0)" -eq 1 ]; then
        check "Model $meta: accuracy $acc > 0.95 (likely overfit)" "fail"
    else
        check "Model $meta: accuracy $acc (reasonable)" "pass"
    fi
done

# --- Summary ---
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "TRUTH AUDIT FAILED — commit claims do not match code state."
    echo "Fix the issues above, or update the commit message to match reality."
    exit 1
fi

echo "TRUTH AUDIT PASSED — all claims verified."
exit 0
