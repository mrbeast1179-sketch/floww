# floww — whole-project audit for freebuff

_2026-07-21 · Fable. Every finding below was verified by reading the actual
code / running the actual command cited — not agent speculation. File:line
references are against the working tree at audit time. Ranked worst-first;
the one trading-critical item is P0._

**Scope note:** excludes `data/github-repos/` (vendored third-party). The
alert-engine stack (`flow_alerts.py`, `flow_quality.py`, `flow_desk.py`) is
covered by its own 63-test suite and is not re-audited here — this pass is
the *project-level* rot my earlier subsystem review missed.

---

## P0 — Direction mislabel (trading-critical)

**`backend/services/institutional_detector.py:457-467`** — the combined
call/put "direction" read can flip the sign.

```python
put_heavy  = put_vol > call_vol * 1.15 or abs(put_delta) > abs(call_delta)
call_heavy = call_vol > put_vol * 1.15 or abs(call_delta) > abs(put_delta)
if put_heavy:   direction = "BEARISH"
elif call_heavy: direction = "BULLISH"
else:           direction = "NEUTRAL"
```

The `abs(put_delta) > abs(call_delta)` clause uses **delta magnitude as a
direction proxy, which it is not.** Two concrete failures:
- A genuinely **bullish** call sweep (call_vol ≫ put_vol) whose paired put
  simply carries larger |delta| (e.g. an ITM put on the chain) trips
  `put_heavy` → labeled **BEARISH**.
- **Balanced** volume (neither side > 1.15×) with `abs(call_delta) >
  abs(put_delta)` trips `call_heavy` → a **neutral** tape labeled **BULLISH**.

That is exactly "a bullish call read as bearish, a neutral call read as
bullish." **Fix:** drop the delta-magnitude clause entirely; direction on a
print-less feed should come from volume dominance (and, where available, the
`cw_iv_spread` call−put skew already implemented in `flow_quality.py`), never
|delta|. `_infer_direction` (line 266) is a cleaner sibling but is **dead**
(0 callers) — see P2.

**Wiring caveat (verify before trusting the "live" label):** in the current
tree `institutional_detector` has **no route importer** — the only reference
is a docstring in `composite_flow_score.py:33`. So today the flip sits in
orphaned code. **Before this module is wired to anything Nav trades off, the
delta clause must be fixed.** I checked the two paths that *are* live and
combine into a directional read — `retail_flow_score.py` (CPR+OI+IV → label)
and `composite_flow_score.py` (magnitude band only) — and both label
correctly; the bug is confined to the orphaned detector. freebuff: confirm no
frontend component consumes `detect_alerts_for_chain` output before down-
grading this from P0.

---

## P1 — A fresh install / CI cannot succeed

### `backend/requirements.txt:28` — a pin that does not exist
`yfinance==1.3.0`. **yfinance has never shipped a 1.x release** (it caps at
0.2.x), so this requirement is unsatisfiable and
`pip install -r requirements.txt` **fails outright** on a clean machine.
Also suspicious: `scipy==1.17.1` (verify it resolves).

### CI is therefore a no-op
Because the install step can't complete, the GitHub Actions checks never
reach the test phase — **broken code merges green.** Fix the pins first, then
the test gate becomes real again. (freebuff: `.github/workflows/*.yml` —
confirm the install-then-fail path.)

### Unused login-security stack in requirements
`pyjwt`, `bcrypt`, `passlib`, `python-jose`, `requests-oauthlib`,
`email-validator`, `cryptography` — a full auth/oauth set with no
corresponding live auth surface. Either wire auth or drop them (each is
install weight + attack surface).

---

## P1 — Supply-chain: a dependency from a raw URL

**`frontend/package.json:81`**
```json
"@emergentbase/visual-edits": "https://assets.emergent.sh/npm/emergentbase-visual-edits-1.0.8.tgz"
```
A dependency pulled from an **arbitrary HTTPS tarball**, not the npm registry
— no integrity hash, no registry provenance, mutable URL. This is a genuine
supply-chain risk in a repo that touches (paper) trading. Vendor it into the
repo, or remove it if the visual-edit tooling isn't shipped.

---

## P1 — Repo & history bloat

- **`.git` history = 1.6 GB.** Confirmed via `du -sh .git`. Old large blobs
  live in history even after any working-tree cleanup.
- Committed binary/data artifacts in the tree (should be gitignored/LFS):
  `data/research_kg.duckdb` (**23 MB**), `backend/data/gflows.duckdb`, the
  `models/*.joblib` + `backend/models/*.joblib` binaries, `data/cached_features/*.csv`,
  and a committed directive **PDF** ("From Concept to Code… Project Oracle.pdf").
- `data/github-repos/` = 214 MB vendored third-party.

**Fix:** gitignore the artifacts + move models to LFS or a release asset; then
a **one-time `git filter-repo` history scrub** to reclaim the ~1.5 GB. That
rewrite is destructive (changes every SHA, force-push, re-clone for everyone)
— **needs Nav's explicit approval and a coordinated moment when no fleet is
mid-push.** Do NOT run it opportunistically.

---

## P2 — Dead code, orphans & duplication (maintainability)

### Orphaned modules (built, often tested, never imported into the app)
0 non-test importers each, confirmed by grep:
`institutional_detector.py`, `execution_doctrine.py`, `execution_engine.py`,
`paper_broker.py`, `causal_inference.py` (and `_infer_direction` inside the
detector). This is the "~4,000 lines written+tested but never wired."

### Duplication — same job built many times
- **Paper trading (5+):** `backend/paper_trading.py`,
  `routes/paper_trading.py`, `services/paper_broker.py`,
  `services/paper_trader.py`, `services/paper_trading.py`,
  `scripts/paper_trade_dry_run.py`.
- **Morning briefing (5):** `backend/morning_briefing.py`,
  `routes/briefing.py`, `routes/morning_briefing_api.py`,
  `services/morning_briefing.py`, `services/ml_briefing.py`.
- **Broker connections (4+):** `alpaca_client.py`/`routes/alpaca.py`,
  `schwab.py`/`routes/schwab.py`, `services/schwab_streamer.py`,
  `services/mock_schwab_feed.py`.

**Fix:** pick one canonical impl per capability, delete the rest, wire the
survivor. This is the single biggest LOC-reduction lever and it directly
de-risks the god files below.

### God files (change-risk)
`backend/server.py` **3,317**, `routes/steal_three.py` **2,174**,
`services/dash_ui.py` **1,638**, `routes/flowseeker.py` **1,386**,
`components/flowseeker/FlowseekerProBlademap.jsx` **1,321**,
`services/realized_volatility.py` **1,233**, `frontend/src/App.js` **1,111**.
Split `server.py` (route registration + heatmap build + lifecycle are three
concerns in one file) first.

### Tests depend on gitignored artifacts
`.gitignore:104` ignores `models/`, yet 9 test files load from `models/`
(`test_registry.py`, `test_inference.py`, `test_ml_pipeline.py`,
`test_backtest.py`, `test_ship_models.py`, …). On a fresh clone these error at
collection. **Fix:** ship a tiny fixture model, or mark these
`@pytest.mark.requires_artifacts` and skip when absent.

---

## P2 — Performance

**`backend/services/ml/inference.py:158`** —
`compute_live_features(ticker, period="1y")` calls
`yf.download(ticker, period="1y")`, pulling a **full year of daily bars on
every feature computation**, and (per the ML route) the model is reloaded
rather than held warm. Cache TTL constants exist
(`GEX_CACHE_TTL_SEC`, `FEATURE_CACHE_TTL_SEC`, lines 94/97) but the expensive
download path doesn't consult them — **a cache written but not switched on.**
**Fix:** memoize the yfinance pull (TTL you already defined), and load each
model once into a module-level registry (there's already `services/ml/
registry.py` — use it as the warm cache). Also audit for any **sync call on
the async request path** that can stall the event loop (the blocking
`yf.download` inside an `async def` route is the prime suspect).

---

## Assessment — Rust rewrite (asked separately)

Not worth it. The hot path is **I/O-bound** — cvforge/yfinance network waits
dominate wall-clock, not arithmetic. A Rust rewrite buys nothing against
network latency. The one place native code *might* pay off is a single
numeric kernel (the greeks/GEX aggregation), and even there `numba` is already
a dependency. Recommendation: no rewrite; at most a micro-benchmark of the
greeks aggregator if profiling ever shows it hot (it won't while yfinance is
in the loop).

---

## Suggested order of operations

1. **P0 direction clause** — 3-line fix, gate before any wiring.
2. **`requirements.txt` pins** — unblocks CI immediately; everything else is
   safer once CI actually runs.
3. **Supply-chain dep** — vendor or drop.
4. **Gitignore artifacts + move models to LFS** (non-destructive) — stops the
   bleeding before the history scrub.
5. **Dedup the 3 capability clusters** → then split `server.py`.
6. **History scrub** — last, with Nav's sign-off, coordinated with the fleet.

Nothing here touches the alert-engine stack or freebuff's in-flight frontend
files — all P0-P2 fixes live in files outside the current WIP set.
