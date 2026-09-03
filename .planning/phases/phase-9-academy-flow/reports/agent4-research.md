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
