# BACKLOG.md — Confluence Decoder

## Active Phase: A — Data Layer

### In Progress
- [ ] Create data layer schema and migrations
- [ ] Set up repository pattern for MongoDB access
- [ ] Create data collection service with proper error handling
- [ ] Add data quality checks and validation

### Pending
- [ ] Phase B: Quant analytics
- [ ] Phase C: ML pipeline
- [ ] Phase D: Backtester
- [ ] Phase E: Alert DSL
- [ ] Phase F: Trading execution
- [ ] Phase G: Portfolio & P&L
- [ ] Phase H: Frontend architecture
- [ ] Phase I: Observability & ops
- [ ] Phase J: Quality processes & ADRs

### Done
- [x] Initial project setup
- [x] Security audit and fixes
- [x] ML training pipeline
- [x] Cron jobs for data collection
- [x] WebSocket improvements
- [x] Paper trading module
- [x] Morning briefing email system

### Discovered Issues (to address in current phase)
- `DEFAULT_STRATEGY = "iron_condible"` typo in paper_trading.py
- `App.js` is 730+ lines, needs decomposition
- No server-state library (need TanStack Query)
- No frontend tests
- `portfolio.py` uses floats instead of Decimal
- Alert engine hardcodes 7 alert types as Python methods
- No structured logging (need structlog)
- No Prometheus metrics
- No ADRs
- No PR template
- No conventional commits enforcement