# Handoff: desk pass (Conviction v2.2) — Fable → freebuff

_2026-07-20. New module `backend/services/flow_desk.py` + 14-case suite
`backend/tests/services/test_flow_desk.py` (run with `--noconftest` while the
tree has WIP). Per fleet protocol: new files only — freebuff wires._

## Integration — 2 lines in `routes/flowseeker.py::_run_institutional_alerts`

```python
from services import flow_desk as fd          # with the other deferred imports
...
alerts = fa.eval_institutional(...)           # existing line
alerts = fd.desk_pass(duckdb_engine, normed, alerts)   # ← ADD: after eval,
...                                                    #   before fa.dedup_filter
```

`desk_pass` fails open (returns alerts unmodified on any error) and
self-initializes its tables — no other setup.

## What it does (post-eval, pre-dedup)

1. **Fresh-interest gate** — cvforge `day_volume` is cumulative; per-contract
   volume marks (`flow_vol_marks`) turn it into new-contracts-since-last-scan.
   SCORE/WHALE/0DTE re-fire only on ≥ max(500, 10%·vol) fresh contracts.
   OICONF/SIGMA exempt. Expect the afternoon feed to get much quieter — that
   is the point.
2. **Campaign promotion** — same ckey alerting on ≥2 prior sessions
   (lookback 10d) promotes one tier notch, `why` gets
   "· campaign: day N of positioning".
3. **IV context** — per-ticker daily median IV store (`flow_iv_daily`,
   self-building). Once a ticker has ≥5 sessions of history, directional
   alerts fired at ≥p80 of its own IV history demote one notch, `why` gets
   "· IV at pNN … rich-vol entry". Inactive until history accrues — no
   behavior change on day one.

No schema changes to `flow_alerts_daily` — campaign/IV context ride in `why`.
Your `cluster BOOLEAN` addition is untouched and composes fine.

## Frontend contract (for InstitutionalAlertsPanel)

- `GET /api/flowseeker/alerts/feed?days&tier&ticker` → `{alerts, count, days}`.
  Ordering: tier rank (GOLD→SILVER→BRONZE) then `asof_ts` DESC. `tier` param
  is a MINIMUM (tier=silver ⇒ GOLD+SILVER).
- Row fields: `tier, side, bias, rule, under, type, strike, exp, dte, score,
  est_entry, premium, notional, vol_oi, sigma, oi_chg_pct, under_price,
  last_price, move_pct, cw_spread, cluster, why`.
- `side == "STRATEGY"` ⇒ `bias` is null — render a neutral pill, never a
  direction color. `bias` null also on SIGMA rows.
- `move_pct` starts 0.0 and drifts with each scan — color by sign vs bias.
- `why` is the desk explanation verbatim (now may carry campaign/IV
  suffixes) — ideal for the tooltip, don't parse it.
- `GET /api/flowseeker/alerts/quality?days` → per rule×tier
  `{n, n_measured, hit_rate, avg_move_pct}` for the quality strip.
  (Saw your multi-window extension in flight — the desk pass doesn't touch
  that route.)

## ⚠️ Heads-up on your WIP

`routes/flowseeker.py:934` currently has a SyntaxError (stray `;` after the
`Query(...)` default in the multi-window quality route) — imports of the
routes tree fail, so DO NOT restart the backend until it's fixed; the
running :8000 process predates the edit and is healthy.
