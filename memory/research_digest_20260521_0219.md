# Research Digest — 2026-05-21 02:19 UTC

## Run #2 | Papers discovered: 110

## Top Papers

### Inferring Latent Market Forces: Evaluating LLM Detection of Gamma Exposure Patterns via Obfuscation Testing
- **ID**: arxiv:2512.17923
- **URL**: https://arxiv.org/abs/2512.17923
- **Abstract**: We introduce obfuscation testing, a novel methodology for validating whether large language models detect structural market patterns through causal reasoning rather than temporal association. Testing 

### Dynamic slippage control and rejection feedback in spot FX market making
- **ID**: arxiv:2603.07752
- **URL**: https://arxiv.org/abs/2603.07752
- **Abstract**: We study an OTC FX market-making problem, built on the Avellaneda-Stoikov tradition, in which a dealer streams size-dependent quotes on a discrete ladder and manages inventory risk over a finite horiz

### Option market making with hedging-induced market impact
- **ID**: arxiv:2511.02518
- **URL**: https://arxiv.org/abs/2511.02518
- **Abstract**: This paper develops a model for option market making in which the hedging activity of the market maker generates price impact on the underlying asset. The option order flow is modeled by Cox processes

### Multi-asset market making under the quadratic rough Heston
- **ID**: arxiv:2212.10164
- **URL**: https://arxiv.org/abs/2212.10164
- **Abstract**: Given the promising results on joint modeling of SPX/VIX smiles of the recently introduced quadratic rough Heston model, we consider a multi-asset market making problem on SPX and its derivatives, e.g

### An approximate solution for options market-making in high dimension
- **ID**: arxiv:2009.00907
- **URL**: https://arxiv.org/abs/2009.00907
- **Abstract**: Managing a book of options on several underlying involves controlling positions of several thousands of financial assets. It is one of the most challenging financial problems involving both pricing an

### Trading Strategy with Stochastic Volatility in a Limit Order Book Market
- **ID**: arxiv:1602.00358
- **URL**: https://arxiv.org/abs/1602.00358
- **Abstract**: In this paper, we employ the Heston stochastic volatility model to describe the stock's volatility and apply the model to derive and analyze the optimal trading strategies for dealers in a security ma

### A Wiener Chaos Approach to Martingale Modelling and Implied Volatility Calibration
- **ID**: arxiv:2602.16232
- **URL**: https://arxiv.org/abs/2602.16232
- **Abstract**: Calibration to a surface of option prices requires specifying a suitably flexible martingale model for the discounted asset price under a risk-neutral measure. Assuming Brownian noise and mean-square 

### Deep Hedging with Reinforcement Learning: A Practical Framework for Option Risk Management
- **ID**: arxiv:2512.12420
- **URL**: https://arxiv.org/abs/2512.12420
- **Abstract**: We present a reinforcement-learning (RL) framework for dynamic hedging of equity index option exposures under realistic transaction costs and position limits. We hedge a normalized option-implied equi

### Forecasting implied volatility surface with generative diffusion models
- **ID**: arxiv:2511.07571
- **URL**: https://arxiv.org/abs/2511.07571
- **Abstract**: Diffusion Probabilistic Model (DDPM) for generating one-day-ahead arbitrage-free implied volatility surfaces. To capture the path-dependent nature of volatility dynamics, we condition our model on a s

### Tail-Safe Stochastic-Control SPX-VIX Hedging: A White-Box Bridge Between AI Sensitivities and Arbitrage-Free Market Dynamics
- **ID**: arxiv:2510.15937
- **URL**: https://arxiv.org/abs/2510.15937
- **Abstract**: We present a white-box, risk-sensitive framework for jointly hedging SPX and VIX exposures under transaction costs and regime shifts. The approach couples an arbitrage-free market teacher with a contr

## Recent Findings from Cloned Repos

### Findings batch 1
# Research Pipeline Findings — 2026-05-19

## Papers Discovered: 79 (arxiv, 0 errors)

## New Repos Cloned: 2

### 1. asridi/DML-Calibration-Heston-Model
- **Paper**: "Applying Deep Learning to Calibrate Stochastic Volatility Models" (arxiv:2309.07843)
- **Content**: Jupyter notebooks for Heston model calibration using deep learning
- **Relevance**: ML-based Heston calibration — could validate our vol_analytics.py Heston implementation
- **Key files**: Calibration.ipynb, DataGeneration.ipynb
- **Status**: Cloned successfully

### 2. owen8877/RLOP
- **Paper**: "RLOP: RL Methods in Option Pricing from a Mathematical Perspective" (arxiv:2205.05600)
- **Content**: Full options pricing library with:
  - Black-76 pricing + robust IV bisection solver
  - Merton jump-diffusion pricing (Poisson mixture of B76)
  - Heston characteristic function + Simpson's rule integration
  - Data preprocessing for American → European conversion
  - Deribit crypto options adapter
  - Hedging metrics and history analysis
- **Relevance**: HIGH — production-quality reference implementations for:
  - `bs_greeks.py` (B76 pricing, IV solver)
  - `vol_analytics.py` (Heston CF, characteristic function)
  - Data pipeline (American → European conversion, parity inference)
- **Key files**: options_pricing_baselines_v7.py (1630 lines), hedging_metrics_hist.py
- **Status**: Cloned successfully (needed git-lfs)

## Techniques Worth Porting

### 1. Robust IV Bisection (from RLOP)
- Bracket expansion (b *= 1.5) when

## State: run #2
- Last HF search: 2026-05-21T02:19:33.901282+00:00
- Last digest: 2026-05-20T02:48:27.863173+00:00
