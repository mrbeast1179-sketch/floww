import React, { useMemo } from "react";
import { fmt } from "../lib/helpers";

/**
 * DOM/Level 2 Order Book Heatmap — Skylit-style
 *
 * Columns: Call GEX | Net GEX | Put GEX | VEX | Charm
 * Price axis descends top to bottom, current price highlighted.
 * Colors: teal/green = positive, purple = negative, yellow = extreme key level
 */

// ── Color scale — matches Skylit DOM heatmap reference ────────────
// Background: #0a0e1a (deep navy)
// Zero/empty: rgba(13, 18, 37, 0.95) — dark but distinguishable from bg
// Low positive:  rgba(22, 78, 99, 0.35) — dark teal
// Med positive:  rgba(45, 212, 191, 0.45) — teal
// High positive: rgba(45, 212, 191, 0.75) — bright teal
// Extreme pos:   rgba(253, 224, 71, 0.85) — yellow with star
// Low negative:  rgba(88, 28, 135, 0.3) — dark purple
// Med negative:  rgba(168, 85, 247, 0.45) — purple
// High negative: rgba(168, 55, 230, 0.65) — bright purple
function domCellColor(v, maxAbs) {
  if (v === null || v === undefined || isNaN(v) || v === 0) {
    return { bg: "rgba(13, 18, 37, 0.95)", text: "#3a4566" };
  }
  const norm = Math.min(1, Math.abs(v) / maxAbs);
  const isNeg = v < 0;

  // ── Positive values (teal → green → yellow) ──
  if (!isNeg) {
    if (norm > 0.70) {
      // Extreme — yellow/gold with star
      return { bg: `rgba(253, 224, 71, ${0.75 + 0.2 * norm})`, text: "#0a0e1a", star: true };
    }
    if (norm > 0.50) {
      // High — bright teal/green
      return { bg: `rgba(45, 212, 191, ${0.6 + 0.3 * norm})`, text: "#0a0e1a" };
    }
    if (norm > 0.25) {
      // Medium — teal
      return { bg: `rgba(45, 212, 191, ${0.3 + 0.4 * norm})`, text: "#a7f3d0" };
    }
    if (norm > 0.08) {
      // Low — subtle teal
      return { bg: `rgba(22, 78, 99, ${0.2 + 0.25 * norm})`, text: "#6ee7b7" };
    }
    // Very low
    return { bg: `rgba(22, 78, 99, 0.15)`, text: "#5eead4" };
  }

  // ── Negative values (purple → magenta) ──
  if (norm > 0.70) {
    // Extreme — bright magenta/purple
    return { bg: `rgba(168, 55, 230, ${0.65 + 0.3 * norm})`, text: "#fce7fe" };
  }
  if (norm > 0.50) {
    // High — purple
    return { bg: `rgba(168, 85, 247, ${0.5 + 0.3 * norm})`, text: "#e9d5ff" };
  }
  if (norm > 0.25) {
    // Medium — muted purple
    return { bg: `rgba(168, 85, 247, ${0.3 + 0.35 * norm})`, text: "#d8b4fe" };
  }
  if (norm > 0.08) {
    // Low — subtle purple
    return { bg: `rgba(88, 28, 135, ${0.2 + 0.25 * norm})`, text: "#c4b5fd" };
  }
  // Very low
  return { bg: `rgba(88, 28, 135, 0.15)`, text: "#a78bfa" };
}

// ── Format cell value ──────────────────────────────────────────────
function domFmt(v) {
  if (v === null || v === undefined || isNaN(v) || v === 0) return "";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e6) return sign + (a / 1e6).toFixed(2) + "M";
  if (a >= 1e3) return sign + (a / 1e3).toFixed(1) + "K";
  return sign + a.toFixed(0);
}

// ── Main Component ─────────────────────────────────────────────────
export default function DomHeatmap({ data, spot, ticker }) {
  const rows = useMemo(() => {
    if (!data?.strikes) return [];
    return data.strikes
      .filter((s) => s.strike != null)
      .sort((a, b) => b.strike - a.strike);
  }, [data]);

  const maxAbs = useMemo(() => {
    let m = 1;
    for (const row of rows) {
      for (const key of ["call_gex", "gex", "put_gex", "vex", "charm"]) {
        const v = Math.abs(row[key] || 0);
        if (v > m) m = v;
      }
    }
    return m;
  }, [rows]);
  // Find current price row — the strike closest to spot
  const spotRowIdx = useMemo(() => {
    if (!spot || !rows.length) return -1;
    let bestIdx = 0;
    let bestDist = Math.abs(rows[0].strike - spot);
    for (let i = 1; i < rows.length; i++) {
      const dist = Math.abs(rows[i].strike - spot);
      if (dist < bestDist) {
        bestDist = dist;
        bestIdx = i;
      }
    }
    return bestIdx;
  }, [rows, spot]);

  if (!rows.length) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-slate-500 text-xs">No DOM data available</span>
      </div>
    );
  }

  return (
    <div className="dom-heatmap-container" data-testid="dom-heatmap">
      <table className="dom-heatmap-table">
        <thead>
          <tr>
            <th className="dom-price-header">Price</th>
            <th className="dom-data-header">Call GEX</th>
            <th className="dom-data-header">Net GEX</th>
            <th className="dom-data-header">Put GEX</th>
            <th className="dom-data-header">VEX</th>
            <th className="dom-data-header">Charm</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const strike = row.strike;
            const isCurrent = i === spotRowIdx;

            const cols = [
              row.call_gex || 0,
              row.gex || 0,
              row.put_gex || 0,
              row.vex || 0,
              row.charm || 0,
            ];

            const hasStar = cols.some((v) => {
              const cc = domCellColor(v, maxAbs);
              return cc.star;
            });

            const netGex = row.gex || 0;
            const pctVal = maxAbs > 0 ? Math.abs(netGex / maxAbs) * 100 : 0;

            return (
              <tr
                key={strike}
                className={`dom-row ${isCurrent ? "dom-current-price-row" : ""}`}
              >
                <td className={`dom-price-cell ${isCurrent ? "dom-current-price" : ""}`}>
                  {hasStar && <span className="dom-star">★</span>}
                  {strike >= 1000 ? fmt(strike, 0) : fmt(strike, 1)}
                </td>

                {cols.map((val, ci) => {
                  const cc = domCellColor(val, maxAbs);
                  return (
                    <td
                      key={ci}
                      className="dom-data-cell"
                      style={{ background: cc.bg, color: cc.text }}
                      title={`${ticker} @ ${strike}: ${domFmt(val)}`}
                    >
                      {cc.star ? (
                        <span className="dom-star-cell">★{domFmt(val)}</span>
                      ) : (
                        domFmt(val)
                      )}
                    </td>
                  );
                })}

                <td className="dom-pct-cell">
                  {pctVal > 50 && (
                    <span className={`dom-pct-badge ${netGex >= 0 ? "dom-pct-pos" : "dom-pct-neg"}`}>
                      {netGex >= 0 ? "+" : ""}{pctVal.toFixed(0)}%
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
