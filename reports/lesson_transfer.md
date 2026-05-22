# Cross-Project Lesson Transfer Report
Generated: 2026-05-22T01:30:47.564832+00:00

## Summary
- Projects analyzed: 2
- Total lessons identified: 11
- Floww gaps found: 5

## Floww Gaps
| File | Description | Status |
|------|-------------|--------|
| `backend/services/risk/gate.py` | Dedicated risk gate module | ❌ missing |
| `backend/services/risk/killswitch.py` | Circuit breaker / kill switch | ❌ missing |
| `backend/services/risk/sizer.py` | Position sizer (Kelly) | ❌ missing |
| `backend/services/events.py` | EventBus pattern | ❌ missing |
| `backend/services/strategies/friday_pin.py` | Friday Pin strategy | ❌ missing |

## Lessons from swarmSPX
Path: `/Users/nav/GitHub/swarmSPX` | Files analyzed: 10

### 1. EventBus decoupled pipeline
**Category:** architecture | **Risk:** medium | **Effort:** high | **Impact:** high

**Description:** swarmSPX uses an EventBus pattern with asyncio.Queue for decoupled pipeline stages (KillSwitch → GEX → Pit → Selector → Sizer → RiskGate → AuditLog → PaperBroker). floww's signal_translator.py and execution_engine.py are tightly coupled.

**Source:** swarmspx/events.py — EventBus with typed events

**Application:** Refactor floww's signal pipeline to use an EventBus. This would decouple signal generation from execution, making it easier to add new signal sources (e.g., DVT, Feigenbaum).

**Target files:** `backend/services/signal_translator.py`, `backend/services/execution_engine.py`

### 2. Pre-trade risk gate with circuit breakers
**Category:** risk | **Risk:** low | **Effort:** medium | **Impact:** high

**Description:** swarmSPX has a dedicated risk/gate.py with multi-trigger circuit breakers and a Kelly sizer with daily lock. floww's risk gates are inline in signal_translator.py — less modular and harder to test.

**Source:** swarmspx/risk/gate.py, risk/sizer.py, risk/killswitch.py

**Application:** Extract floww's risk gates from signal_translator.py into a dedicated risk/gate.py module with circuit breaker pattern. Add daily loss lock (floww currently has no daily kill switch).

**Target files:** `backend/services/signal_translator.py`, `backend/services/execution_engine.py`

### 3. Paper broker with shadow trading
**Category:** architecture | **Risk:** low | **Effort:** medium | **Impact:** high

**Description:** swarmSPX has a full paper broker (paper.py) with 10 unit tests, shadow trading, and PnL tracking. floww's paper_trading.py only writes to Mongo orders_dry_run — no execution simulation.

**Source:** swarmspx/paper.py — shadow trading with fill simulation

**Application:** Enhance floww's paper broker to simulate fills, track PnL, and provide a 30-day paper trading report. This is critical before enabling LIVE_TRADING_ENABLED.

**Target files:** `backend/paper_trading.py`, `backend/services/paper_trading.py`

### 4. Per-decision JSONL audit log
**Category:** architecture | **Risk:** low | **Effort:** low | **Impact:** medium

**Description:** swarmSPX has an audit.py that logs every decision to JSONL, ET-partitioned for efficient querying. floww's audit_trail.py exists but may not have the same level of detail.

**Source:** swarmspx/audit.py — per-decision JSONL, ET-partitioned

**Application:** Enhance floww's audit_trail.py to log every signal, risk gate decision, and order intent to JSONL. This is essential for post-trade analysis and regulatory compliance.

**Target files:** `backend/services/audit_trail.py`

### 5. Friday Pin strategy (validated edge)
**Category:** ml | **Risk:** low | **Effort:** medium | **Impact:** high

**Description:** swarmSPX's Friday Pin strategy has Sharpe 3.66 over 90 days, 100% win rate, 14 trades. It sells 0DTE iron condor at 15:30-15:40 ET on Fridays when prior 30 1m-bars stayed in <0.5% range. This is the only validated edge in any of Nav's projects.

**Source:** swarmspx/strategies/friday_pin.py — Sharpe 3.66, 14 trades

**Application:** Port the Friday Pin strategy to floww as a new strategy module. floww has the infrastructure (GEX, VPIN, paper trading) to validate and extend this edge. Could combine with VPIN toxicity filter.

**Target files:** `backend/services/execution_doctrine.py`, `backend/paper_trading.py`

### 6. DIY GEX engine (replaces SpotGamma)
**Category:** architecture | **Risk:** low | **Effort:** low | **Impact:** medium

**Description:** swarmSPX built a DIY GEX engine that replaces $199/mo SpotGamma. floww also has a GEX aggregator. Comparing implementations could reveal optimizations or bugs.

**Source:** swarmspx/dealer/gex.py — DIY GEX engine

**Application:** Cross-validate floww's gex_aggregator.py against swarmSPX's GEX engine. Look for differences in formula, handling of edge cases (0DTE, weeklies), and performance (Numba vs pure Python).

**Target files:** `backend/services/gex_aggregator.py`

### 7. Backtester with real data + slippage model
**Category:** testing | **Risk:** low | **Effort:** medium | **Impact:** high

**Description:** swarmSPX's backtest/replay.py uses real Polygon-class data via D2DT cache and includes a slippage model. floww's backtesting is less mature.

**Source:** swarmspx/backtest/replay.py — real data + slippage

**Application:** Enhance floww's backtesting with a slippage model and realistic fill simulation. This is critical for validating the Friday Pin strategy and any future ML signals.

**Target files:** `backend/services/backtest`

## Lessons from gflows
Path: `/Users/nav/GitHub/floww/data/github-repos/cloned/aaguiar10_gflows` | Files analyzed: 5

### 1. GEX pattern from app.py
**Category:** architecture | **Risk:** low | **Effort:** low | **Impact:** medium

**Description:** Found GEX-related code in gflows/app.py

**Source:** /Users/nav/GitHub/floww/data/github-repos/cloned/aaguiar10_gflows/app.py

**Application:** Cross-validate against floww's gex_aggregator.py

**Target files:** `backend/services/gex_aggregator.py`

### 2. GEX pattern from layout.py
**Category:** architecture | **Risk:** low | **Effort:** low | **Impact:** medium

**Description:** Found GEX-related code in gflows/layout.py

**Source:** /Users/nav/GitHub/floww/data/github-repos/cloned/aaguiar10_gflows/modules/layout.py

**Application:** Cross-validate against floww's gex_aggregator.py

**Target files:** `backend/services/gex_aggregator.py`

### 3. GEX pattern from stats.py
**Category:** architecture | **Risk:** low | **Effort:** low | **Impact:** medium

**Description:** Found GEX-related code in gflows/stats.py

**Source:** /Users/nav/GitHub/floww/data/github-repos/cloned/aaguiar10_gflows/modules/stats.py

**Application:** Cross-validate against floww's gex_aggregator.py

**Target files:** `backend/services/gex_aggregator.py`

### 4. GEX pattern from calc.py
**Category:** architecture | **Risk:** low | **Effort:** low | **Impact:** medium

**Description:** Found GEX-related code in gflows/calc.py

**Source:** /Users/nav/GitHub/floww/data/github-repos/cloned/aaguiar10_gflows/modules/calc.py

**Application:** Cross-validate against floww's gex_aggregator.py

**Target files:** `backend/services/gex_aggregator.py`

## Priority Matrix

### Quick Wins (Low Effort, High Impact)

### High Value (Medium Effort, High Impact)
- **Pre-trade risk gate with circuit breakers** (swarmSPX) — swarmSPX has a dedicated risk/gate.py with multi-trigger circuit breakers and a Kelly sizer with dai
- **Paper broker with shadow trading** (swarmSPX) — swarmSPX has a full paper broker (paper.py) with 10 unit tests, shadow trading, and PnL tracking. fl
- **Friday Pin strategy (validated edge)** (swarmSPX) — swarmSPX's Friday Pin strategy has Sharpe 3.66 over 90 days, 100% win rate, 14 trades. It sells 0DTE
- **Backtester with real data + slippage model** (swarmSPX) — swarmSPX's backtest/replay.py uses real Polygon-class data via D2DT cache and includes a slippage mo

### Strategic (High Effort, High Impact)
- **EventBus decoupled pipeline** (swarmSPX) — swarmSPX uses an EventBus pattern with asyncio.Queue for decoupled pipeline stages (KillSwitch → GEX
