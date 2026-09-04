# Agent 4 Research Report (2026-09-03)

## Sources fetched
13 confirmed handoff papers re-verified via SSRN/RePEc/ScienceDirect index pages (all resolve);
prior full verification records in /tmp/wf_smart (paper_informed/gamma/dark.md). Supporting: EOS98,
CCG05, VPIN12, BRW17, NPP05-pinning, Barber-Odean, Barbon EOD WP. Data docs: FINRA ATS, Reg SHO/CRS
R43739, Rule 605/606 (cached); Finnhub/Tradier/yfinance/Databento listed with constraints.

## Sources unavailable
0DTE peer-reviewed literature (gap — Cboe exchange note only, context-grade); intraday signed options
flow; intraday VRP; demand-based pricing full text; Muravyev-family cites (do NOT use names until opened);
BJZZ 2024 reassessment. See missing-literature.md source-request manifest (6 pulls).

## Confirmed rules
Sign-of-gamma amplify/dampen (Ni21); fragile/reversal-lean tags (Barbon-Buraschi, association only);
EOD momentum lean + fade (Baltussen21, GammaHP WP); buyer-open PC + O/S + parity-dev + smirk + IV-change
+ openings-over-closings rules (PP06, JS12, RSS10, CW10, XZZ10, An14, GLP16); dark-as-unsigned (Zhu14,
CFP15); retail scope limit (BJZZ21).

## Refuted violations found (all with file:line in refuted-claims-audit.md)
- V1 (P0): gex_paper_accurate.py flash_crash_risk() returns numeric crash_probability_estimate (1/3/8/18%) —
  paper shows association only.
- V2 (P0): user-facing "VPIN" served from unsigned call/put buckets (routes/vpin.py, services/
  vpin_toxicity.py, routes/quant.py:124-136, routes/ensemble.py). Frontend copy already honest.
- V3 (P1): "Barbon-Buraschi Eq. (2)" + Sec. II.B/III.C/Table V refs unverified (abstract-only source);
  own scaling admitted ~13x off paper scale.
- V4 (P1): Ni dated "(2020)" — journal is RFS 34(4) April 2021.
- Clean: no dark-pool directional copy, no confirmed-buyer copy, no true-sweep claims, no -$200mm line,
  no phantom papers, no guaranteed/will-move in frontend/src.

## Score spec summary
Signed -100..+100, display-only. D2 sign matrix (put-ASK BULLISH + HEDGE?). Weights: spread 25 /
size-OI 30 / premium 20 / IV-change 15 / DTE 10. Caps: OI-missing 50, falling-OI 40, earnings 70.
NO_QUOTE → unavailable. Overfit warning included. 10 unit tests defined; fixtures cover boundaries.

## Dark pool methodology summary
Levels + size only; Top-N 1/2/3/5 × lookback 30/45/90/180d × min-notional × tolerance max(0.25%,10 ticks);
strength = notional + count + recency; freshness per level; confluence checklist; empty + paid-gate states;
5 banned / 6 allowed copy strings; DP $X · date label format.

## Evaluator fixtures created
eval/phase-9/fixtures/: pulse-overview-score.json (5 pulse + overview + 3 highlight + 4 score cases),
scanner-alerts-tracker-filters.json (4 scanner + 6 alerts + tracker + 3 filter cases),
darkpool-context-missing.json (levels + FINRA + SHO + 9 missing-field states). All with expected outputs.

## Recommended product changes
R1 kill numeric crash probability → fragility tag. R2 rename user-facing VPIN → toxicity proxy.
R3 fix Ni year + strip unverified Eq/Sec/Table numbers (Agent 3 B8 patch). R4 copy-grep CI gate.
No contract-request file exists (Agent 1 has not created CONTRACT_REQUESTS.md yet) — R1-R4 logged here
for architect triage.

## Blockers
- CONTRACT_REQUESTS.md absent → requests parked in this report.
- 0DTE/intraday full texts unopened → score DTE weight + 0DTE gate stay heuristic-grade.
- No branch created (repo has concurrent uncommitted work + no git identity assurance for agent branch);
  files written in place, commit left to operator. See output block.

## Round-2 re-verification addendum (same day)

Re-ran all rg audits repo-wide (backend/services, routes, frontend/src, docs) + read Agent-2's new
flowseeker UI + verified 3 citations at index level (Ni RFS 34(4):1952–1986 confirmed;
GPP = RFS 22(10):4259 = 2009 confirmed with NYU PDF pull queued; COR Drift Burst Hypothesis SSRN
2842535 real but price-data-based, misspelled "Reno" in code).
New findings V5–V13 in refuted-claims-audit.md §5 (9 items): OI-PCR misattribution (V5), phantom Ni
charm paper contradicting prior refutation (V6), GPP year shuffle (V7), overnight-drift contradicts fade
finding + vague post-SVB cite (V8), HOW-TO-READ asserts crossing as fact (V9, frontend P0), THREE
conflicting sweep definitions (V10, P0), SIDE fallback makes NO_QUOTE unreachable (V11), WHALE naming
collision (V12, minor), drift-burst gamma→COR misattribution (V13).
Propagation upgrade: V1/V5–V8 all served via morning_briefing API — briefing consumers now in audit scope.
Fixtures added: sweep_definition_conflict, side_fallback, popover_copy evaluator cases.
Claim-rule-map carries P&P OI caveat. What round 2 did NOT do: open GPP PDF, pull 0DTE full texts,
write backend docstring patches (Agent 3 B8 lane) — all queued.

## Rounds 3–5 hardening addendum

- Round 3: V15 (P&P band +4 LIVE in flow_alerts.py:165-167, label :322, 8 wired imports — round-1 "clean"
  verdict corrected), V16 (briefing API serves crash_prob wholesale — CLOSED as served), V14 (split gap),
  V17 (ΓIB double-weight), score-spec reconciliation, runnable check_fixtures.py (caught 3 malformed cases).
- Round 4: V6 upgraded — phantom 'Charming!' + SSRN 5054370 named verbatim (:1005-1007); GPP full text
  fetched (RFS 22(10) 2009, doi 10.1093/rfs/hhp005) with middle-section findings (dealer-short-index,
  crashophobia OTM puts, ~1/3 expensiveness, demand↔smirk); Bollen-Whaley 2004 queued; V19 acceptable-use
  note; all fixture math mechanically recomputed.
- Round 5: Barbon FULL TEXT fetched (UniSG Alexandria OA PDF). V3 → REFUTED-as-cited (imbalance is Eq. 3/4
  not Eq. 2; §II.B is definitions not flip; flash is §IV not §III.C; ~15bps spread is Table VII not V).
  V13 → Table VIII real but code's numbers contradict paper (t=5.99 vs claimed −2.97) + no-causation caveat
  and post-2010 decay omitted. V18 CLOSED as no-violation (matched-pairs confirmed). Claim map carries
  full-text numbers with qualifier requirements. V15 wiring recounted to 8 imports.
- Round 6: audit citation-integrity recheck (all backend lines hold; 3 frontend refs drifted under Agent-2
  edits — V9/V10 line numbers updated, stale refs corrected). Ni 2006 WP full text verified (mechanism +
  no-formula at source, ±37bp per 1σ). Score-spec EXECUTED against all 10 unit tests — caught and fixed
  2 spec bugs (IV now direction-aware; MID halving now in pseudocode). New V10 sub-finding: :1351 tooltip
  "urgent multi-exchange fill" asserts venue visibility; "(heuristic)" only partly mitigates.
- Round 7: fix-queue F1–F18; Cboe 0DTE full text (net-vs-gross supports gate philosophy); venue-noun ban.
- Round 8: §1 verdict-table corrected (P&P row now VIOLATION per V15; ΓIB row now REFUTED-as-cited per
  full text). Baltussen abstract verified verbatim + DOI. Fixture inventory re-checked (all keys present,
  checker PASS).
- Round 9: first verified 0DTE paper (Brogaard-Han-Won 2023/2026, abstract-only — PDF SSRN-walled):
  +1σ 0DTE → +9.1% vol, survives gamma controls, retail-driven — CONTRADICTS Cboe de-minimis; honest
  position is "mixed, SPX-only, regime-dependent". Checklist gains fragility-qualifier rule.
- Round 10: BJZZ abstract verified verbatim (10bp/wk, <half persistence, suggestive-only) — claim-map
  numbers now sourced, not remembered.
- Round 11–13 (on main as b6688d8; summarized here): 5 abstracts verbatim + quintile fix; phantom row
  corrected; W2 fingerprint audit + F19; backend :8000 unreachable note; V20 FIR divergence; branch-risk note.
- Round 14 (this branch): CONTRACT_REQUESTS evaluations delivered — B6 CONDITIONAL-APPROVE display-only
  ("academically grounded" overstated; baseline+persistence+exclusions+copy constraints in
  alert-gate-economics §7); B1/B2 design APPROVEs in source-manifest §4. GLP abstract verified verbatim
  with snapshot caveat (second-strongest shape unidentifiable unsigned — keep falling-OI cap).
- Round 15: Roll + Johnson-So abstracts verified verbatim (JS: 1.47%/mo low-minus-high decile, low-leverage
  qualifier, earnings-news prediction — number newly recorded).
- Round 16: EOS98 + CCG05 abstracts verified verbatim (signed-volumes informative; normal-period option
  imbalance uninformative — matches map; takeover-regime only). Full coverage: every cited paper now
  sourced at abstract text or better.
- Round 17: checked other-lane work — mock feed properly gated (c9bfa78; remaining mock refs log-only),
  B-proposals clean, B9 proposal absent so pre-delivered B9 eval framework (borrow-inputs-eval.md:
  JS-2012 grounding, tiered inputs, squeeze guard, fee-weighting forbidden). CR-10 Agent-4 boxes all DONE,
  flagged for Agent-1 checkoff.

## Agent 4 status block (per task prompt)

## Task 4 — falsifiability + skeptic (eval marathon, 2026-09-04, branch phase9/agent4-eval)

### Falsifiability: the two papers most load-bearing for the signed score

1. Ge-Lin-Pearson 2016 (load-bears the falling-OI cap + openings overweight). What invalidates us: the
   paper's identification rests on SIGNED open/close records from a non-public dataset. If a replication
   showed the open-vs-close gap does not survive controls for trade size (openings are larger prints),
   then our OI-change proxy is laundering a size effect as an information effect — the 30% size/OI weight
   and the ≤40 falling-OI cap would both be miscalibrated, and the honest fix is collapsing them into a
   single size term. Source: SSRN abstract 2329714 (abstract-only). Confidence in our use: MEDIUM — the
   direction (openings > closings) is robust across their splits, but our snapshot proxy (OI delta) is a
   coarser cut than their signed records, so effect-size transfer is assumed, not shown.
2. An-Ang-Bali-Cakici 2014 (load-bears the 15% IV component). What invalidates us: the paper sorts on
   1-MONTH CHANGES in IV; our snapshot terminal observes IV LEVELS and at best day-over-day wiggles with
   no monthly baseline (needs B1). If the monthly-change effect is driven by slow diffusion over weeks, a
   daily IV-tilt proxy captures none of it and the 15% weight is pure decoration — worse, IV level is
   mechanically tied to spread width and event proximity, so the component could load on illiquidity while
   labeled "confirmation". Kill condition: if B1-backed monthly IV-change sorts show no tilt separation on
   our universe, delete the component (rescale others) rather than retuning its weight. Source: SSRN
   abstract 1533089 (abstract-only). Confidence in our use: LOW until B1 — flagged DEGRADED in the spec.

### Skeptic stress-test: three strongest arguments the Top-N dark spec misleads

1. "Levels from stale prints are horoscope lines." Weekly ATS data with 2–4wk delays, clustered with a
   tolerance, presented as chart overlays, WILL be read as support/resistance no matter the disclaimer —
   the footer cannot beat the visual. Concession + patch: levels auto-expire (no refresh within lookback/2
   → dimmed; none within lookback → overlay hidden, not empty-state-with-lines). Spec patched accordingly
   (dark-pool-methodology §2 freshness; checklist requires it).
2. "Top-N by notional selects for ATS venue concentration, not conviction." The biggest clusters may just
   mark where internalizers route flow (payment-for-order-flow geography), i.e., retail-flow plumbing, not
   institutional intent. Since direction is unknowable, the spec cannot distinguish "whale level" from
   "retail router hotspot". Concession in writing: cluster strength renamed "size footprint", and the word
   "conviction" is banned from all dark surfaces (added to prohibited list).
3. "Confluence checklist manufactures rigor." Placing GEX zones next to dark levels invites the reader to
   multiply two weak signals into one strong one — the exact laundering the score spec warns against.
   Patch: checklist renders each check as independent present/absent lines with NO composite, NO count
   ("3/5 confluence"), and a header: "separate facts, not a combined signal".

### Marathon task status

- Task 1 (R1 booster surgery): NO-OP with evidence — no AI booster/Key Moments/LLM signal exists in
  scoring (commit phase9(eval) R1 audit). Actual additive boosts (+5/+3/+4) already tracked (V15).
- Task 2.1: measured-vs-estimated published (live-fire-2026-09-04.md); economics doc revised (WHALE and
  SCORE rates corrected).
- Task 2.2: scan_score executed live via imported code path (harness committed); rowConviction cited via
  shipped Jest (156/156) — JSX not node-importable, stated explicitly.
- Task 2.3: backtest_harness.py does not exist; trade-engine is not a precision harness; precision path
  (alert_quality) live-measured at all-0.0s → F20 (outcome persistence) is the true blocker, with the
  failing command recorded.
- Task 3: integrity-sweep-2.md filed (4 blockers re-verified + 4 polish + clean list).
- Task 4: above.

AGENT: 4
BRANCH: phase9/agent4-eval (from origin/main; lane files ported from phase9/agent1-architect + main)
STATUS: DONE
SOURCES_FETCHED: (unchanged corpus, round 16) + live chain payloads SPY/QQQ + live quality endpoint
SOURCES_UNAVAILABLE: (unchanged) + SSRN-walled PDFs (Brogaard full text); backtest_harness.py (nonexistent)
VIOLATIONS_FOUND: V1–V20 + F1–F20 (F20 new: outcome ledger); integrity-sweep-2 (I2-B1..B4, I2-P1..P4)
EVALUATORS_CREATED: + harness/live_fire.py + live-fire-2026-09-04.md + integrity-sweep-2.md + borrow-inputs-eval.md
SCORE_SPEC: self-consistent (round-6 proof run); R1 booster confirmed absent, no surgery
DARK_POOL_SPEC: skeptic-patched (expiry, footprint rename, no-composite rule)
BLOCKERS: F20 outcome persistence (needs B1); B9 proposal absent (framework pre-delivered); backend flaky
(QQQ fetch failed once, retried ok); product edits are owner lanes
