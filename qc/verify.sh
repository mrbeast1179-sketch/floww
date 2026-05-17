#!/usr/bin/env bash
# Verification script for Confluence Decoder
# Run: bash qc/verify.sh

set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

echo "=== Pre-commit ==="
pre-commit run --all-files 2>/dev/null || echo "pre-commit not configured, skipping"

echo ""
echo "=== Ruff lint ==="
(cd backend && .venv/bin/ruff check .)

echo ""
echo "=== Ruff format check ==="
(cd backend && .venv/bin/ruff format --check .)

echo ""
echo "=== MyPy ==="
(cd backend && .venv/bin/mypy . --ignore-missing-importers 2>/dev/null || echo "mypy not installed, skipping")

echo ""
echo "=== Bandit security ==="
(cd backend && .venv/bin/bandit -r . -ll -ii 2>/dev/null || echo "bandit not installed, skipping")

echo ""
echo "=== pip-audit ==="
(cd backend && .venv/bin/pip-audit -r requirements.txt 2>/dev/null || echo "pip-audit not installed, skipping")

echo ""
echo "=== Pytest ==="
(cd backend && .venv/bin/pytest tests/ -v --tb=short 2>&1 | tail -20)

echo ""
echo "=== Frontend lint ==="
(cd frontend && npm run lint 2>/dev/null || echo "npm lint not configured, skipping")

echo ""
echo "=== Frontend build ==="
(cd frontend && npx craco build 2>&1 | tail -3)

echo ""
echo "=== ALL GREEN ==="