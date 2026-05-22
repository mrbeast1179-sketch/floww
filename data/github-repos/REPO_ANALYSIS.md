# GitHub Repo Analysis — Quantitative Options Trading

**Date:** 2026-07-09
**Analyst:** OWL (PhD-level math/physics review)
**Purpose:** Evaluate repos for integration into Floww / Confluence Decoder

---

## Tier 1: Production-Ready / High Quality

### 1. je-suis-tm/quant-trading (9,916 stars)
**URL:** https://github.com/je-suis-tm/quant-trading
**Language:** Python
**Size:** ~30+ strategy scripts

**Strengths:**
- VIX Calculator follows CBOE white paper methodology exactly (variance swap formula, forward level extraction, OTM option selection, interpolation between near/far term)
- Monte Carlo backtesting framework
- London Breakout, Dual Thrust, Pair Trading, RSI Pattern Recognition, Bollinger Bands, MACD, Parabolic SAR, Heikin-Ashi
- Oil Money project (commodity FX carry trade)
- Smart Farmers project (agricultural supply/demand forecasting)

**Math/Physics Accuracy:**
- VIX formula: Correct implementation of CBOE variance swap approach. The `compute_sigma` function properly implements: σ² = (2/T) × Σ(ΔK/K²) × e^(rT) × Q(K) - (F/K₀ - 1)²/T. This is the standard replication-by-portfolio approach from Carr & Madan (1998) and the CBOE white paper.
- Forward level extraction: Correctly uses put-call parity (C-P = e^(-rT)(F-K)) to find the forward level that minimizes put-call disparity.
- Strike interval weighting: Properly handles edge cases (first/last strike) with forward/backward differences.

**Verdict:** ✅ Excellent. Production-quality quant code. VIX calc is textbook-correct.

---

### 2. jasonstrimpel/volatility-trading (1,905 stars)
**URL:** https://github.com/jasonstrimpel/volatility-trading
**Language:** Python
**Size:** ~1,000 lines

**Strengths:**
- Implements 7 volatility estimators from Euan Sinclair's "Volatility Trading"
- Clean, well-structured OOP design
- Estimators: Parkinson, Garman-Klass, Rogers-Satchell, Yang-Zhang, Hodges-Tompkins, Kurtosis, Skew

**Math/Physics Accuracy:**
- **Garman-Klass (1980):** Correct formula: σ² = 0.5×ln(H/L)² - (2ln2-1)×ln(C/O)². This is the classic OHLC estimator assuming geometric Brownian motion with no drift.
- **Yang-Zhang (2000):** Correct multi-component estimator combining open-to-close, close-to-close, and Rogers-Satchell. The weighting constant k = 0.34/(1.34 + (n+1)/(n-1)) is correct.
- **Parkinson (1980):** Uses high-low range. Correct for GBM with no drift.
- **Rogers-Satchell (1991):** Correct for processes with drift (unlike Garman-Klass).
- **Hodges-Tompkins:** Bias-corrected version. Implementation looks correct.
- **Skew & Kurtosis:** Standard moment estimators.

**Verdict:** ✅ Excellent. All estimators are mathematically correct and match the published formulas. This is a reference implementation.

---

### 3. goldspanlabs/optopsy (1,353 stars)
**URL:** https://github.com/goldspanlabs/optopsy
**Language:** Python (uses uv, ruff, ty)
**Size:** ~49,000 lines (including tests)

**Strengths:**
- Full options backtesting library with 38+ strategies
- Supports: long/short calls/puts, vertical spreads, iron condors, butterflies, straddles, strangles, calendars, diagonals, ratio spreads, collars, and more
- Clean architecture: strategies → core engine → rules → definitions
- Data feeds: CSV import with flexible column mapping, EODHD API provider
- AI chat UI (Chainlit + LiteLLM) for interactive backtesting
- Proper test suite with pytest
- Modern Python tooling (uv, ruff, ty)

**Math/Physics Accuracy:**
- P&L calculation: Correctly computes entry/exit prices, multi-leg positions
- Strike validation: Proper ordering rules (ascending for butterflies, equal-width wings)
- DTE filtering, OTM % filtering, bid-ask spread filtering
- Delta targeting support

**Verdict:** ✅ Excellent. This is the most complete open-source options backtesting library I've found. Architecture is clean, math is correct, and it's actively maintained.

---

### 4. Lumiwealth/lumibot (1,587 stars)
**URL:** https://github.com/Lumiwealth/lumibot
**Language:** Python

**Strengths:**
- Full trading framework: backtesting + live trading
- Supports stocks, options, crypto, futures, forex
- Data sources: Alpaca, Polygon, Yahoo Finance, FRED
- Strategy abstraction with proper event-driven backtesting
- ML agent support

**Verdict:** ✅ Good for live trading infrastructure. More of a framework than a strategy library.

---

## Tier 2: Specialized / Niche

### 5. Matteo-Ferrara/gex-tracker (191 stars)
**URL:** https://github.com/Matteo-Ferrara/gex-tracker
**Language:** Python

**Strengths:**
- Gamma Exposure (GEX) tracker for SPX/SPY
- Calculates dealer gamma positioning from options chain data
- GEX = Σ(Γ × OI × 100 × S) for calls, negative for puts

**Math/Physics Accuracy:**
- GEX formula is standard: Γ × Open Interest × Contract Multiplier × Spot Price
- Sign convention: Long gamma (dealer buying) = positive, short gamma (dealer selling) = negative
- References CBOE data correctly

**Verdict:** ✅ Good for GEX calculation. We already have this cloned.

---

### 6. alexgolec/tda-api (1,333 stars)
**URL:** https://github.com/alexgolec/tda-api
**Language:** Python

**Strengths:**
- TD Ameritrade (now Schwab) API client
- Historical data, options chains, streaming order book
- OAuth2 authentication

**Verdict:** ✅ Useful for Schwab integration. Well-maintained.

---

### 7. panosp0/Hawkes-Processes-trading-analysis (small)
**URL:** https://github.com/panosp0/Hawkes-Processes-trading-analysis-and-custom-Amplitude-indicator-ML-features

**Strengths:**
- Hawkes process for trade arrival modeling
- Amplitude index as trend identifier
- ML feature engineering from Hawkes parameters

**Math/Physics Accuracy:**
- Hawkes process: λ(t) = μ + Σ α×exp(-β(t-tᵢ)) — standard self-exciting process
- Parameters: μ (baseline intensity), α (excitation magnitude), β (decay rate)
- Correct for modeling clustered trade arrivals and flash crashes

**Verdict:** ✅ Good for market microstructure research. Niche but mathematically sound.

---

## Repos Already Cloned (from previous rounds)

### Existing GEX repos:
- `Matteo-Ferrara/gex-tracker` — GEX tracker (191 stars)
- `Proshotv2/Gamma-Vanna-Options-Options-Exposure` — Gamma/Vanna exposure (17 stars)
- `iAmGiG/gex-llm-patterns` — LLM + GEX analysis (21 stars)

### Existing options repos:
- `yzoz/python-option-calculator` — Black-Scholes, Greeks
- `MattL922_implied-volatility` — IV calculation
- `kyosenergy_options-calculator` — Options calculator
- `EsterHlav_Black-Scholes-Option-Pricing-Model` — BS model

### Existing microstructure repos:
- `TechfaneTechnologies_QtsApp` — QtsApp for market data
- `wnnii_Unusual-Options` — Unusual options activity

---

## Key Findings & Recommendations

### What to integrate from new repos:

1. **volatility-trading** → Use the 7 volatility estimators (Garman-Klass, Yang-Zhang, etc.) for realized vol calculation. More robust than simple close-to-close.

2. **optopsy** → Reference implementation for options backtesting. Study their strategy definitions and P&L calculation for our own backtesting engine.

3. **quant-trading/VIX Calculator** → The VIX calculation is textbook-correct. We should replicate this for our own VIX-style fear index.

4. **lumibot** → Study their live trading architecture for our paper→live transition.

5. **tda-api** → Direct Schwab API integration path.

### Mathematical correctness assessment:
All reviewed repos implement their formulas correctly. No errors found in:
- Volatility estimators (Garman-Klass, Yang-Zhang, Parkinson, Rogers-Satchell)
- VIX calculation (CBOE variance swap replication)
- GEX calculation (standard gamma × OI × spot)
- Black-Scholes Greeks (standard formulas)
- Hawkes process (standard self-exciting point process)

### Gaps identified:
- No repo implements VPIN (Volume-Synchronized PIN) correctly — we already have our own
- No repo has a complete gamma exposure heatmap with real-time data — we built this
- No repo combines order flow toxicity with options Greeks — our unique value prop
- Most repos lack proper risk management (circuit breakers, position sizing) — we've built this
