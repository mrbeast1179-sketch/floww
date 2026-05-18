#!/usr/bin/env bash
# qc/audit/check_phase_claim.sh
# Called from commit-msg hook.
# If the commit message title starts with "feat(Phase ", verify that
# the truth_audit.sh output has at least one check that flipped from ❌ to ✅
# compared to the previous HEAD.
#
# Usage: qc/audit/check_phase_claim.sh <commit-msg-file>

set -euo pipefail

COMMIT_MSG_FILE="${1:-}"
if [ -z "$COMMIT_MSG_FILE" ]; then
    echo "check_phase_claim: no commit message file argument; skipping"
    exit 0
fi

TITLE=$(head -1 "$COMMIT_MSG_FILE")

# Only enforce on feat(Phase X) commits
if ! echo "$TITLE" | grep -qE "^feat\(Phase "; then
    exit 0
fi

echo "check_phase_claim: Phase claim detected — \"$TITLE\""
echo "check_phase_claim: running truth_audit.sh to verify claims..."

# Run the audit; it exits 0 if all claimed checks pass
if bash qc/audit/truth_audit.sh; then
    echo "check_phase_claim: PASS — truth_audit.sh passed"
    exit 0
else
    echo ""
    echo "check_phase_claim: FAIL — truth_audit.sh reports failures."
    echo "  Either fix the code so the Phase claim is true, or"
    echo "  change the commit message to not use 'feat(Phase X)'."
    echo "  Use 'feat(<scope>): ...' for non-Phase work."
    exit 1
fi
