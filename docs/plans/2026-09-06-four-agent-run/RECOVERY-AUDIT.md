# Recovery audit — September 6 snapshot with September 7 addendum

## September 7 current boundary

Canonical G1 is now b5f9ae5d99a4d502efdaf1d0c4d8386c2fa9b0d0. The two subsequent commits are fb34324 (visible ticker scrollbar) and b5f9ae5 (5000 Finnhub symbols alongside featured tickers). There are five local commits beyond the named origin/G1 head959b3ff; the complete current history has been pushed separately to origin/archive/20260907-g1-recovery and its full SHA verified. Dirty scroller caps, Serena migration and four untracked notes are preserved in the evidence directory. Sections below retain their original earlier boundary.

Snapshot note: this audit was taken at the Sep-6 boundary with `origin/main=5b9d9a9` and G1 local head `b5f9ae5`. Main has since advanced to `56cfff2` (PR28–47 merged, PR44 merged 2026-09-08T11:48:51Z). The PR table, candidate findings and external gates below record the state at that boundary — re-read GSD-PASSES.md and RECOVERY-QUEUE.md for current truth before acting on any item below.

Latest delegated Heat audit reports deterministic failures in synthetic-row analytics, upstream budget accounting, ticker cache behavior and capped search reachability. Its final receipt records the commands and limits; these are repair inputs, not completed fixes. The GSD build pass handed issue8 back for unconfirmed credits. See GSD-PASSES.md for actual current build/review mutations.

This is the architect's current-state boundary. It distinguishes fresh source/GitHub
evidence from historical test totals in worker reports.

## Authoritative acceptance state

- Freshly fetched `origin/main`: `5b9d9a96a29951e548e883d108a806b93c2d11a9`
  (PR #25). None of PRs #26–#31 is merged.
- Canonical checkout: `phase9/g1-reads-witness`, currently at local `123e78f` with
  untracked Heatseeker planning notes and a modified Serena config.
- The local G1 branch has three commits after its remote head `959b3ff`; it is saved in
  local Git, not yet backed by the remote at this audit boundary.
- The four prepared run worktrees remain clean at `5b9d9a9`. Their old checkpoint
  files still say `prepared_not_started`.

## Pull requests

| PR | Exact head | State | Files | Architect disposition |
|---|---|---:|---:|---|
| #26 D7 original | `6b40820` | closed, unmerged | 13 | Superseded; carried 11 unrelated files |
| #27 X1 original | `a66845e` | closed, unmerged | 15 | Superseded; carried 11 unrelated files |
| #28 D7 clean | `18b10b5` | open, clean/mergeable | 2 | Review exact issue #18 contract; Nav merge if approved |
| #29 X1 clean | `568de16` | open, clean/mergeable | 4 | Review exact issue #17 contract; Nav merge if approved |
|| #30 silent gate | `06b7502` → `377dfa5` → `e68bdb5` (now `56cfff2`) | merged to main 2026-09-07T18:42:13Z | 2 (+PR29/PR31) | MERGED. Gate files byte-identical to 06b7502; CI green on PR head and main; audit evidence/PR30-merge-attempt.md |
| #31 exposure score | `f7f7103` | open, clean/mergeable | 2 | DECISION/REWORK: helper unused by production; weights are new policy |

GitHub reports backend-tests, frontend-build, and ruff successful on #28–#31.
Docker is skipped for PR refs. Current CI still makes frontend tests advisory,
frontend lint advisory, and backend mypy advisory, so a green build is not proof that
all those checks passed.

## Candidate-specific findings

### PR #30

PR30 was reviewed by Agent-4 as REWORK (gate fires/passes but missing CI wiring,
malformed/missing-root false-clean bugs). Fix was verified as
E4-30-gate-fix.patch. Branch was updated to 377dfa5 with PR29/PR31 product
included, then merged to main at e68bdb5 on 2026-09-07T18:42:13Z (now `56cfff2`). Gate files
(script/silent_except_gate.py, backend/tests/test_silent_except_gate.py) are
byte-identical to the original 06b7502 commit. CI green on PR head and on main:
ruff, backend-tests, frontend-build. Final audit: evidence/PR30-merge-attempt.md.

### PR #31

The candidate adds `exposure_adjustment_for_events()` and a new optional argument to
`score_conviction()`. The production `_mk_alert()` call still invokes
`score_conviction(r, factors)`. Its per-event weights and +/-5 clamp are new scoring
policy, while the original backlog can also mean verifying exposure events reach the
existing feed. Those outcomes must be separated before code is wired.

## Saved branch work outside main

| Location | State | Required disposition |
|---|---|---|
| `phase9/g1-reads-witness` | Discord work plus Heatseeker/ticker commits; 22-file diff vs main | Split by contract into clean branches; do not merge wholesale |
| `phase9/g3-paper-loop @ 04d2b16` | G3 paper work, no PR, one monitoring doc dirty | Independent GATE-2 review; reconcile overlapping G1 commits |
| `/private/tmp/w-f0` | F1 docstring edit plus untracked test; no commit | Preserve and finish one honesty ID at a time |
| `astra/c4-doc-hygiene` | Saved plan package plus inherited G1 history | Plan artifacts recovered onto clean architect branch |
| `/private/tmp/floww-2 @ 4d9715b` | Accessible friend fork | Compare by behavior/blob; do not assume missing fork |
| Tidehunter worktree | old local `main @ efca38f` | Historical comparison only; behind fetched main |

## Recent Heatseeker/ticker work

The G1 branch contains eight product commits after its morning close:

- `53267ae`: ticker arrow navigation.
- `f1ed4bf`: wider strike bands.
- `658e6cb` and `4e52e77`: cvserver sparse-chain enrichment.
- `959b3ff`: deeper Public fetch and synthetic gap rows.
- `898fb11` and `3e8097c`: 11,220-symbol universe experiment.
- `123e78f`: removes that universe path and returns to `/api/tickers`.

The commit sequence contains both an experiment and its partial reversal, touches
frozen `App.js`, shared `server.py`, provider budgets, and renders synthetic zero-Greek
rows. It needs exact-head review and clean task branches. Live-process prose in commit
bodies is historical evidence and does not establish the currently served SHA.

## Failed four-worker launch

Hermes manifest
`/Users/nav/.hermes/cache/delegation/live/deleg_72bd2bfa/manifest.json` records four
task starts. Task 0, 1, and 3 ended after no response bytes across retries; task 2 ended
on HTTP 429. Task 3 also recorded a denied command whose full compound command is not
recoverable from the summary. No `/private/tmp/astra_G_*.md` reports exist. The launch
therefore produced preliminary reads, not completed lanes.

## Obsidian and Tidehunter

`2026-09-03.md` records two frontend waves: the Pulse tape/UI pass and the SHIP signal
engine/synthesis work. `Freebuff Handoff.md` is older and contains contradictions,
including a statement that `swarmSPX` was deleted and a different screener/floww engine
boundary. The two institutional blueprints are aspirational architecture sources, not
proof that OPRA/direct-exchange infrastructure exists.

The accessible friend fork contains no new redesign/mockup/`curious-cerf` artifact.
The Windows-only brief described by an earlier sweep cannot be inspected here. Track
B0 remains an external prerequisite rather than a coding task.

## External gates

- Nav: merge approved PRs; apply `gsd:ready`; provide proprietary provider/entitlement
  details; approve any frozen-file task; supply Oracle VM; perform Discord/paper human
  witnesses.
- Friend: push the Tidehunter redesign brief, mockups, and audit traceability.
- Vendor/account owner: confirm data redistribution, retention, historical access,
  and market-data entitlement terms.
- Security owner: rotate any credential identified by the existing tracked-text audit;
  redaction alone is not revocation.
