# Floww branch / PR / failed-run evidence — 2026-09-06

Read-only audit of canonical repo `/Users/nav/Documents/GitHub/floww`; no branch switches, code edits, commits, pushes, merges, service operations, or test-suite runs. This report is the only file written. GitHub REST records and git trees were freshly read in this audit; older report test totals below are explicitly historical assertions. Root fetched origin during the audit and confirmed the same main SHA.

## 1. Authoritative main and PR matrix

GitHub `branches/main` and local `origin/main` both resolve to `5b9d9a96a29951e548e883d108a806b93c2d11a9` (merge PR #25). Local `main` is older: `efca38f4116ef57f330df3af670d53cce1e21fb3`, behind origin/main by 5 commits, checked out in `floww-worktrees/tidehunter`. Canonical checkout is G1, not main.

All six PRs below were initially against the same base SHA `5b9d9a96a29951e548e883d108a806b93c2d11a9`. Initial GitHub check-runs reported backend-tests=success, frontend-build=success, ruff=success, docker-build=skipped. Subsequent merge status changed for #29, #30, #31; see the September 7 addendum.

Initial state (September 6 snapshot):

| PR | Branch | Exact head | State | Actual PR files | Recovery interpretation |
| --- | --- | --- | --- | --- | --- |
| [26](https://github.com/mrbeast1179-sketch/floww/pull/26) | astra/d7-contract-parity | `6b408204b3e578bd0ad25bf4a295e8004a976fc4` | closed unmerged 11:27:26Z | 13 | superseded; 11 unrelated G1/ledger files |
| [27](https://github.com/mrbeast1179-sketch/floww/pull/27) | astra/x1-tradeentry-journal | `a66845e67047449deb6e742859f4d442cc04b3dc` | closed unmerged 11:27:27Z | 15 | superseded; 11 unrelated G1/ledger files |
| [28](https://github.com/mrbeast1179-sketch/floww/pull/28) | astra/d7-clean | `18b10b5601ef0bc0dd27a083d66f2d8ad164665a` | open; mergeable=true, clean | 2, +166/-45 | clean D7 candidate, not landed |
| [29](https://github.com/mrbeast1179-sketch/floww/pull/29) | astra/x1-clean | `568de16a3d2da32c218660e1007ad89b2d97228f` | open; mergeable=true, clean | 4, +301/-1 | clean X1 candidate, not landed |
|| [30](https://github.com/mrbeast1179-sketch/floww/pull/30) | astra/p1-clean → merged to main | `06b75020dddb7b6ecc1d9c220b9fffac6fc0575b` → `e68bdb512a4a56bed3bcbcb8081f975d8c5cddf9` | merged 2026-09-07T18:42:13Z | 2 (+PR29/PR31) | MERGED to main. Gate files byte-identical to original; CI green: ruff, backend-tests, frontend-build. Audit: evidence/PR30-merge-attempt.md |
| [31](https://github.com/mrbeast1179-sketch/floww/pull/31) | astra/a3-clean | `f7f7103b2744a7a052c66a917a7a7d4662a3c310` | open; mergeable=true, clean | 2, +222/-2 | scorer API+tests; live caller explicitly still missing |

Clean file sets, freshly checked through PR `/files` and git diff:

- D7: `backend/routes/analytics.py`, `backend/tests/routes/test_contract_shape_parity.py`.
- X1: `frontend/src/components/{TradeEntry.jsx,TradeEntry.test.jsx,tradeMath.js,tradeMath.test.js}`.
- P1: `scripts/silent_except_gate.py`, `backend/tests/test_silent_except_gate.py`.
- A3: `backend/services/flow_alerts.py`, `backend/tests/services/test_conviction_exposure_wiring.py`.

All four clean file sets are byte-identical to their corresponding original branch tip, verified with separate `git diff --exit-code ORIGINAL CLEAN -- <owned paths>` calls, each exit 0. Thus repair removed inherited branch content without changing owned files. The D7 clean first commit is `dadbad63e2bc443a476cd39a7f40153e6bfecd19`, followed by ruff fix `18b10b5`; all other clean heads are direct one-commit children of main.

The 11 contaminating paths in PR26/27 are `backend/discord_bot.py`, `backend/services/discord_harness.py`, `backend/services/discord_ops.py`, six test files (`test_discord_g1_alerts_honesty.py`, `test_discord_g1_chain_honesty.py`, `test_discord_g1_contract.py`, `test_discord_g1_counters.py`, `test_discord_g1_help_honesty.py`, `test_discord_harness.py`), `institutional_loop/LEDGER.md`, and `kanban/BOTTLENECK_ALERTS.md`. Earlier X1 report assertion of 21 PR files is stale; current authoritative count is 15, with 4 owned and 11 inherited.

## 2. CI evidence and its limits

Successful clean-PR CI run records:

- #28: [CI 34030234351](https://github.com/mrbeast1179-sketch/floww/actions/runs/34030234351), lint 34030234427. Backend completed 11:36:58Z.
- #29: [CI 34030251330](https://github.com/mrbeast1179-sketch/floww/actions/runs/34030251330), lint 34030251305. Backend completed 11:38:59Z.
- #30: [CI 34030279610](https://github.com/mrbeast1179-sketch/floww/actions/runs/34030279610), lint 34030279607. Backend completed 11:39:35Z.
- #31: [CI 34030298212](https://github.com/mrbeast1179-sketch/floww/actions/runs/34030298212), lint 34030298300. Backend completed 11:40:04Z.

Main branch protection currently requires only context `ruff`, `strict=false`, no required review setting. Force pushes/deletions are disabled. This is a repository setting observation, not a proposed relaxation.

At exact main `.github/workflows/ci.yml`, backend job executes `python -m pytest tests/ -v --tb=short --cov=. -m "not flaky_env"` on Python 3.11 with Mongo and dummy LLM keys. Thus its success excludes flaky_env tests. Backend mypy and frontend lint use `|| true`; frontend Tests has `continue-on-error: true`. Green frontend-build is therefore not sufficient by itself to establish zero failing Jest tests. Fresh #29 job 101478322542 does list Tests conclusion=success, but raw test totals were not fetched. Docker is intentionally skipped for PR refs and runs only main. The root/backlog audit owns assessment of silent-except scanner coverage and CI wiring.

Historical local-test assertions, not rerun by this subagent:

- #28 body: D7 targeted 4 passed; route regression 183 passed / 2 failed; failures claimed pre-existing LLM-key issues.
- #29 body and `/private/tmp/astra_F_X1pr.md`: owned tests 46 passed; full suite 463 passed from earlier run/report.
- #30 body and `/private/tmp/astra_F_P1.md`: 2 tests passed; fixture fire proof.
- #31 body and `/private/tmp/astra_F_A3.md`: 17 new tests, 62 combined passed; caller plumbing left open.

## 3. Remaining branches and local work

Local and origin Astra branch heads matched on inspection. The two columns below count origin/main-only versus branch-only commits from `git rev-list --left-right --count origin/main...BRANCH`.

| Branch | Exact head | Behind / ahead | Full branch diff vs main merge-base |
| --- | --- | --- | --- |
| phase9/g1-reads-witness | `9d3057d1888e77608d5fc9952a2e9fdd2127a822` | 1 / 23 | 11 files, +486/-42 |
| phase9/g3-paper-loop | `04d2b1647e1bbb35238f4b4ac2958011afcd0ffa` | 1 / 8 | 9 files, +732/-22 |
| astra/a3-conviction-wiring | `a4952dc69ed9e9d535566bfc526d0fc17251abe9` | 1 / 24 | 13 files, +708/-44 |
| astra/c4-doc-hygiene | `65760c13963b71535377ad69813c287ff5bf62c1` | 1 / 25 | 28 files, +2178/-57 |
| astra/d7-contract-parity | `6b408204b3e578bd0ad25bf4a295e8004a976fc4` | 1 / 24 | 13 files, +651/-87 |
| astra/p1-silent-except | `53b076cbe978db58ed9cd0af51242467c506272e` | 1 / 23 | 13 files, +589/-42 |
| astra/x1-tradeentry-journal | `a66845e67047449deb6e742859f4d442cc04b3dc` | 1 / 23 | 15 files, +786/-43 |
| astra/f0-honesty-backend | `5b9d9a96a29951e548e883d108a806b93c2d11a9` | 0 / 0 | uncommitted work only |

G1 tip subject says `D7 landed PR26`; GitHub and main history disprove any interpretation that #26 merged. No G1/G3 or C4 PR appears in all repo PRs returned (31 total). Their work is saved on branches but not accepted into main. G3 includes three early G1 commits (`41acb4b`, `3b02a02`, `bb787ae`) plus five G3 commits; the G3-specific stack begins `7b70d604dec6632a48d092b26dc44bf36b2d2bda`, followed by `d5a0dfa87aabe40b6204f131719b77fd1e5076e8`, `ac3375908d68d008e4ca7f16986a2ae447e6e982`, `8764655401f3edf4886f29dc07b8fb022d605e5b`, `04d2b1647e1bbb35238f4b4ac2958011afcd0ffa`. Overlap in discord_bot/discord_ops/ledger requires deliberate integration.

C4 contains more than its two-file hygiene commit: parent `84031ea296610e7c7b2b1967fa1adecf1da85683` saved 15 plan/run files plus one ledger edit (+1688 across 16 paths) above G1. Its 28-file branch diff includes inherited G1 work. Preserve these saved program plans explicitly; do not wholesale treat C4 branch as a two-file docs patch. C4 report admits residual STATE text still says 6.4 done while ROADMAP header says OPEN.

Worktree inventory:

| Path | Head/branch | Dirty state |
| --- | --- | --- |
| `/Users/nav/Documents/GitHub/floww` | G1 `9d3057d` | modified `.serena/project.yml` (config schema migration languages→language_servers plus generated comments) |
| `/private/tmp/floww-a3` | original A3 `a4952dc` | clean |
| `/private/tmp/w-f0` | F0 at main `5b9d9a9` | modified `backend/services/gex_paper_accurate.py`; untracked `backend/tests/services/test_honesty_f0.py` |
| `/Users/nav/Documents/GitHub/floww-g3` | G3 `04d2b16` | modified `kanban/BOTTLENECK_ALERTS.md` |
| `/Users/nav/Documents/GitHub/floww-worktrees/run-20260906-{data,experience,platform,proof}` | each corresponding run branch at `5b9d9a9` | all four clean |
| `/Users/nav/Documents/GitHub/floww-worktrees/tidehunter` | local main `efca38f` | clean |

F0 retained change is only an 11-line docstring patch (+4/-7): remove fabricated Ni-Pearson/SSRN citation and invalid gamma/net_gamma argument docs, label theta-derived charm as heuristic/proxy. Untracked 3-test file additionally expects runtime interpretation to drop `Per Ni-Pearson 2021` and gain proxy language; no runtime change exists in the diff. No fresh tests run here; root/backlog audit owns reproduction. Do not discard this partial work. No astra/p2-fastapi-bump, astra/a3-callers, or astra/e2-proof branch/worktree exists in current inventory.

## 4. Did the four delegated tasks run?

Yes: four distinct tasks started and executed preliminary tools. No: none completed. This is directly recorded, not an inference from missing reports.

Primary record: `/Users/nav/.hermes/cache/delegation/live/deleg_72bd2bfa/manifest.json`:

- line 4 `task_count: 4`; line 3 start `2026-09-06 07:37:13`; line 37 completed `2026-09-06 10:31:32` (timestamps have no timezone annotation in this file).
- task0 status failed/error lines 12–13; task1 lines 19–20; task2 lines 26–27; task3 lines 33–34.

| Task | Log (same delegation directory) | Freshly read terminal evidence | Failure and limits |
| --- | --- | --- | --- |
| 0 P2 platform | `task-0.log` | lines 9–16: CLAUDE read, fetch/inventory, copied/read queue, requirements read | lines 17–18: API failed after 3 retries; Codex stream no bytes within 1017s, TTFB threshold 120s. No install/resolver outcome recorded in this run. |
| 1 F0 backend honesty | `task-1.log` | lines 9–10: worktree-add fails because F0 branch already exists; lines 11–16 inventory, queue read, git log | lines 17–18: no bytes within 4092s, 3 retries, threshold120s. Existing F0 branch/dirty edits cannot be attributed to this run from its log. |
| 2 A3 callers/frontend honesty | `task-2.log` | lines 9–12: fetch/inventory | lines 13–14: API failed after 3 retries: HTTP429 Rate limit exceeded. No implementation or tests recorded. |
| 3 E2 proof | `task-3.log` | lines 9–12: fetch/inventory/queue read; line13 command summary `sed -n '20,45p' .planning/STATE.md + 6 commands` | line14 terminal BLOCKED, user denied; lines15–16 no bytes within4093s, 3 retries, threshold120s. Summary does not expose six other commands, so exact denied subcommand cannot be identified. |

The elapsed `duration=` fields in final log text do not align with the wall-clock span and retry timeout numbers, so do not present them as reliable task runtimes. The manifest is evidence of dispatch/failure, not productive work for three hours. Model/provider are null in manifest; error wording references Codex streaming, not proof of a specific configured model.

Selective `/private/tmp` report search found `astra_F_A3.md`, `astra_F_X1pr.md`, `astra_F_C4.md`, `astra_F_P1.md`, `astra_F_D7ruff.md`; no `astra_G_*.md` was found. F reports are earlier successful-unit summaries, distinct from failed four-task run. C4 and P1 say untouched dirty `.serena/project.yml`; A3 report says live caller still open. Report presence and assertions were not promoted to fresh passing-test evidence.

## 5. Exact read-only reproduction commands

Run from canonical repo; command families below were actually used, instantiated for each PR/head/path above. Root alone performed fetch.

```sh
git status --short
git worktree list --porcelain
git for-each-ref --format='%(refname:short) %(objectname) %(upstream:short)' refs/heads/astra refs/remotes/origin/astra refs/heads/main refs/remotes/origin/main refs/heads/phase9/g1-reads-witness refs/heads/phase9/g3-paper-loop
git log --oneline -10 origin/main
git rev-list --left-right --count origin/main...phase9/g1-reads-witness
git diff --stat origin/main...phase9/g1-reads-witness
git diff --stat origin/main...phase9/g3-paper-loop
git log --format='%h %s' phase9/g1-reads-witness..astra/c4-doc-hygiene
git show --stat --oneline 84031ea
git -C /private/tmp/w-f0 status --short
git -C /private/tmp/w-f0 diff -- backend/services/gex_paper_accurate.py
sed -n '1,260p' /private/tmp/w-f0/backend/tests/services/test_honesty_f0.py
git show origin/main:.github/workflows/ci.yml
git show origin/main:.github/workflows/lint.yml
gh api repos/mrbeast1179-sketch/floww/branches/main
gh api repos/mrbeast1179-sketch/floww/branches/main/protection
gh api repos/mrbeast1179-sketch/floww/pulls/28
gh api repos/mrbeast1179-sketch/floww/pulls/28/files --paginate
gh api repos/mrbeast1179-sketch/floww/commits/18b10b5601ef0bc0dd27a083d66f2d8ad164665a/check-runs
gh api 'repos/mrbeast1179-sketch/floww/pulls?state=all&per_page=50'
gh api repos/mrbeast1179-sketch/floww/actions/jobs/101478322542
nl -ba /Users/nav/.hermes/cache/delegation/live/deleg_72bd2bfa/manifest.json
rg -n -m 20 'Traceback|exit_reason|Error|error|denied|BLOCKED|maximum|limit|turns|Exception|failed|completed|cancelled|timeout' /Users/nav/.hermes/cache/delegation/live/deleg_72bd2bfa/task-0.log
```

API outputs were filtered to status, SHA, file counts, bodies, CI summaries, and URLs; no credentials or broad application logs were read. A transient sandbox GitHub connection failure was rerun with the already-approved `gh api` escalation and succeeded.
