# Current truth at v4 publication

Revalidate all facts at boot. A moved SHA invalidates a prior review.

## GitHub graph

- `origin/main` at audit: `7a0a16aedd503f427a6b43ae453e7f6f541c2078`
  (PR55 merge, 2026-09-10). Wave 0 complete: PR54, PR56, PR55 all ancestors.
- Prior bases `12c53d8` (PR48 merge), `d5dbd7d` (PR54 merge), `5851f53`
  (PR56 merge) remain the ancestors each candidate was reviewed against.
- PR51 (`d4a5b1f`), PR52 (`ba3ef4c`), and PR53 (`84fc1ed`) are ancestors of
  current main.
- PR49 merge `480e953` is an ancestor of current main through PR48.
- PR50 merge `81255b8` is **not** an ancestor of main. Its kind-aware badge
  behavior was lost when the feature lineage was rebuilt.
- PR54 (`c4970a5`, merged via `d5dbd7d`) is an ancestor of current main.
- PR56 (`a46f7b4`, merged via `5851f53`) is an ancestor of current main.
- PR55 (`7481f72`, merged via `7a0a16a`) is an ancestor of current main.
- No open repair PRs remain from the publication set. Wave 0 is DONE.

## Verified product facts

- Current main required CI at `d5dbd7d` (PR54 merge): backend, frontend,
  Ruff passed; Docker build skipped. The backend deployment job is excluded
  from this run and must not be presented as product-test failure.
- PR54 merged evidence: 97 focused order/Discord tests and Ruff pass at
  `c4970a5` (includes the anonymous-idempotency-key repair); no venue or
  Discord request was made.
- PR56 merged evidence: exact-head CI green at `a46f7b4` (backend, frontend,
  Ruff); merged via `5851f53`. The four upgraded direct packages have no
  findings; one NLTK advisory remains with no published fix version.
- PR55 local exact-head evidence at payload: 60 focused tests
  (55-suite base + empty-ticker repair + 5 kind-precedence tests),
  full frontend 66 suites / 531 tests, and production build pass.
  GitHub CI at each new head remains mandatory.

## Known unresolved defects and limitations

- `alertEngineBadges.js` contains eleven mappings but has no runtime UI consumer.
  Do not describe mapper tests as alert surfacing.
- `/api/alerts/{ticker}` input plumbing drops at least `momentum_score` and
  `volume_by_strike` on the reviewed path, preventing corresponding producers
  from firing through that API. Verify on current main before filing work.
- Close submissions that are not immediately filled remain pending after PR54;
  an eventual fill-reconciliation worker is still required.
- PR51 makes option-chain interval deltas safer, but the liquidity signal remains
  an option-chain proxy with uncalibrated score/threshold semantics. It is not
  exchange order flow or institutional identity.
- P2's shared local environment has unrelated `agentfield` dependency gaps;
  never convert `pip check` output into a clean claim without naming them.
- No proprietary vendor entitlement, license, redistribution right, raw-retention
  policy, or correction protocol has been proven. Provider-specific integration
  remains gated; provider-neutral offline contracts may proceed.

## Preserved, not admitted

- Historical recovery/control receipts remain on the control branch.
- Dirty external review worktrees and the canonical G1 checkout are preserved;
  they are not merge sources.
- swarmSPX, Azure/deployment, and X-credit work are excluded by owner direction.
- A human/broker/message witness cannot be manufactured by an agent prompt.

