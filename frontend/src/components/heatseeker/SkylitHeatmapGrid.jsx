import React, { memo, useMemo } from "react";

/**
 * SkylitHeatmapGrid — DOM/Level 2 style heatmap
 *
 * Matches Skylit reference:
 * - Left column: Strike prices (descending, sticky)
 * - Data columns: Call GEX, Net GEX, Put GEX, VEX, Charm (per strike)
 * - Color coding: teal/green (positive), purple (negative)
 * - Current price row: white background + black text
 * - POC (highest value): yellow background + star
 * - Monospace font, tight spacing, no cell borders
 *
 * Data shape: data.strikes[] with { strike, call_gex, gex, put_gex, vex, charm, ... }
 */

const DATA_COLUMNS = [
  { key: "call_gex", label: "Call GEX", group: "gex" },
  { key: "gex", label: "Net GEX", group: "gex" },
  { key: "put_gex", label: "Put GEX", group: "gex" },
  { key: "call_oi", label: "Call OI", group: "oi" },
  { key: "put_oi", label: "Put OI", group: "oi" },
  { key: "total_oi", label: "Total OI", group: "oi" },
  { key: "vex", label: "VEX", group: "vex" },
  { key: "vega", label: "Vega", group: "vega" },
  { key: "charm", label: "Charm", group: "charm" },
  { key: "vomma", label: "Vomma", group: "vega" },
  { key: "zomma", label: "Zomma", group: "vega" },
];

// Default visible columns per view mode
const DEFAULT_VISIBLE = {
  gex: ["call_gex", "gex", "put_gex"],
  vex: ["vex", "call_gex", "put_gex"],
  charm: ["charm", "gex"],
};

function fmtHeatmapCell(v) {
  if (v === null || v === undefined || isNaN(v) || v === 0) return "";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  let s;
  if (a >= 1e6) s = (a / 1e6).toFixed(1) + "M";
  else if (a >= 1e3) s = (a / 1e3).toFixed(1) + "K";
  else s = a.toFixed(0);
  return sign + "$" + s;
}

function heatmapColor(v, maxAbs, isPOC = false) {
  if (v === null || v === undefined || isNaN(v) || v === 0 || maxAbs === 0) {
    return { bg: "rgba(13, 17, 23, 0.95)", text: "#3a4566" };
  }

  const norm = Math.min(1, Math.abs(v) / maxAbs);
  const isNeg = v < 0;

  // POC — highest value: bright yellow + black text
  if (isPOC) {
    return {
      bg: `rgba(241, 196, 15, ${0.75 + 0.2 * norm})`,
      text: "#000000",
      star: true,
    };
  }

  // Extreme values (top 15%)
  if (norm > 0.85) {
    return isNeg
      ? { bg: `rgba(107, 33, 168, ${0.55 + 0.35 * norm})`, text: "#ffffff" }
      : { bg: `rgba(46, 204, 113, ${0.50 + 0.40 * norm})`, text: "#000000" };
  }

  // High values (top 30%)
  if (norm > 0.60) {
    return isNeg
      ? { bg: `rgba(142, 68, 173, ${0.35 + 0.35 * norm})`, text: "#ffffff" }
      : { bg: `rgba(46, 204, 113, ${0.25 + 0.40 * norm})`, text: "#ffffff" };
  }

  // Medium values
  if (norm > 0.30) {
    return isNeg
      ? { bg: `rgba(41, 128, 185, ${0.18 + 0.30 * norm})`, text: "#e2e8f0" }
      : { bg: `rgba(38, 138, 138, ${0.15 + 0.30 * norm})`, text: "#e0f2f1" };
  }

  // Low values
  if (norm > 0.08) {
    return isNeg
      ? { bg: `rgba(44, 62, 80, ${0.10 + 0.18 * norm})`, text: "#94a3b8" }
      : { bg: `rgba(30, 100, 100, ${0.08 + 0.18 * norm})`, text: "#94a3b8" };
  }

  // Very low
  return { bg: "rgba(13, 17, 23, 0.85)", text: "#475569" };
}

function SkylitHeatmapGrid({
  data,
  spot = null,
  viewMode = "gex",
  visibleColumns,
  onCellClick,
  onStrikeClick,
}) {
  // Build rows from strikes data
  const rows = useMemo(() => {
    if (!data?.strikes) return [];
    return data.strikes
      .filter((s) => s.strike != null)
      .sort((a, b) => b.strike - a.strike);
  }, [data]);

  // Determine which columns to show
  const columns = useMemo(() => {
    if (visibleColumns) {
      return DATA_COLUMNS.filter(c => visibleColumns.includes(c.key));
    }
    const defaultKeys = DEFAULT_VISIBLE[viewMode] || DEFAULT_VISIBLE.gex;
    return DATA_COLUMNS.filter(c => defaultKeys.includes(c.key));
  }, [viewMode, visibleColumns]);

  // Find max absolute value across all visible columns
  const maxAbs = useMemo(() => {
    let m = 1;
    for (const row of rows) {
      for (const col of columns) {
        const v = Math.abs(row[col.key] || 0);
        if (v > m) m = v;
      }
    }
    return m;
  }, [rows, columns]);

  // Find POC (point of control) — highest absolute value
  const pocCell = useMemo(() => {
    let maxVal = 0;
    let pocRI = -1, pocCI = -1;
    for (let ri = 0; ri < rows.length; ri++) {
      for (let ci = 0; ci < columns.length; ci++) {
        const v = Math.abs(rows[ri][columns[ci].key] || 0);
        if (v > maxVal) { maxVal = v; pocRI = ri; pocCI = ci; }
      }
    }
    return { rowIdx: pocRI, colIdx: pocCI };
  }, [rows, columns]);

  // Find current price row (closest strike to spot)
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

  if (!rows.length) {
    return (
      <div className="skylit-heatmap-empty">
        <span>No heatmap data available</span>
      </div>
    );
  }

  return (
    <div className="skylit-heatmap-wrapper">
      <div className="skylit-heatmap-container">
        <table className="skylit-heatmap-table">
          <thead>
            <tr>
              <th className="skylit-th-strike">Strike</th>
              {columns.map((col) => (
                <th key={col.key} className="skylit-th-expiry">
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, ri) => {
              const isATM = ri === spotRowIdx;
              return (
                <tr
                  key={row.strike}
                  className={`skylit-heatmap-row${isATM ? " skylit-atm-row" : ""}`}
                >
                  {/* Strike price cell */}
                  <td
                    className={`skylit-strike-cell${isATM ? " skylit-atm-strike" : ""}`}
                    onClick={() => onStrikeClick && onStrikeClick(row.strike)}
                  >
                    {isATM && <div className="skylit-atm-pointer" />}
                    <span className="skylit-strike-value">
                      {row.strike >= 1000 ? row.strike.toFixed(0) : row.strike.toFixed(1)}
                    </span>
                  </td>

                  {/* Data cells */}
                  {columns.map((col, ci) => {
                    const v = row[col.key] || 0;
                    const isPOC = pocCell.rowIdx === ri && pocCell.colIdx === ci;
                    const col_color = heatmapColor(v, maxAbs, isPOC);
                    return (
                      <td
                        key={col.key}
                        className="skylit-data-cell"
                        style={{
                          background: col_color.bg,
                          color: col_color.text,
                        }}
                        onClick={() => onCellClick && onCellClick(row.strike, col.key, v)}
                        title={`Strike ${row.strike} · ${col.label} ${fmtHeatmapCell(v)}`}
                      >
                        {col_color.star ? (
                          <span className="skylit-star-cell">★{fmtHeatmapCell(v)}</span>
                        ) : (
                          fmtHeatmapCell(v)
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default memo(SkylitHeatmapGrid);
