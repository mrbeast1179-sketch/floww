# Proprietary research and trading-farm standard

This standard governs research, data, signals, UI claims, replay, paper orders,
and evaluation. It is designed for institutional rigor, not institutional
branding.

## Evidence hierarchy

- L3/order-event data with venue sequence and corrections may support observed
  order-event claims within its licensed scope.
- L1/L2 quotes support book-state and quote-change inference, not aggressor
  identity unless the feed supplies it.
- Options open interest is delayed aggregate positioning. Its change is not a
  signed trade and does not identify buy-side institutions.
- Chain call/put volume and underlying returns can form a liquidity proxy. They
  are not Kyle's original signed order-flow input or Amihud's canonical equity
  dollar volume unless the implementation proves those inputs.
- Dealer-Greek exposure depends on explicit positioning/sign assumptions. VEX,
  charm, gamma, and vomma walls are modeled concentrations, not observed dealer
  books.
- HMM state labels are relative regimes of their configured features. They do not
  establish cause, identity, or future return.

## Point-in-time dataset contract

Every normalized row carries source, schema version, instrument identity, event
time, receive time, sequence if available, correction/cancel state, entitlement
mode, delay, raw/derived class, and quality flags. Corporate actions and symbol
mapping are time-versioned. Training/evaluation data is reconstructable as known
at the decision timestamp.

Raw proprietary retention, replay, redistribution, screenshots, and derived-data
rights remain UNKNOWN until the actual agreement is recorded. In the meantime,
agents may build schemas and synthetic conformance fixtures but must not store or
publish vendor payloads.

## Research acceptance

A candidate signal needs:

- frozen hypothesis and formula before evaluation;
- train/validation/test or walk-forward splits with purge/embargo where labels
  overlap;
- a realistic comparator and an ablation for every added input;
- multiple-testing control and a registry of failed hypotheses;
- stability across symbols, regimes, time buckets, and data-quality strata;
- fees, spread, slippage, latency, fill probability, rejects, capacity, and
  borrow/locate constraints where applicable;
- calibration/reliability evidence for scores presented as probabilities;
- reproducible artifact hashes and data/code versions.

No Sharpe, hit rate, P&L, or speed claim is accepted without sample window,
universe, timestamp convention, costs, baseline, uncertainty, and limitations.
Synthetic/mocked results stay labeled synthetic/mocked.

## Shadow-to-paper progression

1. Offline deterministic fixtures.
2. Historical point-in-time replay.
3. Live shadow reads with public-source comparator and no consumer preference.
4. Paper decisions with no order submission.
5. Explicitly authorized paper orders with venue receipts.

Each stage needs quality thresholds and rollback conditions before the next. No
stage in this harness authorizes live capital.

## Current Floww corrections

- `multi_level_ofi.py`: tested research module; verify a production importer
  before calling it wired.
- `composite_flow_score.py` and `hmm_regime.py`: production importers exist; their
  labels remain model/proxy outputs.
- `chain_replay.py`: do not infer production wiring from docstrings or tests;
  verify an executable importer/caller.
- PR51 liquidity state: option-chain interval proxy, not institutional flow.
- PR52 vomma walls: modeled exposure concentration; units, dealer-sign assumption,
  calibration, and economic validation remain review surfaces.
- PR53 vectorization: performance/equivalence engineering, not new alpha.
- `alertEngineBadges.js`: tested mapper is currently not equivalent to rendered UI.

The governing principle is simple: richer data may improve measurement quality;
it never upgrades an unverified claim by vocabulary alone.

