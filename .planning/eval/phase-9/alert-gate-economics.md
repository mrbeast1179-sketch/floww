# Alert-Gate Economics (fixtures only — no defaults changed) — Agent 4

Gates evaluated: SCORE≥92 · WHALE≥$25M · SIGMA≥6σ · 0DTE volOI≥2 · per-rule TTL dedup · 4/hour noise cap.
Method: reasoning over fixture shapes in fixtures/ (alerts.json). RECOMMENDATIONS ONLY.

## 1. Estimated effects (fixture-based, order-of-magnitude)

| Gate | Count reduction (est.) | Mechanism |
|---|---|---|
| SCORE≥92 | ~90–95% of scored rows suppressed | right-tail only; with caps (§4 of score spec) most prints sit 20–70 |
| WHALE≥$25M | ~99%+ of prints suppressed | single-name single-print ≥$25M is rare by construction |
| SIGMA≥6σ | ~99.7%+ under normality; less under fat tails | 6σ is extreme; baseline quality decides real rate |
| 0DTE volOI≥2 | passes only high-conviction 0DTE bursts | closes the 0DTE loophole without opening a floodgate |
| TTL dedup | kills repeat-fire on the same contract/rule (biggest saver during bursts) | per-rule TTL; same-contract refires collapse to 1 |
| 4/hour cap | hard ceiling on user-visible noise during mania | tail-drop with "N suppressed" counter |

Combined: user-visible alert rate ≈ a handful/hour in normal flow, capped at 4/hour/rule in mania.
Dedup is the highest-leverage saver (bursts re-trigger the same contract dozens of times per 15s poll).

## 2. Dedup effectiveness

- Per-rule TTL (separate clocks for SCORE/WHALE/SIGMA/0DTE) prevents cross-rule starvation.
- Same-contract same-rule refire inside TTL → suppressed + counted (fixture alerts.json cases A3/A4).
- Risk: TTL too long hides genuine escalation (size doubling). Recommend: escalation override —
  refire if premium ≥2× the firing print (fixture case A5). Needs Agent 2 display ("updated" badge).

## 3. Noise-cap behavior

- 4/hour is per-rule (per HANDOFF). Whole-market universe × 4 rules = up to 16/hour worst case —
  acceptable but worth stating.
- Cap must be VISIBLE: "3 more SIGMA alerts suppressed this hour — widen filters to review" pattern
  (funnel empty-state philosophy, not silent drops).
- Never silently reorder: oldest-first within cap; overflow counted, not hidden.

## 4. False-positive risk classes

1. Stale-OI volOI spikes (OI not yet updated → fake volOI≥2). Mitigation: OI-freshness check; DEGRADED tag.
2. Wide-spread SIDE misinference (last-vs-mid on a $2-wide market). Mitigation: spread-width guard
   (no ASK/BULLISH on spreads >X% of mid — needs desk value).
3. Falling-OI "unusual" volume (closings, Ge-Lin-Pearson). Mitigation: already capped in score spec; alerts
   should require OI-rising or premium-dominant for SCORE≥92.
4. 0DTE lottery prints (tiny premium, huge volOI on near-zero OI). Mitigation: $25K premium floor holds
   even for 0DTE.

## 5. User-visible cost of threshold changes

| Change | Cost |
|---|---|
| 92→85 | ~2–3× alert volume; dilutes "high-conviction" meaning; needs outcome read first |
| $25M→$10M WHALE | large-cap normal flow starts tripping WHALE; rename or tier (WHALE/SILVER/GOLDEN already exist) |
| 6σ→4σ | fat-tail names fire constantly; baseline-per-name (not global) becomes mandatory |
| 4/hr→8/hr | linear noise increase; acceptable only with escalation override + suppression counters |

## 6. Recommendations (no action taken)

- Keep all defaults. Add escalation override (2× premium refire) + suppression counters.
- Add spread-width guard and OI-freshness check before any threshold loosening.
- Every threshold change ships with its evaluator (Gate 1) + 30-min outcome read.

## 7. B6 quiet-accumulation evaluation (Agent-4 gate eval, round 14)

Proposal: vol z-score >2 AND price-range compression z-score <1σ → display-only "coiled" label.

- Academic grounding: proposer's "academically grounded" is OVERSTATED. No paper in the manifest
  supports volume+compression as accumulation (nearest neighbors: Baltussen EOD momentum needs directional
  day-move, not compression; Barbon needs gamma sign). This is a practitioner pattern (compression-breakout
  family). Verdict: evaluate as heuristic, never cite a paper for it.
- CONDITIONAL-APPROVE as display-only, with constraints:
  1. Baseline mandatory (needs B1): z-scores computed against a DECLARED trailing window (recommend ≥20
     sessions, min-bars guard); no baseline → "unavailable", never 0.
  2. Persistence: single-bar 300% prints are blocks, not accumulation — require ≥3 qualifying bars.
  3. Exclusions: OPEX week + expiry day (mechanical pinning), earnings ±2 sessions (event volume),
     premium floor $25K (penny-contract z-noise), illiquid names with <N baseline bars.
  4. Label copy: "coiled (compression + elevated volume vs N-session baseline — pattern, not prediction;
     no direction implied)". Never an alert gate in v1 (proposer agrees).
- False-positive classes: OPEX pinning, earnings ingestion, one-print blocks, thin-baseline z-inflation,
  regime shifts (baseline stale after gaps — require baseline freshness ≤5 sessions).
- Noise cost: zero while display-only. Promotion to alert-gating requires Gate-1 evaluator + TTL dedup
  + 30-min outcome read. Re-evaluate after B1 lands with real baselines.
