# ADR-0006 — Black Friday / Ferrari coupling boundary

**Status:** Accepted
**Date:** 2026-08-31
**Context:** The codebase has two distinct layers: the **Black Friday** layer (routing, execution, paper trading, signal-to-intent translation, risk gates) and the **Ferrari** layer (GEX computation, heatmap, node classification, patterns, advanced analytics). The audit flagged tight coupling between these layers as a concern. This ADR records the decision on the coupling boundary.

---

## Decision

The **Black Friday ↔ Ferrari coupling** is managed by a clear boundary:

- **Ferrari** (`services/gex_core.py`, `server.py:_build_heatmap_impl`, `advanced_analytics.py`, `vol_analytics.py`, `vol_analytics.py`) is the **data/analytics layer**. It produces:
  - GEX by strike, GEX grid, aggregate GEX curve
  - Node classification (king, floors, ceilings, gatekeepers, air pockets)
  - Pattern detection (rug, reverse rug, pika cloud, beach ball, whipsaw, etc.)
  - IV surface, skew, realized volatility, IV rank
  - Market regime, implied PDF, gamma flip levels, hedge impulse
  - Charm integral, vomma, zomma

- **Black Friday** (`services/signal_translator.py`, `services/trading_signals.py`, `routes/portfolio.py`, `services/paper_trading.py`, `services/turboquant_cache.py`) is the **policy/execution layer**. It consumes Ferrari outputs and decides:
  - Signal translation (GEX regime → buy_call/buy_put/hold)
  - Position sizing (GEX level → position size)
  - Paper trading execution
  - Portfolio/P&L tracking
  - TurboQuant cache status

The coupling is **one-directional**: Black Friday reads from Ferrari, but Ferrari does NOT read from Black Friday (no execution state, no portfolio data in the GEX computation path).

**What's already built:**
- `portfolio.py` (Position, Greeks calculation, P&L) — exists, used by `calc_portfolio_summary`, `calc_portfolio_scenario`, `calc_hedge_recommendation` in server.py
- `routes/portfolio.py` — `/api/portfolio/*` routes (get, add_position, delete_position, scenario, hedge, position-size)
- `paper_trading.py` — PaperTradingEngine ($100K initial capital, max position 10%, max delta exposure $500)
- `signal_translator.py` — SignalInput → SignalOutput translation with 10+ risk gates
- `trading_signals.py` — Signal state management

**What's still needed (Phase 6.5):**
- Portfolio persistence to MongoDB (partly done — `db.portfolios` CRUD in routes/portfolio.py, but no `services/portfolio.py` module)
- `/api/portfolio/summary` with live spot/IV from heatmap (currently requires user to pass spot/IV as query params)
- P&L tracking across time (currently only current P&L, no history)

## Consequences

### Positive
- Clear boundary means Ferrari can be tested independently (no execution state needed).
- Black Friday can be tested with mocked Ferrari outputs (signal_translator tests already do this).
- The one-directionality prevents circular dependencies and makes the data flow auditable.

### Negative
- The boundary is implicit (convention, not enforced by module structure). A future refactor could accidentally introduce Ferrari→Black Friday reads.
- `portfolio.py` is a top-level module (not in `services/`), which is inconsistent with the rest of the services layout. This is a minor organizational debt.

## Alternatives considered

- **Merge the layers:** Would simplify the call graph but make testing harder (can't test GEX without execution state). Rejected.
- **Formal interface boundary:** Would require defining abstract interfaces between layers. Over-engineered for current scale; the implicit boundary + one-directionality is sufficient.

## References

- `backend/portfolio.py` — Position, Greeks, P&L (top-level module)
- `backend/routes/portfolio.py` — portfolio API routes
- `backend/services/signal_translator.py` — signal translation (Black Friday)
- `backend/services/trading_signals.py` — signal state (Black Friday)
- `backend/services/backtest/engine.py` — backtest engine (uses RuleBasedSignal from signals.py)
- `.planning/ROADMAP.md` Phase 6.5 — Portfolio & P&L foundation
