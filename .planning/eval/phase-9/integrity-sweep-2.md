# Integrity Sweep 2 — merged code (Agent-2 39 modules + SHIP additions), 2026-09-04

**Scope:** frontend/src (+ backend user-facing strings), prohibited lexicon + subtle certainty checks.
Method: rg over merged tree; every line re-verified today (line numbers drift fast — see round 6).
Previous sweep (refuted-claims-audit §§1–6) still stands; this file covers NEW + re-verified items only.

## Blockers (user-visible honesty violations, still open)

- I2-B1 (=V9): HOW-TO-READ popover FlowseekerProBlademap.jsx:1314 + column tooltips :1343 assert
  crossing/aggressor as fact ("lifted the offer → aggressive buy", "last print", "latest print").
  Suggested: "SIDE (inferred — last vs mid, no tape)"; "quote stamp".
- I2-B2 (=V10): tooltip :1365 "Sweep: urgent multi-exchange fill (heuristic)" — venue noun with no venue
  data. Suggested: "multi-print burst proxy".
- I2-B3 (=V10/F19): tooltip :1365 "Block: negotiated single fill (heuristic)" — execution-character claim.
  Suggested: "large single-contract size (proxy)".
- I2-B4 (=V11): SIDE fallback :88,:601 (voi≥1.5→ASK) makes NO_QUOTE unreachable for side.
  Suggested: unknown dash on missing quote.

## Polish (not blockers)

- I2-P1: is_best_rule crowns a "winner" even when all wins are 0 (live: 0DTE/BRONZE n=5, hit 0.0 got the
  flag; min-n floor is only 3). Not displayed in flowseeker UI (no frontend hits) — API-only wart.
  Suggested: require wins>0 for the flag, or rename most_measured.
- I2-P2: "Conviction X/99" (:1418) reads calibrated but is an internal heuristic; component breakdown
  shown (good transparency). Suggested: append "(heuristic)" once in the label.
- I2-P3: ChartModal.jsx:34,42 user-facing "fixture mode" jargon. Honest (not fake data) but meaningless
  to users. Suggested: "waiting for history (snapshot cadence)".
- I2-P4: preset "High-Conviction Sweeps" (methodology/presets.js:11-13) — certainty adjective on proxy
  classification. Suggested: "High-Volume Sweeps (proxy)".

## Verified clean (merged code)

- Prohibited lexicon: zero hits for confirmed buy/seller, dark-pool buying/selling, guaranteed,
  institutional-buying-detected, will-move/rally/crash (only CSS 100% noise). One honest hit:
  :1316 "(direction = premium-flow proxy, not confirmed buys/sells)".
- VPIN: all four mentions are n/a-on-snapshot disclaimers (:8,:1421,:2016, ToxicityGauge.jsx:136).
- Strategy fingerprints (973bbb3): "?" suffix + "no exchange linkage" — template behavior.
- Sweep filter chip carries "(proxy)" (FilterBar); mock-feed gating post-c9bfa78 verified.
- Backend tests + frontend tests: no violation strings enshrined.
