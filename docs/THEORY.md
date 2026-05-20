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
