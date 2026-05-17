# Claude Code Deep Review Prompt

You are doing a second-pass deep review of the Confluence Decoder project at /Users/nav/Documents/GitHub/floww. This is a FastAPI + React + MongoDB options trading intelligence platform.

## Context
We already did a first-pass review and fixed 22 CRITICAL + 39 HIGH issues. Now we need a deeper review focusing on:

1. **Remaining issues** from the first pass that we haven't fixed yet
2. **New issues** that may have been introduced by our fixes
3. **Architecture improvements** — the server.py file is 2900+ lines and needs refactoring
4. **Performance optimizations** — identify bottlenecks in data fetching, rendering, API calls
5. **Trading logic correctness** — verify all GEX calculations, Greeks, alert logic
6. **Security hardening** — even though this is a personal tool, best practices matter
7. **Test coverage** — we only have 24 integration tests, need unit tests for core logic

## Instructions

Review ALL files in the project. For each issue found:
- File path and line number
- Severity: CRITICAL, HIGH, MEDIUM, LOW
- Category: SECURITY, PERFORMANCE, CORRECTNESS, CODE_QUALITY, TESTING
- Description of the issue
- Suggested fix with actual code

## Specific Areas to Focus On

### Backend (backend/)
- server.py (2900 lines) — needs to be split into modules
- data_providers.py — verify all API error handling
- alert_engine.py — verify all alert logic edge cases
- flashalpha_client.py — verify all 81 endpoints are correctly implemented
- alpaca_client.py — verify order placement logic
- databento_provider.py — verify OI parsing and caching
- bs_greeks.py — verify Black-Scholes math
- vol_analytics.py — verify IV surface calculations
- advanced_analytics.py — verify GEX, PDF, impulse calculations
- portfolio.py — verify position/Greeks aggregation
- schwab.py — verify OAuth flow

### Frontend (frontend/src/)
- App.js (680 lines) — needs refactoring
- All components — check for React best practices
- All hooks — check for memory leaks, stale closures
- State management — is it efficient?
- Rendering performance — unnecessary re-renders?

### Infrastructure
- tests/test_api.py — needs unit tests, not just integration
- Dockerfile.* — multi-stage builds, security
- docker-compose.yml — networking, volumes
- .github/workflows/ — CI/CD improvements
- .env.example — document all required vars

### New Features to Suggest
Based on the research we've done (FlashAlpha API, Alpaca paper trading, options flow), suggest:
1. What new features would most help a day trader?
2. What's missing compared to paid tools like Skylit?
3. What can we build with the data sources we have?

## Output Format

Produce a structured report with:
1. Executive summary (top 10 most important issues)
2. Detailed findings by category
3. Recommended refactoring plan for server.py
4. Suggested new features with implementation plan
5. Priority order for all fixes

Be thorough. This is a trading tool that will handle real money decisions. Every bug could cost money.
