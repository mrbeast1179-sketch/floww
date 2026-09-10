# Ranked backlog — one admitted unit per builder

Agent 1 revalidates this list after every main merge. DONE work is never rebuilt.
Dependencies are hard gates, not suggestions.

## Wave 0 — finish the audited repair set

### G-54 — paper execution safety review and integration — DONE

- Merged: PR54 at `c4970a5` via `d5dbd7d` (2026-09-10).
- Delivered: stable venue client-order ID computed once per submission;
  lookup-before-submit and lookup after ambiguous response; confirmed-fill-only
  journal close; 97 focused tests green at merge head.
- Residual: pending/partial/rejected/canceled closes stay honest-pending;
  eventual reconciliation worker still required (EXEC-RECON-1).

### G-55 — kind-aware exposure copy review and integration

- Candidate: PR55 at its fetched remote head.
- Outcomes: PR50 subtype semantics reach main; CLUSTER remains; full frontend and
  build green; broken/approach copy remains truthful.
- Exclusions: no backend, global shell, new badges, or visual redesign.
- Owner: Agent 4 review, then Agent 1 merge if exact-head gates pass.

### G-56 — P2 dependency compatibility

- Candidate: PR56 at its fetched remote head.
- Outcomes: clean-CI application compatibility; direct-package advisories closed;
  remaining no-fix NLTK advisory recorded; requirements plus the narrowly scoped
  public-route-inventory compatibility test.
- Exclusions: no test weakening, no unrelated package churn, no claim that local
  `pip check` is clean.
- Owner: Agent 4 review, then Agent 1 merge only if all required CI passes.

## Wave 1 — correctness before new signal count

### EXEC-RECON-1 — eventual paper-close fill reconciliation

- Needs: G-54 merged.
- Builder: Agent 2.
- Deliverable: an idempotent reconciler that turns `pending_fill` into one journal
  close only after venue status `filled` and positive average fill price; canceled,
  rejected, partial, missing, and retry states stay honest.
- Required proof: deterministic broker mocks, restart replay, duplicate poll, partial
  fill, cancellation, and zero/invalid-price tests. No network witness.

### ALERT-API-1 — make alert-engine request inputs reach producers

- Builder: Agent 2.
- Deliverable: prove and fix current `/api/alerts/{ticker}` or snapshot plumbing so
  `momentum_score` and `volume_by_strike` reach the fields that actually consume
  them.
- Required proof: route-level RED/GREEN tests that cause only the intended alert;
  catalog semantics quoted from current source. No thresholding changes.

### ALERT-UI-1 — decide the dead mapper honestly

- Needs: ALERT-API-1 merged.
- Builder: Agent 3.
- Deliverable: either (a) wire one bounded UI surface that fetches the alert-engine
  endpoint with freshness/error, abort, degraded, empty, and unknown-rule behavior,
  or (b) delete the unused mapper/tests if product placement cannot be justified.
  Mapping tests alone do not count as surfacing.
- Required proof: mounted consumer test, stale ticker/race test, full frontend, build.

### DOC-TRUTH-1 — correct agent-produced institutional research prose

- Builder: Agent 1 (docs-only) with Agent 4 review.
- Deliverable: retire overclaiming `INSTITUTIONAL-EDGE-MEMO.md` as historical and
  point active work to `PROPRIETARY-RESEARCH-STANDARD.md`. Correct module wiring and
  importer/test counts using code-derived facts only; do not convert proxies into
  causal or tradable institutional-flow claims.

## Wave 2 — provider-neutral institutional research infrastructure

### DATA-CONTRACT-1 — normalized point-in-time event schema

- Needs: entitlement-specific fields remain optional/UNKNOWN.
- Builder: Agent 2.
- Deliverable: a provider-neutral schema and synthetic conformance suite for source,
  event/receive time, sequence, correction/cancel, instrument identity, freshness,
  delay/entitlement mode, quality flags, and fallback lineage.
- Exclusions: no vendor SDK, paid call, raw licensed row, retention promise, Kafka/
  Flink/ClickHouse, or consumer cutover.

### DATA-PROVENANCE-UI-1 — truthful source/degraded state

- Needs: DATA-CONTRACT-1 merged.
- Builder: Agent 3.
- Deliverable: bounded provenance/freshness/coverage/degraded rendering on one existing
  surface; unknown stays unknown and stale data cannot look live.

### RESEARCH-EVAL-1 — institutional evaluation harness

- Builder: Agent 2.
- Deliverable: point-in-time walk-forward evaluation primitives with purge/embargo,
  cost/slippage/latency inputs, capacity diagnostics, benchmark/ablation, and a failed-
  hypothesis registry. Start with synthetic fixtures and one existing proxy; do not
  claim alpha.

## Discovery-only queue

- XH-1: audit quote/side/sweep/block copy; label inference and preserve unknowns.
- X2: mounted Phase9 consumer/responsive acceptance discovery.
- X4: poll/remount/race/partial-data discovery; depends on X2 decision.
- Proprietary D-1–D-6: vendor entitlements, correction semantics, license/retention,
  thresholds, recovery objectives, and UI policy. Agents may prepare a decision packet
  but cannot invent answers.
- Model weights/papers: no weight, formula, or citation change without the exact paper,
  frozen hypothesis, and an approved evaluation contract.

## Permanently outside automatic admission

Live trading, credential rotation, paid provider requests, production deployments,
destructive migrations, external Discord/broker witnesses, swarmSPX, Azure work, and
X-credit work.
