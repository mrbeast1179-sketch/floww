import React, { memo, useEffect, useMemo, useRef } from "react";

/**
 * SkylitHeatmapGrid — Trinity/Skylit single-bar heatmap
 *
 * Matches the Skylit TRINITY panel reference:
 * - Left rail: strike prices (descending, sticky); spot row gets a white
 *   chip with a notch pointing at the row
 * - One full-width bar per strike, colored on a viridis scale over the
 *   SIGNED metric value (deep purple = most negative … yellow = max)
 * - Value right-aligned inside the bar ("$5,621.1K"), king row bold + ★
 * - % change badge vs the previous data refresh, left inside the bar
 * - Right rail: KING / FLR / CEIL / GK / AIR markers (same sources as the
 *   metrics sidebar, so grid and sidebar always agree)
 * - Bottom min→max viridis legend
 *
 * Data shape: data.strikes[] ({ strike, gex, vex, charm, … }) plus
 * data.nodes ({ king, floors, ceilings, gatekeepers, air_pockets }).
 */

const METRIC_BY_VIEW = { gex: "gex", vex: "vex", charm: "charm", skylit: "gex" };

// Viridis stops, most-negative → max
const VIRIDIS = [
  [0x44, 0x01, 0x54], [0x46, 0x32, 0x7e], [0x36, 0x5c, 0x8d], [0x27, 0x7f, 0x8e],
  [0x1f, 0xa1, 0x87], [0x4a, 0xc1, 0x6d], [0xa0, 0xda, 0x39], [0xfd, 0xe7, 0x25],
];

function viridis(t) {
  const x = Math.max(0, Math.min(1, t)) * (VIRIDIS.length - 1);
  const i = Math.min(Math.floor(x), VIRIDIS.length - 2);
  const f = x - i;
  const [r1, g1, b1] = VIRIDIS[i];
  const [r2, g2, b2] = VIRIDIS[i + 1];
  return `rgb(${Math.round(r1 + (r2 - r1) * f)}, ${Math.round(g1 + (g2 - g1) * f)}, ${Math.round(b1 + (b2 - b1) * f)})`;
}

function fmtK(v) {
  if (v === null || v === undefined || isNaN(v) || v === 0) return "";
  const sign = v < 0 ? "-" : "";
  const a = Math.abs(v);
  if (a >= 1e9) {
    return `${sign}$${(a / 1e6).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}M`;
  }
  return `${sign}$${(a / 1e3).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}K`;
}

function fmtStrike(s) {
  return s >= 1000 ? s.toFixed(0) : s.toFixed(1);
}

// Marker priority when a strike earns more than one
const MARKER_ORDER = ["KING", "FLR", "CEIL", "GK", "AIR"];

function SkylitHeatmapGrid({
  data,
  spot = null,
  ticker = "",
  viewMode = "gex",
  onCellClick,
  onStrikeClick,
}) {
  const metricKey = METRIC_BY_VIEW[viewMode] || "gex";

  const rows = useMemo(() => {
    if (!data?.strikes) return [];
    return data.strikes
      .filter((s) => s.strike != null)
      .sort((a, b) => b.strike - a.strike);
  }, [data]);

  // Signed min/max over the visible metric for the viridis scale
  const [minV, maxV] = useMemo(() => {
    let lo = 0, hi = 0;
    for (const row of rows) {
      const v = row[metricKey] || 0;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    return [lo, hi];
  }, [rows, metricKey]);

  // King row for THIS metric: max |value| → bold + ★
  const starStrike = useMemo(() => {
    let best = null, bestAbs = 0;
    for (const row of rows) {
      const a = Math.abs(row[metricKey] || 0);
      if (a > bestAbs) { bestAbs = a; best = row.strike; }
    }
    return best;
  }, [rows, metricKey]);

  // Spot row (closest strike to spot)
  const spotStrike = useMemo(() => {
    if (spot == null || !rows.length) return null;
    let best = rows[0].strike, bestDist = Math.abs(rows[0].strike - spot);
    for (let i = 1; i < rows.length; i++) {
      const d = Math.abs(rows[i].strike - spot);
      if (d < bestDist) { bestDist = d; best = rows[i].strike; }
    }
    return best;
  }, [rows, spot]);

  // Side markers — same sources as SkylitMetricsSidebar so they agree
  const markers = useMemo(() => {
    const m = new Map();
    const nodes = data?.nodes || {};
    const add = (strike, tag) => {
      if (strike == null) return;
      const k = Number(strike.strike ?? strike);
      if (isNaN(k)) return;
      const arr = m.get(k) || [];
      if (!arr.includes(tag)) arr.push(tag);
      m.set(k, arr);
    };
    add(nodes.king, "KING");
    (nodes.floors || []).forEach((f) => add(f, "FLR"));
    (nodes.ceilings || []).forEach((c) => add(c, "CEIL"));
    (nodes.gatekeepers || []).forEach((g) => add(g, "GK"));
    for (const row of data?.strikes || []) {
      for (const ap of nodes.air_pockets || []) {
        if (ap?.low != null && ap?.high != null && row.strike >= ap.low && row.strike <= ap.high) {
          add(row.strike, "AIR");
        }
      }
    }
    for (const [k, arr] of m) {
      arr.sort((a, b) => MARKER_ORDER.indexOf(a) - MARKER_ORDER.indexOf(b));
      m.set(k, arr);
    }
    return m;
  }, [data]);

  // % change vs the previous data refresh (guarded by asof so identical
  // cached payloads don't wipe the snapshot)
  const prevRef = useRef({ key: null, asof: null, values: null });
  const snapKey = `${ticker}|${metricKey}`;
  const badges = useMemo(() => {
    const out = new Map();
    const prev = prevRef.current;
    if (prev.key !== snapKey || !prev.values || !data?.asof || prev.asof === data.asof) {
      return out;
    }
    for (const row of rows) {
      const p = prev.values.get(row.strike);
      const v = row[metricKey] || 0;
      if (p != null && p !== 0) {
        const pct = Math.round(((v - p) / Math.abs(p)) * 100);
        if (pct !== 0) out.set(row.strike, Math.max(-999, Math.min(999, pct)));
      }
    }
    return out;
  }, [rows, metricKey, snapKey, data]);

  useEffect(() => {
    if (!data?.asof) return;
    const prev = prevRef.current;
    if (prev.key === snapKey && prev.asof === data.asof) return;
    prevRef.current = {
      key: snapKey,
      asof: data.asof,
      values: new Map(rows.map((r) => [r.strike, r[metricKey] || 0])),
    };
  }, [rows, metricKey, snapKey, data]);

  if (!rows.length) {
    return (
      <div className="skylit-heatmap-empty">
        <span>No heatmap data available</span>
      </div>
    );
  }

  const range = maxV - minV;

  return (
    <div className="skylit-heatmap-wrapper">
      <div className="skylit-heatmap-container">
        <table className="trin-grid-table">
          <tbody>
            {rows.map((row) => {
              const v = row[metricKey] || 0;
              const t = range > 0 ? (v - minV) / range : 0.5;
              const bright = t > 0.55;
              const isStar = row.strike === starStrike && v !== 0;
              const isSpot = row.strike === spotStrike;
              const pct = badges.get(row.strike);
              const marks = markers.get(row.strike);
              return (
                <tr key={row.strike} className="trin-row">
                  <td
                    className="trin-strike-cell"
                    onClick={() => onStrikeClick && onStrikeClick(row.strike)}
                  >
                    {isSpot ? (
                      <span className="trin-spot-chip">{fmtStrike(row.strike)}</span>
                    ) : (
                      <span className="trin-strike">{fmtStrike(row.strike)}</span>
                    )}
                  </td>
                  <td
                    className="trin-bar-cell"
                    style={{ background: viridis(t), color: bright ? "#000" : "#fff" }}
                    onClick={() => onCellClick && onCellClick(row.strike, metricKey, v)}
                    title={`Strike ${row.strike} · ${metricKey.toUpperCase()} ${fmtK(v) || "$0"}`}
                  >
                    <div className="trin-bar-inner">
                      {pct != null && (
                        <span className={`trin-pct ${pct > 0 ? "up" : "down"}`}>
                          {pct > 0 ? "+" : ""}{pct}%
                        </span>
                      )}
                      <span className={`trin-val${isStar || isSpot ? " trin-val-bold" : ""}`}>
                        {fmtK(v)}
                        {isStar && <span className="trin-star">★</span>}
                      </span>
                    </div>
                  </td>
                  <td className="trin-mark-cell">
                    {marks && (
                      <span className={`trin-badge trin-badge-${marks[0].toLowerCase()}`}>
                        {marks[0]}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="trin-legend">
        <span className="trin-legend-label">{fmtK(minV) || "$0"}</span>
        <div className="trin-legend-bar" />
        <span className="trin-legend-label">{fmtK(maxV) || "$0"}</span>
      </div>
    </div>
  );
}

export default memo(SkylitHeatmapGrid);
