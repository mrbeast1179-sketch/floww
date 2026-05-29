# Professional Code Review: Confluence Decoder / Heatseeker GEX Terminal

**Reviewer:** Quant Dev, HFT desk (Jane Street–level standard)  
**Date:** 2026-07-17  
**Classification:** CONFIDENTIAL — INTERNAL USE ONLY

---

## Opening Assessment

I spent 4+ hours deep-diving every line that matters. I have good news and bad news.

**The good news:** The ambition is right. Building a Skylit-style institutional GEX terminal for retail is a real need. The breadth of analytics — GEX, VEX, Charm, Vomma, Zomma, IV surface, skew, realized vol, regime detection, ML predictions — shows you understand the problem space. You're thinking about the right things.

**The bad news:** This codebase would not survive 15 minutes on a real trading desk. Not because the ideas are wrong, but because the **execution is at hobbyist quality** while claiming to be institutional. That gap is dangerous — it creates a false sense of capability. A tool that silently returns wrong answers is worse than no tool at all.

Let me be specific about what I see.

---

## 1. MATHEMATICAL RIGOR — You Need Citations, Not Vibes

### What You're Doing Wrong

**Risk-free rate inconsistency:** `bs_greeks.py` uses 5%. `advanced_analytics.py` uses 4.5%. Neither has a comment explaining why. On a real desk, this would be a 2-minute argument ending with "check the Fed funds rate for today" and the value would be sourced from a market data feed, not a magic constant.

**Dividend yields hardcoded in 5 places:** You have `DIV_YIELD` dicts scattered across `server.py` and `advanced_analytics.py` — and they could diverge. These should be sourced from a single config or, better, from live data. Options pricing with stale dividend assumptions will give you wrong Greeks. That loses money.

**Black-Scholes implementation:** You roll your own `bs_greeks.py` (112 lines). Why? Unless you have a specific modification (e.g., dividend-adjusted, rate curve interpolation), you should be using `py_vollib` or `quantlib` — battle-tested libraries used by actual trading desks. Your implementation doesn't handle:
- Division by zero when volatility is zero
- Deep ITM/OTM edge cases in norm CDF
- Interest rate term structure
- Early exercise premium (American options)

**Breeden-Litzenberger implied PDF:** You compute it in `advanced_analytics.py` but I don't see any smoothing (spline or otherwise). Raw second differences of call prices produce jagged, non-monotonic PDFs that are financial nonsense. If you're not using a smoothing method — even a simple cubic spline — your PDF is noise.

**Orphaned expressions:** `server.py:413` has `yf_data["spot"]` as a standalone expression that does nothing. `advanced_analytics.py:66` has `len(sorted_calls)` that does nothing. These aren't just code smells — they signal that someone was working without a type checker or linter. On a trading desk, our CI would reject these before a human ever saw them.

### What You Should Do

1. **Single source of truth for rates and dividends**: One config module, loaded from environment or market data. Every Greek calculation reads from the same place.
2. **Use a battle-tested library for core pricing**: `py_vollib` for Black-Scholes. If you must roll your own, every formula needs a comment citing the source (Hull, Gatheral, etc.) and unit tests verifying against known values.
3. **Validate all math outputs**: Every Greek function should have property-based tests: put delta + call delta ≈ 1, gamma of put ≈ gamma of call, vanna symmetry, etc. These invariants catch bugs that unit tests miss.
4. **Smooth your implied PDF**: Even a simple cubic spline is better than raw second differences. Cite a source for your method.

---

## 2. ARCHITECTURE — Your Server.py Is a Crime Scene

### What You're Doing Wrong

**2,890 lines in one file.** This isn't just "not ideal" — it's dangerous. Every time someone opens `server.py`, they're looking at:
- MongoDB connection setup
- 4 `@app.on_event("startup")` handlers
- ~30 route wiring imports
- Inline analytics functions
- Helper utilities
- Middleware
- Error handlers
- CORS configuration
- Cache setup

On a professional desk, a file this size would be rejected in code review. Period. The cognitive load of understanding what touches what is too high. You WILL introduce bugs because someone will edit a function at line 2000 not realizing it's used by middleware at line 100.

**Duplicate routes:** `routes/market_data.py` and `server.py` both define `/api/tickers`. FastAPI silently picks one. This is a deployment time bomb.

**44 route files with no consistent pattern:** Some routes return error objects. Some return plain strings. Some return 500 with no message. Some return None and let FastAPI figure it out. A professional API has a consistent response envelope — every response is `{data, error, meta}` with proper HTTP status codes.

### What You Should Do

1. **Break server.py into modules immediately**: Config, middleware, analytics, data fetching, admin. Max 400 lines per module. This isn't optional.
2. **Standardize API response format**: Every route returns `{"success": true/false, "data": ..., "error": ...}`. Write one helper function. Use it everywhere.
3. **Use FastAPI lifespan properly**: Replace 4 `@app.on_event("startup")` handlers with one `@asynccontextmanager lifespan` function.
4. **Remove duplicate routes**: Run `app.routes` and check for duplicates. You have at least 1 confirmed.
5. **Automated route inventory**: A script that lists all registered routes and their response schemas. Currently nobody knows what the API surface actually is.

---

## 3. THE ML PIPELINE — You Have No ML Pipeline

### What You're Doing Wrong

**Feature computation cloned 3+ times** with different `min_periods` values. This isn't just messy — it means training and inference compute different features. Your model trains on features with certain NaN behavior and then predicts on features with different NaN behavior. **Your inference results are mathematically invalid.**

**MODEL_REGISTRY points to files that don't exist.** Every call to predict returns a `DegenerateModelError`. This means the ML dashboard, the prediction API, the retrain orchestrator — none of them work. If you showed this to a professional quant, they would walk out of the room.

**Data leakage in retrain.py:** The label (`pct_change().shift(-1)`) is computed on the entire dataset before the temporal split. Future returns are present in the training set. This means your backtest results are overoptimistic by an unknown margin. You cannot trust any reported accuracy metric.

**Lookahead bias in features.py:** The target-based row filter drops rows where `directional_move == 0 AND return_pct == 0` — this filters based on the FUTURE label. This is textbook data leakage. Any model trained with this pipeline will look artificially good in backtest and fail in production.

**Quality gates not enforced:** `retrain.py` saves models directly via `joblib.dump()` without calling `_save_with_gates`. Degenerate models enter the registry. The entire gate module exists but is bypassed by the main training path.

### What You Should Do

1. **ONE feature computation function**: `compute_features()` lives in one file. Training calls it. Inference calls it. It has one set of parameters. Tested with property tests. Full stop.
2. **Fix MODEL_REGISTRY**: Make it dynamic — scan `models/` directory and build the registry from filenames + manifest JSON. Never hardcode paths.
3. **Fix the lookahead bias**: Temporal split BEFORE any label or feature computation that could leak forward information. Walk-forward validation must be strict.
4. **Enforce quality gates**: `_save_with_gates` is the ONLY way to persist a model. If a model fails quality gates, it goes to quarantine, not production.
5. **Add prediction verification**: Every prediction should be logged with features, timestamp, model version. You need to be able to reproduce any prediction after the fact. This is table stakes for any serious ML system.

---

## 4. TESTING — Your Test Suite Is a Mirage

### What You're Doing Wrong

**2,343 out of 2,378 tests fail.** Someone somewhere says "2500 tests pass" but that hasn't been true since... when? The single `conftest.py` event loop bug kills everything async — which is almost everything.

Having a test suite that's 98.5% red is worse than having no tests at all. It gives you a false sense of security. Someone looking at the file count (138 test files!) thinks the project is well-tested. It is not.

**18 tests skipped** with `@pytest.mark.skip(reason="needs network")`. Tests that need network should mock the network layer. If they can't, they should be integration tests in a separate directory that only runs in CI with credentials. Currently they're just dead code that accumulates bit rot.

**6 flaky tests** marked `@pytest.mark.flaky`. Flaky tests are worse than no tests — they teach developers to ignore test failures. The correct response to a flaky test is to fix it or delete it, not mark it flaky.

**Stateful hypothesis test entirely skipped.** Property-based testing is how professional quant desks validate their math. You have one. It's disabled. You wrote it, then gave up on it.

### What You Should Do

1. **Fix conftest.py TODAY.** This is a 1-line conceptual fix — remove the autouse event loop teardown fixture. Doing this restores the entire test suite.
2. **Delete or fix every skipped test.** If it's not running, it's not a test. It's documentation debt.
3. **Delete or fix every flaky test.** Do not tolerate non-deterministic tests.
4. **Add property-based tests for ALL Greeks.** The Hypothesis framework is already in your dependencies. Use it. Test financial invariants, not just function outputs.
5. **CI pipeline that blocks on test failures.** If tests fail, the PR doesn't merge. This is non-negotiable for any professional software project.

---

## 5. FRONTEND — You're Building a Trading Terminal That Silently Hangs

### What You're Doing Wrong

**`fetch()` with non-standard `timeout` option.** This isn't a minor bug — it's a fundamental misunderstanding of how `fetch` works in browsers. Every request from `useMarketData.js` can hang indefinitely. Your CharmChart, VannaChart, and all components using this hook will freeze when the backend is slow or unreachable. For a trading terminal that needs to display live data, **this is unacceptable.**

**16 files missing BACKEND_URL fallback.** When the environment variable is not set, API calls silently go to `"undefined/api/..."`. Every request fails silently because of empty catch blocks. The user sees a blank screen with no error indication.

**12+ empty catch blocks.** `catch (e) { /* noop */ }` or `catch (e) {}` scattered through AlertsPanel, App.js, OptionsChainTable, and others. **Silent error swallowing is the single most damaging pattern in a trading application.** A user who sees blank data doesn't know if:
- The API is down
- Their network is down
- There's no data for this ticker
- There's a bug in the code

They just stare at a blank screen. If this were a live trading terminal, they'd be guessing about position risk. That's how you lose money.

### What You Should Do

1. **Fix `useMarketData.js` timeout**: Use `AbortSignal.timeout(30000)`. Anything less and the trading terminal is unreliable.
2. **Add BACKEND_URL fallback**: `process.env.REACT_APP_BACKEND_URL || "http://localhost:8000"`. Every file. Today.
3. **Eliminate empty catch blocks**: Every catch should set user-visible error state. A trading terminal must communicate failures to the operator. Full stop.
4. **Consistent fetch strategy**: Pick `axios` (already in the project) and use it everywhere. 4 files use raw `fetch`. This creates inconsistent timeout, error handling, and interceptor behavior.

---

## 6. SECURITY — You're Leaking API Keys

### What You're Doing Wrong

**`routes/alpha_advantage.py` takes API keys as URL query parameters.** Every call is logged in the server access log. Every call is visible in browser history. Every call is cached by any proxy between the browser and the server. Query parameters also leak through the `Referer` header when the page makes subsequent requests.

This is a basic security failure. For a trading application that handles financial data, this is embarrassing.

### What You Should Do

1. **Server-side API key management**: Load API keys from environment variables on the server. The client should never see the key.
2. **If the client must provide a key**, use a header (`X-API-Key`) or a short-lived token from an auth endpoint.
3. **Audit all routes** for API keys in URLs. `alpha_advantage.py` is the only confirmed case, but there may be others.

---

## 7. PATH FORWARD — Priority Order

Here's what I'd do tomorrow morning if this were my desk:

| Priority | Action | Time Estimate | Impact |
|----------|--------|---------------|--------|
| **P0** | Fix `conftest.py` event loop fixture | 15 minutes | Restores 2,363 tests |
| **P0** | Fix `inference.py MODEL_REGISTRY` to scan models/ | 30 minutes | Restores ML inference |
| **P0** | Fix `heatseeker.py:119` _fetch_history signature | 5 minutes | Stops a route crash |
| **P0** | Add `import os` to `ml_api.py` | 1 minute | Fixes model registration |
| **P0** | Add `await` to `admin.py:37` | 1 minute | Fixes error clearing |
| **P0** | Fix `useMarketData.js` timeout | 5 minutes | Stops silent browser hangs |
| **P0** | Remove dead `ml_training.py` routes | 10 minutes | Cleans API surface |
| **P1** | Eliminate all empty catch blocks | 2 hours | User can see errors |
| **P1** | Add BACKEND_URL fallback to 16 files | 30 minutes | Stops silent API failures |
| **P1** | Unify feature computation | 4 hours | ML becomes scientifically valid |
| **P1** | Fix data leakage in retrain.py | 2 hours | Backtests become trustworthy |
| **P2** | Break up server.py | 8 hours | Code becomes maintainable |
| **P2** | Fix duplicate /api/tickers route | 30 minutes | No more silent route conflict |
| **P2** | Standardize API response format | 4 hours | Consistent client error handling |
| **P3** | Add property-based tests for Greeks | 4 hours | Catch math bugs early |
| **P3** | Put models/ in .gitignore | 1 minute | Stop tracking binary artifacts |
| **P3** | Fix alpha_advantage.py API key leakage | 2 hours | Security hygiene |

---

## Final Word

Here's what I'd tell the architect face to face:

**You're building the right thing, but you're building it wrong.** The ambition, the feature set, the domain knowledge — that's all real. The problem is execution quality. You have a small team (or one person) building something that at Jane Street would have 3-5 people minimum, plus QA, plus a quant review board.

That means you need to be **ruthless about simplicity**. You don't have the bandwidth for duplicated feature pipelines, dead routes, unused variables, and 6 different patterns of error handling. Every ounce of complexity you carry slows you down.

The fixes I've outlined aren't academic. Every single one of them is a real bug that either crashes the application, silently returns wrong data, or creates a security exposure. The test suite being 98.5% red means you're flying blind.

**Fix the fundamentals first:**
1. Make the tests pass
2. Make the ML pipeline actually compute one feature set
3. Make errors visible to the user
4. Make the architecture maintainable

Then add features. You'll move faster on a clean base than you ever could on the current one.

Good hunting.

— Quant Dev, ex-HFT desk