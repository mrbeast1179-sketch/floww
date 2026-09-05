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
| | | |

## Contract proposals / decisions
| Time | Proposer | Change | Decision |
|---|---|---|---|
| | | | |

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
