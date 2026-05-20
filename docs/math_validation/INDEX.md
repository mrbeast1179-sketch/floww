# Math Validation Index

This directory documents the mathematical correctness of every Hermes microstructure
kernel. Each file covers one formula: its source paper, the Hermes implementation,
the reference implementation it was cross-validated against, and the parity verdict.

## Formula Index

| Formula | Hermes Implementation | Reference Repo | Parity Verdict | Test File |
|---------|----------------------|----------------|----------------|-----------|
| BSM Gamma | `services/numba_greeks.py:bs_gamma_vec` | FlashAlpha-lab_gex-explained `compute_gex.py:bsm_gamma` | PASS (rel-err < 1e-4) | `test_reference_parity.py::TestParityFlashAlphaGex` |
| BSM Call/Put Price | `services/numba_greeks.py:bs_call_price_vec` / `bs_put_price_vec` | boyac_pyOptionPricing `black_scholes.py:BlackScholes` | PASS (rel-err < 1e-4) | `test_reference_parity.py::TestParityBoyacBlackScholes` |
| GEX (SpotGamma) | `services/gex_aggregator.py:GexAggregator.compute` | FlashAlpha-lab_gex-explained `compute_gex.py:contract_gex` | PASS (rel-err < 1e-4) | `test_reference_parity.py::TestParityFlashAlphaGex` |
| GEX (CBOE) | `services/gex_aggregator.py:GexAggregator.compute` | Matteo-Ferrara_gex-tracker `main.py:compute_total_gex` | PASS (sign + magnitude) | `test_reference_parity.py::TestParityCBOEGex` |
| BSM Gamma (TS) | `services/numba_greeks.py:bs_gamma_vec` | FullStackCraft_floe `src/blackscholes/index.ts` | PASS (hand-translated) | `test_reference_parity.py::TestParityFullStackCraftFloe` |
| GEX Aggregation | `services/gex_aggregator.py:GexAggregator.compute` | iAmGiG_gex-llm-patterns (patterns) | PASS (ATM peak, zero-gamma) | `test_reference_parity.py::TestParityIAmGiGGexPatterns` |
| VPIN BVC | `services/vpin_engine.py:VpinEngine.classify_volume` | Easley/LdP 2012 (paper) | PASS (identity tests) | `test_microstructure_math.py::TestVpinClassification` |
| Hawkes Intensity | `services/hawkes_process.py:HawkesProcess.intensity` | Bacry/Mastromatteo/Muzy 2015 (paper) | PASS (analytical + MLE) | `test_microstructure_math.py::TestHawkesProcess` |
| SABR Hagan Vol | `services/stochastic_vol.py:SABRModel.hagan_lognormal_vol` | Hagan et al. 2002 (paper) | PASS (closed-form identity) | `test_microstructure_math.py::TestSABR` |
| Kyle Lambda | `services/liquidity_metrics.py:KyleLambda.compute` | Kyle 1985 (paper) | PASS (OLS recovery) | `test_microstructure_math.py::TestKyleLambda` |
| Amihud ILLIQ | `services/liquidity_metrics.py:AmihudIlliquidity.compute` | Amihud 2002 (paper) | PASS (ratio test) | `test_microstructure_math.py::TestAmihudIlliquidity` |
| Trinity Alignment | `services/trinity_alignment.py:TrinityAlignmentIndex.compute` | Custom (SPX/SPY/QQQ ZG confluence) | PASS (score bounds) | `test_microstructure_math.py::TestTrinityAlignment` |
| Market Fragility | `services/liquidity_metrics.py:MarketFragilityIndex.compute` | Custom (weighted composite) | PASS (regime classification) | `test_microstructure_math.py::TestMarketFragilityIndex` |
| Node Lifecycle | `services/node_lifecycle.py:NodeLifecycleTracker` | Custom (state machine) | PASS (transition tests) | `test_microstructure_math.py::TestNodeLifecycle` |
| Anomaly Detector | `services/anomaly_detector.py:StatisticalAnomalyDetector` | Ozbayoglu et al. 2020 (paper) | PASS (recall ≥95%) | `test_microstructure_math.py::TestAnomalyDetector` |
| Vol Surface | `services/stochastic_vol.py:VolSurfaceConstructor.build_surface` | Gatheral 2004 SVI + Hagan 2002 SABR | PASS (monotonicity) | `test_microstructure_math.py::TestVolSurfaceConstructor` |

## Version Pins

| Reference Repo | Commit SHA (at parity time) |
|----------------|----------------------------|
| FlashAlpha-lab_gex-explained | `HEAD` (cloned 2026-05-20) |
| boyac_pyOptionPricing | `HEAD` (cloned 2026-05-20) |
| Matteo-Ferrara_gex-tracker | `HEAD` (cloned 2026-05-20) |
| FullStackCraft_floe | `HEAD` (cloned 2026-05-20) |
| iAmGiG_gex-llm-patterns | `HEAD` (cloned 2026-05-20) |

## How to Run

```bash
# All math validation tests
cd backend && python -m pytest tests/services/test_microstructure_math.py -v

# Reference parity tests only
cd backend && python -m pytest tests/services/test_reference_parity.py -v

# Specific test class
cd backend && python -m pytest tests/services/test_reference_parity.py::TestParityFlashAlphaGex -v
```
