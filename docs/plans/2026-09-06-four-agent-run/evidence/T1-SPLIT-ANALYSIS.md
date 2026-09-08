# T1 split analysis — Nav decision support (2026-09-07)

PR32 head is now `9289775` (lint fix on top of `c17fc61`, pushed, CI re-running).
E4-32's [SCOPE] finding stands: title sells T1-only, payload is 23 files.
Two paths. Pick one.

## Option A — T1-only branch (recommended)

Ship only the scroller contract. Mechanical checkout is NOT sufficient: the T1
versions of `SkylitTickerBar.jsx` / `SkylitControlBar.jsx` / `App.css` also carry
G1-base hunks (main never touched these files since merge-base, so no textual
conflict — but the G1 hunks would ride along silently). Requires Agent-3
hunk-level rebase onto `e68bdb5`:

- KEEP (7): `tickerUniverse.js` + `tickerUniverse.test.js` (new, clean),
  `SkylitTickerBar.contract.test.jsx` (new), T1 hunks of `SkylitTickerBar.jsx`,
  `SkylitControlBar.jsx`, `App.js` (28 surgical lines), `App.css` (2-line T1 hunk).
- DROP: `frontend/yarn.lock` (4270-line churn from `8e30a60`, unjustified),
  `.gitignore` (worktree-local `.venv` scratch, must never ship to main).
- PROOF: full frontend suite green + `ruff` clean + Agent-4 fast verdict on the
  new head (T1 behavior already proven 61/469 — confirmation only).

## Option B — authorize full scope (23 files)

Link an issue covering the Discord backend (`discord_harness.py` A, `discord_ops.py`,
`discord_bot.py`, 6 discord test files), `/tickers/all` endpoint + finnhub/cvserver
wiring, `_fill_strike_gaps` interpolation in `server.py` (fabricates `interpolated`
strikes — needs H1-lens review: zero-OI rows in analytics input is exactly what H1
forbids downstream), LEDGER + kanban. Then Agent-4 audits the non-T1 remainder
against that issue's O/X. Heavier; unblocks G1-SALVAGE partially.

## Blocking either path right now

- CI on `9289775` must go green (was red on `c17fc61` for lint; fixed, re-running).
- `App.js` frozen-file waiver: record the 28-line surgical scope before any merge.
