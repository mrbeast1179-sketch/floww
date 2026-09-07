## Destination

Floww has enough settled provider, entitlement, semantic, retention, rollout, and
acceptance decisions to file independent contract-grade issues for a shadow-tested
proprietary market-data plane without changing existing signal meaning.

## Decisions so far

- Floww remains paper/simulation only; this data transition does not authorize live execution.
- Public API remains the comparator and rollback source during shadow operation.
- Provider adapters terminate at normalized contracts with field-level provenance; consumers do not depend on vendor payloads.
- Quote-derived side and aggregate proxies remain labeled separately from exchange-reported trades.
- Frozen ML/model artifacts and the dual GEX scale convention do not change in this program.

## Decision frontier

### D-1 — Establish the actual proprietary source and entitlements

Type: Prerequisite
Question: Which vendor/feed/account is in scope, and exactly which real-time, delayed, historical, OPRA, equities, index-options, Greeks, OI, and redistribution entitlements are active?
Needs: None.
Issue: Pending.

### D-2 — Define authoritative event and correction semantics

Type: Research
Question: For each entitled surface, which timestamps, sequences, venue identifiers, condition codes, corrections/cancels, crossed/locked quotes, and missing fields are authoritative?
Needs: D-1
Issue: Pending.

### D-3 — Set licensing, retention, and display boundaries

Type: Research
Question: What may Floww store, replay, transform, display, and expose to other users, and for how long, under the active agreement?
Needs: D-1
Issue: Pending.

### D-4 — Choose shadow acceptance and rollback thresholds

Type: Discussion
Question: Which coverage, freshness, gap, duplicate, correction, parity, latency, and cost thresholds must hold before a consumer can prefer the proprietary source, and which breach rolls it back?
Needs: D-2, D-3
Issue: Pending.

### D-5 — Choose replay retention and recovery objectives

Type: Discussion
Question: What raw/normalized retention window, replay granularity, recovery point, recovery time, and deletion behavior does this program require?
Needs: D-2, D-3
Issue: Pending.

### D-6 — Choose user-visible provenance and degraded-state behavior

Type: Discussion
Question: Which source, age, coverage, delayed/real-time, correction, and fallback states must the UI expose, and when must a signal be withheld instead of degraded?
Needs: D-4
Issue: Pending.

## Not yet specified

- Provider-specific authentication, SDK/client, subscription topology, and reconnect protocol.
- Canonical OCC/OSI/root symbology mappings and corporate-action backfill mechanics.
- Concrete storage engine sizing and partitioning, which depend on entitled message volume and retention.
- Consumer cutover order, which depends on the shadow acceptance contract.

## Out of scope

- Automated live-order execution.
- New alpha, thresholds, causal claims, or ML retraining merely because richer data is available.
- Direct-exchange/Kafka/Flink/ClickHouse infrastructure before D-1 proves its need and entitlement.
- Replacing the current Tidehunter UI before the B0 redesign artifacts and Nav visual sign-off exist.
- Folding the separate `swarmSPX` repository into Floww.

## Delivery slices

None.

## Graduation

Not ready.

## Queue issues

None.
