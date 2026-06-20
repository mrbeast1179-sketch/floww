import React, { useMemo } from "react";
import { fmt } from "../lib/helpers";

/**
 * DOM/Level 2 Order Book Heatmap — Skylit reference style
 *
 * Layout: Price (left) | 5 data columns | Tags (right)
 * Price: bold, prominent, left-border accent on current row
 * Tags: KING/FLR/CEIL/GATE/AIR badges on the right side
 * Colors: teal/green = positive, purple = negative, yellow = extreme
 * Footer: gradient legend bar (purple → teal → green → yellow)
 */

function domCellColor(v, maxAbs) {
  if (v === null || v === undefined || isNaN(v) || v === 0) {
    return { bg: "rgba(10, 15, 30, 0.95)", text: "#2a3550" };
  }
  const norm = Math.min(1, Math.abs(v) / maxAbs);
  const isNeg = v < 0;

  if (!isNeg) {
    if (norm > 0.70) return { bg: `rgba(251, 191, 36, ${0.75 + 0.2 * norm})`, text: "#0a0e1a", star: true };
    if (norm > 0.50) return { bg: `rgba(45, 212, 191, ${0.55 + 0.35 * norm})`, text: "#0a0e1a" };
    if (norm > 0.25) return { bg: `rgba(45, 212, 191, ${0.25 + 0.4 * norm})`, text: "#a7f3d0" };
    if (norm > 0.08) return { bg: `rgba(22, 78, 99, ${0.18 + 0.25 * norm})`, text: "#6ee7b7" };
    return { bg: `rgba(22, 78, 99, 0.12)`, text: "#5eead4" };
  }

  if (norm > 0.70) return { bg: `rgba(168, 55, 230, ${0.6 + 0.3 * norm})`, text: "#fce7fe" };
  if (norm > 0.50) return { bg: `rgba(168, 85, 247, ${0.45 + 0.3 * norm})`, text: "#e9d5ff" };
  if (norm > 0.25) return { bg: `rgba(168, 85, 247, ${0.25 + 0.35 * norm})`, text: "#d8b4fe" };
  if (norm > 0.08) return { bg: `rgba(88, 28, 135, ${0.18 + 0.25 * norm})`, text: "#c4b5fd" };
  return { bg: `rgba(88, 28, 135, 0.12)`, text: "#a78bfa" };
}

function domFmt(v) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  if (v === 0) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e6) return sign + (a / 1e6).toFixed(2) + "M";
  if (a >= 1e3) return sign + (a / 1e3).toFixed(1) + "K";
  return sign + a.toFixed(0);
}

export default function DomHeatmap({ data, spot, ticker }) {
  const rows = useMemo(() => {
    if (!data?.strikes) return [];
    return data.strikes
      .filter((s) => s.strike != null)
      .sort((a, b) => b.strike - a.strike);
  }, [data]);

  // Global max for cell color scaling (across all 5 columns)
  const colorMaxAbs = useMemo(() => {
    let m = 1;
    for (const row of rows) {
      for (const key of ["call_gex", "gex", "put_gex", "vex", "charm"]) {
        const v = Math.abs(row[key] || 0);
        if (v > m) m = v;
      }
    }
    return m;
  }, [rows]);

  // Max for percentage badge (net GEX only)
  const gexMaxAbs = useMemo(() => {
    let m = 1;
    for (const row of rows) {
      const v = Math.abs(row.gex || 0);
      if (v > m) m = v;
    }
    return m;
  }, [rows]);

  const spotRowIdx = useMemo(() => {
    if (!spot || !rows.length) return -1;
    let bestIdx = 0;
    let bestDist = Math.abs(rows[0].strike - spot);
    for (let i = 1; i < rows.length; i++) {
      const dist = Math.abs(rows[i].strike - spot);
      if (dist < bestDist) { bestDist = dist; bestIdx = i; }
    }
    return bestIdx;
  }, [rows, spot]);

  const kingStrike = useMemo(() => {
    if (!data?.nodes?.king?.strike) return null;
    return data.nodes.king.strike;
  }, [data]);

  const tagSets = useMemo(() => {
    const floors = new Set((data?.nodes?.floors || []).map(f => f.strike));
    const ceilings = new Set((data?.nodes?.ceilings || []).map(f => f.strike));
    const gates = new Set((data?.nodes?.gatekeepers || []).map(f => f.strike));
    return { floors, ceilings, gates };
  }, [data]);

  // Min/max for legend
  const { minGex, maxGex } = useMemo(() => {
    if (!rows.length) return { minGex: 0, maxGex: 0 };
    let min = Infinity, max = -Infinity;
    for (const row of rows) {
      const v = row.gex || 0;
      if (v < min) min = v;
      if (v > max) max = v;
    }
    return { minGex: min === Infinity ? 0 : min, maxGex: max === -Infinity ? 0 : max };
  }, [rows]);

  if (!rows.length) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-slate-500 text-xs">Loading DOM data…</span>
      </div>
    );
  }

  return (
    <div className="dom-heatmap-wrapper">
      <div className="dom-heatmap-container" data-testid="dom-heatmap">
        <table className="dom-heatmap-table">
          <tbody>
            {rows.map((row, i) => {
              const strike = row.strike;
              const isCurrent = i === spotRowIdx;
              const isKing = strike === kingStrike;
              const isFloor = tagSets.floors.has(strike);
              const isCeil = tagSets.ceilings.has(strike);
              const isGate = tagSets.gates.has(strike);
              const inAir = (data?.nodes?.air_pockets || []).some(a => strike >= a.low && strike <= a.high);

              const cols = [
                row.call_gex || 0,
                row.gex || 0,
                row.put_gex || 0,
                row.vex || 0,
                row.charm || 0,
              ];
              const hasStar = cols.some((v) => domCellColor(v, colorMaxAbs).star);
              const netGex = row.gex || 0;
              const pctVal = gexMaxAbs > 0 ? Math.abs(netGex / gexMaxAbs) * 100 : 0;
              const isEven = i % 2 === 0;

              return (
                <tr
                  key={strike}
                  className={`dom-row ${isCurrent ? "dom-current-row" : ""} ${isEven ? "dom-row-even" : ""}`}
                >
                  {/* Price axis cell */}
                  <td className={`dom-price-cell ${isCurrent ? "dom-current-price" : ""}`}>
                    {hasStar && <span className="dom-star">★</span>}
                    {strike >= 1000 ? fmt(strike, 0) : fmt(strike, 1)}
                  </td>

                  {/* 5 data columns */}
                  {cols.map((val, ci) => {
                    const cc = domCellColor(val, colorMaxAbs);
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

                  {/* Tags column */}
                  <td className="dom-tags-cell">
                    <div className="dom-tags-row">
                      {isKing && <span className="dom-tag king"><span className="dom-tag-dot"/>KING</span>}
                      {isFloor && <span className="dom-tag floor">FLR</span>}
                      {isCeil && <span className="dom-tag ceiling">CEIL</span>}
                      {isGate && <span className="dom-tag gate">GATE</span>}
                      {inAir && <span className="dom-tag air">≈AIR</span>}
                    </div>
                  </td>

                  {/* Percentage badge — show on all rows with visual weight */}
                  <td className="dom-pct-cell">
                    <span className={`dom-pct-badge ${pctVal > 50 ? "dom-pct-hot" : pctVal > 20 ? "dom-pct-warm" : "dom-pct-cool"} ${netGex >= 0 ? "dom-pct-pos" : "dom-pct-neg"}`}>
                      {netGex >= 0 ? "+" : ""}{pctVal < 1 && pctVal > 0 ? pctVal.toFixed(1) : pctVal.toFixed(0)}%
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Bottom gradient legend bar */}
      <div className="dom-legend">
        <span className="dom-legend-min">{domFmt(minGex)}</span>
        <div className="dom-legend-bar">
          <div className="dom-legend-gradient" />
          <div className="dom-legend-ticks">
            <span>0</span>
            <span>{domFmt(maxGex * 0.5)}</span>
            <span>{domFmt(maxGex)}</span>
          </div>
        </div>
        <span className="dom-legend-max">{domFmt(maxGex)}</span>
      </div>
    </div>
  );
}
