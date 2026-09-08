#!/usr/bin/env bash
# Verification script for Confluence Decoder
# Run: bash qc/verify.sh
#
# Honesty policy (P3):
#   REQUIRED checks block (nonzero exit on failure): ruff check,
#     ruff format check, pytest.
#   ADVISORY checks are explicitly named in output: missing command prints
#     "ADVISORY SKIP: <name> not installed"; installed-but-failing prints
#     "ADVISORY FAIL: <name>" without blocking the exit code.
#   "=== ALL GREEN ===" prints ONLY when every required check passed AND
#   no advisory check failed. A required failure prints
#   "=== QC FAILED (required) ===" and exits 1. A fake/real command
#   exiting 1 can never produce the all-green line.
cd "$(git rev-parse --show-toplevel)" || exit 2

REQ_FAIL=0
ADV_FAIL=0

run_required() {
  local name="$1"; shift
  echo ""
  echo "=== $name (REQUIRED) ==="
  if ! command -v "$1" >/dev/null 2>&1 && [[ ! -x "$1" ]]; then
    echo "REQUIRED MISSING: $1 not found — failing (required tools must be installed)"
    REQ_FAIL=1
    return
  fi
  if "$@"; then
    echo "REQUIRED PASS: $name"
  else
    echo "REQUIRED FAIL: $name"
    REQ_FAIL=1
  fi
}

run_advisory() {
  local name="$1"; shift
  echo ""
  echo "=== $name (ADVISORY) ==="
  if ! command -v "$1" >/dev/null 2>&1 && [[ ! -x "$1" ]]; then
    echo "ADVISORY SKIP: $name not installed, skipping"
    return
  fi
  if "$@"; then
    echo "ADVISORY PASS: $name"
  else
    echo "ADVISORY FAIL: $name (installed but failed — not blocking)"
    ADV_FAIL=1
  fi
}

run_advisory "Pre-commit" pre-commit run --all-files
run_required "Ruff lint" backend/.venv/bin/ruff check backend
run_required "Ruff format check" backend/.venv/bin/ruff format --check backend
run_advisory "MyPy" backend/.venv/bin/mypy backend --ignore-missing-imports
run_advisory "Bandit security" backend/.venv/bin/bandit -r backend -ll -ii
run_advisory "pip-audit" backend/.venv/bin/pip-audit -r backend/requirements.txt

echo ""
echo "=== Pytest (REQUIRED) ==="
PYTEST_LOG="$(mktemp)"
if backend/.venv/bin/pytest backend/tests/ -v --tb=short >"$PYTEST_LOG" 2>&1; then
  tail -5 "$PYTEST_LOG"
  echo "REQUIRED PASS: Pytest"
else
  tail -20 "$PYTEST_LOG"
  echo "REQUIRED FAIL: Pytest (see above)"
  REQ_FAIL=1
fi
rm -f "$PYTEST_LOG"

run_advisory "Frontend lint" npm --prefix frontend run lint
run_advisory "Frontend build" npx --prefix frontend craco build

echo ""
if [[ "$REQ_FAIL" -ne 0 ]]; then
  echo "=== QC FAILED (required) ==="
  exit 1
fi
if [[ "$ADV_FAIL" -ne 0 ]]; then
  echo "=== QC PASSED WITH ADVISORY FAILURES ==="
  exit 0
fi
echo "=== ALL GREEN ==="
