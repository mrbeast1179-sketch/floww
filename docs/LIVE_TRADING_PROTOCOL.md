"""
docs/LIVE_TRADING_PROTOCOL.md

Live Trading Switch Protocol for Floww / Confluence Decoder
============================================================

This document defines the strict protocol for enabling live trading.
Violating this protocol can result in real financial loss.

## Prerequisites Checklist

Before flipping the switch to LIVE mode, ALL of the following must be true:

- [ ] **1. All tests green**
  - `pytest backend/tests/ -x` passes with zero failures
  - Coverage >= 80% on critical paths (execution, risk, auth)
  - No flaky tests

- [ ] **2. Security audit passed**
  - `SECURITY_AUDIT.md` reviewed and all CRITICAL findings resolved
  - No secrets in git history (verify: `git log --all --full-history -- .env`)
  - API auth enabled (API_SECRET_KEY set, not empty)
  - WebSocket token set
  - CORS origins restricted (no wildcards)

- [ ] **3. Circuit breakers tested**
  - `test_circuit_breaker.py` passes (8+ tests)
  - P&L drawdown trip verified
  - Error rate trip verified
  - Latency trip verified
  - Manual reset verified

- [ ] **4. Paper trading validated**
  - Minimum 7 days of paper trading with positive expectancy
  - Max drawdown in paper < 5%
  - Sharpe ratio > 1.0 (if enough data)

- [ ] **5. Nav 2FA confirmation**
  - TOTP code verified
  - Email confirmation code verified
  - Both codes entered within 60-second window

## State Machine

Trading states (in order):

| State | Label | Max Notional | Description |
|-------|-------|-------------|-------------|
| 0 | OFF | $0 | All trading disabled |
| 1 | PAPER_ONLY | $0 | Paper trading only |
| 2 | LIVE_TINY | $1,000 | Live trading, tiny size |
| 3 | LIVE_NORMAL | $10,000 | Live trading, normal size |
| 4 | LIVE_FULL | Unlimited | Live trading, full size |

### Transition Rules

1. Can only advance ONE state at a time
2. Cannot skip states going up
3. Can drop to any lower state (emergency)
4. Each transition requires 2FA (TOTP + email)
5. After circuit breaker trip: 24h cooldown before advancing

## API Endpoints

### GET /api/admin/trading/status
Returns current trading state, circuit breaker status, and SLO summary.

### POST /api/admin/trading/transition
Request a state transition.

```json
{
  "target_state": "LIVE_TINY",
  "totp_code": "123456",
  "email_code": "ABCD1234"
}
```

### POST /api/admin/trading/circuit-breaker/reset
Manually reset the circuit breaker (requires admin auth).

### POST /api/admin/trading/circuit-breaker/trip
Manually trip the circuit breaker (emergency stop).

## Emergency Procedures

### Immediate Stop
1. Call `POST /api/admin/trading/circuit-breaker/trip` with reason="emergency"
2. Or: `POST /api/admin/trading/transition` with target_state="OFF"
3. Verify: `GET /api/admin/trading/status` shows state=OFF

### After Incident
1. Review trip log: `GET /api/admin/trading/circuit-breaker/log`
2. Identify root cause
3. Fix the issue
4. Run full test suite
5. Reset circuit breaker
6. Resume at PAPER_ONLY
7. Validate for 24h before going live again

## Audit Trail

Every state transition and circuit breaker event is logged to:
- MongoDB `audit_trail` collection (hash-chained, immutable)
- Application logs (`backend/logs/app.log`)
- Structured log: `logger.critical("TRADING_STATE_CHANGE", ...)`

## Cost Controls

- Databento budget: $125/month (alert at 80%)
- Azure budget: $50/month (alert at 80%)
- Max daily loss: -2% of equity (circuit breaker)
- Max position size: defined by state

## Contact

- Nav: [email]
- Emergency: trip circuit breaker via API
"""
