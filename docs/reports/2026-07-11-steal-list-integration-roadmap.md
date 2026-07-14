# floww — Feature Integration Roadmap ("Steal List")

_Generated 2026-07-11 by a multi-agent scan of floww's 26 cloned reference repos + web discovery, synthesized by Fable 5._

**Scope:** capabilities floww does NOT yet have, portable onto its free/cvforge + yfinance data (no paid tick feeds, no broker execution). Ranked by value/effort. Effort 1=hours, 5=weeks. Value 1-9.

## Themes

- **Buy the realized side of the trade** — Floww is entirely implied/positioning-side today. The single biggest value cluster (RV suite + VRP, typical ranges, earnings screener, wheel screener) is about benchmarking implied against realized — is this premium rich? — which is precisely the premium-selling edge floww's journal has already validated. Four of the sixteen items chain together into one 'is vol rich or cheap' answer.
- **From read to trade: close the last mile** — Floww tells you what dealers are doing but not what YOU should structure. The strategy builder (PoP/payoff), strike cone, wheel screener, scenario stress grid, and eventually the backtester convert existing analytics into concrete strikes, structures, odds, and book-level risk — the layer where a retail user actually acts.
- **Fix the inputs before adding more outputs** — Everything downstream — GEX, flip, King node, RND, PoP — inherits yfinance's noisy last-price IVs and stale 0DTE OI. Three cheap items (IV-from-mid solver, 0DTE volume-for-OI, and later the SVI arb-free surface) form a staged input-quality pipeline that quietly improves every existing panel with zero new UI.
- **Positioning as a movie, not a snapshot** — Current GEX is a point-in-time, current-spot, OI-only picture. The profile engine (exposure vs hypothetical spot), dual-GEX activity ratio (flow vs stock), regime-persistence classifier (30-day stability), max-pain drift, and OCC account-type data each add a missing dimension: price, activity, time, and actor.
- **Sequencing matters: three dependency chains** — Ship in dependency order: (a) IV solver → RND → SVI surface; (b) RV service → VRP tile → earnings screener; (c) strategy payoff engine → scenario grid → backtester. The quick wins (ranks 1-3, 5, 8-10) are order-independent and can land in any single session.

## Roadmap — vol / GEX / pricing / strategy

### #1 · Dual-GEX: OI vs volume-weighted gamma + hedging-intensity activity ratio  `[quick-win]`  — value 6 / effort 1
- **Why:** Highest value/effort on the board (6:1). One extra aggregation pass distinguishes what dealers structurally HOLD from what they are actively DOING today — identical flip levels behave differently when flow fights vs confirms resting OI, which floww's OI-only GEX cannot see.
- **Steal from:** `iAmGiG_gex-llm-patterns/src/gex/gex_calculator.py:271-366 (calculate_dual_gex)`
- **Lands in floww:** Extend backend/services/gex_aggregator.py compute() to also aggregate GEX weighted by contract volume (already in chain dicts via routes/heatseeker.py:43); emit gex_volume + activity_ratio = |GEX_vol/GEX_OI| as a 'hedging intensity' badge on the dealer-positioning panel.

### #2 · 0DTE/1DTE exposure weighted by same-day volume instead of stale OI  `[quick-win]`  — value 5 / effort 1
- **Why:** 0DTE dominates SPX/SPY/QQQ dealer gamma and day-of OI hasn't printed yet, so floww systematically mis-weights the bucket that drives most intraday hedging. A one-branch data-quality fix that improves every downstream gamma signal (heatmap, flip, King node).
- **Steal from:** `aaguiar10_gflows/modules/calc.py:339-364 (is_short_dte volume-for-OI substitution, fillna to OI)`
- **Lands in floww:** In backend/services/gex_aggregator.py and the gex_history compute path, branch on T <= 1/252 and select volume (fillna OI) as the per-contract weight. Volume already flows through heatseeker.py:43.

### #3 · Wheel / premium-selling income screener (CSP + covered calls ranked by annualized return on collateral)  `[quick-win]`  — value 7 / effort 2
- **Why:** Directly serves floww's only validated edge — premium selling. Nothing in floww ranks contracts by income yield or breakeven; Flowseeker ranks by flow archetype, which is orthogonal. Cross-tagging with IV-rank floats rich-vol, high-yield names to the top.
- **Steal from:** `fanzhenya_options_lab/options_lab.ipynb — find_best_put_to_sell, find_best_call_to_sell, annualize_return/calc_put_breakeven`
- **Lands in floww:** New backend/services/screeners/wheel_income.py iterating yfinance option_chain over expirations, computing ARR + breakeven + IV/volume filters; expose /api/screener/income?symbol=&side=put|call&max_breakeven=; sortable table in the existing scanner UI.

### #4 · Risk-neutral density (Breeden-Litzenberger implied PDF) from the chain  `[high-impact]`  — value 9 / effort 3
- **Why:** Adds a whole missing axis: price-space probability. 'Market prices a 12% chance of SPY < 580 by Friday' is the single most legible output for a retail trader and nothing in GEX/Trinity expresses it. Cheap because floww already has the chain, BS repricing, and scipy. Natural consumer of the clean-IV work (rank 5) and feeder for the strike cone (rank 10).
- **Steal from:** `PavanAnanthSharma/Breeden-Litzenberger-formula-for-risk-neutral-densities (smile fit -> reprice calls -> d2C/dK2 = e^{rT} f_Q(K))`
- **Lands in floww:** New backend/analytics/risk_neutral_density.py fed by the same yfinance chain Trinity pulls; cubic-spline smile smoothing + numerical 2nd derivative; GET /api/rnd/{symbol}/{expiry}; React PDF/CDF panel beside the Trinity smiles with tail-prob and expected-move readouts.

### #5 · IV inversion solver — recompute clean IV from bid/ask mids  `[quick-win]`  — value 6 / effort 2
- **Why:** Floww's entire vol stack trusts yfinance's impliedVolatility field, which is stale, last-price-based, and missing on illiquid strikes. ~15 lines (Newton via existing bs_vega, bisection fallback) cleans the input to skew, term structure, RR, GEX, and the RND above. Also stage 1 of the SVI surface (rank 16).
- **Steal from:** `MattL922_implied-volatility/implied-volatility.js::getImpliedVolatility (upgrade bisection to Newton using floww's bs_vega)`
- **Lands in floww:** Add implied_vol_from_price() to backend/bs_greeks.py; wire into vol_analytics.calc_iv_surface_data preferring solver(mid) over raw yfinance IV, with a 'clean IV' toggle; q from yfinance dividendYield.

### #6 · Spot-shifted exposure PROFILE engine (gamma/vanna/charm/delta vs price curves + true flip points)  `[high-impact]`  — value 8 / effort 3
- **Why:** Upgrades floww's flip from 'strike where per-strike GEX crosses zero' to the SqueezeMetrics-style true gamma-neutral and delta-neutral spot, interpolated from aggregate exposure recomputed across 300 hypothetical spot levels. Also yields vanna/charm PROFILE curves (vanna wall, charm-into-close) and 0DTE-vs-structural decomposition via per-expiry masks. Highly portable — floww's vectorized numba greeks already exist; only the spot-grid loop and flip solver are new.
- **Steal from:** `aaguiar10_gflows/modules/calc.py:306-749 (calc_exposures, zerodelta/zerogamma) + modules/stats.py:44-121`
- **Lands in floww:** New ExposureProfileService looping backend/services/numba_greeks.py over np.linspace(0.5*spot, 1.5*spot, 300) using existing databento_eod_chains data; new route beside routes/greeks.py; 'Exposure Profile' curve chart on Skylit next to the GEX heatmap, complementing zero_gamma_levels.

### #7 · Realized-vol suite + variance risk premium (Yang-Zhang, GK, Parkinson, vol cones) with realized-range percentile bands  `[high-impact]`  — value 8 / effort 3
- **Why:** Trinity is entirely IV-side, so floww literally cannot compute IV-minus-RV — the core premium-seller edge — or judge if today's implied move is rich vs how far the name actually travels. Merges two candidates: volest's estimator suite + cones, and EzOptions' daily/weekly/monthly typical-range p50/p80/p95 bands overlaid with floww's existing calc_implied_move.
- **Steal from:** `jasonstrimpel/volatility-trading volest.VolatilityEstimator (cones, rolling_quantiles) + EazyDuz1t_EzOptions/ezoptions.py calculate_typical_ranges (L1018)`
- **Lands in floww:** New RV service fed by yfinance OHLC floww already pulls; /vol/realized returning 20/30/60d RV across estimators + cone percentile + range bands; VRP tile (front ATM IV − Yang-Zhang RV) beside IV/GEX panels; gate premium-selling ideas (wheel screener, rank 3) on it. Prerequisite for the earnings screener (rank 13).

### #8 · 30-day net-GEX regime-persistence classifier  `[quick-win]`  — value 6 / effort 2
- **Why:** Floww classifies each day long/short gamma but never says whether the regime is a durable tradable backdrop or transitional chop. Pure post-processing (sign-persistence %, flip count, magnitude conviction, CV) over a time series floww already builds.
- **Steal from:** `iAmGiG_gex-llm-patterns/src/validation/regime_classifier.py:110-243 (classify_window, _classify_regime_type)`
- **Lands in floww:** Feed backend/services/gex_history.py:build_gex_history per-day gex_total into a ported RegimeClassifier; regime badge (persistent_positive / persistent_negative / low_conviction / transitional) on the Skylit dealer-positioning panel.

### #9 · Max pain + max-pain drift tracking into expiry  `[quick-win]`  — value 6 / effort 2
- **Why:** OI-weighted pinning magnet genuinely distinct from the King node (gamma-based); the two often disagree, and the daily drift of max pain toward spot into expiry is a testable pin signal for 0DTE/weekly names. Zero new data — computed from OI already fetched for GEX.
- **Steal from:** `asad70/Options-Max-Pain-Calculator OptionsMaxPainCalc.py + ZubZubZuberi/MaxPainHistory for the drift study`
- **Lands in floww:** backend/analytics/max_pain.py over existing per-strike OI; snapshot daily into a DuckDB floww_* table via execute_write (per audit rule); overlay the max-pain line on the Skylit strike×expiry GEX heatmap.

### #10 · 16-delta/30-delta expected-range strike cone  `[quick-win]`  — value 5 / effort 2
- **Why:** Converts floww's existing prob_above distribution into the concrete output premium sellers act on: the actual strikes at P=16/84% and 30/70%. Small and incremental, but it's the last mile from curve to strike selection, and it pairs with the wheel screener and RND.
- **Steal from:** `EazyDuz1t_EzOptions/ezoptions.py find_probability_strikes (L2948), find_delta_strikes (L2990)`
- **Lands in floww:** Helper over the existing prob-distribution output (backend/server.py:496-524) emitting strike_above/strike_below at target probabilities; tiles + cone lines on the implied-move panel.

### #11 · Multi-leg strategy builder: payoff curves, breakevens, PoP, expected P&L, VaR/ES  `[high-impact]`  — value 9 / effort 4
- **Why:** The biggest capability hole: floww has per-position greeks but no way to assemble an iron condor/vertical/calendar and see its payoff diagram, breakevens, max P/L, probability of profit, or tail risk. Merges two candidates — use optionlab (pure-Python pip, selectable PoP engines: BS/array/laplace/montecarlo) as the engine rather than porting harryho71's C++; steal harryho71's MultiLegStrategy.js as the React UI blueprint. Turns the whole GEX/vol read into 'build a trade and see its odds.'
- **Steal from:** `rgaveiva/optionlab run_strategy/Inputs/Outputs + get_pl(); UI from harryho71_option-strategy-pricer/src/frontend/src/components/MultiLegStrategy.js; VaR/ES pattern from RiskMeasures.cpp`
- **Lands in floww:** POST /strategy/evaluate builds optionlab Inputs from the DuckDB chain snapshot (spot, r, mids, per-leg IV floww already computes); returns PoP/expected-P&L/breakevens/payoff arrays; new 'Strategy Builder' tab on Skylit with payoff + greeks-vs-spot curves. Use lognormal σ from the RV/IV service for probability weighting.

### #12 · Whole-book scenario stress-test matrix (spot × IV × time shock grid)  `[high-impact]`  — value 8 / effort 4
- **Why:** Answers 'what happens to my book if spot drops 5% and IV pops 20% over 3 days' — impossible today with only point-in-time portfolio greeks. Pure recompute over the existing position store with floww's own BS pricer; no new data.
- **Steal from:** `George-Dros_Options_Portfolio/functions.py:457-770 (analyze_combined_impact, process_portfolio, compute_portfolio_stats) + 3D surface plots 797-884`
- **Lands in floww:** POST /portfolio/scenario running the shock grid (spot 0.8-1.2x, IV 0.8-1.2x, +7/30/60d decay) over floww's position store; aggregate net greeks + repriced P&L; Plotly surface or spot-vs-time heatmap in Skylit. Shares leg-repricing code with the strategy builder (rank 11).

### #13 · Earnings-volatility screener (IV30/RV30 + term-slope Recommended/Consider/Avoid rule)  `[high-impact]`  — value 7 / effort 4
- **Why:** Floww has zero earnings-event handling. Codifies the well-known sell-rich-pre-earnings-IV strategy with concrete thresholds (ADV ≥ 1.5M, IV30/RV30 ≥ 1.25, slope ≤ −0.00406) and a universe scan by report date. Mostly wiring: RV30 comes from the rank-7 RV service, IV30/term slope from Trinity, earnings dates from yfinance calendar (skip the paid Investing.com scrape).
- **Steal from:** `Acelogic/Earnings-Volatility-Calculator src/calculator.py`
- **Lands in floww:** Earnings-vol screener job pulling yfinance earnings dates, applying the decision rule, emitting candidates into the Flowseeker feed/alerts as event-timed straddle/calendar ideas. Depends on rank 7 (RV service).

### #14 · OCC cleared volume by account type — Customer vs Firm vs Market-Maker panel  `[high-impact]`  — value 8 / effort 5
- **Why:** The only genuinely NEW free data source in the batch: answers 'WHO traded' (dealers vs customers, call/put split, dealer directional bias), which yfinance aggregate volume/OI can never reveal. Tempered by T+1 daily granularity and an unofficial endpoint — port EzOptions' 5-day date-fallback and defensive CSV parsing wholesale.
- **Steal from:** `EazyDuz1t_EzOptions/ezoptions.py: download_volume_csv (L4010), get_params_for_date (L3793), process_market_maker_data (L3819), charts L3939/L6540-6620`
- **Lands in floww:** New backend service (httpx GET https://marketdata.theocc.com/volume-query, browser User-Agent, no key) -> /api/occ-volume/{ticker} cached daily in DuckDB -> React 'Who Traded' panel next to Flowseeker with customer-vs-dealer call/put ratios.

### #15 · Historical options-strategy backtester over accumulated chain snapshots (optopsy)  `[ambitious]`  — value 6 / effort 4
- **Why:** Turns floww's cached daily chains into a strategy lab — 'how would selling 30Δ SPY put spreads have done since I started caching.' Strategic long-term capability, but value ramps with snapshot depth: near-term it only covers the window already stored, so start the adapter now and let history accrue (optionally seed from free CBOE EOD).
- **Steal from:** `michaelchu/optopsy (pandas-native strategy constructors: verticals, straddles/strangles, condors, calendars)`
- **Lands in floww:** backend/backtest/optopsy_adapter.py mapping floww's cache/ + DuckDB chain snapshots into optopsy's column schema; Backtest tab in React; feed results into existing sizing/journal modules (floww_trades_v2 via tradeMath.js conventions).

### #16 · Arbitrage-free SVI vol surface + no-arb violation feed  `[ambitious]`  — value 8 / effort 6
- **Why:** The capstone data-quality layer: a Gatheral 5-param SVI fit per expiry gives a smooth surface valid at ANY strike/expiry (needed to price off-grid legs for the strategy builder) and de-noises inputs to GEX/flip/King-node/RND; butterfly/parity/calendar violations double as a rich/cheap mispricing feed. Last because effort is highest and calibration on thin retail chains is the real risk — ship after the rank-5 IV solver proves the clean-mid pipeline.
- **Steal from:** `XanderRobbins/Arbitrage-Free-Volatility-Surface vol_surface/{svi.py, arbitrage.py, iv_solver.py, surface.py} (skip heston.py initially)`
- **Lands in floww:** Port to backend/analytics/vol_surface_svi.py; fit on cached chain snapshots; persist 5 SVI params per expiry in DuckDB via execute_write; serve interpolated IV to GEX/greeks/RND/strategy evaluator; arbitrage-violation badges on the Trinity smile view and a 'no-arb breaks' feed in Flowseeker.

## Roadmap — signal & sentiment layer (from run-1, merged back in)

_These 6 came from mining the flow-scanner + ML/sentiment repos; they cover a dimension the vol/GEX items above don't touch._

### Multi-model sentiment reconciliation engine (VADER compound + TextBlob polarity with cross-source agreement gate)  — value 4 / effort 1
- **Why:** The actual sentiment SCORING that floww is missing. floww's social_flow_pipeline.py declares a TickerSentiment dataclass with avg_vader and avg_textblob fields (L149-150) but ships NO code that computes them — there is no SentimentIntensityAnalyzer, no TextBlob import, and the dataclass decorators are even broken. This is the concrete implementation: score text with both VADER (compound) and TextBlob (polarity/subjectivity), and only label positive/negative when BOTH agree (and optionally a third web source), else neutral. The agreement gate materially cuts false-positive sentiment flags on noisy finance text.
- **Steal from:** `shirosaidev_stocksight` — shirosaidev_stocksight/sentiment.py — sentiment_analysis() (L467-528), agreement logic at L493-506; clean_text()/clean_text_sentiment() (L412-428)
- **Lands in floww:** Drop-in function services/sentiment.py::score_text(text) returning (polarity, subjectivity, label) using vaderSentiment + textblob (add both to requirements). Feed it headlines from the news feed (finding 1) or tweets; aggregate per-ticker into the existing TickerSentiment model and populate the /api/social/sentiment/{ticker} endpoint that currently returns an empty stub. Add sentiment as a feature column for ml_realtime_features / composite_flow_score.

### Opportunity Engine: regime classification + opportunity scoring + risk-defined trade-idea construction  — value 4 / effort 2
- **Why:** A per-ticker DIRECTIONAL trade-idea layer that floww lacks. floww's Flowseeker ranks FLOW (whale/lotto/hedge) but never emits a ranked, risk-defined trade recommendation with a regime label and invalidation. This engine maps (trend x realized-vol) into a 6-cell regime grid (Trending Low-Vol / High-Vol / Range Bound / Choppy / Downtrend / Panic), computes opportunity_score = |trend| + momentum_bonus + alignment_bonus - vol_penalty + mean_rev_bonus clamped 0-10, then arbitrates with gamma sign (positive gamma -> mean-reversion bias, negative gamma -> directional bias) and IV rank (elevated IV -> prefer premium selling) to output {regime, opportunity_tier, direction, trade_type, trade_bias, invalidation}. Every input (trend/momentum/extension scores, realized_vol_20d, gamma flip sign, IV rank) is data floww ALREADY computes, so this is a pure synthesis/ranking layer on top of existing signals.
- **Steal from:** `jwolberg_options-scanner` — docs/opportunity_engine.md (STEP 1 regime table, STEP 2 scoring formula, STEP 4 signal arbitration) + docs/api_v2_ticker_output_spec.md (trade_recommendation + market_state output shape). NOTE: the paid Trading Volatility upstream computes it; only the spec/formula is in-repo, so port the DESIGN, not code.
- **Lands in floww:** New FastAPI endpoint /opportunities that pulls each universe ticker's existing floww signals (GEX gamma-flip sign already in the gamma module; IV rank/skew from Trinity; realized vol from price history; trend/momentum from a simple MA+ROC on yfinance OHLC) and returns a ranked top-3-5 list. Surface as a new Skylit 'Trade Ideas' card next to Flowseeker. Reuses tradeMath.js for the risk plan (entry/stop from expected-move sigma wings). Data source: 100% floww-internal, no new feeds.

### Free financial-news headline ingestion (Yahoo Finance scraper + follow-links to article body text)  — value 4 / effort 2
- **Why:** A zero-cost financial NEWS feed per ticker. floww currently has NO market-news source at all — the only scraper in the backend (services/research/discovery.py) pulls arXiv/HuggingFace/GitHub/SSRN research papers, not headlines. This adds a NewsHeadlineListener-style poller that scrapes Yahoo Finance quote pages for <h3> headlines, dedupes, optionally follows /news/ links, and extracts up to N paragraphs of article body — all via requests+BeautifulSoup, no paid API. It gives floww a genuine catalyst/news stream to pair with GEX and flow.
- **Steal from:** `shirosaidev_stocksight` — shirosaidev_stocksight/sentiment.py — NewsHeadlineListener class (L265-337), get_news_headlines() (L339-382), get_page_text() (L385-409)
- **Lands in floww:** New backend service (e.g. services/news_feed.py) modeled on NewsHeadlineListener.get_news_headlines()/get_page_text(); source = https://finance.yahoo.com/quote/{ticker} via existing HTTP client. Wire into scheduler.py as a periodic poll, persist headlines to DuckDB, and surface under the already-stubbed /api/social route (routes/social_flow.py) or a new /api/news route. Replaces the broken xurl/paid-X dependency in social_flow_pipeline.py with a free source.

### Signal-to-realized-move event-study engine (timestamp an event, sample price at fixed forward horizons, log the move)  — value 4 / effort 3
- **Why:** A generic 'did this signal actually move the stock?' measurement loop. floww's realized-outcome tracking (services/ml/outcomes.py) is hard-wired to its OWN ML predictions and only computes a single next-day open->close label. jasti's perform_financial_analysis records the price at event time and then re-samples it at fixed intervals (T+0, T+30s, ... x8), writing the forward path for each event. Generalized, this lets floww attach an empirical forward-return distribution to ANY event type — a sentiment spike, a news headline, a WHALE/sweep flow signal, a gamma-flip cross — building a per-signal edge/backtest that floww's prediction-only tracker cannot express.
- **Steal from:** `jasti_Stock-Predictor` — jasti_Stock-Predictor/src/main.py — Predictor.perform_financial_analysis() (L74-94) and the event dispatch in checkIfValidTweet()/stream loop (L98-161)
- **Lands in floww:** New services/event_study.py that, on any emitted alert/signal, snapshots yfinance/cvforge spot and schedules follow-up samples at configurable horizons (e.g. +5m/+30m/+1d), persisting {event_id, signal_type, t, price} rows to DuckDB via execute_write. Aggregate into hit-rate/avg-forward-return per signal_type and expose alongside the Flowseeker/alerts UI. Reuse the existing scheduler.py for the delayed sampling instead of jasti's raw threads/sleep.

### OI-weighted expected/consensus price per expiration (chain-implied pin)  — value 3 / effort 1
- **Why:** A new per-expiry scalar floww does not compute: the open-interest-weighted 'expected price' the whole chain is positioned around. For calls it weights (strike+premium)*OI, for puts (strike-premium)*OI, then blends: option_expect_price = [Sum(call_expect*call_OI) + Sum(put_expect*put_OI)] / Sum(all_OI). This gives a market-consensus/breakeven-weighted price magnet per expiry that is DISTINCT from floww's GEX King node (which is a dealer-gamma concentration strike, not an OI-premium-weighted breakeven). Tracking it day-over-day shows where positioning consensus is drifting.
- **Steal from:** `czong_option_chain_unusual_activity_detect` — main-google.py lines 13-33 and main-yahoo.py lines 22-53 (call_expect_price = strike+premium, put_expect_price = strike-premium, OI-weighted blend grouped by expire_date)
- **Lands in floww:** Add a pure function to floww's options-math module (alongside greeks/tradeMath) that takes the chain floww already fetches per expiry and returns expect_price per expiry + a blended term curve. Overlay a dotted 'chain consensus' line on the existing strike x expiry Heatseeker matrix, and store daily values so the term-structure view can show consensus drift. Data source: existing yfinance/cvforge option chain (strike, last/mid premium, OI) - no new fetch.

### Finviz insider-trading scraper (latest / top-by-value / per-ticker)  — value 3 / effort 2
- **Why:** A corporate insider-transaction signal floww has zero coverage of. Three scrapers pull Finviz's insider-trading tables into DataFrames: getLatestInsiderTrading(), getTopInsiderTrading() (filtered to transactions >$100k, last 7 days, sorted by transaction value), and getInsiderTradingFor Ticker(t). Cross-referencing a Flowseeker unusual-flow alert against a same-week insider BUY on the same ticker is a genuinely new corroboration lens (smart-money options flow + insider equity buying) that no current floww module provides.
- **Steal from:** `Buzzfund_UnusualOptions` — insider.py: getLatestInsiderTrading() (lines 12-28), getTopInsiderTrading() (lines 30-46, note the ?tv=100000&tc=7 filter), getInsiderTradingForTicker() (lines 57-64)
- **Lands in floww:** Wrap the three functions as a small fetch module; expose GET /insider/{ticker} and a daily 'top insider buys' pull. In the Flowseeker scanner, add an 'insider' badge/column that lights up when a scanned ticker also appears in the recent Finviz insider-buy table. Data source: Finviz public HTML (free) via requests+BeautifulSoup; needs a cache + polite rate-limit and a parser-fragility guard (Finviz table index is hardcoded to table[5]/table[9], so add a header-based lookup). Best treated as a soft/optional signal given scraper brittleness.

## New repos worth cloning (not yet in data/github-repos/cloned)

- **rgaveiga/optionlab** — mature pip lib — multi-leg PoP (BS/array/MonteCarlo), payoff, expected P&L → powers the Strategy Builder (#11)
- **American-Dynasty/GEX-Dashboard** — React + FastAPI (floww's exact stack) — GEX engine + key levels (gamma flip / call+put walls / max pain), liftable components
- **aaguiar10/gflows** — spot-shifted exposure profiles + 0DTE volume-for-OI (#2, #6)
- **iAmGiG/gex-llm-patterns** — dual-GEX (OI vs volume) + regime-persistence classifier (#1, #8) — already cloned
- **jasonstrimpel/volatility-trading** — realized-vol estimator suite + vol cones (#7)
- **michaelchu/optopsy** — pandas-native options backtester (#15)
- **XanderRobbins/Arbitrage-Free-Volatility-Surface** — Gatheral SVI arb-free surface (#16)
