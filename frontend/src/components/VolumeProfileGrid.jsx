import React, { useMemo } from "react";
import { fmt, fmtAbs, expFmt, cellColor } from "../lib/helpers";

/**
 * VolumeProfileGrid — GEX Profile View
 *
 * Institutional gamma profile: strikes (rows) × expiries (cols).
 * Viridis-free — uses the same dark institutional palette as the
 * main heatmap (teal/purple via cellColor). Spot row highlighted
 * with a white notch, OI column + total GEX footer.
 *
 * Handles both data shapes:
 *   - data.grid = { expiries, strikes, grid }  (heatseeker)
 *   - data.strikes = [{strike, gex, ...}]       (direct)
 */
export default function VolumeProfileGrid({ data, spot }) {
  const { expiries, strikes, grid, totalByStrike } = useMemo(() => {
    if (!data) return { expiries: [], strikes: [], grid: {}, totalByStrike: {} };

    // Shape 1: heatseeker grid object
    if (data.grid && (data.grid.expiries || data.grid.grid)) {
      const g = data.grid;
      const exps = (g.expiries || []).slice().sort();
      // strikes may be in g.strikes as numbers, or in g.grid keys
      let sts = [];
      if (Array.isArray(g.strikes) && g.strikes.length) {
        // g.strikes is number[]
        sts = [...g.strikes].sort((a, b) => b - a);
      } else if (g.grid) {
        // derive strikes from grid keys
        const s = new Set();
        for (const col of Object.values(g.grid)) {
          for (const k of Object.keys(col)) s.add(Number(k));
        }
        sts = [...s].sort((a, b) => b - a);
      }
      // Totals per strike (for footer bar)
      const totals = {};
      for (const s of sts) {
        let t = 0;
        for (const e of exps) t += (g.grid?.[e]?.[String(s)] || 0);
        totals[s] = t;
      }
      return { expiries: exps, strikes: sts, grid: g.grid || {}, totalByStrike: totals };
    }

    // Shape 2: flat strikes array with gex per strike
    if (Array.isArray(data.strikes) && data.strikes.length) {
      const sts = [...data.strikes]
        .map((r) => (typeof r === "number" ? r : r.strike))
        .filter((s) => s != null)
        .sort((a, b) => b - a);
      const byStrike = {};
      for (const r of data.strikes) {
        if (typeof r === "object" && r.strike != null) byStrike[r.strike] = r.gex ?? r.total_gex ?? 0;
      }
      return { expiries: [], strikes: sts, grid: {}, totalByStrike: byStrike };
    }

    return { expiries: [], strikes: [], grid: {}, totalByStrike: {} };
  }, [data]);

  const maxAbs = useMemo(() => {
    let m = 1;
    if (expiries.length) {
      for (const exp of expiries) {
        const col = grid[exp] || {};
        for (const s of strikes) {
          const v = Math.abs(col[String(s)] || 0);
          if (v > m) m = v;
        }
      }
    } else {
      for (const s of strikes) {
        const v = Math.abs(totalByStrike[s] || 0);
        if (v > m) m = v;
      }
    }
    return m;
  }, [grid, expiries, strikes, totalByStrike]);

  const spotIdx = useMemo(() => {
    if (spot == null || !strikes.length) return -1;
    let best = 0;
    let bestDist = Math.abs(strikes[0] - spot);
    for (let i = 1; i < strikes.length; i++) {
      const d = Math.abs(strikes[i] - spot);
      if (d < bestDist) { bestDist = d; best = i; }
    }
    return best;
  }, [strikes, spot]);

  const hasData = strikes.length > 0;
  const isSingleCol = expiries.length === 0;

  // Enrichment: air pockets (low-GEX strikes) for context below grid
  const airStrikes = useMemo(() => {
    const out = [];
    for (const s of strikes) {
      const v = isSingleCol ? (totalByStrike[s] || 0) : expiries.reduce((a, e) => a + Math.abs(grid[e]?.[String(s)] || 0), 0);
      if (Math.abs(v) < maxAbs * 0.08) out.push(s);
    }
    return out;
  }, [strikes, totalByStrike, grid, expiries, maxAbs, isSingleCol]);

  if (!hasData) {
    return (
      <div className="flex flex-col items-center justify-center flex-1 py-16 gap-2" data-testid="volume-profile-grid">
        <span className="text-slate-500 text-sm">No profile data available</span>
        <span className="text-slate-600 text-xs">Load a ticker with live GEX to see the gamma profile.</span>
      </div>
    );
  }

  return (
    <div className="volume-profile-wrap" data-testid="volume-profile-grid">
      {/* Header */}
      <div className="volume-profile-header">
        <div className="volume-profile-title">
          <span className="volume-profile-label">Gamma Profile</span>
          <span className="volume-profile-meta">
            {strikes.length} strikes{expiries.length ? ` · ${expiries.length} expiries` : ""}{" "}
            · spot {spot != null ? `$${Number(spot).toFixed(2)}` : "—"}
          </span>
        </div>
        {airStrikes.length > 0 && (
          <span className="volume-profile-air-hint" title={`Low-GEX strikes: ${airStrikes.slice(0, 8).join(", ")}`}>
            Air: {airStrikes.length} strikes
          </span>
        )}
      </div>

      <div className="volume-profile-scroll">
        <table className="volume-profile-table">
          <thead>
            <tr>
              <th className="volume-profile-th-strike">Strike</th>
              {isSingleCol ? (
                <th className="volume-profile-th-exp">GEX</th>
              ) : (
                expiries.map((e) => (
                  <th key={e} className="volume-profile-th-exp" title={e}>{expFmt(e)}</th>
                ))
              )}
              <th className="volume-profile-th-tag" />
            </tr>
          </thead>
          <tbody>
            {strikes.map((s, i) => {
              const isSpot = i === spotIdx;
              const total = totalByStrike[s] || 0;
              const isAir = Math.abs(isSingleCol ? total : expiries.reduce((a, e) => a + Math.abs(grid[e]?.[String(s)] || 0), 0)) < maxAbs * 0.08;
              return (
                <tr key={s} className={isSpot ? "volume-profile-row-spot" : undefined}>
                  <td className={`volume-profile-strike${isSpot ? " is-spot" : ""}${isAir ? " is-air" : ""}`}>
                    {isSpot && <span className="volume-profile-spot-notch" />}
                    {fmt(s, s >= 1000 ? 0 : 1)}
                  </td>
                  {isSingleCol ? (
                    (() => {
                      const v = total;
                      const col = cellColor(v, maxAbs);
                      return (
                        <td className="volume-profile-cell" style={{ background: col.bg, color: col.text }} title={`strike ${s} · gex ${fmtAbs(v)}`}>
                          {col.star ? `★${fmtAbs(v)}` : fmtAbs(v)}
                        </td>
                      );
                    })()
                  ) : (
                    expiries.map((e) => {
                      const v = grid[e]?.[String(s)] || 0;
                      const col = cellColor(v, maxAbs);
                      return (
                        <td key={e} className="volume-profile-cell" style={{ background: col.bg, color: col.text }} title={`strike ${s} · exp ${e} · gex ${fmtAbs(v)}`}>
                          {col.star ? `★${fmtAbs(v)}` : fmtAbs(v)}
                        </td>
                      );
                    })
                  )}
                  <td className="volume-profile-tag-cell">
                    {isSpot && <span className="tag king">SPOT</span>}
                    {isAir && !isSpot && <span className="tag air">AIR</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="volume-profile-legend">
        <span className="volume-profile-legend-label">Neg GEX</span>
        <div className="volume-profile-legend-bar" />
        <span className="volume-profile-legend-label">Pos GEX</span>
        {airStrikes.length > 0 && (
          <span className="volume-profile-legend-air">· {airStrikes.length} air pockets (dashed)</span>
        )}
      </div>
    </div>
  );
}
