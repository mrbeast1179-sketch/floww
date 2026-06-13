# AlphaPod Clone — Program Architecture & Execution Spec

- **Status:** DRAFT — pending Nav review (brainstorming gate). Not yet committed (dead origin + shared-index race; see §8.3).
- **Date:** 2026-06-02
- **Author:** Claude (architect)
- **Method:** superpowers brainstorming → (on approval) writing-plans

## 1. Goal & scope

Make floww a faithful clone of **AlphaPod** (hub.alphapodtrading.com) — **UI *and* methods**, so floww emits the same flow alerts — while **preserving floww's crown-jewel tabs unchanged**.

Decisions locked with Nav (2026-06-02):
- **Methods = all three (hybrid):** replay the 2,148 captured payloads to bootstrap the UI, *and* reverse-engineer the alert rules, *and* run them live on floww's own feeds behind one interface. End state: live, ours, functionally-equivalent.
- **Supabase = all three:** Postgres alert **store** + **Realtime** push + **Auth**/accounts. Additive.
- **Everything, not only UI.** Full product: every tab + the alert engine + data layer.
- **Execution:** the fleet — DeepSeek Pro (30h window) + 10 Hermes (H1–H10) + Owl Alpha — over multiple days, lanes assigned here.

Non-goals: bit-for-bit identical alerts (different data feed + inferred thresholds — unreachable and not required). Replacing floww's existing backend.

## 2. Source material

Mirror: `~/GitHub/hub-alphapodtrading` (not TCC-protected; always reachable).
- `assets/index-Bnpw5mug.css` — full AlphaPod design system (`:root` token block).
- `assets/index-CFbq_e3t.js` (784KB) — SPA bundle (routes, sort modes, rule names).
- `captured/*.html` (16 pages, real data) · `api-data/*.json` (**2,148 payloads, 278 tickers**).
- `fonts/` (Inter, JetBrains Mono, Space Grotesk WOFF2 + `local-fonts.css`) · `screenshots/`.
- Rule taxonomy already visible: `RepeatedHits`, `RepeatedHitsAscendingFill`, `RepeatedHitsDescendingFill`, `Golden Sweeps`, `LowHistoricVolumeFloor`, `OTM Conviction`, `*_TIER_n`; confidence `HIGH/MED/LOW`; sort modes `actionability/confidence/premium/ticker` (conviction HIGH=3/MED=2/LOW=1).

**Phase 0 (capture completeness)** closes any gaps before the fleet builds (§7).

## 3. Target architecture

### 3.1 Frontend shell
New `frontend/src/shell/AppShell.jsx` renders AlphaPod's **fixed 240px left rail** (collapsible, persisted to `localStorage["apw.sidebarCollapsed"]` via `data-collapsed`, 180ms width animation, `#070708` bg, 1px right border `#ffffff0f`). The rail owns nav and drives the existing `page` state. **App.js keeps its `page===` switch** — AppShell wraps it; App.js edits stay surgical (frozen-file rule). `react-router-dom@7` (already a dep) is used only for `/t/:ticker` ticker routes inside the Ticker Analysis tab, not for the top-level shell.

### 3.2 Design system (token consolidation + re-hue)
Today floww has **two conflicting `:root` files** (App.css wins on `--bg/--panel/--border`; index.css owns semantics). Consolidate into one token layer in `src/index.css`, mapped to AlphaPod:

| Role | floww now | AlphaPod target |
|---|---|---|
| Page bg | `#07080a` | `#080b10` |
| Sidebar bg | — | `#070708` |
| Card/surface-1 | glass `rgba(18,20,24,.72)` | `#0d1117`, radius 24px, inset hi-light + `0 4px 24px #0006` |
| Row hover | `rgba(255,255,255,.025)` | `#111820` |
| Border | solid `#1c1f24` | **white-alpha `#ffffff0f`** (hover `#ffffff1f`) |
| Text 1/2/3 | `#e4e4e7` / — / — | `#fffffff2` / `#ffffffa6` / `#ffffff73` |
| **Brand accent** | teal `#5eead4` + yellow `--pika #facc15` + purple `--barney #a855f7` | **gold `#c9a84c`** (links, `:focus-visible` 2px ring, MED conf) |
| Bull / bear | `#34d399` / `#f87171` | `#22c55e` / `#ef4444` |
| Confidence | — | HIGH `#22c55e` · MED `#c9a84c` · LOW `#e07b00` (text + ~12–15% dim bg + ~25% border) |
| UI font | Sora | **Inter** |
| Display font | — | **Space Grotesk** |
| Mono | JetBrains Mono | JetBrains Mono ✓ |
| Badge geometry | `.tag` 10px, r3px | `.fa-status-badge` h18px, px6, 10px/700, r3px, tracking .04em |

**Preservation:** Trinity / Heatseeker are wrapped in a `.legacy-theme` scope that pins the *current* token values, so the global gold re-hue cannot alter them. (Skylit is re-skinned, per Nav.) Fonts self-hosted from the mirror's `fonts/` tree — **no npm dependency**.

### 3.3 Tabs
- **Preserved exactly:** Trinity, Heatseeker.
- **Re-skinned (inherit AlphaPod tokens):** **Skylit**, Flowseeker→**Flow Alerts**, Portfolio, Journal, SwarmSPX.
- **New (ported from mirror):** Alpha Flow, Daily Report, SPX GEX, Ticker Analysis (`/t/:ticker` + report), Earnings — *real-data tabs first*. Then mock-tier: Heatmaps, Signals, Trade Log, Performance, Key Levels, SPX Alerts, Dashboard.

### 3.4 Alert engine (new backend service)
`backend/services/alpha/` — reverse-engineered rule set producing the AlphaPod flow-alert schema:
```
{ time, ticker, type(call|put), side(buy|sell), strike, oi, premium, spot,
  sentiment(BULLISH|BEARISH), confidence(HIGH|MED|LOW),
  rule(RepeatedHits|GoldenSweeps|LowHistoricVolumeFloor|OTMConviction|…),
  tier(int), repeated_hits_count(int) }
```
- **Replay harness** serves the 2,148 captured payloads first (UI parity day one).
- **Live rules** re-implemented on floww feeds (Databento OPRA / Polygon / yfinance). Sentiment + confidence reuse `/api/uoa` logic (`u.sentiment`, `u.score`); repeated-hits = net-new server-side print aggregation (group identical contract prints, count recurrences).
- Single interface (`AlertSource`) so replay→live is a swap, not a rewrite.

### 3.5 Supabase (additive)
- `alerts` table (alert schema above) + `tickers`, `repeated_hits` rollups.
- **Realtime** channel per page (flow-alerts, alpha-flow, spx) pushing inserts to the UI (replaces hand-rolled SSE for the new tabs).
- **Auth** = accounts + watchlists + `apw.*` prefs. Mongo/DuckDB/FastAPI remain authoritative for Trinity/Heatseeker/Skylit.

### 3.6 Untouched
Trinity, Heatseeker rendering; `inference.py`, `dash_ui.py`, model artifacts; the GEX/ML engine. (Skylit's *data* engine stays; only its skin changes.)

## 4. Data strategy
Replay (captured truth) → reverse-engineer thresholds *against those 2,148 payloads as ground truth* → live engine validated to reproduce the captured rule tags on known inputs. The 2,148 payloads double as the alert-engine's regression fixture set.

## 5. Build order (phases)

| Phase | Deliverable | Depends on |
|---|---|---|
| 0 | Capture completeness: mirror audit + crawl missing pages/api + **rules dossier** (exact thresholds from api-data + bundle) | — |
| 1 | **Foundation:** design-system token layer + fonts + `AppShell` left rail | 0 |
| 2 | Alert engine (replay + live skeleton) + Supabase schema/realtime/auth | 0 |
| 3 | **Flagship:** Flow Alerts tab end-to-end (FlowTable→AlphaPod table, wired to engine/realtime) | 1,2 |
| 4 | Real-data tabs: Alpha Flow, Daily Report, SPX GEX, Ticker Analysis, Earnings | 1,2 |
| 5 | Mock-tier tabs | 1 |
| 6 | Parity QA: visual diff vs screenshots, schema diff vs payloads, test gates | all |

Phase 1 tokens are **frozen before** Phases 3–5 start, so per-tab lanes never fight over global CSS.

## 6. Fleet execution model

| Lane | Agent | Owns (disjoint files) |
|---|---|---|
| Foundation | **DeepSeek Pro** | `src/shell/`, `src/index.css` token layer, font assets, `App.js` surgical wrap |
| Alert engine | **DeepSeek Pro** (cont.) | `backend/services/alpha/`, replay harness, regression fixtures |
| Supabase | **Hermes H1** | `backend/services/supabase/`, schema/migrations, realtime client |
| Flow Alerts | **Hermes H2** | `src/components/flowalerts/` (forked from flowseeker) |
| Alpha Flow | **H3** · Daily Report **H4** · SPX GEX **H5** · Ticker Analysis **H6** · Earnings **H7** | one tab dir each |
| Mock tier | **H8 / H9** | one tab dir each, split |
| Parity QA / verification | **Owl Alpha** + **H10** | `tests/`, visual-diff harness, no source ownership |

**Race rules (single clone):** each lane owns a disjoint file set; **pathspec commits** (`git commit -- <lane files>`); `git pull --rebase --autostash` before push; shared globals (tokens, App.js) only mutated in Phase 1 by DeepSeek, frozen after. **No agent trusts another's "done"** — every lane gated by real `pytest` / `craco test` / `curl` output (Round-7 fabrication is the floor).

## 7. Constraints honored
Frozen files (`package.json`, `craco.config.js`, `App.js`, `inference.py`, `dash_ui.py`) — only changed via the §8 approvals or surgical App.js edits. TDD per change; never skip/xfail a passing test. PWA launch via `decoder` alias unchanged.

## 8. OPEN DECISIONS (need Nav's sign-off)

1. **Supabase dependency.** Realtime/auth want `@supabase/supabase-js` (+ maybe `@supabase/ssr`) — a **new dep in the frozen `package.json`**. Approve adding it, or go REST-only (no client lib, uglier realtime)?
2. **App.js approach.** Wrapper + surgical edits (recommended, safest with concurrent agents) vs full App.js refactor (faster, higher race/regression risk)?
3. **Remote.** Origin (GitHub) is **suspended/dead** — 11 agents over days need a coordination remote. New **GitLab** (recommended; avoids re-suspension), new GitHub account, or local-only + frequent bundles (highest race risk, no offsite copy)?
4. **Preserved-tab confirm.** Preserve Trinity + Heatseeker + Skylit exactly; re-skin Flowseeker/Portfolio/Journal/SwarmSPX. Correct?

## 9. Verification & acceptance
- **Visual:** side-by-side vs `screenshots/01-flow-alerts.png` et al.
- **Schema:** new alerts validate against the 2,148 captured payload shapes.
- **Behavior:** replayed alerts render identically; live engine reproduces captured rule tags on known inputs.
- **Tests:** backend `pytest` green, frontend `craco test` green, `ruff` clean per lane.

## 10. Risks
Single-clone races (→ lanes + remote + rebase) · frozen-file collisions (→ §8 approvals) · inaccurate reverse-engineered thresholds (→ tune against 2,148 payloads) · agents fabricating completion (→ Owl Alpha verification lane) · GitHub re-suspension (→ GitLab + bundles).
