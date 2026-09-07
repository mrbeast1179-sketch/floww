# Read-only audit: recent Heatseeker / ticker / Solstice work

Archive note by coordinator: this report's origin-containment snapshot predates the separate backup push. G1 b5f9ae5 is now preserved on origin/archive/20260907-g1-recovery, verified by ls-remote. Its REWORK findings remain unchanged. References to a full universe or unknown-ticker behavior below are findings/proposals; current product choices must be recorded in the task contract.

Date: 2026-09-07 (America/New_York)
Repository: `/Users/nav/Documents/GitHub/floww`
Disposition: **REWORK — do not promote the current range or dirty scroller patch as a unit.**

This was a bounded, read-only review. I did not edit repository code, switch branches, start/restart services, or call Public.com, cvserver, Finnhub, or another live provider. Commit messages and pasted claims were treated as untrusted. The only written artifact is this report.

## Current state after fresh origin refresh

`git fetch --prune origin` completed successfully immediately before the final state check.

- Current branch: `phase9/g1-reads-witness`; it has **no configured upstream**.
- Local `HEAD`: `b5f9ae5d99a4d502efdaf1d0c4d8386c2fa9b0d0` (`fix(tickers): fetch full Finnhub US equities list (5000) alongside featured tickers`).
- `origin/phase9/g1-reads-witness`: `959b3ff02e2157556b032a275b3d5182aef48e53`.
- Local is `0 behind / 5 ahead` of that remote ref: `898fb11`, `3e8097c`, `123e78f`, `fb34324`, `b5f9ae5` are local-only. No remote branch contains `b5f9ae5` or `123e78f`; only `origin/phase9/g1-reads-witness` contains `959b3ff`.
- `origin/main`: `5b9d9a96a29951e548e883d108a806b93c2d11a9`; `origin/main...HEAD` is `1 / 33`, merge-base `5ab259fb1e8cb1f7decb7e449fdeca28d5840295`. Thus this is not a clean descendant of current main.
- Dirty tracked files: `.serena/project.yml`, `frontend/src/App.js`, `frontend/src/components/heatseeker/SkylitTickerBar.jsx`.
- Untracked planning files: `.planning/GSD_HEATSEEKER_CONTEXT.md`, `.planning/GSD_HEAT_DEEPEN.md`, `.planning/HEATSEEKER_DEEPEN_PLAN.md`, `.planning/HEATSEEKER_GSD_CONTEXT.md`.
- Committed net `53267ae^..HEAD`: 11 files, 401 insertions, 45 deletions across `backend/routes/market_data.py`, `backend/server.py`, `backend/services/{cvserver_client,finnhub_client}.py`, `frontend/src/{App.js,App.css}`, and five `frontend/src/components/heatseeker/*` files. The only test changed in the entire committed range is `SkylitControlBar.test.jsx`.

## Stop-ship findings

### 1. `959b3ff` fabricates contracts, fails to render the claimed rows, and changes real analytics

`backend/server.py:953-1005` inserts nonexistent contracts at generated strikes with `type="none"` and zero OI, volume, IV, and gamma. It then feeds those records into the ordinary raw-contract analytics at `backend/server.py:1268-1291`.

The commit's claimed visual result is not implemented end to end. Both GEX builders skip zero-OI/zero-IV rows (`backend/services/gex_core.py:105-114`, `:187-199`), while `SkylitHeatmapGrid` derives displayed strikes only from `grid.strikes` or computed `data.strikes` (`frontend/src/components/heatseeker/SkylitHeatmapGrid.jsx:83-87`). The styling check at `:204-214` therefore never sees the generated strikes.

Fresh offline fixture result:

```text
interpolated_strikes [102.5, 105.0, 107.5]
contract_strikes [100.0, 102.5, 105.0, 107.5, 110.0]
gex_strikes [100.0, 110.0]
grid_strikes [100.0, 110.0]
```

The same fixture proves semantic corruption. A synthetic strike exactly at spot becomes the ATM selection in routines that consume raw contracts (`calc_implied_move` at `backend/services/gex_core.py:431-442`; regime at `backend/advanced_analytics.py:190-200`; pressure at `:440-457`):

```text
real_implied_move: atm_strike=100.0, avg_iv=0.25, implied_move_dollars=6.02
filled_implied_move: None
real_regime: stressed, atm_iv=0.25, atm_strike=100.0
filled_regime: calm, atm_iv=0.0, atm_strike=105.0
real_pressure_nonzero: True
filled_pressure_nonzero: False
```

This is not safe interpolation. Options strikes are discrete listings; a missing strike is not a real zero-OI/zero-IV contract. Even if clearly marked visual gap guides were desired, they must not enter market-data or trading analytics.

### 2. The sparse 4→8-expiry path spends 16 cold Public requests without debiting the budget

For a normal default request, `backend/server.py:1087-1115` first fetches four expiries and then calls the provider stack again with eight when the chain has fewer than 40 strikes. The Public adapter documents and implements `2 + N` upstream requests per cold key (`backend/services/public_api_adapter.py:242-250`, `:354-397`), and caches by `(ticker, max_expiries)` (`:287-307`). The 4- and 8-expiry calls are different cache keys, so the cold total is `(2+4) + (2+8) = 16`.

Fresh fake-broker reproduction (no network):

```text
calls {'expiries': 2, 'quotes': 2, 'chains': 12} total 16
available_before_after 60.0 60.0
inflight_before_after 0 0
ok_delta 2
```

The adapter records success but never calls `budget.acquire_n`; its available tokens remained 60. The existing `FetchCoordinator` takes only one token (`backend/services/fetch_coordinator.py:95-115`), and the `/api/heatmap/{ticker}` path calls `build_heatmap` directly, so this Heatseeker request does not pass through that coordinator anyway. Passing the budget unit tests therefore does not validate this new call graph.

The claim that the deeper Public fetch “bypasses cvserver rate limit entirely” is also false. `backend/server.py:1117-1145` still performs a cvserver full-chain enrichment whenever the result remains below 30 strikes and a key is configured. The four untracked Heat documents explicitly say cvserver is limited to 20 calls/hour and must be used only for Solstice parity; the implementation violates that contract. The code also does not require `raw.data_source == "public_api"` before describing/retrying the first result as Public.

### 3. `/tickers/all` claims are false and its current cache is nonfunctional

`959b3ff` did not fix a pre-existing `/tickers/all` crash. Its diff **introduced the endpoint** and an unused `Request` import/helper; its parent had no such route. At `959b3ff`, the endpoint called `FinnhubClient.symbols_us_equities()`, but that method did not exist until local-only `898fb11`, so the new endpoint could not serve the claimed list.

The current route still does not cache. `backend/routes/market_data.py:113-124` imports `_TICKER_CACHE` and `_TICKER_CACHE_TS` by value from `server`, then assigns local names rather than the server module globals declared at `backend/server.py:776-780`. A fresh patched-provider call twice produced:

```text
provider_calls 2
server_cache None None
cached_flags True True
ages 0.0 0.0
```

Thus every page load can call Finnhub, and even the first uncached response falsely says `cached=true`. The synchronous SDK call at `backend/routes/market_data.py:120-122` also blocks the async route. `refresh=true` can force a provider call and has no route-specific authentication/rate gate visible here.

### 4. Ticker navigation is inconsistent; the latest 500/200 claim is not what the code does

Current App and ControlBar navigation concatenate `trinity + default + popular` without case-normalized deduplication (`frontend/src/App.js:697-717`; `frontend/src/components/heatseeker/SkylitControlBar.jsx:58-80`). The original API sets contain 95 entries but only 80 unique symbols. With that ordering, `SPY -> QQQ -> SPY` can loop because `indexOf` always finds the first duplicate. The ticker bar separately deduplicates, so visible order/count, arrow order, and position denominator disagree.

The current focused test also exposes an unresolved contract split: the production component accepts a ticker object, but `SkylitControlBar.test.jsx:67-86` still passes arrays. Result: 1 of 18 focused tests fails (`Expected HOOD; received MSFT`). At `53267ae`, the opposite mismatch was worse: App passed an object while ControlBar called array `.indexOf`, so the claimed isolated tests masked the integration failure. `4e52e77` added a position calculation that calls `.indexOf` during render and inherited that object/list break.

`b5f9ae5` mounts up to 5,000 buttons; React/browser does not automatically virtualize a flex row. It also takes only the alphabetically first 5,000 of a claimed ~11,220-symbol universe (`frontend/src/App.js:524-550`), so “full universe” and “every tradable name” are inaccurate.

The latest uncommitted patch does this:

- `SkylitTickerBar.jsx:25-50` truncates the deduplicated button list to the first 500 while displaying the full unique count.
- Its input does **not** search or filter the retained 5,000-symbol array; it merely submits arbitrary free text. The comment “full list is still available via search” is false.
- `frontend/src/App.js:128-160,189` supplies only the first 200 raw symbols to a different header autocomplete, which filters that prefix and displays at most 12 suggestions. It is not “200 search results” and cannot suggest a symbol outside that prefix, though Enter still submits free text.
- Arrow keys and ControlBar continue to cycle the uncapped, duplicate-containing array rather than the 500 visible buttons or 200 suggestion source.
- The focus selector typo introduced by `3e8097c` remains at `frontend/src/App.css:4109`: `.scylit-ticker-search:focus`; `.skylit-ticker-more` is dead styling.

### 5. Frozen `App.js` approval is not evidenced for these changes

`CLAUDE.md:36-45` and `.planning/AGENT_CONTRACT.md:25-34` require stopping for explicit approval before touching `frontend/src/App.js`. Commits `53267ae`, `898fb11`, `123e78f`, and `b5f9ae5`, plus the current dirty patch, touch it. Their commit bodies do not cite a waiver.

The durable waiver found in `.planning/ROADMAP.md:283-287` is a prior, specific 2026-09-03 approval that says unknown tickers stay put. It is not evidence for these later edits and directly conflicts with `53267ae` changing unknown tickers to wrap. This does not prove no out-of-band approval existed; it proves no durable in-repo evidence was found.

### 6. Four untracked Heat docs are stale, duplicative, and internally contradictory

The four untracked files are 17, 41, 55, and 23 lines (136 total), with near-identical Heatseeker-deepening context. All stop at “3 commits” / `4e52e77`, omit `959b3ff` and the five later local ticker commits, and repeat the cvserver-only-for-parity constraint that the code violates. `HEATSEEKER_DEEPEN_PLAN.md:30-40` proposes the unsafe deeper-fetch/interpolation design but acknowledges the Public rate-limit risk without a debit contract. They should not all be committed.

## Exact commit/state matrix

Verdicts below assess each delta against its stated contract. `ACCEPT (isolated delta)` is not approval of the cumulative branch.

| SHA / state | Location | Verdict | Exact reason |
|---|---|---|---|
| `53267ae` — full ticker arrow nav / unknown wrap | On origin branch | **REWORK** | App passes an object to an array-only ControlBar; raw duplicates break full traversal; changes previously approved unknown-ticker behavior; frozen App waiver not evidenced. |
| `f1ed4bf` — wider bands / route cap 120 | On origin branch | **ACCEPT (isolated delta)** | Deterministic bounded band/cap change; no defect found in this delta. Its live VSAT/SPY counts and “60 passed” remain historical, and dedicated band regressions are still recommended. |
| `658e6cb` — sparse cvserver screen enrichment | On origin branch | **REWORK** | Normal Heatseeker requests consume the 20/hour parity-only provider; globally widens the screen band; no contract test. |
| `4e52e77` — cvserver full chain / position badge | On origin branch | **REWORK** | Increases dependence on the prohibited parity-only provider; position badge makes the ticker object/array failure occur during render; no verification evidence in body. |
| `959b3ff` — deep refetch / interpolation / route claim | Origin tip | **REWORK** | Critical fabricated-data analytics corruption; claimed dashed rows are absent; 16 unbudgeted Public requests; cvserver still called; route was introduced rather than fixed and initially called a missing method; zero tests added. |
| `898fb11` — 11,220 universe | Local-only | **REWORK** | Fresh commit-state lint found undefined `universe`, `universeTotal`, and `displayList`; endpoint/cache contract broken; 11k mounted buttons; frozen App waiver not evidenced. |
| `3e8097c` — render all / “CSS typo fix” | Local-only | **REWORK** | Dashboard's undefined `universe` persists; browsers do not natively virtualize 11k React buttons; it changes the correct selector to misspelled `.scylit...`, opposite the claim. |
| `123e78f` — remove universe concept | Local-only | **REWORK** | Deletes App's `loading/setLoading` state while leaving consumers, causing undefined identifiers; leaves the backend universe endpoint/helpers behind; navigation remains duplicate-sensitive; frozen App waiver not evidenced. |
| `fb34324` — visible scrollbar | Local-only | **ACCEPT (isolated delta)** | CSS-only scrollbar discoverability change is internally sound. Its parent head remains broken, so this is not a runnable-head acceptance. |
| `b5f9ae5` — fetch/render 5,000 | Local `HEAD` | **REWORK** | Restores missing loading state, but mounts 5k buttons, exposes only an alphabetical prefix, inherits broken endpoint/cache and duplicate navigation, adds an all-or-nothing dual fetch, has no tests, and touches frozen App without durable waiver evidence. |
| Dirty cap-500 / header-source-200 patch | Uncommitted | **REWORK** | The 500 buttons, first-200 suggestion source, max-12 suggestions, free-text TickerBar input, and uncapped arrow list are four different universes; comments/counts overclaim discoverability. |

## Fresh verification and limitations

Fresh commands run against current `b5f9ae5` plus the dirty App/TickerBar patch:

```text
cd frontend
CI=true npm test -- --watchAll=false --runInBand \
  --testPathPattern='Skylit(ControlBar|Dashboard|TickerBar|HeatmapGrid)\.test\.jsx'
Result: 3 suites passed, 1 failed; 17 tests passed, 1 failed.
Failure: SkylitControlBar array-vs-object expectation (HOOD vs MSFT).
```

```text
cd frontend
npx eslint --no-config-lookup --ext .js,.jsx [explicit JSX/browser globals] \
  --rule no-undef:error --rule react/jsx-uses-vars:error \
  App.js and the four touched Heat components
Result: pass after declaring standard browser globals. This is a focused no-undef check,
not the repository's canonical lint (ESLint 9 had no directly usable project config here).
```

```text
cd backend
./.venv/bin/ruff check routes/market_data.py server.py \
  services/cvserver_client.py services/finnhub_client.py
Result: fail, 5 findings (unused Request; two unsorted import blocks;
SIM105; UP017).
```

```text
cd backend
./.venv/bin/pytest -q tests/perf/test_feed_economics.py \
  tests/services/test_public_budget.py tests/services/test_public_api_integration.py
Result: 24 passed, 21 warnings, 48.79s.
```

Those 24 tests use mocks and validate the existing adapter shape/cache and budget component. `test_feed_economics.py` explicitly documents the adapter's debit gap; none exercises `959b3ff`'s 4→8 Heatseeker flow, interpolation, `/tickers/all`, or cvserver exclusion. The two additional Python fixture probes reproduced the 16-call/no-debit behavior and analytics corruption shown above.

Not freshly verified: commit-body live curls, actual VSAT “20 + 17” rows, SPY “120 unchanged”, Finnhub “11,220” or “5,000” responses, served bundle hashes, browser performance, and historical “11/51/60 tests pass” claims. No services were used to test them, by scope. No full suite or production build was run.

## Recommended task contracts

### H1 — Preserve strike truth (P0)

Scope: `backend/server.py`, analytics tests, optional grid-only presentation.

Acceptance contract:

1. Raw `contracts` contains only vendor-listed contracts; remove `type="none"` zero records from every analytics input.
2. Either show listed strikes only, or represent visual gaps in a separate presentation-only field. Any gap row is labelled “no listed contract,” non-clickable/non-tradable, and never expressed as zero GEX/OI/IV.
3. Fixture invariants prove implied move, market regime, pressure cloud, GEX nodes, and opportunities are identical with visual gap metadata enabled or disabled.
4. Tests prove every rendered data strike exists in the vendor-listed strike set, unless it is an explicit non-data guide.

### H2 — Make provider cost atomic and keep cvserver parity-only (P0)

Scope: `public_api_adapter.py`, Heatseeker fetch orchestration, Public budget tests.

Acceptance contract:

1. On a cache miss, atomically acquire the real fan-out cost before any Public call (`2 + N` or an exact equivalent); release one in-flight slot on every exit. Warm cache costs zero.
2. Deepening from four to eight reuses the expiry list, quote, and first four chains, for at most 10 cold upstream calls—not 16—or is removed.
3. A fake `CountingBroker` proves cold/warm/concurrent counts and exact token deltas; budget refusal proves zero upstream calls.
4. Normal Heatseeker never calls cvserver. cvserver is available only behind an explicit, test-pinned Solstice parity action/flag; a spy test asserts zero cvserver calls on sparse Public data.
5. Only a result positively identified as Public may use Public-specific deepening; fallback source labels remain honest.

### T1 — One ticker universe contract (P0/P1)

Scope: ticker normalization/navigation components; `App.js` only after a new explicit waiver is recorded.

Acceptance contract:

1. Choose one case-normalized, order-preserving deduped list and reuse it for displayed count, position, arrows, buttons, and search identity. Pin 95 raw / 80 unique for the static fixture.
2. Pin traversal across duplicates (`SPY -> QQQ -> next unique`, no two-symbol loop), both boundaries, and the approved behavior for unknown tickers. Do not change “unknown stays put” without a new product decision/waiver.
3. Do not mount 5k/11k buttons. Use server-side/query-driven search or actual list virtualization. If only 500 are browsable, label it “showing 500 of N”; search tests must find symbols beyond 200 and 500.
4. Component tests use the production ticker object contract; add an App/Dashboard integration test instead of mocking both bars.
5. Record the frozen-App approval in the task and commit body before editing.

### T2 — Decide and harden or remove `/tickers/all` (P1)

Recommended default: remove the unused/dead endpoint and Finnhub helpers if free-text open-universe entry is sufficient.

If retained, acceptance requires: a real module-owned cache (two calls => one provider call), accurate first-hit `cached=false` metadata, `asyncio.to_thread` or an async client, refresh authorization/rate limiting, stable fallback when the universe call fails, pagination/query search tests, and no claim that a 5,000-symbol prefix is the full market.

### D1 — Heat document hygiene (P1)

Consolidate the four untracked files into one canonical, current plan. It must name the exact reviewed SHAs/origin state, distinguish desired provider policy from current code, remove live results that lack durable evidence, and record the H1/H2/T1/T2 contracts. Delete the other three only in an explicitly authorized documentation cleanup.

## Final recommendation

Archive the current local head if preservation is required, but do not push it as the feature branch tip and do not merge the origin tip. Start with H1 and H2; ticker work should then be rebuilt under one explicit universe/navigation contract with a documented `App.js` waiver. The only independently acceptable deltas found were `f1ed4bf` and `fb34324`.
