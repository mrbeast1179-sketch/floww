import React, { useMemo } from "react";
import { fmt, fmtAbs, pctClass, tagFor, expFmt, cellColor } from "../lib/helpers";

/**
 * Volume Profile Grid — Historical GEX Heatmap
 *
 * Rows = strike prices (descending), Columns = expiry dates
 * Cells = GEX value for that strike × expiry
 * Colors via cellColor(): teal = positive, purple = negative, yellow = extreme
 *
 * This is the classic "GEX grid" view showing gamma exposure
 * distributed across strikes and expiration dates.
 */

export default function VolumeProfileGrid({ data, spot }) {
  const { expiries, strikes, grid } = useMemo(() => {
    if (!data?.grid) return { expiries: [], strikes: [], grid: {} };
    const g = data.grid;
    const exps = (g.expiries || []).slice().sort();
    const sts = (g.strikes || []).slice().sort((a, b) => b - a);
    return { expiries: exps, strikes: sts, grid: g.grid || {} };
  }, [data]);

  // Max abs value across all cells for color scaling
  const maxAbs = useMemo(() => {
    let m = 1;
    for (const exp of expiries) {
      const col = grid[exp] || {};
      for (const s of strikes) {
        const v = Math.abs(col[String(s)] || 0);
        if (v > m) m = v;
      }
    }
    return m;
  }, [grid, expiries, strikes]);

  // Current price strike (closest)
  const spotIdx = useMemo(() => {
    if (!spot || !strikes.length) return -1;
    let best = 0;
    let bestDist = Math.abs(strikes[0] - spot);
    for (let i = 1; i < strikes.length; i++) {
      const d = Math.abs(strikes[i] - spot);
      if (d < bestDist) { bestDist = d; best = i; }
    }
    return best;
  }, [strikes, spot]);

  if (!expiries.length || !strikes.length) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-slate-500 text-xs">No grid data available</span>
      </div>
    );
  }

  return (
    <div className="overflow-auto flex-1" data-testid="volume-profile-grid" style={{ background: "#0a0e1a" }}>
      <table className="border-collapse mono text-[10px]" style={{ borderSpacing: 0 }}>
        <thead className="sticky top-0 z-10" style={{ background: "#0a0e1a" }}>
          <tr>
            <th className="px-1.5 py-1 text-left text-slate-500 sticky left-0 z-20"
                style={{ background: "#0a0e1a", fontSize: 9, letterSpacing: "0.05em" }}>
              Strike
            </th>
            {expiries.map((e) => (
              <th key={e} className="px-1 py-1 text-slate-400 font-normal text-center"
                  style={{ minWidth: 56, fontSize: 9, letterSpacing: "0.03em" }}>
                {expFmt(e)}
              </th>
            ))}
            <th className="px-1 py-1 text-slate-500 text-left" style={{ fontSize: 9 }}>Tags</th>
          </tr>
        </thead>
        <tbody>
          {strikes.map((s, i) => {
            const isSpot = i === spotIdx;
            return (
              <tr key={s} style={isSpot ? { background: "rgba(255,255,255,0.03)" } : {}}>
                <td className="px-2 py-0.5 font-bold sticky left-0 z-10 text-slate-400"
                    style={{ background: isSpot ? "rgba(10,14,26,0.95)" : "#0a0e1a", fontSize: 10 }}>
                  {fmt(s, s >= 1000 ? 0 : 1)}
                </td>
                {expiries.map((e) => {
                  const v = grid[e]?.[String(s)] || 0;
                  const col = cellColor(v, maxAbs);
                  return (
                    <td key={e}
                        className="text-center cursor-pointer"
                        style={{ background: col.bg, color: col.text, minWidth: 54, padding: "1px 3px", fontSize: 10 }}
                        title={`strike ${s} · exp ${e} · gex ${fmtAbs(v)}`}>
                      {col.star ? `★${fmtAbs(v)}` : fmtAbs(v)}
                    </td>
                  );
                })}
                <td className="px-1 py-0.5">
                  {isSpot && <span className="tag king">SPOT</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
