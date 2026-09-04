# B9 Borrow-Inputs Evaluation (Agent-4 gate eval, round 17)

**Request:** CR-08 — Agent 3 has NOT yet submitted a borrow data-source proposal. This is a
pre-delivered evaluation framework: any future B9 proposal is judged against these criteria.
No data source is endorsed sight-unseen.

## 1. Academic grounding (verified, round 15)

Johnson & So 2012: low-minus-high O/S deciles 1.47%/mo risk-adjusted; effect stronger when short-sale
costs are high or option leverage is low; O/S predicts firm-specific earnings news. Role for product:
borrow state UPWEIGHTS bearish O/S-conjunction signals. It is a CONDITION, never a standalone signal —
the paper predicts from option volume interacted with constraints, not from borrow data alone.

## 2. Acceptable input tiers

- Tier 1 (free, delayed): Reg SHO daily short-volume ratio (positioning context, 1d+ delay stamp);
  FINRA short interest % float (bi-weekly, ~2-week lag stamp).
- Tier 2 (unavailable free): stock borrow fee / rebate rate (no free source — stays UNAVAILABLE; the
  Cremers-Weinbaum rebate-rate sanity check therefore cannot run on free data either — record as gap).
- Tier 3 (paid-gate): securities-lending feeds. Paid-gate flag only, never on critical path.

## 3. Rules for any B9 proposal

1. Borrow flag = context tag ("hard-to-borrow", "elevated short interest") attached to an existing
   O/S-conjunction signal. A borrow flag ALONE fires nothing.
2. Every borrow field carries as-of + lag stamps; short-interest older than one cycle → stale state.
3. Fee-based weighting is FORBIDDEN until a real fee feed exists (no proxies from short volume).
4. Squeeze guard: high short interest + positive day-move ≥2σ → SUPPRESS bearish upweighting and show
   "squeeze-risk context" instead. Crowded shorts cut both ways (neither Johnson-So nor any manifest
   paper licenses ignoring covering dynamics).
5. ETF/dividend-arbitrage shorts excluded where identifiable; creation-unit flows are not directional.

## 4. False-positive classes

Covering squeezes · stale short-interest (settled positions) · ETF creation/redemption short prints ·
ex-dividend arbitrage volume · single-day short-volume spikes without O/S conjunction.

## 5. Verdict

CONDITIONAL-APPROVE the framework; implementation BLOCKED on (a) Agent-3 data-source proposal naming
exact feeds + lags, (b) B1 cadence for the O/S baseline the conjunction needs. Re-evaluate with fixtures
when a proposal lands. CR-10 note: all three Agent-4 boxes (spec, fixtures, citation audit) are DONE —
ready for Agent-1 checkoff; C18 (no alert-gating) acknowledged and preserved in signed-score-spec §5/§6.
