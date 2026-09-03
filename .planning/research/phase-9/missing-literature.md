# Missing 0DTE / Intraday Literature — Agent 4 (2026-09-03)

Web search 2026-09-03; index pages resolve but full texts NOT all opened.
Confidence abstract-only unless noted. Nothing below is a product rule until the full text is opened.
"Context" = background only, no UI claim. "Rule candidate" = needs full-text verification first.

## 1. 0DTE options and market quality

### Cboe — "Evaluating the Market Impact of SPX 0-DTE Options" (Volatility Insights)
- Link: https://www.cboe.com/insights/posts/volatility-insights-evaluating-the-market-impact-of-spx-0-dte-options/
- Summary: exchange research on whether 0DTE flow destabilizes SPX; practitioner/exchange source, not peer-reviewed.
- Relevance: directly addresses 0DTE volOI≥2 gate calibration context.
- Confidence: abstract-only. Context only (never cite as academic support).

### Broader 0DTE literature (to pull, not yet verified)
- Targets: 0DTE share-of-volume growth papers (2023–2025), 0DTE pinning/expiry-effects studies.
- Status: unavailable this pass — source-request: pull via SSRN query "0DTE" + JFE/RFS forthcoming lists.
- Supports product rule? No — context only until verified.

## 2. Dealer gamma hedging intraday (CONFIRMED entries)

### Baltussen, Da, Lammers & Martens 2021, JFE 142(1):377–403 — CONFIRMED (cached)
- Link: https://ideas.repec.org/a/eee/jfinec/v142y2021i1p377-403.html and
  https://www.sciencedirect.com/science/article/abs/pii/S0304405X21001598 (both resolve 2026-09-03).
- Finding: hedging short-gamma exposure trades with the move; last-30-min return positively predicted
  by rest-of-day return across 60 futures (1974–2020); reverts over following days.
- Product rule: EOD momentum lean + next-day fade (already in claim-rule-map). Supports W5 score DTE/EOD handling.

### Barbon, Beckmeyer, Buraschi & Moerke — EOD rebalancing WP (ΓHP) — cached (PDF opened prior pass)
- Link: https://abarbon.com/assets/Liquidity_Provision_to_Rebalancing_Flows_from_Leveraged_ETFs_and_Equity_Options.pdf
- Finding: negative ΓHP → EOD momentum; positive → reversal; effects dissipate next day.
- Product rule candidate: ΓHP-style pressure display. Partial (working paper) — label as such.

## 3. Intraday options flow and informed trading — GAP

- No verified intraday-signed-options-flow paper in hand. Snapshot-only terminal cannot use intraday
  signed-flow results directly anyway (needs OPRA).
- Source-request: search "intraday option volume informed" (SSRN/JFQA 2020+); muravyev-style signed-volume
  microstructure work is the template but unconfirmed — do NOT cite names until opened.

## 4. Short-term momentum and options — PARTIAL

- Baltussen et al. 2021 covers intraday momentum via hedging demand (confirmed, above).
- LETF-rebalancing EOD flows (Barbon et al. WP) — partial.
- No verified short-term (daily/weekly) momentum-from-options-signal paper in hand — gap.

## 5. Volatility risk premium intraday — GAP

- No verified intraday-VRP paper in hand. An et al. 2014 covers monthly IV changes (confirmed).
- Source-request: intraday VRP / variance-swap intraday literature.

## 6. Market-maker inventory — PARTIAL

- Ni et al. 2021 covers hedger inventory → volatility (daily, confirmed) but NOT intraday timing.
- Garleanu-Pedersen-Poteshman style demand-pressure work NOT verified this pass — do not cite.
- Source-request: demand-based option pricing full-text pull.

## 7. Off-exchange block trades and price levels — CONFIRMED context

- Comerton-Forde & Putnins 2015 (confirmed): block dark trades show no evidence of harming discovery —
  blocks are the LEAST informative category. Directly supports dark-pool-methodology.md.
- FINRA ATS weekly: volume + trade counts only, no side, delayed (verified via FINRA transparency pages,
  prior pass). Supports "levels and size evidence only".

## Source-request manifest (for next research pass)

1. SSRN query "0DTE" → candidate list with abstracts.
2. "intraday option volume informed trading" 2020+ → candidates.
3. Intraday VRP / variance risk premium intraday → candidates.
4. Demand-based option pricing (Garleanu-Pedersen-Poteshman) full text.
5. Muravyev-family signed options microstructure (confirm exact citations before use).
6. BJZZ 2024 reassessment (arXiv 2403.17095) — check magnitude stability for copy bounds.
