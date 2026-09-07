# Proprietary-data engineering roadmap

Status: architectural proposal with explicit discovery dependencies. This does not certify a vendor subscription, firm-grade readiness or an investment edge. In Floww, “Public API” means the existing authenticated Public.com integration; it is not a promise of unrestricted public-domain data.

## Decisions before delivery

Resolve D-1..D-6 in PROPRIETARY-DATA-DISCOVERY-MAP.md: actual vendor/account entitlements, event semantics, permitted storage/display/redistribution, shadow acceptance, recovery objectives and UI degraded behavior. Use actual agreements and sample payloads. No price, free-tier access, feed completeness or Greek availability is inherited from the pasted inventory.

OPRA publishes separate subscriber/vendor and non-display materials; the account owner must identify what applies to this deployment. [OPRA document library](https://www.opraplan.com/document-library).

## Delivery graph

```text
entitled source + semantic contract
  -> capture/quarantine -> normalization -> deterministic replay
                         -> shadow comparator -> consumer router
                                              -> UI provenance
  -> correction/gap recovery + budgets/observability
  -> independent fault/load proof -> staged consumer cutover -> rollback drill
```

Each row below becomes a small six-section contract after its prerequisite decisions close. Storage/queue technology follows measured volume and retention needs; Kafka/Flink/ClickHouse are options, not automatic requirements.

| Candidate | Owner | Minimum proof |
|---|---|---|
| PD1 schema/identity | Backend +Proof | SPX index versus SPY ETF; OCC/OSI/root identity, multiplier/currency/units, null versus zero, version compatibility |
| PD2 capture | Backend | Entitled sanitized fixtures; auth errors redacted; reconnect/backpressure; bounded resources; raw provenance and quarantine |
| PD3 time/order/corrections | Backend +Proof | Event time and receive time separated; sequence scope documented; duplicate idempotency; late/cancel/correct replay; session/DST/holiday cases |
| PD4 replay/storage | Backend +Proof | Content hashes, schema/config/code versions, event ordering, retention/deletion contract, restart/recovery and reproducible output |
| PD5 shadow comparator | Backend +Proof | Same instrument/session/as-of state; freshness/coverage/null/Greek/OI semantic differences classified; no blind value-equality metric |
| PD6 routing/fallback | Backend | Per-consumer source policy; staleness and disagreement explicit; no field-level mixing without provenance; rollback trigger fixtures |
| PD7 UI provenance | Frontend | Source, as-of age, delayed/real-time, coverage and estimate labels; degraded states; no invented listed strikes or executable quotes |
| PD8 operations | Backend +Proof | Request/fan-out and subscription budgets; lag, gaps, dropped frames, quarantine and spend visibility; restart and replay runbook |
| PD9 qualification | Proof | Deterministic chaos matrix, representative load measurements, adverse-market fixtures, recovery drill and contract-by-contract verdict |
| PD10 cutover | Architect/Nav | One consumer at a time; documented thresholds and rollback; actual deployed revision; human sign-off |

The requirement to preserve distinct event and receipt timestamps is compatible with vendor schemas such as Databento's trade records, which expose ts_event, ts_recv, publisher_id and instrument_id. This is a schema reference, not a vendor selection. [Databento trades schema](https://databento.com/docs/schemas-and-data-formats/trades).

## Quantitative research boundary

Data correctness precedes signal changes. Quote-derived side is a classification estimate, OI has its own update cadence, computed Greeks depend on model assumptions, and interpolated visual rows are not observations. Preserve the current S2 display/S1 feature convention until a separate model migration contract exists.

Research candidates must state hypothesis, target, point-in-time feature availability, baseline, costs/fill assumptions, train/test chronology, leakage checks and a falsification criterion before evaluation. Freeze the holdout; log every tried specification and dataset/config/code hash. Report uncertainty, missingness, regime dependence and failed hypotheses. Any sequential/multiple-test correction and sample-size threshold is a research design decision, not a decorative “PhD” requirement.

Trading simulations require contract identity, multi-leg positions where applicable, executable quote assumptions, fees, slippage, expiry/settlement and unresolved-price states. A missing quote cannot establish zero terminal value. Synthetic demonstrations and SPY-price proxy tests cannot satisfy options P&L validation.

## Harness qualification on Spark/Muse 1.3

Resolve the exact configured provider/model name before use. Perform a small offline capability check: read a permitted file, obey an exact file lease, report a tool exit faithfully, write/restore a checkpoint, and survive session replacement. Reuse existing fixtures; do not create product edits for the test. Record model/tool/context limits rather than assuming a brand name guarantees long-running execution.

Measure accepted task throughput, rework, unsupported completion claims, lost checkpoints, lease collisions and recovery time. Begin with the bounded prompts in this package; adjust the harness from observed failures. Explicit progress artifacts and incremental sessions follow the pattern described in [Anthropic's long-running-agent engineering article](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents). That article is evidence for the workflow pattern, not a benchmark for the requested host.
