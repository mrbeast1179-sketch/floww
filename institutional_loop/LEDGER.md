# LEDGER — institutional loop running record
Agent D owns this file. APPEND-ONLY protocol: agents append timestamped rows/sections; never edit or rebase another agent's rows. D may add triage columns to red-test rows. Merge conflicts here resolve by union (keep both sides), never by overwrite.

## Baselines (captured 2026-09-05, pre-loop verification sweep)
- backend pytest (full): **4745 passed, 64 skipped, 1 xfailed, 0 failed** (493s)
- frontend jest (full): **420 passed, 58 suites, 0 failed**
- ruff backend: **clean**
- Pre-existing dirty (NOT ours, do not touch without Nav): `.planning/eval/phase-9/signed-score-spec.md`, `kanban/BOTTLENECK_ALERTS.md`

## Pre-loop fixes applied (2026-09-05, red-team findings, all green above)
- 0DTE backend aligned to tape (85 + vol_oi>=2); pin test updated
- Alert dicts always emit premium_truth/p_move/p_method (C6 additive contract)
- Dealer ΓIB pct None (unknown) + engine None-guard; regime propagates, confluence needs magnitude
- scan-public honest stale flag from slice ages/drops
- Sweep RTH 09:30–16:05 ET, off-hours first-tick skip, FLOWW_PUBLIC_SWEEP_MAX_EXPIRES
- P&P citation aligned to frontend's honest wording; B/C region markers in flowseeker.py + server.py
- Live boot proof (:8001, 0 errors): sweep loop started, scan-public returned real paid chains (SPY 769.47/NVDA 229.01/QQQ 717.97), background sweep rotated cursor (slice DIA/IWM/QQQ/SPY → AAPL/EWZ/GDX/MSFT/NVDA/SMH/TSLA/XBI), 127+92 alerts persisted, clean shutdown

## Ready posts (Hour 0–1)
- [ ] A ready: understanding + first 3 tasks claimed
- [ ] B ready: understanding + first 3 tasks claimed
- [ ] C ready: understanding + first 3 tasks claimed
- [ ] D ready: machinery up, gate baselines captured (pytest counts, jest counts, ruff clean)

## Baselines (D captures Hour 0)
- backend pytest: ___ passed / ___ failed / ___ errors
- frontend jest: ___ passed
- ruff: clean / dirty (files: ___)

## Task log
| Time | Agent | Entry |
|---|---|---|
| 2026-09-05 ~09:45 ET | D | D2 core landed: `4a2605c` sweep recorder + replayer + `alert_digest` + golden fixture `tests/fixtures/sweep_golden_v1.json`. 6 replay tests green; 64 passed incl. chain_replay + flow_alerts suites; ruff clean. Noted: C landed C1 `flow_alert_moves` (f5bf200) — replay snapshot must capture horizon legs; coordinating table shape with C before D2 closeout. Next: D3 provider-boundary validators. |
| 2026-09-05 ~10:15 ET | D | C1 replay sign-off: APPROVED as-is (`6b662b1`). Readers take any engine + fail open + None-for-unknown, so outcome replay runs captured `moves_legs` through a scratch engine — no C change needed. Recorder now captures `moves_legs` (deep-copied, tested). D2 remaining: wire recorder into a live sweep capture path at Sync-1; then D3 validators. |
| 2026-09-05 ~10:35 ET | D | `diff_alerts` landed (`86e9928`, verified on origin): keyed added/removed/changed + identical flag; 8 replay tests green, 67 passed with chain_replay + flow_alerts suites, ruff clean. D2 harness complete standalone (record → replay → digest → diff + golden fixture). Noted C2/C3 concurrently landed (calibration blob live, Kelly sizing) — replay `opts.calibration` path already covers staged p_move. Next: D3 provider-boundary validators. |
| 2026-09-05 ~11:00 ET | D | D3 core landed (`051e674`, verified on origin): `contract_validators.py` (bar/chain-row/quote validators, OHLC invariants, crossed-NBBO flagged, one-sided quotes OK) + `Quarantine` (bounded, counted, never raises) + `quarantine_total{source,reason}` in D-owned observability. 6 validator tests incl. 500-iter seeded fuzz; 14 + 14 passed with replay + observability suites; ruff clean. No feed-logic touched (B-owned). Next: D4 chaos matrix + D5 health payload. |
| 2026-09-05 ~11:20 ET | D | D4 feed matrix landed (`c9208ba`, verified on origin): 7 characterization pins (429 block/recover, clock-skew sanity, cold→None, warm→stale, partial-chain quarantine, crossed-quote flag, broken-engine fail-open); 36 passed with chaos+validators+replay; ruff clean. INCIDENT: commit swept C's staged hunks under D message — content intact, logged in proposals for C confirm. Finding: stale-serve lacks `age_s` (C8) — proposal filed for B. Next: D5 health payload. |
| 2026-09-05 ~11:40 ET | D | D5 health landed (`47af96f`, verified on origin): C11 `institutional` section on /api/health (feed × budget × sweep-age × alerts × calibration, all fail-open/unknown-tolerant) + `sweep_watch` + dead-man gauge. 14 passed with standalone suite (existing structure untouched); ruff clean. Hook requests filed for B/C. Next: secret-scan job + Sync-1 gate prep. |
| 2026-09-05 ~12:00 ET | D | Secret scanner landed (`ec672c1`, verified on origin): patterns for db/openai/github/aws/slack/private-key/assigned-secret; FP fixes (dropped `xxx` marker that ate a live key, db- floor 12, enum skip, data/ out of scope). 4 passed incl. shipped-tree gate; ruff clean. LAW-8 DISCLOSURE: `test_dbn_live.py` (tracked root, committed pre-loop `39d7a63`) holds a live Databento key — needs Nav rotation; file untouched (not D-owned). Scanner fix verified against that exact key shape. Next: Sync-1 gate. |
| 2026-09-05 ~12:20 ET | D | D6 feed-economics landed (`bf32828`, verified on origin): 2+N fan-out pinned (1 expiries + 1 quotes + N chains), cache-hit-zero-token/zero-upstream verified (B1 claim audited ✓), 3-poller single-flight (1 expiries flight), 1 ok-credit/success. GAP QUANTIFIED for B4: chain fetch costs 2+N upstream but debits 0 — adapter never calls acquire; acquire_n + adaptive slice pending B. Characterization pins (green on existing behavior), ruff clean. Next: Sync-1 gate chair. |
| 2026-09-05 ~12:45 ET | D | Health rewire (`ac99f7d`, on origin): C11 calibration now via C's `get_calibration_status()` (D NEED C resolved ✓); B `note_sweep` + `age_s` still pending. Frontend triage: bare-`npx jest` fails 7 flowseeker suites on CSS transform — runner error, not code; canonical `craco test` is 18/18 + 262/262 green. Full backend suite running in background for mid-loop health (result to Sync-1). |
| 2026-09-05 ~13:00 ET | D | MID-LOOP GATE (background full suite): **4832 passed, 64 skipped, 1 xfailed, 0 failed** (344s) — up +87 vs pre-loop 4745, all loop work integrating green. Frontend flowseeker 262/262 via craco. Ruff clean on D paths. No forbidden-file action taken by D. Sync-1 (H6) gate inputs ready. |
| 2026-09-05 ~13:10 ET | D | B1 audit landed (`6f45291`, on origin): C13 shape ✓, D3 cross-agreement on survivors ✓, budget-on-miss/not-on-hit ✓, all-bad→None+reason ✓, ADV mean/thin-None ✓. DIVERGENCE for B: `_validate` passes `inf` (inf>0 true, range checks vacuous) where D3 rejects non-finite — suggest `math.isfinite` guard. Debug note: failures were my mock (`dict()` on a junk str), product was correct throughout. |
| 2026-09-05 ~13:20 ET | D | Doctrine review PASS: no verified-sweep/HIRO claims in engine; DarkPoolPanel compliant (honest no-side/no-direction copy, empty-fed). HANDOFF draft landed (`2017f6a`, D-owned docs): per-agent changes+commits, measured evidence, labeled proxies, 5 Nav decisions. Sync-1 chair at H6; final numbers at H23-24. |
| | | |

## Contract proposals / decisions
| Time | Proposer | Change | Decision |
|---|---|---|---|
| 2026-09-05 ~11:20 ET | D | Stale chain payloads carry `stale:True` but no age (`_cached_copy`); CONTRACTS C8 requires age on every stale payload. Propose `age_s` on stale-serve (B implements, D tests). | Pending B |
| 2026-09-05 ~11:20 ET | D | INCIDENT (mine): `c9208ba` swept C's staged hunks (flowseeker.py, flow_desk.py, test_flow_earnings_protocol.py) under D's message — content intact on origin, attribution wrong. No amend/force per forbidden ops; C please confirm content is yours and complete, or tell me what to revert forward. D stages own-paths-only + checks staged section pre-commit. | Disclosed |
| 2026-09-05 ~11:40 ET | D | NEED B (one line): call `sweep_watch.note_sweep()` per completed sweep in the sweep loop → health `sweep.age_s` goes live; until then None + note. NEED C: expose staged-calibration stage accessor (health reads `_calibration_blob` lazily today; explicit accessor preferred). | Pending B/C |

## Red-test triage
| Time | Test | Owner | Cause | Fix/Commit |
|---|---|---|---|---|
| | | | | |

## Sync notes
- Sync 1 (H6): _
- Sync 2 (H12): _
- Sync 3 (H18): _
- Final gate (H23–24): _

## Agent D ready — 2026-09-05 ~09:30 ET
- Understanding: proof track. Own replay/chaos/perf/observability/health/LEDGER + merge duty; write nowhere else without owner sign-off. Baselines already captured pre-loop (4745 passed / 420 jest / ruff clean) — no re-baseline, straight to replay harness. D2 freeze-list rationale confirmed in code: `eval_institutional` mints `asof` from live clock (flow_alerts.py:605) and `_mk_alert` mints `mins_since_open` per alert (:497) — byte-identical replay is impossible without freezing both, plus rows/baselines/prev-OI/regimes/gex_context/oi_tags/calibration blob.
- Claims: D2 (sweep recorder + replayer + determinism test + golden dataset) → D3 (provider-boundary validators + quarantine + fuzz suite) → D4 (chaos matrix: 429/Mongo/DuckDB-lock/clock-skew/partial-chains/crossed-quotes, fault hooks `fetch_chain_from_public_api`/`pub_budget.acquire`/HTTP-429 injector shared with B).
- Interfaces: B6↔D4 fault hooks named above; C1 horizon-table design coordination (replay-determinism constraint: per-horizon persistence must be snapshot-capturable); P1-8 MCP guardrail tests + prompt pack with B; P2-10 non-builds doctrine enforced in review.
- Loop discipline: failing test → patch → module suite + ruff → commit (HEREDOC + evidence) → push → ledger line. Syncs chaired at 6/12/18h.

## Agent A ready — 2026-09-05 ~09:15 ET
- Understanding: quant track. Pure functions only, no network in A modules. Highest value first: per-contract Lee-Ready signing (R10) replaces the vol_oi>=1.5 BUY proxy with quote-rule + tick-test discipline; unknowns stay UNKNOWN. Engine hooks proposed as diffs, never direct edits to flow_alerts.py.
- Claims: A1 (flow_signing.py Lee-Ready core) → A9 (server-side Roll service, pure port) → A3 (bar-VPIN on injected bars-lists).
- B interface: A3/A4 consume C13 bars-lists only — `get_1min_bars(ticker,days)->[{t,o,h,l,c,v}]`, `get_daily_bars`, `get_adv_21d->float|None`. Confirming as-is; no signature change requested. A2/A7 engine-hook diffs will be posted here when ready; applier=C.

## Agent C ready — 2026-09-05 ~09:30 ET
- Understanding: desk risk manager. Close alert→sized-paper→measured-outcome loop. C-REGION owns _run_institutional_alerts/_cached+_merged_gex_context//alerts/* in routes/flowseeker.py, plus flow_calibration/flow_outcomes/flow_trade_bridge/flow_desk/journal_store/position_sizing/oi_hygiene; _mk_alert/key-levels/context in flow_alerts.py only, coordinated with A. p_move=None never blocks a fire. Paper only, kill-switches stay.
- Verified gap pre-claim: update_moves (flow_alerts.py:1084) overwrites single move_pct per scan — no per-horizon persistence, so +1/+5/+20 abnormal-return reads (C1) have no measured legs. flow_outcomes.py event-study math exists on caller-supplied bars; calibration stage gates exist (STAGE1_MIN=60).
- Claims: C1 (horizon table flow_alert_moves + stamp alongside update_moves, additive) → C2 (calibration promotion wiring: attach staged p_move/p_method onto alerts when earned, else uncalibrated) → C3 (Kelly-capped sizing into bridge, uncalibrated ⇒ flat minimum).
- Needs from D: horizon-table shape sign-off for replay determinism (proposing below; silence = proceed): flow_alert_moves(asof_date, key, under, stamp_date, session_idx, last_price, move_pct; PK(asof_date,key,stamp_date)).
- Needs from A: nothing yet; toxicity-gate key request will come with C4.

## Agent C task log
| Time (ET) | Agent | Entry |
|---|---|---|
| 2026-09-05 ~10:00 | C | C1 DONE (f5bf200): flow_alert_moves horizon-leg table + stamp alongside update_moves (additive, fail-open) + get_move_path/horizon_moves readers. Evidence: 3 new passed; 65 related passed (quality/calibration/outcomes/bridge/alerts routes); ruff clean. Only own hunks staged — others' in-flight hunks in flow_alerts.py untouched. Table shape needs D replay sign-off (proposed above). Next: C2 calibration promotion wiring. |
| 2026-09-05 ~10:40 | C | C2 DONE (c1e45ce): _load_calibration (1h cache, fail-open) → opts["calibration"] into eval_institutional only when stage>=1 blob exists; else byte-identical call. Evidence: 3 new passed; 46 related passed; ruff clean. Own hunks only. |
| 2026-09-05 ~11:10 | C | C3 DONE (c8d389d): kelly_size in flow_trade_bridge — quarter-Kelly from calibrated p + key-level b, 5% single-name cap (1% earnings protocol), negative edge → 0, uncalibrated → legacy flat numbers preserved. order metadata gains size_basis/p_move/p_method (C10). Evidence: 6 new + 72 related passed; ruff clean. Noted: D2 replay commits already consume C1 legs (sign-off implicit). Next: C4 execution advisor. |

## Assists — Opencode pre-Sync-1 (agents flapping, stepped in per Nav)
| Time (ET) | Agent | Entry |
|---|---|---|
| 2026-09-05 ~11:30 | Opencode/A1 | A1 DONE (uncommitted, for agent commit): created backend/services/flow_signing.py — Agent A's write_file flapped (file never persisted across 4 attempts). Implemented to the on-disk test contract: quote rule on last-vs-mid, tick fallback compares last-vs-prev_mid (snapshot-data adaptation, documented — prev trade price unavailable in chain snapshots), degenerate→UNKNOWN. Fixed `from future import` typo from agent draft. Evidence: 13/13 test_flow_signing passed; ruff clean. A2 hook proposal still owned by A. |
| 2026-09-05 ~11:45 | Opencode/B1 | B1 DONE (uncommitted, for agent commit): created backend/services/market_bars.py (C13: get_1min_bars/get_daily_bars/get_adv_21d) — Agent B looped on exploration. Budget acquire moved to _get (not _upstream) so mocked upstreams still exercise budget; stale-serve + last_error reasons; OHLC quarantine counters; day-granular cache (daily 6h / 1min 120s). Adapter fetch_bars_from_public_api gained backward-compat period/aggregation overrides (B-owned file). Evidence: 8 new passed; 155 related passed (public_*, flow_*, routes); ruff clean. Test bug caught own tail: stale-expiry delta (10ks) < daily TTL (6h) — fixed to TTL+10. |
| 2026-09-05 ~11:30 | C | C4 DONE (04f77af): advise_execution TAKE/WORK/SKIP + slippage est in bridge; order metadata gains execution block. Evidence: 25 passed (6 advisor + 6 kelly + 13 bridge), ruff clean. CORRECTION: commit message says "31 passed" — wrong, true count 25. Thresholds provisional (Sync-3 kill/keep). Needs from A/B: λ/spread/velocity attached to alerts to activate (currently patient default). |
| 2026-09-05 ~11:50 | C | C5 C-side DONE (inside D's c9208ba — my staged hunks were swept into D's chaos commit; code verified present, tests green): apply_earnings_protocol in flow_desk (flag + 1.5x wider stop + exit note, never removes) + oi_tags hoist in route (zero extra work). A-side items (eval GOLD-cap exists; frontend hygiene labels) need A sign-off — proposed, not landed. |
| 2026-09-05 ~11:50 | C | INCIDENT (no harm, process note): D's c9208ba committed my staged C5 hunks + C5 test file — authorship mixed, code intact. Separately, test_flowseeker_calibration_wire.py (C2, committed c1e45ce) was deleted from worktree uncommitted; restored byte-identical from HEAD (hash 09828e9 verified). Request: agents commit own paths only; never `commit -a`. |
| 2026-09-05 ~12:10 | C | C6 VERIFIED (pre-existing, no change): apply_campaign promotes one notch with receipt in why; pinned by test_apply_campaign_promotes_one_notch_with_reason + ignores-short-history test. 3-day fixture behavior confirmed in test file. |
| 2026-09-05 ~12:20 | C | C7 DONE (28bdad1): rule_value_table in flow_outcomes — per-rule n/hit_rate/avg_edge_net/verdict net of C4 slippage (25bps default one-way). THIN below n=10, verdicts display-only. Evidence: 25 passed (bridge+value+outcomes); ruff clean. |
| 2026-09-05 ~12:20 | C | C8 BRIDGE-LAYER DONE (28bdad1): replay determinism (same alerts → identical orders) + timestamp audit (asof, never clock) pinned. OPEN (engine owner): order-level idempotency keys, fee/slippage model in paper_trader, kill-switch behavior tests. |
| 2026-09-05 ~12:20 | C | PROPOSALS needing sign-off: (1) A: frontend hygiene labels for earnings-protocol alerts (C5 full contract needs A+B+C); (2) A/B: attach kyle_lambda/spread_bps/velocity_per_min/toxic onto alerts to activate C4 TAKE path; (3) D: horizon table shape flow_alert_moves approved implicitly by D2 use — formal sign-off pending; (4) engine owner: C8 engine-level items above. Agent C claims C1–C8 complete (C6 verified, C8 partial+proposed). |
| 2026-09-05 ~12:40 | C | P1-7 DONE (9da0cb4): whale tracker in journal_store — bookmark_whale (idempotent), pure whale_state (STILL_IN/PARTIAL/EXITED/EXPIRED via OI decay + closer shape + expiry), update_whales, read_whales badge read. P&L = underlying-leg proxy, labeled. Evidence: 19 passed (tracker+journal suites); ruff clean. OPEN (route owner): badge endpoint + scan-loop hookup. |
| 2026-09-05 ~12:45 | C | C7 report wiring: /outcomes/refresh now stamps stats["rule_value"] from the same labeling pass (additive, fail-open) — value table ships in the cached calibration report for Sync-3 kill/keep. |
| 2026-09-05 ~13:00 | C | D-NEED RESOLVED: get_calibration_status() accessor in C-REGION (stage/n/method/model_kind/age_s, fail-open stage-0). D can replace health's lazy _calibration_blob read + "pending C accessor" note. Evidence: 5 passed (accessor+wire); ruff clean. |
| 2026-09-05 ~13:00 | C | FULL backend suite after 10 C commits: 4826 passed (+81 vs 4745 baseline), 64 skipped, 1 xfailed, 0 failed (365s). Ruff backend clean. Agent C regression-proof. |
| 2026-09-05 ~13:15 | C | P1-7 END-TO-END (whale e2e commit): GET /api/alerts/whales badge endpoint + scan-loop bookmark/update hookup in C-REGION (fail-open, zero extra calls). Evidence: 13 passed; ruff clean. Frontend badge surface left to A/B. |
| 2026-09-05 ~13:30 | C | C7 live report: /model now carries rule_value (same table, fail-open) — per-rule precision + n in both cached and live calibration reports. Evidence: 4 passed; ruff clean. |
| 2026-09-05 ~12:00 | Opencode/D-gate | STAGING GATE IMPLEMENTED (Nav directive): institutional_loop/OWNERSHIP.md (path→owner map, script-readable) + scripts/loop_guard.sh (stage/check-staged/hook) + D7b sync-gate mandate + Law 6/README amendments. Verified in temp repo: stage-only-own, foreign-block, shared-needs-LOOP_SIGNOFF, hook-silent-without-LOOP_AGENT, clean-pass. `git add -A`/`commit -a` banned. OWNERSHIP fallback for unlisted paths = UNOWNED (allowed, warned for D review). |
| 2026-09-05 ~14:00 | C | FINAL full-suite proof (3 chunks, tool cap): services 3620 + routes 184 + rest 1036 = 4840 passed (+8 vs mid-loop 4832), 64 skipped, 1 xfailed, 0 failed. Ruff clean. C4 TAKE activation still blocked (A never attached λ/spread to alerts; velocity alone changes nothing — left untouched per ownership). Agent C closed. |
| 2026-09-05 ~12:30 | Opencode/gate | STAGING GATE COMMITTED: OWNERSHIP.md + scripts/loop_guard.sh (stage/check-staged/hook, temp-repo verified) + D7b/Law-6/README mandates. Pre-existing dirty files (.planning signed-score-spec, BOTTLENECK_ALERTS) and other agents' in-flight work left untouched. D: reference in HANDOFF + enforce at final gate. |
