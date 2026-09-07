# Recovery queue v2

`QUEUE.md` retains the full P1–P7, D1–D7, X1–X5, and E1–E5 contracts. This
file adds current candidate heads, recent work, institutional integration, and the
proprietary-data frontier. Status is evidence-based as of 2026-09-06 20:58 EDT.

## Admission order

### Wave 0 — preserve and adjudicate

| ID | Lane | State | Result required before moving on |
|---|---|---|---|
| R0 | Agent 1 | PREPARED; publication receipt required | Clean recovery package committed and remote-backed |
| E4-28 | Agent 4 | REVIEW COMPLETE; policy-escalated to Nav | Verdict at `18b10b5`, seven contract tests passed; no new code blocker; see GSD-PASSES |
| E4-29 | Agent 4 | NEXT REVIEW | Exact-head O/X + quality verdict for PR #29 at `568de16` |
| F0-F1 | Agent 2 | PRESERVED-WIP; no active worker inferred | Finish preserved F1 citation/proxy correction with valid red/green proof |
| RH-1 | Agent 3 + Agent 4 | AUDIT SAVED; split/admission next | Net-behavior audit of `53267ae..b5f9ae5` plus dirty caps; rework H1/H2/T1/T2 |
| GSD-8 | Agent 1 | BLOCKED | Remove or leave out of build queue until X credits exist; no spend |

Nav merges #28/#29 only after E4 approval of the same head. A later push invalidates
the verdict and returns the PR to review.

### Wave 1 — close confirmed integrity gaps

September7 priority correction: the final Heat audit reproduced H1 raw-analytics contamination and H2 upstream budget bypass. Admit H1 then H2 to Agent2 after preserving/closing the small F1 unit. These take priority over P2 and speculative new feed work. Agent3 can complete T1/SCROLL-1 discovery in parallel; App.js/unknown-ticker policy is decided before edits. See evidence/recent-heat-audit.md for the exact reproduction and H1/H2/T1/T2 candidate contracts. H1/H2 share server.py and must be serialized. Their proposed call-count targets must be reconciled with the actual provider contract at admission.

| ID | Lane | Source | Contract |
|---|---|---|---|
| P1 | Agent 2 | PR #30 as source material | Fail-closed AST gate, baseline/suppression policy, CI wiring, workflow-equivalent proof |
| P3 | Agent 2 | `QUEUE.md` | Truthful QC command exits and ownership guard reproduction |
| P4 | Agent 2 + Agent 4 | `QUEUE.md` | Python/runtime matrix and required frontend test/lint policy with baseline resolution |
| F0-F3 | Agent 2 | Phase9 F3 | Remove numeric crash probability from API; serve supported categorical state only |
| F0-F4 | Agent 2 | Phase9 F4 | Correct OI put/call proxy framing and citation |
| F0-F7 | Agent 2 | Phase9 F7 | Remove phantom charm attribution |
| XH-1 | Agent 3 | Phase9 F5/F6/F11/F19 | UI quote/side/sweep/block copy preserves unknowns and labels proxies |
| RH-2 | Agent 3 | RH-1 verdict | Clean Heatseeker candidate branch with only approved behavior and tests |
| RT-1 | Agent 3 | RH-1 verdict | Clean ticker-navigation candidate branch; no dead universe experiment |
| SCROLL-1 | Agent 3 + Agent 4 | User September7 addition | SOLSTICE-SCROLLER.md: capped DOM, full collection reachability, active-item reveal, actual mounted surface |

F2 and F13 both touch `flow_alerts.py` and remain serialized behind the PR #31
decision. `App.js` is not in Agent 3's lease unless Agent 1 records a surgical waiver
for RT-1.

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
