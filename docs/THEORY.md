# THEORY.md — Trading System Theory Bible

## 1. Easley/López de Prado VPIN

### Intuition
VPIN (Volume-Synchronized Probability of Informed Trading) measures flow toxicity —
the fraction of volume that comes from informed traders rather than liquidity
providers. High VPIN means the market is more likely to move against you because
informed traders are actively trading.

### Math
The core is Bulk Volume Classification (BVC). Given price changes Δp_i and volumes v_i
over a window:

    buy_volume  = Σ Φ(Δp_i / (σ · √dt)) · v_i
    sell_volume = Σ (1 - Φ(Δp_i / (σ · √dt))) · v_i

where Φ is the standard normal CDF. VPIN is then:

    VPIN = |buy_volume - sell_volume| / (buy_volume + sell_volume)

aggregated over rolling buckets of equal volume (not equal time).

### Hermes Code Pointer
- `services/vpin_engine.py:VpinEngine.classify_volume` — BVC step
- `services/vpin_engine.py:VpinEngine.update` — rolling bucket state
- `services/vpin_engine.py:VpinEngine.get_state` — current VPIN value

---

## 2. Hagan SABR Model

### Intuition
SABR (Stochastic Alpha Beta Rho) models the forward price F and its stochastic
volatility α as correlated Brownian motions. It produces a closed-form approximation
for implied volatility as a function of strike, which fits market smiles remarkably
well with just 4 parameters.

### Math
The SABR dynamics:
    dF = α · F^β · dW₁
    dα = ν · α · dW₂
    dW₁ · dW₂ = ρ · dt

Hagan's asymptotic expansion for Black-equivalent implied vol:

    σ_B(K,F) = α / F^(1-β) · [1 + ((1-β)²α²/(24F^(2-2β)) + ρβνα/(4F^(1-β)) + (2-3ρ²)ν²/24) · T]

Parameters: α (vol level), β (backbone: 0=normal, 0.5=stochastic vol, 1=lognormal),
ρ (skew), ν (vol-of-vol).

### Hermes Code Pointer
- `services/stochastic_vol.py:SABRModel.hagan_lognormal_vol` — closed-form vol
- `services/stochastic_vol.py:SABRModel.fit` — Levenberg-Marquardt calibration

---

## 3. Gatheral SVI Model

### Intuition
SVI (Stochastic Volatility Inspired) parameterizes total variance w(k) = σ²T as a
function of log-moneyness k = ln(K/F). It guarantees no-arbitrage under simple
parameter constraints and fits both the wings and ATM of the smile.

### Math
Raw SVI: w(k) = a + b · (ρ · (k - m) + √((k - m)² + σ²))

Parameters: a (vertical shift), b (wing slope), ρ (skew), m (horizontal shift),
σ (ATM curvature). No-arbitrage constraints: b ≥ 0, |ρ| < 1, a ≥ 0.

### Hermes Code Pointer
- `services/stochastic_vol.py:SVIProfile.fit` — SVI calibration per expiry
- `services/stochastic_vol.py:SVIProfile.implied_vol` — IV from SVI params

---

## 4. Bacry-Mastromatteo Hawkes Process

### Intuition
A Hawkes process is a self-exciting point process: each event (trade) increases the
probability of future events. In finance, this captures trade clustering — informed
trades tend to arrive in bursts. The branching ratio n = α/β measures the fraction
of events that are "children" of previous events.

### Math
Conditional intensity: λ(t) = μ + Σ_{t_i < t} α · e^(-β(t - t_i))

where μ is the baseline rate, α is the excitation magnitude, and β is the decay rate.
The branching ratio n = α/β must be < 1 for stability (subcritical regime).

### Hermes Code Pointer
- `services/hawkes_process.py:HawkesProcess.intensity` — λ(t) computation
- `services/hawkes_process.py:HawkesProcess.fit` — MLE parameter estimation
- `services/hawkes_process.py:HawkesProcess.simulate` — Ogata's thinning algorithm

---

## 5. Kyle's Lambda

### Intuition
Kyle's λ measures price impact — how much the price moves per unit of order flow.
In a market with informed traders and market makers, the equilibrium price impact
is linear in the net order flow. Higher λ means the market is less liquid.

### Math
λ = Cov(returns, signed_volume) / Var(signed_volume)

Estimated via OLS: r_t = λ · signed_vol_t + ε_t

where signed_volume is positive for buyer-initiated trades and negative for
seller-initiated trades.

### Hermes Code Pointer
- `services/liquidity_metrics.py:KyleLambda.update_from_prices` — ingest trades
- `services/liquidity_metrics.py:KyleLambda.compute` — OLS estimator

---

## 6. Amihud Illiquidity

### Intuition
The Amihud ILLIQ measure captures the price impact per dollar of trading volume.
It's the average absolute return divided by dollar volume. Higher values mean
the stock is more illiquid — small trades cause large price moves.

### Math
ILLIQ_t = mean(|r_t| / dollar_volume_t) × 10⁶

where r_t is the daily return and dollar_volume_t is the trading volume in dollars.
The 10⁶ scaling is conventional (units: per million dollars).

### Hermes Code Pointer
- `services/liquidity_metrics.py:AmihudIlliquidity.update` — ingest daily data
- `services/liquidity_metrics.py:AmihudIlliquidity.compute` — rolling mean

---

## 7. Trinity Alignment

### Intuition
When SPX, SPY, and QQQ all have zero-gamma levels (strikes where net dealer gamma
flips sign) near the same price, it indicates strong dealer hedging alignment.
This creates a "magnetic" level — price is likely to be attracted to this zone
because dealers' hedging flows all push in the same direction.

### Math
1. Find zero-gamma levels for each instrument (SPX normalized to SPY scale by ÷10)
2. Group levels within tolerance_pct (default 0.5%)
3. Score = Σ [min(n_instruments/3, 1) × 40 + (1 - spread_pct/(tolerance×100)) × 30]
4. Clamp to [0, 100]. Regime: STRONG (≥75), MODERATE (≥50), WEAK (≥25), NONE (<25)

### Hermes Code Pointer
- `services/trinity_alignment.py:TrinityAlignmentIndex.compute` — full scoring
- `services/trinity_alignment.py:TrinityAlignmentIndex._find_alignments` — grouping

---

## 8. Market Fragility Index

### Intuition
Market fragility is a composite score that combines multiple liquidity and toxicity
metrics into a single 0-100 measure. When fragility is high, the market is prone
to sudden moves, flash crashes, and liquidity evaporation.

### Math
Components (z-scored against rolling history, sigmoid-normalized to [0,1]):
- Kyle's Lambda (weight 0.25)
- Amihud ILLIQ (weight 0.20)
- VPIN CDF (weight 0.25)
- Quote Imbalance z-score (weight 0.15)
- Bid-Ask Spread z-score (weight 0.15)

Score = Σ(w_i · sigmoid(z_i)) × 100

Regime: NORMAL (<33), ELEVATED (33-66), CRISIS (≥66)

### Hermes Code Pointer
- `services/liquidity_metrics.py:MarketFragilityIndex.compute` — composite score
- `services/liquidity_metrics.py:MarketFragilityIndex._zscore` — z-score computation

---

## 9. Causal Inference in Flow Toxicity

### Motivation
Correlation between VPIN/QI and SPY returns does not imply causation. This section presents rigorous causal analysis to determine whether flow toxicity signals *cause* price movements or merely correlate with them.

### 9.1 Granger Causality Tests

**Method:** Vector autoregression (VAR) with F-test for lag significance. Tests whether lagged values of VPIN CDF or Quote Imbalance improve predictions of future returns/volatility beyond what past returns/volatility alone provide.

**Data:** SPY daily features, 103 observations (2024), VPIN computed via Bulk Volume Classification on daily OHLCV, QI proxy from put_call_ratio and overnight_gap.

**Results:**

| Test | Optimal Lag | F-Statistic | P-Value | Significant |
|------|------------|-------------|---------|-------------|
| VPIN CDF → SPY Returns | 4 | 0.518 | 0.723 | No |
| Quote Imbalance → SPY Returns | 8 | 0.988 | 0.452 | No |
| VPIN CDF → SPY Volatility | 5 | 1.062 | 0.387 | No |
| Quote Imbalance → SPY Volatility | 6 | 2.782 | 0.016 | Yes * |

**Interpretation:**
- VPIN CDF does NOT Granger-cause SPY returns or volatility at daily frequency (p > 0.05).
- Quote Imbalance DOES Granger-cause SPY volatility (p = 0.016), with consistent significance across lags 4-10.
- The QI → Volatility result suggests that order flow imbalance has predictive power for future volatility, even if not for direction.
- VPIN's failure at daily frequency is expected: the Easley/López de Prado framework is designed for tick-level data where volume-clock sampling captures intraday informed trading.

### 9.2 Double Machine Learning (DML) Treatment Effects

**Method:** EconML LinearDML with GradientBoosting nuisance models. Estimates the Average Treatment Effect (ATE) of VPIN CDF on next-day SPY returns, controlling for confounders (realized volatility, volume, GEX, put/call ratio, ATR, day of week, month).

**Treatment:** VPIN CDF (continuous, 0-1)
**Outcome:** Next-day SPY return (ret_1d)
**Confounders:** realized_vol_10d, realized_vol_21d, relative_volume, net_gex, put_call_ratio, atr_14, day_of_week, month

**Results:**

| Regime | ATE | 95% CI | N | Significant |
|--------|-----|--------|---|-------------|
| Overall | 0.0243 | [0.0161, 0.0325] | 115 | Yes |
| Calm (low vol) | 0.0029 | [-0.0037, 0.0096] | 58 | No |
| Urgent (high vol) | 0.0317 | [0.0217, 0.0418] | 57 | Yes |

**Interpretation:**
- The overall ATE is statistically significant: a unit increase in VPIN CDF (0→1) is associated with a 2.43% increase in next-day returns, controlling for confounders.
- The effect is regime-dependent: in calm markets, VPIN has no significant causal effect; in urgent (high volatility) markets, the effect is 10x larger (3.17%).
- This regime dependence is critical for strategy design: VPIN-based signals should be weighted more heavily during volatile periods.
- The calm regime's non-significance suggests that in low-volatility environments, VPIN is mostly noise.

**Conditional ATE by VPIN Quantile:**

| VPIN Quantile | ATE | N |
|---------------|-----|---|
| Q4 (high) | 0.0161 | 29 |
| Q3 | -0.0166 | 28 |
| Q2 | 0.0025 | 29 |
| Q1 (low) | 0.1986 | 29 |

The Q1 (low VPIN) high ATE is likely a boundary artifact from the small sample and the non-linear relationship between VPIN and returns. The negative Q3 ATE suggests an inverted-U relationship: moderate VPIN may predict negative returns while very high VPIN predicts positive ones (short squeeze / gamma squeeze dynamics).

### 9.3 Counterfactual Analysis

**Method:** Simulated three strategies on 2024 data:
1. **Baseline:** Buy and hold SPY
2. **VPIN-Filtered:** Reduce position 50% when VPIN CDF > 0.7
3. **DML-Weighted:** Position sized by DML-estimated causal effect

**Results:**

| Metric | Baseline | VPIN-Filtered | DML-Weighted |
|--------|----------|---------------|--------------|
| Total Return | 19.19% | 13.27% | 20.27% |
| Annualized Sharpe | 2.86 | 2.17 | 3.10 |
| Max Drawdown | -5.22% | -5.22% | -4.91% |

**Interpretation:**
- Simple VPIN threshold filtering UNDERPERFORMED buy-and-hold by 5.93% in 2024's bull market (being out of the market was costly).
- DML-weighted positioning OUTPERFORMED by 1.08% with better Sharpe (3.10 vs 2.86) and lower max drawdown.
- The DML approach's advantage comes from using the continuous causal estimate rather than a binary threshold, demonstrating that *how* you use the causal signal matters.
- In a bear market or high-volatility regime, VPIN filtering would likely show greater benefit (per the DML regime analysis).

### 9.4 Implications for Strategy Robustness

1. **VPIN is regime-dependent:** The signal's causal power is concentrated in high-volatility regimes. Strategies should modulate VPIN weight by regime.

2. **Quote Imbalance > VPIN for volatility prediction:** QI Granger-causes volatility (p=0.016) while VPIN does not. For volatility-targeting strategies, QI is the stronger signal.

3. **DML > threshold rules:** The DML-weighted approach outperformed binary threshold filtering. Continuous causal estimates provide more nuance than binary signals.

4. **Daily VPIN is a proxy:** The lack of Granger causality for VPIN (vs. the significant DML result) suggests that daily-frequency VPIN captures some signal but loses the intraday dynamics that make VPIN powerful. Tick-level data would likely strengthen all results.

5. **Causal ≠ profitable:** Even with a significant causal effect, the edge (1.08% annual alpha from DML weighting) is modest and may not survive transaction costs. The value is in risk reduction (lower max drawdown) rather than raw return enhancement.

### Hermes Code Pointer
- `scripts/causal_analysis_granger.py` — Granger causality test suite
- `scripts/causal_analysis_dml.py` — Double Machine Learning analysis
- `scripts/causal_analysis_counterfactual.py` — Counterfactual simulation
- `reports/causal_granger_*.md` — Granger test reports
- `reports/causal_dml_*.md` — DML analysis reports
- `reports/counterfactual_*.md` — Counterfactual analysis reports
