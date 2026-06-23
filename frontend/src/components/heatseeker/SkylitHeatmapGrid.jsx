import React, { memo, useMemo } from "react";

/**
 * SkylitHeatmapGrid — The main heatmap data grid
 *
 * Matches Skylit reference:
 * - Left column: Strike prices (descending, sticky)
 * - Data columns: GEX/VEX values per expiry
 * - Color coding: cyan/teal (positive), red/purple (negative)
 * - Current price row: white left border highlight
 * - POC (highest value): yellow background + star
 * - Extreme values: colored backgrounds
 * - Monospace font, tight spacing, no cell borders
 */

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

  // POC (Point of Control) — highest value: bright yellow
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
  onCellClick,
  onStrikeClick,
}) {
  const { rows, maxAbs, pocCell, expiries } = useMemo(() => {
    if (!data?.grid) return { rows: [], maxAbs: 1, pocCell: null, expiries: [] };

    const grid = data.grid;
    const expiries = grid.expiries || [];
    let strikes = (grid.strikes || []).slice().sort((a, b) => b - a);

    // Get the data grid based on view mode
    const dataGrid = viewMode === "vex" ? (grid.vex_grid || grid.grid) : grid.grid;

    // Filter strikes that have data
    strikes = strikes.filter((s) =>
      expiries.some((e) => {
        const g = dataGrid || {};
        const ge = g[e];
        if (!ge) return false;
        const v = ge[String(s)] ?? ge[String(s.toFixed(1))] ?? ge[String(parseInt(s))] ?? 0;
        return Math.abs(v) > 0;
      })
    );

    // Build rows
    const rows = strikes.map((strike) => {
      const cells = expiries.map((e) => {
        const g = dataGrid || {};
        const ge = g[e];
        if (!ge) return 0;
        return ge[String(strike)] ?? ge[String(strike.toFixed(1))] ?? ge[String(parseInt(strike))] ?? 0;
      });
      return { strike, cells };
    });

    // Find max absolute value
    let maxAbs = 1;
    let pocVal = 0;
    let pocRI = -1;
    let pocCI = -1;

    for (let ri = 0; ri < rows.length; ri++) {
      for (let ci = 0; ci < rows[ri].cells.length; ci++) {
        const v = Math.abs(rows[ri].cells[ci] || 0);
        if (v > maxAbs) maxAbs = v;
        if (v > pocVal) {
          pocVal = v;
          pocRI = ri;
          pocCI = ci;
        }
      }
    }

    return {
      rows,
      maxAbs,
      pocCell: { rowIdx: pocRI, colIdx: pocCI },
      expiries,
    };
  }, [data, viewMode]);

  // Find current price row index
  const spotRowIdx = useMemo(() => {
    if (!spot || !rows.length) return -1;
    // Find the strike closest to spot (at or below)
    for (let i = 0; i < rows.length; i++) {
      if (rows[i].strike <= spot) return i;
    }
    return -1;
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
              {expiries.map((e) => (
                <th key={e} className="skylit-th-expiry">
                  {formatExpiry(e)}
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
                  {row.cells.map((v, ci) => {
                    const isPOC = pocCell && pocCell.rowIdx === ri && pocCell.colIdx === ci;
                    const col = heatmapColor(v, maxAbs, isPOC);
                    return (
                      <td
                        key={ci}
                        className="skylit-data-cell"
                        style={{
                          background: col.bg,
                          color: col.text,
                        }}
                        onClick={() => onCellClick && onCellClick(row.strike, expiries[ci], v)}
                        title={`Strike ${row.strike} · ${formatExpiry(expiries[ci])} · ${viewMode.toUpperCase()} ${fmtHeatmapCell(v)}`}
                      >
                        {col.star ? (
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

function formatExpiry(e) {
  try {
    const [, m, d] = e.split("-");
    return `${m}-${d}`;
  } catch {
    return e;
  }
}

export default memo(SkylitHeatmapGrid);
