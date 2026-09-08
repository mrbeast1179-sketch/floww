# Recovery queue v2

`QUEUE.md` retains the full P1–P7, D1–D7, X1–X5, and E1–E5 contracts. This
file adds current candidate heads, recent work, institutional integration, and the
proprietary-data frontier. Status is evidence-based as of 2026-09-06 20:58 EDT.

## Admission order

### Wave 0 — preserve and adjudicate

| ID | Lane | State | Result required before moving on |
|---|---|---|---|
| R0 | Agent 1 | PREPARED; publication receipt required | Clean recovery package committed and remote-backed |
| E4-28 | Agent 4 | MERGED to main (`de88c1f`) | PR28 merged 2026-09-08 under owner take-over order (prior escalation was branch-convention policy, no code defect). Pre-merge proof on update commit: parity 4/4, routes 183 pass (2 pre-existing LLM-key failures identical on pristine main), ruff clean. |
| E4-29 | Agent 4 | REVIEW COMPLETE; APPROVED, Nav merge call | O/X delivered at `568de16`, 46 exact-head tests; two advisories; see proof/receipts/E4-29.md |
| E4-30 | Agent 4 | MERGED to main | PR30 merged at 377dfa5 (merge of origin/main into astra/p1-clean); scripts/silent_except_gate.py and backend/tests/test_silent_except_gate.py byte-identical to 06b7502; CI green: ruff, backend-tests, frontend-build; audit: evidence/PR30-merge-attempt.md |
| E4-31 | Agent 4 | REVIEW COMPLETE; APPROVED-conditional | `f7f7103` inert scaffolding, 62 exact-head tests; weights pending A3-SCORE; see proof/receipts/E4-31.md |
| PR32 | SUPERSEDED by PR33 | T1-only split built, tested, PR open | E4-32 verdict stands (receipt + evidence mirror). T1-only `astra/t1-only`: 8 files, 62 suites / 479 tests green on main base, zero G1 riders. Backend/Discord remainder still needs scope issue. PR32 to be closed as superseded after PR33 merges. App.js touch authorized under owner take-over order 2026-09-08 (surgical scope recorded in PR33). |
| PR33 | T1-only candidate | PR open, CI running | `astra/t1-only` @ `217236c` (post-main-update). Full suite green pre-update; re-verified post-merge. |
| PR34 | H1-test candidate | PR open, CI running | `astra/h1-strike-truth` @ `a09e040` (post-main-update). Fixture 4 green; negative control proven. |
| PR35 | F0-wave candidate | 1 test fix pushed, CI re-running | `49f467e`: fake-clock/monotonic bug in 429-cooldown test fixed (proven via clock-patch repro). 15 gate files 151 green locally. |
| PR36 | H2-partial candidate | PR open, CI running | O-1/O-3 shipped (`0a690a1`); O-2/O-4/O-5 queued with rationale. Full suite 4984 green locally. Receipt: agent-2-backend/receipts/H2.md. |
| F0-F1 | Agent 2 | COMPLETE; VERIFIED GREEN, PR35 open | Wave-1 honesty/integrity complete: F1/F3/F4/F7, P1/P3/P4, D1–D7. Architect re-verified 2026-09-08: 15 gate test files **151 passed**, backend ruff clean. Receipts in agent-2-backend/receipts/ (+H1.md, P2 supplement, FINAL supplement, H2.md). Open: P2 baseline KNOWN (11 advisories, upgrade Nav-gated), P6/P7 Nav-gated. |
| GSD-8 | Agent 1 | BLOCKED | Remove or leave out of build queue until X credits exist; no spend |

Nav merges #28/#29 only after E4 approval of the same head. A later push invalidates
the verdict and returns the PR to review.

### Wave 1 — Wave-1 integrity complete

- F1/F3/F4/F7: done, pushed, receipts on disk
- P1/P3/P4: done, pushed
- D1–D7: done, pushed
- Open: P2 (pip-audit timed out, baseline UNKNOWN), P6 (rotation Nav-gated), P7 (Oracle offline, Nav-gated)

### Next admissions (contracts preserved from QUEUE.md / heat audit)

- H1 PR34 open (`a09e040`), H2 PR36 open (`0a690a1`, O-1/O-3 only), serialized theme continues: whoever lands first constrains server.py analytics vs provider cost. H2 call-count targets reconciled at admission (see H2.md receipt). FLAG (unchanged): PR32 payload's `_fill_strike_gaps` (`type:"none"` zero-OI rows) vs H1 O-1 — resolved by taking Option A (T1-only PR33 carries no server.py changes).
- XH-1 (Agent 3): UI quote/side/sweep/block copy preserves unknowns, labels proxies.
- RH-2 (Agent 3): clean Heatseeker candidate branch, only approved behavior + tests.
- RT-1 (Agent 3): clean ticker-navigation candidate, no dead universe experiment.
- SCROLL-1 (Agent 3 + Agent 4): capped DOM, full collection reachability, active-item reveal, actual mounted surface.
- F2/F13 both touch `flow_alerts.py`: serialized behind the PR31 decision.
- `App.js` not in Agent 3's lease without a surgical Nav waiver (per CLAUDE.md frozen files).

### Wave 2 — dependency, data, and consumer truth

| ID | Lane | State | Notes |
|---|---|---|---|
| P2 | Agent 2 | READY after P4 facts | FastAPI/Starlette/PyMongo resolver + advisory comparison + full backend proof |
| D1–D5 | Agent 2 sequential | DISCOVERY | Reproduce budget, fairness, empty/stale, quote/session, and cache hypotheses before patch |
| D6 | Agent 2 + Agent 4 | VERIFY | Prove snapshot→event→dedup→persist→actual REST/SSE feed; no invented score change |
| A3-SCORE | Agent 1/Nav | DECISION | Decide whether exposure changes conviction; PR #31's weights are not an accepted contract |
| X2 | Agent 3 + Agent 4 | VERIFY | Mounted Phase9 consumer and responsive acceptance |
| X4 | Agent 3 | DISCOVERY | Poll/remount/race/partial-data stability |
| E1 | Agent 4 | BACKLOG | Revalidate F1–F19 individually at current base/candidates |
| E2 | Agent 4 | READY | Deterministic mocked public/proprietary-boundary chaos matrix |

### Wave 3 — institutional integration and operations

| ID | Lane | State | Exit |
|---|---|---|---|
| G1-SALVAGE | Agent 1 + Agent 4 | SAVED/UNMERGED | Split Discord-only commits from Heat/ticker work; review; task PR |
| G3-SALVAGE | Agent 1 + Agent 4 | SAVED/UNMERGED | Isolate G3-specific commits; prove offline GATE-2; task PR |
| G-WITNESS | Nav/G4 | EXTERNAL GATE | Same guild/channel, test channel, non-admin help, genuine paper approve/fill/close |
| P6 | Agent 2 + Agent 4 | READY | Path-only credential audit, current-doc redaction, rotation handoff |
| P7 | Agent 2 | READY | Oracle offline validation; VM/DNS/TLS remain Nav-gated |
| B0 | Friend | EXTERNAL GATE | Push redesign brief/mockups with prior verdict and finding traceability |
| X5/B1 | Agent 3 | BLOCKED ON B0 | Parallel preview and Nav visual sign-off before replacement |

## Phase9 honesty disposition

All F1–F19 remain open until Agent 4 produces per-ID evidence at the relevant head.
The first build wave is F1, F3, F4, F7, then UI F5/F6/F11/F19. The remaining IDs
follow individually. F2 and F13 change scoring semantics and require one explicit
contract before edits. A bulk “honesty fixed” commit is prohibited.

## Recent Heatseeker/ticker decision boundary

RH-1 must answer these separately:

1. Does deeper expiry fetch respect the actual upstream-call budget and cache contract?
2. Does cvserver enrichment violate the declared Solstice-only/rate-limited boundary?
3. Are synthetic strikes excluded from analytics, node detection, totals, and trading
   selection, and unmistakably labeled as visual estimates?
4. Does the net ticker implementation use only the supported `/api/tickers` response,
   preserve search, wrap navigation, abort/stale-response behavior, and render scale?
5. Which commits are experiments fully superseded by `123e78f`, and what is the minimal
   net diff from main?
6. Was the frozen `App.js` scope explicitly approved, and is the final edit surgical?

Until those answers pass proof, the branch is saved work, not a merge candidate.

## Proprietary-data program

The GSD discovery map is `PROPRIETARY-DATA-DISCOVERY-MAP.md`. It is not ready for
specification until D-1 through D-6 close. After graduation, expected one-day slices
are: normalized contracts; provider capture; sequencing/gap recovery; raw+normalized
replay; Public shadow comparator; observability/budgets; consumer router; UI provenance;
chaos/performance audit; staged cutover/rollback. These names are planning candidates,
not filed contracts until the discovery process approves them.

## Separate `swarmSPX` program

`/Users/nav/GitHub/swarmSPX` has its own Git history, configuration, tests, provider
policy, paper engine, synthetic backtest concerns, and UI/alert surfaces. It receives a
separate GSD map after its truth audit. No Floww worker deletes Schwab or changes that
repo from a Floww task card. Shared ideas cross repositories only through an explicit
interface/spec, never by copying an entire provider or agent framework.

## Stop conditions

- Provider stream returns no bytes or HTTP 429 without a durable boot/checkpoint.
- Branch ancestry or diff includes files outside the task lease.
- A task needs a frozen file without a recorded waiver.
- A data field's semantics, licensing, entitlement, or timestamp are unresolved.
- A worker would hide a failing check, fabricate a live witness, or infer merge/deploy.
- Two builders need the same whole file.
