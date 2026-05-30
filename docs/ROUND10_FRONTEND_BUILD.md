# Round 10 Frontend Build + Jest Sweep Results

**Date:** 2026-05-29  
**Build command:** `npx craco build`  
**Test command:** `CI=true npx craco test --watchAll=false --passWithNoTests`

## Build Status

✅ **BUILD PASSED** — Compiled successfully.

### Bundle Sizes (gzip)

| File | Size |
|------|------|
| main.js | 1.51 MB |
| main.css | 14.62 kB |

### Bundle Size Check

Main bundle is **1.51 MB** — well under the 5 MB threshold. No lazy-loading ticket needed.

## Jest Test Results

| Metric | Count |
|--------|-------|
| Test Suites | 26 passed, 2 failed, 28 total |
| Tests | 104 passed, 10 failed, 114 total |

### Failed Tests (10 total, all pre-existing)

All 10 failures originate from `src/components/VannaChart.jsx` — a `TypeError: window.URL.createObjectURL is not a function` triggered during `react-plotly.js` loading. This is a **JSDOM compatibility issue** with react-plotly.js, not related to Round 10 changes.

**Recommendation:** These test failures are pre-existing and unrelated to R10. Fix by adding a `createObjectURL` polyfill in `setupTests.js` or mocking `react-plotly.js` entirely.

### Passing Test Files (26)

All 26 remaining test suites pass. No regressions from Round 10.

## Summary

- ✅ Build: Clean compilation, 1.51 MB main bundle
- ✅ Tests: 104/114 passing (91%)
- ⚠️ 10 pre-existing failures (react-plotly.js / JSDOM, not R10)
- ✅ No R10 regressions detected
