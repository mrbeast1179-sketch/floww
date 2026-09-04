# Phase 9 Fix Queue — Agent 4 (ranked, evidence-linked)

**Rule:** owner lanes edit; Agent 4 only reports. Each item: severity · file:line · current text ·
fix · evidence. Status column for owners (OPEN default).

## P0 — fix before any honesty sign-off

| ID | Finding | Location | Fix | Status |
|---|---|---|---|---|
| F1 | Fabricated citation "'Charming!...' SSRN 5054370" | gex_paper_accurate.py:1005-1007 | Delete citation + SSRN; hold charm unverified; fix Args (gamma/net_gamma absent from signature) | OPEN |
| F2 | Refuted P&P band +4 in live scoring + UI label | flow_alerts.py:165-167, :322; wired flowseeker.py ×8 | Strip band+citation OR relabel "internal tenor heuristic" + outcomes read | OPEN |
| F3 | Numeric crash_probability_estimate served via briefing API | gex_paper_accurate.py:525; morning_briefing.py:898; morning_briefing_api.py:160,194 | Remove field; serve fragile/stable tag only | OPEN |
| F4 | OI-PCR cites buyer-open-volume paper | gex_paper_accurate.py:616-640; morning_briefing.py:743-745,899 | Label "OI-based PC proxy (not P&P volume)" or drop cite | OPEN |
| F5 | HOW-TO-READ + tooltips assert crossing as fact | FlowseekerProBlademap.jsx:1301,:1330 | "SIDE (inferred — last vs mid, no tape)"; "quote stamp" not "print" | OPEN |
| F6 | 3 sweep definitions + "multi-exchange fill" venue claim | CONTRACTS C1 vs Blademap.jsx:83,594 vs scanLogic.js:72-77; tooltip :1351 | Single owner (scanLogic); "multi-print burst proxy"; reconcile CONTRACTS | OPEN |
| F7 | Phantom "Ni-Pearson 2021 Charm" comment | morning_briefing.py:750 | Delete | OPEN |

## P1 — fix this wave

| ID | Finding | Location | Fix | Status |
|---|---|---|---|---|
| F8 | Wrong Eq/Sec refs (Eq.2→3/4, II.B≠flip, III.C≠flash, Table V≠spread) | gex_paper_accurate.py:6-24,40-50,428-460 | Cite Eq.3/4 w/ assumption, §IV for flash, Table VII for spread; or drop numbers | OPEN |
| F9 | Ni year 2020→2021; P&P title "OF"→"IN" | gex_paper_accurate.py:6,:624 | Correct | OPEN |
| F10 | Table VIII numbers contradict paper (t=−2.97 vs 5.99); no-causation + post-2010 omitted | gex_paper_accurate.py:1083-1162 | Correct numbers or drop; add caveats | OPEN |
| F11 | SIDE voi-fallback kills NO_QUOTE path | FlowseekerProBlademap.jsx:88,595 | Unknown dash, no fallback guess | OPEN |
| F12 | Overnight-drift contradicts fade finding; vague post-SVB cite | gex_paper_accurate.py:2013,:2165 | Verify/remove; name source or drop framing | OPEN |
| F13 | ΓIB double-weighted on unverified formula | flow_alerts.py:247,:270-273 | Down-weight; "ΓIB-proxy" label | OPEN |
| F14 | COR gamma_proxy misattribution + "Reno" typo | gex_paper_accurate.py:1111-1162 | Price-data-only framing; fix spelling | OPEN |

## P2 — polish + contract gaps

| ID | Finding | Location | Fix | Status |
|---|---|---|---|---|
| F15 | "split" type missing from CONTRACTS | scanLogic.js:72-77 vs CONTRACTS.md (0 hits) | Agent 1 adds or code drops | OPEN |
| F16 | WHALE $1M badge vs $25M alert collision | Blademap.jsx:1301 (disclaimed) | Keep disclaimer; consider rename | OPEN |
| F17 | N=2 "P&P next-day power" needs "heuristic" | flow_outcomes.py:55 | One-word label | OPEN |
| F18 | CW label could note volume-weighting ours | flow_quality.py:82 | "volume-weighted CW proxy" (optional) | OPEN |
| F19 | "Block: negotiated single fill" asserts execution character | FlowseekerProBlademap.jsx:1351 BLOCK branch | Drop "negotiated"; "large single-contract size (proxy)" | OPEN |
| F20 | Alert-level outcome ledger non-persistent; quality serves all-0.0s | flow_alerts.py:950 (stamps) + :memory: DuckDB (duckdb_engine.py:540); live proof quality?days=30 → 25 measured, all 0.0 | File-backed DuckDB ≥30d (B1); until then alert calibration is decoration | OPEN |
| F20-REFINED | Scope correction: POSITION-level outcomes DO persist — journal_store is file-backed (data/journal.duckdb, journal_store.py:35,45-52) with lifecycle closes. Only ALERT-level move stamps evaporate. Fix narrows to: persist alerts table file-backed OR join quality to journal closes | OPEN |
| F21 | F20-REFINED join feasibility audit — ckey formats match, journal holds 1 test row, tape tables empty | journal_store.py:12-16,58-77 (card schema); flow_alerts.py:637-646 (daily key, ckey); live journal file read 2026-09-04: 1 row, 0 tape records | Recommended fix order: (1) persist alerts table file-backed for immediate calibration; (2) join alerts→journal on ckey + asof_date≈entry_date (±1 session) for realized-P/L metric long-term | OPEN |
| F22 | F20/F21 verdict overclaims persistence | fix-queue.md:37-38 (F20-REFINED row) + report paragraphs | Rewrite both to: mechanism proven, scope corrected, join feasible-but-empty, cleaner recommended first | OPEN |
| F23 | Signed overlay is fixture-grade on live chains — GET /api/public/chain/SPY has NO `last` field (keys: T/ask/bid/delta/expiry/gamma/iv/oi/oi_source/osi/strike/theta/type/vega/volume); spread_position and last-vs-mid side inference uncomputable; every live row evaluates UNAVAILABLE under signed-score-spec.md §7 (signature: signed_score(row, last=None) → UNAVAILABLE("NO_LAST")) | signed-score-spec.md:67-110 (§7); live chain verified 2026-09-04 /tmp/chain_spy_n.json (200, 352525 bytes, 1480 contracts, no last/premium/dte) | Add `last` to chain payload when bid/ask tick crosses mid (executable trade proxy), OR ship signed overlay fixture-only with honest UNAVAILABLE badge on live rows until then. No quote-proxy workaround — proxy can never evidence aggression (CONTRACTS C1) | OPEN |
| F24 | signed-score-spec.md §7 pseudocode still references `row.last` inside body after adding `last=None` param + NO_LAST gate; body should use `last`, not `row.last`, for internal consistency (the function argument is `last`, not `row.last`) | signed-score-spec.md:95-98 (§7 body: sp uses `last`, but mid/side still reference `row.last`) | Replace `row.last` with `last` in §7 body lines 95-98 so the pseudocode is self-consistent: `mid = (row.bid+row.ask)/2; if abs(last-mid) < tick(row): ... else: ... (ASK if last>=mid else BID)` | OPEN |

## Verified clean (do NOT "fix")

- ROUND-12: W2 strategy fingerprints (973bbb3) — VERT?/STRADDLE? with "?" suffix + tooltip
  "(heuristic: matched volumes, no exchange linkage)". Exemplary; use as template.

- oi_hygiene.py:18-20, fetch_earnings.py:7-9 (P&P cited as caveat — correct)
- ToxicityGauge.jsx honest empty state; FilterBar.jsx:9 "(proxy)"; Blademap.jsx VPIN n/a disclaimers
- cw_iv_spread matched-pairs construction (V18 closed)
- backend/tests + frontend tests: no violation strings enshrined (verified round 7)
