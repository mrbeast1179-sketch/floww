# Integration Checklist — Phase 9 Academy Flow Build

**Created:** 2026-09-03 · **Agent:** 1 (Architect) · **Branch:** phase9/agent1-architect

## Purpose

This checklist verifies that all Phase 9 integration points between agents work correctly. Each integration point has a verification method and expected state. Agent 1 (or a designated verifier) runs this checklist at integration milestones.

---

## Integration points

### I1 — Agent 2 (frontend) ↔ Agent 3 (backend) data contracts

| ID | Integration point | Verification method | Expected state | Status |
|---|---|---|---|---|
| I1.1 | Pulse row data shape (bid/ask/last/vol/OI/IV/premium/size/meta) | Agent 2 fixture matches Agent 3 backend response shape | JSON shapes match per CONTRACTS.md C1-C15 | OPEN |
| I1.2 | Scanner row data shape (same as Pulse + ticker/meta) | Agent 2 fixture matches Agent 3 backend response shape | JSON shapes match per CONTRACTS.md C1-C15 | OPEN |
| I1.3 | Earnings calendar API (CR-02) | curl Agent 3 endpoint, compare to Finnhub | Returns real Finnhub data for 5+ tickers | OPEN — depends on B2 |
| I1.4 | Sector/industry map API (CR-02) | curl Agent 3 endpoint, compare to Finnhub profile2 | Returns real Finnhub data for 5+ tickers | OPEN — depends on B2 |
| I1.5 | DuckDB snapshot query (CR-01) | Agent 2 queries DuckDB with documented contract | Returns real historical rows | OPEN — depends on B1 |
| I1.6 | Min volume alignment (CR-04) | Compare frontend MIN_VOLUME=1 with backend threshold | Thresholds match or divergence documented | OPEN — depends on B5 |

---

### I2 — Agent 2 (frontend) ↔ Agent 4 (research/eval) evaluator fixtures

| ID | Integration point | Verification method | Expected state | Status |
|---|---|---|---|---|
| I2.1 | Overview bar evaluator fixtures | Agent 4 fixtures match Agent 2 overview bar values | Net premium, P/C, FIR, session lean match for known payloads | OPEN |
| I2.2 | Filter subtractiveness evaluator fixtures | Agent 4 fixtures validate filters reduce noise | Each filter reduces row count on known fixture | OPEN |
| I2.3 | Context column evaluator fixtures (earnings/sector) | Agent 4 fixtures match Agent 2 column values | Earnings proximity, sector/industry match for 5 tickers | OPEN — depends on B2 |
| I2.4 | Tracker evaluator fixtures | Agent 4 fixtures match Agent 2 tracker P/L | P/L within tick of mark on known payloads | OPEN |
| I2.5 | History view evaluator fixtures | Agent 4 fixtures match Agent 2 history views | NetPremium trend, strike distribution, Vol/OI 14d reproduce from snapshots | OPEN — depends on B1 |
| I2.6 | Score boundary case evaluator fixtures | Agent 4 fixtures match Agent 2 score display | -100, 0, +100, no-quote, zero OI, missing IV, put-ASK hedge, 0DTE volOI>=2 all match | OPEN |
| I2.7 | Investigation checklist evaluator fixtures | Agent 4 fixtures validate checklist persistence | 6 steps checkable, verdict + reason persisted | OPEN |
| I2.8 | Dark pool methodology evaluation | Agent 4 doc passed, no directional dark pool language in UI | Citation audit passes | OPEN — depends on W7.4 + CR-03 |

---

### I3 — Agent 3 (backend) ↔ Agent 4 (research/eval) proposal evaluation

| ID | Integration point | Verification method | Expected state | Status |
|---|---|---|---|---|
| I3.1 | B1 cadence proposal evaluation | Agent 4 evaluates Agent 3 B1 proposal | Proposal viable, DuckDB schema documented, no mock data | OPEN — depends on Agent 3 proposal |
| I3.2 | B2 earnings cache proposal evaluation | Agent 4 evaluates Agent 3 B2 proposal | Finnhub rate limits addressed, cache TTL reasonable | OPEN — depends on Agent 3 proposal |
| I3.3 | B3 FINRA ETL proposal evaluation | Agent 4 evaluates Agent 3 B3 proposal | FINRA auth path declared, dark pool NO directional claims | OPEN — depends on Agent 3 proposal |
| I3.4 | B6 quiet accumulation alert evaluation | Agent 4 evaluates Agent 3 B6 proposal | False positive rate estimated, signal strength assessed, fatigue risk assessed | OPEN — depends on Agent 3 proposal |
| I3.5 | B9 O/S borrow inputs evaluation | Agent 4 evaluates Agent 3 B9 proposal | Borrow rate data source documented, impact on score assessed | OPEN — depends on Agent 3 proposal |

---

### I4 — Agent 1 (architect) ↔ All agents contract tracking

| ID | Integration point | Verification method | Expected state | Status |
|---|---|---|---|---|
| I4.1 | Contract request status | Agent 1 reads CONTRACT_REQUESTS.md, verifies each CR status | All CRs have correct status (OPEN/SHIPPED/WISH/PARTIAL/PROPOSAL ONLY) | OPEN |
| I4.2 | Gate plan status | Agent 1 reads GATE_PLAN.md, verifies each gate state | All gates have correct state (OPEN/PASSING/FAILING/DEFERRED/CLOSED) | OPEN |
| I4.3 | Risk register status | Agent 1 reads RISK_REGISTER.md, verifies each risk status | All risks have correct status (OPEN/MONITORING/MITIGATED/DEFERRED WINDOW) | OPEN |
| I4.4 | Lane discipline | Agent 1 verifies no agent edited files outside its lane | Git diff shows no cross-lane edits | OPEN — ongoing |
| I4.5 | Sub-agent environment | Agent 1 reads AGENT_RUNBOOK.md, verifies all agents have run commands | All agents can run tests, read docs, operate independently | OPEN — depends on CR-12 |

---

### I5 — Existing system integration (pre-Phase 9 baseline)

| ID | Integration point | Verification method | Expected state | Status |
|---|---|---|---|---|
| I5.1 | Backend :8000 health | curl http://localhost:8000/api/health | 200 OK | VERIFIED (pre-Phase 9) |
| I5.2 | Proxy :3000 CORS | curl -H "Origin: http://example.com" http://localhost:3000/ | Access-Control-Allow-Origin: * present | VERIFIED (pre-Phase 9) |
| I5.3 | WTI vol endpoint | curl http://localhost:3000/api/wti/vol | 200 with HAR-IV forecast data | VERIFIED (pre-Phase 9) |
| I5.4 | Pairs scan endpoint | curl "http://localhost:3000/api/pairs/scan?top_n=6" | 200 with cointegrated pairs | VERIFIED (pre-Phase 9) |
| I5.5 | Frontend build | Check frontend/build/static/js/main.*.js exists | Build present, size reasonable | VERIFIED (pre-Phase 9) |
| I5.6 | Public.com brokerage tab | curl http://localhost:3000/api/public/brokerage/portfolio | 200 with portfolio data | VERIFIED (pre-Phase 9) |

---

### I6 — Phase 9 new surface integration (post-delivery)

| ID | Integration point | Verification method | Expected state | Status |
|---|---|---|---|---|
| I6.1 | Pulse tape with spread bar + fill + overview | Open Pulse tab in frontend, verify bars render | Spread bar shows position, fill column shows premium, overview bar shows net premium/P/C/FIR/session | OPEN — post W1 |
| I6.2 | Scanner with filters | Open Scanner tab, apply filters, verify row counts change | Each filter reduces row count as expected | OPEN — post W6 |
| I6.3 | Chart modal | Click row in Pulse, open chart modal, verify views render | Contract history + Net Premium views show data | OPEN — post W3.1 |
| I6.4 | Tracker | Bookmark a row, verify tracker shows in list, P/L updates | Tracker shows bookmarked row, P/L within tick of mark | OPEN — post W3.2 |
| I6.5 | Highlighting | Open Pulse tab, verify Size>OI rows are yellow, Vol>OI rows are purple | Highlighting renders correctly | OPEN — post W3.3 |
| I6.6 | Tab config persistence | Change tab config, reload, verify config survives | Config survives reload | OPEN — post W3.4 |
| I6.7 | Feed tabs + !exclude | Open Scanner, add feed tab, use !exclude, verify ticker excluded | !exclude works, feed tabs render | OPEN — post W4.4 |
| I6.8 | CSV export | Export scanner results, verify CSV contains filters + timestamp + columns | CSV round-trips correctly | OPEN — post W4.7 |
| I6.9 | Signed score display | Open Pulse/Scanner, verify score column shows -100..+100 | Score displays correctly, marked DISPLAY-ONLY | OPEN — post W5.1-W5.2 |
| I6.10 | Dark pool overlay (post-B3) | Open heatseeker, verify dark pool levels overlay renders | Top-N dashed lines + notional labels match FINRA ETL data | DEFERRED — post B3 |

---

## Integration verification procedure

### Pre-Phase 9 baseline verification (done)

All I5.x checks have been verified before Phase 9 started. These are the integration points that Phase 9 builds on top of.

### Phase 9 integration verification (ongoing)

Agent 1 runs this checklist at the following milestones:

1. **After Agent 2 ships W1 (tracer):** Verify I6.1
2. **After Agent 2 ships W6 (filters):** Verify I6.2
3. **After Agent 2 ships W3 (workflow):** Verify I6.3, I6.4, I6.5, I6.6
4. **After Agent 2 ships W4 (history):** Verify I6.7, I6.8
5. **After Agent 2 + Agent 4 ship W5 (score):** Verify I6.9
6. **After Agent 3 ships B1 (cadence):** Verify I1.5, I2.5, I6.10 (if W7.4 ships)
7. **After Agent 3 ships B2 (earnings cache):** Verify I1.3, I1.4, I2.3
8. **After Agent 3 ships B3 (FINRA ETL):** Verify I6.10 (dark pool overlay)

### Full integration verification (end of Phase 9)

Agent 1 runs all I1-I6 checks at the end of Phase 9. All checks must pass before Phase 9 is considered complete.

---

## Integration checklist maintenance

Agent 1 updates this checklist when:
- A new integration point is identified
- An integration point is verified (status: OPEN → VERIFIED)
- An integration point fails (status: OPEN → FAILED, with reason)
- An integration point is deferred (status: OPEN → DEFERRED, with reason)

Agent 2 updates this checklist when:
- A frontend feature ships that changes an integration point

Agent 3 updates this checklist when:
- A backend proposal ships that changes an integration point

Agent 4 updates this checklist when:
- An evaluation identifies a new integration point

---

## Integration checklist summary

| Category | Count | Integration points |
|---|---|---|
| I1 (A2↔A3 data contracts) | 6 | I1.1-I1.6 |
| I2 (A2↔A4 eval fixtures) | 8 | I2.1-I2.8 |
| I3 (A3↔A4 proposal eval) | 5 | I3.1-I3.5 |
| I4 (A1↔all contract tracking) | 5 | I4.1-I4.5 |
| I5 (existing baseline) | 6 | I5.1-I5.6 |
| I6 (Phase 9 new surfaces) | 10 | I6.1-I6.10 |

**Total integration points:** 40

**Verified (pre-Phase 9):** 6 (I5.1-I5.6)

**Open:** 34 (all Phase 9 integration points)

**Deferred:** 1 (I6.10, dark pool overlay, post-B3)

**Integration checklist status:** OPEN (Phase 9 just started, most integration points are OPEN)
