# Backend Proposal B1 — Snapshot Cadence Job

**Proposed by:** Agent 3 (Backend/Data lane) · **Status:** PROPOSAL — needs Agent 1 gate decision + BACKEND_LANE_OWNER=1
**Depends on:** HANDOFF B1, PLAN.md C1/C2, FULL_PLAN.md B1, CONTRACTS.md CR-01
**Blocks:** W2.3 (ΔOI), W2.4 (strategy badge), W3.2 close-detection stages, W4.1-W4.3 (history views), W5 backtest fixtures

## Problem

Server.py:1143 saves snapshots only on request (heatmap build), so history exists only for
ticker/contracts that were viewed at view cadence. Server.py:540 DuckDB is :memory: — all
durable history reads go to Mongo capped at 50/ticker. Intraday RVOL baselines (20d same-time)
cannot live in Mongo-50. W4-history items (NetPrem trend, Strike distribution, Vol/OI 14d) and
W2.3 ΔOI are fixture-first until a cadence job persists snapshots on a fixed interval.

## Proposal

Add a fixed-interval snapshot cadence job in `backend/scheduler.py` (precedent exists: scan loop
with 429-backoff pattern already in flowseeker.py). The job:

1. **Polls the Public API** on the same chains the existing `/` route uses (same data source,
   same auth) at a declared `POLL_CADENCE` (default 15s, tunable).
2. **Persists each snapshot** to a file-backed DuckDB (NOT Mongo, NOT :memory:) at
   `backend/data/flow_snapshots.duckdb` (path declared in proposal, env-overridable).
3. **Schema** (matches CONTRACTS.md C1-C15 row shape):
   ```
   timestamp, ticker, strike, option_type, expiry, side, last, bid, ask,
   volume, open_interest, iv, mark_price, premium, size, notional, meta(JSON)
   ```
4. **Query contract** (matches CR-01):
   - `SELECT * WHERE ticker=? AND timestamp>=? ORDER BY timestamp DESC LIMIT ?`
   - `SELECT * WHERE expiry=? ORDER BY timestamp DESC LIMIT ?`
   - `SELECT * WHERE side=? ORDER BY timestamp DESC LIMIT ?`
   - Time-windowed aggregates for NetPrem trend / strike distribution / Vol/OI 14d
5. **Rate safety:** inherits existing scan 429-backoff pattern (H8). Undisclosed Public limits
   assumed; backoff mandatory, not optimistic.
6. **Startup:** job starts automatically on backend startup (no manual trigger). If DuckDB path
   is missing, job creates it.
7. **Monitoring:** job emits heartbeat metric (last successful poll timestamp) on a debug endpoint
   `/debug/cadence` (proposal-only; not a user-facing route).

## Why file-backed DuckDB, not Mongo

- Mongo 50/ticker cap is too small for 20d intraday baselines (C2).
- Mongo promotion gate (`TICK-SNAPSHOT-BACKEND`) still applies for other consumers, but the
  cadence job writes to DuckDB first; Mongo can be a downstream sync if desired.
- File-backed DuckDB survives backend restart; :memory: does not (C2).

## Alternatives considered

- **Raise Mongo cap:** works for daily resolution but not intraday baselines; still capped.
- **Keep :memory: DuckDB + Redis:** adds infra; file-backed DuckDB is simpler and persistent.
- **Skip cadence, keep fixture-first forever:** W4-history items never ship live; violates Phase 9 goal.

## Risks

- Public API rate limits: mitigated by backoff + tunable cadence. If cadence is too aggressive,
  job throttles itself.
- Disk space: DuckDB file grows with snapshot volume. Mitigation: retention policy (proposal: keep
  30d, then compact; exact policy deferred to implementation).
- Backend restart losing in-flight polls: file-backed DuckDB persists; job resumes on restart.

## Acceptance criteria (when implemented)

- [ ] Cadence job starts on backend startup, no manual trigger
- [ ] Snapshots persist to file-backed DuckDB at declared path
- [ ] DuckDB survives backend restart
- [ ] Query contract matches CR-01 (4 query types)
- [ ] Agent 2 can query DuckDB and get real historical rows
- [ ] Rate backoff inherited from existing scan pattern
- [ ] No mock data in the cadence job

## Gate decision requested

Agent 1: grant BACKEND_LANE_OWNER=1 for B1. This is the critical path for W2.3, W2.4, W3.2-close,
W4.1-W4.3. Without B1, these features stay fixture-first.

**Proposer's recommendation:** Ship B1. It unblocks the most Phase 9 features of any backend proposal.
