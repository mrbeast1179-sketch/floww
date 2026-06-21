import React, { useMemo } from "react";
import { fmt } from "../lib/helpers";

/**
 * DOM/Level 2 Order Book Heatmap — Skylit reference style
 *
 * Layout: Price (left, dark bg, white triangle on current) |
 *         Left % badge | 5 data columns | Right % badge
 *
 * Reference colors:
 * - Background: dark navy (#0b1121)
 * - Base cells: muted teal (#2c7a7b range)
 * - High positive: bright green (#00e676 range)
 * - Negative: deep purple (#6a1b9a range)
 * - Extreme/POC: bright yellow (#ffea00 range), black text + star
 * - Current price: white triangle marker on left edge
 * - Zero padding, faint vertical grid lines between columns
 */

function domCellColor(v, maxAbs) {
  if (v === null || v === undefined || isNaN(v) || v === 0) {
    return { bg: "rgba(15, 23, 42, 0.92)", text: "#1e3a5f" };
  }
  const norm = Math.min(1, Math.abs(v) / maxAbs);
  const isNeg = v < 0;

  // Extreme values (top 10%): yellow for positive, purple for negative
  if (norm > 0.85) {
    return isNeg
      ? { bg: `rgba(107, 33, 168, ${0.55 + 0.35 * norm})`, text: "#e9d5ff", star: true }
      : { bg: `rgba(255, 234, 0, ${0.75 + 0.2 * norm})`, text: "#000000", star: true };
  }

  if (!isNeg) {
    // Positive: muted teal → bright green as norm increases
    if (norm > 0.60) return { bg: `rgba(0, 230, 118, ${0.35 + 0.45 * norm})`, text: "#000000" };
    if (norm > 0.35) return { bg: `rgba(44, 122, 123, ${0.25 + 0.4 * norm})`, text: "#ffffff" };
    if (norm > 0.12) return { bg: `rgba(38, 166, 90, ${0.12 + 0.3 * norm})`, text: "#e0f2f1" };
    return { bg: `rgba(30, 90, 90, 0.15)`, text: "#b2dfdb" };
  }

  // Negative: deep purple
  if (norm > 0.60) return { bg: `rgba(107, 33, 168, ${0.45 + 0.35 * norm})`, text: "#e9d5ff" };
  if (norm > 0.35) return { bg: `rgba(107, 33, 168, ${0.25 + 0.35 * norm})`, text: "#d1c4e9" };
  if (norm > 0.12) return { bg: `rgba(74, 20, 140, ${0.12 + 0.25 * norm})`, text: "#b39ddb" };
  return { bg: `rgba(74, 20, 140, 0.12)`, text: "#9575cd" };
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

  // Global max for cell color scaling
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

  // POC cell (single max value)
  const pocCell = useMemo(() => {
    let maxVal = 0;
    let pocRI = -1, pocCI = -1;
    for (let ri = 0; ri < rows.length; ri++) {
      const keys = ["call_gex", "gex", "put_gex", "vex", "charm"];
      for (let ci = 0; ci < keys.length; ci++) {
        const v = Math.abs(rows[ri][keys[ci]] || 0);
        if (v > maxVal) { maxVal = v; pocRI = ri; pocCI = ci; }
      }
    }
    return { rowIdx: pocRI, colIdx: pocCI };
  }, [rows]);

  // Max for percentage badges (net GEX only)
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
      const d = Math.abs(rows[i].strike - spot);
      if (d < bestDist) { bestDist = d; bestIdx = i; }
    }
    return bestIdx;
  }, [rows, spot]);

  // Legend
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
              const cols = [row.call_gex||0, row.gex||0, row.put_gex||0, row.vex||0, row.charm||0];
              const netGex = row.gex || 0;
              const pctVal = gexMaxAbs > 0 ? Math.abs(netGex / gexMaxAbs) * 100 : 0;
              const isEven = i % 2 === 0;

              return (
                <tr key={strike}
                    className={`dom-row${isCurrent ? " dom-current-row" : ""}${isEven ? " dom-row-even" : ""}`}>

                  {/* Price axis — dark bg, white triangle on current */}
                  <td className={`dom-price-cell${isCurrent ? " dom-current-price" : ""}`}>
                    {isCurrent && <span className="dom-triangle" />}
                    {strike >= 1000 ? fmt(strike, 0) : fmt(strike, 1)}
                  </td>

                  {/* Left-side % badge */}
                  <td className="dom-pct-left-cell">
                    <span className={`dom-pct-badge ${pctVal > 50 ? "dom-pct-hot" : pctVal > 20 ? "dom-pct-warm" : "dom-pct-cool"} ${netGex >= 0 ? "dom-pct-pos" : "dom-pct-neg"}`}>
                      {netGex >= 0 ? "+" : ""}{pctVal < 1 && pctVal > 0 ? pctVal.toFixed(1) : pctVal.toFixed(0)}%
                    </span>
                  </td>

                  {/* 5 data columns */}
                  {cols.map((val, ci) => {
                    const cc = domCellColor(val, colorMaxAbs);
                    const isPoc = i === pocCell.rowIdx && ci === pocCell.colIdx;
                    return (
                      <td key={ci}
                          className={`dom-data-cell${isPoc ? " dom-poc-cell" : ""}`}
                          style={{
                            background: isPoc ? "rgba(255, 234, 0, 0.88)" : cc.bg,
                            color: isPoc ? "#000000" : cc.text,
                          }}
                          title={`${ticker} @ ${strike}: ${domFmt(val)}`}>
                        {isPoc ? (<span className="dom-star-cell">*{domFmt(val)}</span>)
                          : cc.star ? (<span className="dom-star-cell">*{domFmt(val)}</span>)
                          : domFmt(val)}
                      </td>
                    );
                  })}

                  {/* Right-side % badge */}
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
