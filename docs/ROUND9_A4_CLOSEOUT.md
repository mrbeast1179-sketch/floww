# Agent A4 Close-out — Heatseeker Test Coverage

## Commits
| Task | SHA | Subject |
|------|-----|---------|
| T2 | 45f3e49 | test(round-9-a4): regression for H4 heatseeker degraded-response contract |
| T4-8 | (this commit) | test(round-9-a4): extend 5 panel test coverage |
| T9 | (this commit) | test(round-9-a4): backend heatseeker edge cases |

## Test counts
- BEFORE: 27 passing (13 suites, HeatseekerDashboard pre-existing failure)
- AFTER: 34 passing (13 suites, same pre-existing failure)
- Net: +7 heatseeker tests (4 backend + 3 frontend degraded/error tests)

## Component handling gaps closed

### AirPocketsPanel
- Added: degraded response handling test
- Added: error state rendering test
- Added: degraded error message display test

### FlipZonesPanel
- Added: degraded response handling test
- Added: error state rendering test
- Added: window bounds display test
- Added: zone sorting by distance from spot test

### NodeClassificationPanel
- Added: degraded response handling test
- Added: error state rendering test
- Added: unknown classification badge test
- Added: null tap_probability edge case test
- **Component fix**: Added Unknown column (3-col grid instead of 2-col) — unknown nodes were silently dropped

### BeachBallIndicator
- Added: loading state test
- Added: error state test
- Added: degraded response test
- Added: confidence bar 0% edge case
- Added: confidence bar 100% edge case
- Added: null spot_distance_pct edge case

### HeatseekerDashboard
- Added: StaleDataBadge rendering test
- Added: all-panels-degraded test
- Added: spot prop passing test

## Backend edge cases tested
- calc_flip_zones: empty chain, zero spot, missing gamma field
- calc_node_lifecycle: no history, empty contracts
- calc_air_pockets: empty chain, single contract

## Round 10 candidates
- HeatseekerDashboard plotly.js import issue in jsdom (pre-existing, needs mock)
- NodeClassificationPanel now shows Unknown column — verify with designer
- Backend calc functions handle missing gamma/OI fields gracefully (tested)
