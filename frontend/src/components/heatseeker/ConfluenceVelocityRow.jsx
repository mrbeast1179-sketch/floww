/**
 * ConfluenceVelocityRow.jsx — historical steal-list signals tile.
 *
 * Renders a 7-column grid of tiles that lift the 7 newly-shipped
 * backend services onto the Zenith dashboard Row 3 ("Meridian &
 * Velocity"). Each tile is a small standalone fetcher (axios +
 * AbortController for unmount cleanup) so swapping tickers doesn't
 * cascade into a single state-tree cleanup race.
 *
 * Tile map:
 *   1. MaxPainDriftTile        ← GET /api/max_pain_drift/{ticker}?days=14
 *   2. ConsensusDriftTile      ← GET /api/consensus_drift/{ticker}?days=14
 *   3. InsiderPressureTile     ← GET /api/insider/{ticker}?limit=20
 *   4. StrikeConeTile          ← GET /api/strike_cone/{ticker}?target_probs=0.16,0.30,0.70,0.84
 *   5. OCCVolumeTile           ← GET /api/occ_volume/{ticker}?days=14
 *   6. RawVsRealizedBadge      ← GET /api/vol/realized/{ticker} (steal-list #7)
 *   7. RvConeTile              ← GET /api/vol/realized/{ticker} (steal-list #7)
 *
 * Visual treatment mirrors `HeatseekerDashboard.jsx`'s slate palette
 * (text-slate-200, bg-slate-800/30, accent emerald/rose/amber/purple
 * /sky). No React Query available in this codebase (see package.json),
 * so we use plain `useEffect` + `useState` + axios with signal-based
 * race-free cleanup.
 *
 * Defensive degrade: any backend failure (timeout / 500 / unreachable)
 * shows the tile in a neutral "—" state, not a crash. Parent
 * dashboard stays usable.
 *
 * Steal intent: aggregate rank #6 (consensus) + #7 (RV/VRP) + #9
 * (max-pain-drift) + #10 (strike-cone) + #14 (OCC who-traded) + #20
 * (insider-scraper) into a single Meridian row visible above the
 * existing real-time steal-list sub-section.
 */

import React, {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import axios from "axios";
import { BACKEND_BASE } from "../../config/api";

const API_BASE = BACKEND_BASE;

// ── Module-level constants ──────────────────────────────────────────
// Hoist empty-state-warning matcher to module scope so React doesn't
// reallocate the closure on every InsiderPressureTile render.
const EMPTY_STATE_WARNING_RE = /Finviz empty or unreachable|no insider activity|no data/i;
const isEmptyStateWarning = (w) => EMPTY_STATE_WARNING_RE.test(w);

// ── Shared primitives ────────────────────────────────────────────────

function Panel({ children, loading, error, label, accent = "emerald" }) {
  const accentMap = {
    emerald: "border-emerald-500/20",
    rose: "border-rose-500/20",
    amber: "border-amber-500/20",
    purple: "border-purple-500/20",
    sky: "border-sky-500/20",
    teal: "border-teal-500/20",
    indigo: "border-indigo-500/20",
  };
  return (
    <div
      className={`rounded-xl border bg-slate-900/60 ${accentMap[accent] || accentMap.sky} p-3 min-h-[110px] flex flex-col justify-between`}
    >
      <div className="flex items-center justify-between">
        <div className="text-[9px] uppercase tracking-widest font-bold text-slate-400">
          {label}
        </div>
        {loading && (
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
        )}
      </div>
      <div className="flex-1 flex flex-col justify-center text-[11px]">
        {error ? (
          <span className="text-rose-400 mono">— unavailable —</span>
        ) : (
          children
        )}
      </div>
    </div>
  );
}

/**
 * useFetch — tiny hook keyed on (url, ticker). Returns {data, loading,
 * error}. Aborts in-flight request on unmount or key change.
 */
function useFetch(ticker, path, opts = {}) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const acRef = useRef(null);

  useEffect(() => {
    if (!ticker) {
      setState({ data: null, loading: false, error: null });
      return undefined;
    }
    acRef.current?.abort?.();
    const ac = new AbortController();
    acRef.current = ac;

    setState({ data: null, loading: true, error: null });
    const url = `${API_BASE}${path}/${encodeURIComponent(ticker)}${
      opts.query ? `?${opts.query}` : ""
    }`;
    axios
      .get(url, { signal: ac.signal, timeout: 5000 })
      .then((r) => {
        if (ac.signal.aborted) return;
        setState({ data: r.data, loading: false, error: null });
      })
      .catch((e) => {
        if (e?.code === "ERR_CANCELED" || ac.signal.aborted) return;
        setState({
          data: null,
          loading: false,
          error: e?.response?.data?.detail || e?.message || "fetch failed",
        });
      });

    return () => ac.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker, path]);

  return state;
}

// ── Tile #1 — Max-Pain Drift ─────────────────────────────────────────

function MaxPainDriftTile({ ticker }) {
  const { data, loading, error } = useFetch(ticker, "/api/max_pain_drift", {
    query: "days=14",
  });
  const score = data?.pin_probability_score;
  const drift = data?.drift_strike_1d;
  const todayStrike = data?.today_strike;
  const direction = data?.direction_label || "stable";

  const dirColor =
    direction === "migrating_toward_spot"
      ? "text-emerald-400"
      : direction === "migrating_away"
      ? "text-rose-400"
      : "text-slate-400";

  return (
    <Panel
      label="Max-Pain Drift"
      loading={loading}
      error={error}
      accent="emerald"
    >
      <div className="flex items-baseline gap-2">
        <span className="text-lg font-bold mono text-slate-100">
          {todayStrike != null ? `$${Number(todayStrike).toFixed(0)}` : "—"}
        </span>
        {drift != null && (
          <span className={`text-[10px] mono ${drift >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {drift >= 0 ? "▲" : "▼"} {Math.abs(drift).toFixed(1)}
          </span>
        )}
      </div>
      <div className="flex items-center justify-between text-[10px] mt-1">
        <span className={`mono ${dirColor}`}>
          {direction.replace(/_/g, " ")}
        </span>
        {score != null && (
          <span className="mono text-slate-500">
            pin {Math.round(score * 100)}%
          </span>
        )}
      </div>
    </Panel>
  );
}

// ── Tile #2 — Consensus Drift ────────────────────────────────────────

function ConsensusDriftTile({ ticker }) {
  const { data, loading, error } = useFetch(ticker, "/api/consensus_drift", {
    query: "days=14",
  });
  const drift = data?.drift_consensus_1d;
  const today = data?.today_consensus;
  const dir = data?.direction_label || "stable";
  const skew = data?.drift_skew_today;

  const dirColor =
    dir === "call_side_pulling_up"
      ? "text-emerald-400"
      : dir === "put_side_pulling_down"
      ? "text-rose-400"
      : dir === "balanced"
      ? "text-amber-400"
      : "text-slate-400";

  return (
    <Panel
      label="Consensus Drift"
      loading={loading}
      error={error}
      accent="purple"
    >
      <div className="flex items-baseline gap-2">
        <span className="text-lg font-bold mono text-slate-100">
          {today != null ? `$${Number(today).toFixed(2)}` : "—"}
        </span>
        {drift != null && (
          <span className={`text-[10px] mono ${drift >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {drift >= 0 ? "▲" : "▼"} {Math.abs(drift).toFixed(2)}
          </span>
        )}
      </div>
      <div className="flex items-center justify-between text-[10px] mt-1">
        <span className={`mono ${dirColor}`}>
          {dir.replace(/_/g, " ")}
        </span>
        {skew != null && (
          <span className="mono text-slate-500">
            skew {Number(skew).toFixed(2)}
          </span>
        )}
      </div>
    </Panel>
  );
}

// ── Tile #3 — Insider Buy Pressure ───────────────────────────────────

function InsiderPressureTile({ ticker }) {
  const { data, loading, error } = useFetch(ticker, "/api/insider", {
    query: "limit=20",
  });
  const summary = data?.summary || {};
  const nBuys = summary.n_buys_30d ?? 0;
  const nSells = summary.n_sells_30d ?? 0;
  const net = summary.net_buy_pressure ?? 0;
  const ceo = summary.ceo_bought_recent === true;

  // Whitelist-of-empty pattern: ONLY the documented empty-state warnings
  // count as "no data"; everything else (exceptions, timeouts, blocks, HTTP
  // codes, ssl/urlopen errors, etc.) classifies as error — future-proof as
  // the backend adds new warning strings.
  const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
  const isError = !!error || (warnings.length > 0 && !warnings.every(isEmptyStateWarning));
  const isEmpty = !!data && !isError && nBuys === 0 && nSells === 0;

  const netColor =
    net > 0 ? "text-emerald-400" : net < 0 ? "text-rose-400" : "text-slate-400";

  return (
    <Panel
      label="Insider Pressure"
      loading={loading}
      error={isError}
      accent="amber"
    >
      {isEmpty ? (
        <span className="text-slate-500 mono">— no activity —</span>
      ) : !isError ? (
        <>
          <div className="flex items-baseline gap-2">
            <span className={`text-lg font-bold mono ${netColor}`}>
              {net > 0 ? "+" : ""}
              {Math.round(net / 1000)}k
            </span>
            {ceo && (
              <span className="inline-block text-[9px] tracking-widest uppercase font-bold px-1.5 py-0.5 rounded"
                style={{ background: "rgba(52,211,153,0.15)", color: "#34d399" }}>
                ★ CEO
              </span>
            )}
          </div>
          <div className="flex items-center justify-between text-[10px] mt-1">
            <span className="mono text-slate-400">
              {nBuys} buy · {nSells} sell
            </span>
            <span className="mono text-slate-500">30d</span>
          </div>
        </>
      ) : null}
    </Panel>
  );
}

// ── Tile #4 — Strike Cone ────────────────────────────────────────────

function StrikeConeTile({ ticker }) {
  const { data, loading, error } = useFetch(ticker, "/api/strike_cone", {
    query:
      "target_probs=0.16,0.30,0.70,0.84&target_deltas=0.16,0.30&expiries=1",
  });
  const spot = data?.spot;
  const cones = Array.isArray(data?.prob_cones) ? data.prob_cones : [];
  // Use the 30%-band (the second tier if available, else first).
  const mid = cones[1] || cones[0] || null;
  const lo = mid?.strike_below;
  const hi = mid?.strike_above;
  const move = spot && lo && hi ? ((hi - lo) / spot) * 100 : null;

  return (
    <Panel
      label="Strike Cone (30Δ)"
      loading={loading}
      error={error}
      accent="sky"
    >
      {spot == null ? (
        <span className="text-slate-500 mono">— no spot —</span>
      ) : (
        <div>
          <div className="flex items-center justify-between text-[11px] mono">
            <span className="text-sky-300">${lo != null ? Number(lo).toFixed(0) : "—"}</span>
            <span className="text-slate-500">spot ${spot.toFixed(2)}</span>
            <span className="text-slate-300">${hi != null ? Number(hi).toFixed(0) : "—"}</span>
          </div>
          <div className="text-center text-[9px] uppercase tracking-widest text-slate-500 mt-1">
            {move != null ? `${move.toFixed(1)}% expected move` : "—"}
          </div>
        </div>
      )}
    </Panel>
  );
}

// ── Tile #5 — OCC Volume (Who Traded) ──────────────────────────────────────────

function OCCVolumeTile({ ticker }) {
  const { data, loading, error } = useFetch(ticker, "/api/occ_volume", {
    query: "days=14",
  });
  const summary = data?.summary || {};
  const bias = (summary.mm_net_bias || "neutral").toLowerCase();
  const customerPct = summary.customer_pct_of_total ?? 0;
  const mmRatio = summary.mm_call_put_ratio ?? 0;
  const warnings = Array.isArray(data?.warnings) ? data.warnings : [];
  const isEmpty =
    !!data &&
    (summary.recent_total_volume == null || summary.recent_total_volume === 0);

  const biasColor =
    bias === "bearish"
      ? "text-rose-400"
      : bias === "bullish"
      ? "text-emerald-400"
      : "text-slate-400";

  return (
    <Panel label="OCC (Who Traded)" loading={loading} error={error} accent="sky">
      {isEmpty ? (
        <span className="text-slate-500 mono">— no actor data —</span>
      ) : (
        <>
          <div className="flex items-baseline gap-2">
            <span className={`text-lg font-bold mono uppercase ${biasColor}`}>
              {bias}
            </span>
            {mmRatio > 0 && (
              <span
                className={`text-[10px] mono ${
                  mmRatio >= 1.15
                    ? "text-emerald-400"
                    : mmRatio <= 0.85
                    ? "text-rose-400"
                    : "text-slate-400"
                }`}
              >
                mm c/p {mmRatio.toFixed(2)}×
              </span>
            )}
          </div>
          <div className="text-[10px] mono mt-1 flex items-center gap-2">
            <span className="text-sky-300">Cust {customerPct.toFixed(0)}%</span>
            <span className="text-slate-500">
              / F&amp;M {(100 - customerPct).toFixed(0)}%
            </span>
          </div>
          <div className="h-1 mt-2 rounded bg-slate-800/60 overflow-hidden">
            <div
              className="h-full bg-sky-400/70"
              style={{ width: `${Math.min(Math.max(customerPct, 0), 100)}%` }}
            />
          </div>
        </>
      )}
    </Panel>
  );
}

// ── Tile #6 — Raw vs Realised (steal-list #7 IV-RV gate) ────────────
//
// Compares front-month ATM implied volatility (from the option chain)
// against Yang-Zhang realised volatility (from 60 daily OHLC bars).
// Short-vol-favored when IV > RV (premium being collected exceeds
// what the market actually delivers); long-vol-favored when IV < RV.
// Mirrors the speculative-grade chip shown on the OptionsFlowCard but
// scaled for the historical Meridian & Velocity row.

function RawVsRealizedBadge({ ticker }) {
  const { data, loading, error } = useFetch(ticker, "/api/vol/realized", {
    query: "days=60&estimator=yang_zhang",
  });
  const frontAtmIv = data?.front_atm_iv;
  const estimators = data?.estimators || {};
  const yz = estimators.yang_zhang;
  const vrp = data?.vrp || {};
  const vrpLabel = vrp.vrp_label || data?.source || "fair";
  const vrpRatio = vrp.ratio != null ? Number(vrp.ratio) : null;

  const hasBoth =
    typeof frontAtmIv === "number" &&
    typeof yz === "number" &&
    yz > 0 &&
    frontAtmIv > 0;
  const labelColor =
    vrpLabel === "short_vol_favored"
      ? "text-emerald-400"
      : vrpLabel === "long_vol_favored"
      ? "text-rose-400"
      : "text-slate-400";

  return (
    <Panel
      label="IV vs YZ-RV"
      loading={loading}
      error={error || !hasBoth}
      accent="teal"
    >
      {!hasBoth ? (
        <span className="text-slate-500 mono">— no IV chain —</span>
      ) : (
        <>
          <div className="flex items-baseline gap-2">
            <span className="text-lg font-bold mono text-slate-100">
              {(Number(frontAtmIv) * 100).toFixed(1)}%
            </span>
            <span className="text-[10px] mono text-slate-500">
              vs {(Number(yz) * 100).toFixed(1)}%
            </span>
          </div>
          <div className="flex items-center justify-between text-[10px] mt-1">
            <span className={`mono uppercase tracking-widest ${labelColor}`}>
              {vrpLabel.replace(/_/g, " ")}
            </span>
            {vrpRatio != null && (
              <span className="mono text-slate-500">
                {vrpRatio.toFixed(2)}×
              </span>
            )}
          </div>
        </>
      )}
    </Panel>
  );
}

// ── Tile #7 — RV Vol Cone (steal-list #7 historical cone) ────────────
//
// Renders the empirical-percentile vol cone at the canonical 20d / 30d
// / 60d lookbacks. Today's spot sits somewhere on the cone; the colour
// cue mirrors the position-vs-distribution convention (current RV in
// p80+ → amber; p50–p80 → emerald; below p50 → slate). Falls back to
// a "no data" state when the daily bars haven't been persisted yet.

function RvConeTile({ ticker }) {
  const { data, loading, error } = useFetch(ticker, "/api/vol/realized", {
    query: "days=60&estimator=yang_zhang",
  });
  const cones = data?.cones || {};
  const estimators = data?.estimators || {};
  const yz = typeof estimators.yang_zhang === "number" ? estimators.yang_zhang : null;

  // Pull 30d cone first (the most-floww-canonical lookback); fall
  // back to 60d then 20d if the API hasn't fully populated yet.
  const bucket30 = cones["30d"] || cones["60d"] || cones["20d"];
  const p50 = bucket30?.p50;
  const p80 = bucket30?.p80;
  const p95 = bucket30?.p95;
  const nPoints = bucket30?.n_points ?? 0;

  const hasData = p50 != null && p80 != null && p95 != null && nPoints > 0;
  let positionColor = "text-slate-400";
  let positionLabel = "—";
  if (hasData && yz != null) {
    if (yz >= p95) {
      positionColor = "text-rose-400";
      positionLabel = "tail";
    } else if (yz >= p80) {
      positionColor = "text-amber-400";
      positionLabel = "high";
    } else if (yz >= p50) {
      positionColor = "text-emerald-400";
      positionLabel = "median";
    } else {
      positionColor = "text-sky-400";
      positionLabel = "calm";
    }
  }

  return (
    <Panel
      label="Vol Cone (30d)"
      loading={loading}
      error={error || !hasData}
      accent="indigo"
    >
      {!hasData ? (
        <span className="text-slate-500 mono">— no cone —</span>
      ) : (
        <>
          <div className="flex items-baseline gap-2">
            <span className="text-lg font-bold mono text-slate-100">
              {(Number(p50) * 100).toFixed(0)}%
            </span>
            <span className="text-[10px] mono text-slate-500">
              p50 / p95 {(Number(p95) * 100).toFixed(0)}%
            </span>
          </div>
          <div className="flex items-center justify-between text-[10px] mt-1">
            <span className={`mono ${positionColor}`}>{positionLabel}</span>
            {yz != null && (
              <span className="mono text-slate-500">
                {(Number(yz) * 100).toFixed(1)}% today
              </span>
            )}
          </div>
        </>
      )}
    </Panel>
  );
}

// ── Container ───────────────────────────────────────────────────────

function ConfluenceVelocityRowBase({
  ticker = "SPY",
  accent = "emerald",
}) {
  const [debouncedTicker, setDebouncedTicker] = useState(ticker);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedTicker(ticker), 300);
    return () => clearTimeout(timer);
  }, [ticker]);

  const upper = useMemo(() => String(debouncedTicker || "").toUpperCase(), [debouncedTicker]);
  if (!upper) return null;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 gap-3">
      <MaxPainDriftTile ticker={upper} />
      <ConsensusDriftTile ticker={upper} />
      <InsiderPressureTile ticker={upper} />
      <StrikeConeTile ticker={upper} />
      <OCCVolumeTile ticker={upper} />
      <RawVsRealizedBadge ticker={upper} />
      <RvConeTile ticker={upper} />
    </div>
  );
}

const ConfluenceVelocityRow = memo(ConfluenceVelocityRowBase);
export default ConfluenceVelocityRow;
