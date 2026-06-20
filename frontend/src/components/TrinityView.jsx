import React, { useEffect, useState, useMemo } from "react";
import axios from "axios";
import { fmt, fmtAbs, TRINITY } from "../lib/helpers";

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : "/api";

/**
 * Trinity 3-Panel View — Skylit reference layout
 *
 * Three side-by-side panels (SPXW, SPY, QQQ), each showing:
 * - Header: ticker, price, change%
 * - Sub-header: King label + yellow dot, net GEX
 * - Data grid: strike price | percentage badge | GEX value
 * - Footer: gradient bar (purple → yellow) with min/max labels
 *
 * Colors per reference image 9:
 * - Positive GEX: teal/green backgrounds, green text badges
 * - Negative GEX: purple backgrounds, red/purple text badges
 * - Extreme (top 20%): bright yellow background
 * - Current price: white background, dark text (inverted)
 * - King node: gold star + highlighted row
 */

// ── Color scale for row backgrounds ─────────────────────────────────
// Reference: purple (neg) → teal (pos) → yellow (extreme)
function rowColor(gexVal, maxAbs) {
  if (!gexVal || !maxAbs) return "transparent";
  const norm = Math.min(1, Math.abs(gexVal) / maxAbs);
  const isNeg = gexVal < 0;

  if (norm > 0.80) {
    // Extreme — bright yellow for both pos and neg
    return "rgba(253, 224, 71, 0.65)";
  }
  if (norm > 0.50) {
    return isNeg ? "rgba(168, 85, 247, 0.40)" : "rgba(45, 212, 191, 0.45)";
  }
  if (norm > 0.20) {
    return isNeg ? "rgba(168, 85, 247, 0.22)" : "rgba(45, 212, 191, 0.25)";
  }
  return isNeg ? "rgba(88, 28, 135, 0.10)" : "rgba(22, 78, 99, 0.10)";
}

// ── Text color for value column ─────────────────────────────────────
function textColor(gexVal, maxAbs) {
  if (!gexVal || !maxAbs) return "#4a5568";
  const norm = Math.min(1, Math.abs(gexVal) / maxAbs);
  if (norm > 0.80) return "#0a0e1a";  // dark text on yellow bg
  if (norm > 0.50) return isNeg(gexVal) ? "#e9d5ff" : "#0a0e1a";
  return isNeg(gexVal) ? "#c4b5fd" : "#6ee7b7";
}

function isNeg(v) { return v < 0; }

// ── Format GEX value as "$X,XXX.XK" ────────────────────────────────
function fmtGex(v) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e6) {
    return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  }
  if (abs >= 1e3) {
    return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  }
  return `${sign}$${abs.toFixed(0)}`;
}

// ── Main Trinity View ──────────────────────────────────────────────
export default function TrinityView({ onFocusTicker }) {
  const [allData, setAllData] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let mounted = true;
    const fetchAll = async () => {
      setLoading(true);
      try {
        const results = await Promise.allSettled(
          TRINITY.map(t =>
            axios.get(`${API}/heatmap/${t}?expiries=3&mode=day`, { timeout: 15000 })
              .then(r => ({ ticker: t, data: r.data }))
          )
        );
        const newData = {};
        results.forEach(r => {
          if (r.status === "fulfilled") newData[r.value.ticker] = r.value.data;
        });
        if (mounted) { setAllData(newData); setLoading(false); }
      } catch (e) {
        if (mounted) { setError(e.message); setLoading(false); }
      }
    };
    fetchAll();
    const id = setInterval(fetchAll, 30000);
    return () => { mounted = false; clearInterval(id); };
  }, []);

  if (loading && Object.keys(allData).length === 0) {
    return <div className="p-4 text-slate-500 text-sm">Loading Trinity…</div>;
  }
  if (error) {
    return <div className="p-4 text-rose-400 text-sm">Error: {error}</div>;
  }

  return (
    <div className="trinity-layout" data-testid="trinity-view">
      {/* Confluence summary bar */}
      <ConfluenceBar data={allData} />

      {/* Three panels */}
      <div className="trinity-panels">
        {TRINITY.map(t => (
          <TrinityPanel
            key={t}
            ticker={t}
            data={allData[t]}
            onFocus={() => onFocusTicker && onFocusTicker(t)}
          />
        ))}
      </div>
    </div>
  );
}

// ── Confluence Summary Bar ─────────────────────────────────────────
function ConfluenceBar({ data }) {
  const tickers = TRINITY.map(t => data[t]).filter(d => d && !d.error);
  if (tickers.length === 0) return null;

  const regimes = tickers.map(d => d.nodes?.regime).filter(Boolean);
  const allSame = regimes.length > 0 && regimes.every(r => r === regimes[0]);
  const confluence = regimes.length > 0
    ? regimes.filter(r => r === regimes[0]).length / regimes.length
    : 0;

  const verdict = confluence === 1 ? "full" : confluence >= 0.66 ? "partial" : "diverge";
  const verdictColor = verdict === "full" ? "trinity-verdict-pos" : verdict === "partial" ? "trinity-verdict-warn" : "trinity-verdict-neg";
  const verdictText = verdict === "full" ? "All three agree. Highest conviction." : verdict === "partial" ? "Two-of-three. Reduced size." : "Disagreement. Wait.";

  return (
    <div className="trinity-summary">
      <div className="trinity-summary-left">
        <div className="trinity-stat">
          <span className="trinity-stat-label">Confluence</span>
          <span className={`trinity-stat-value ${confluence === 1 ? "text-emerald-400" : confluence >= 0.66 ? "text-amber-400" : "text-rose-400"}`}>
            {(confluence * 100).toFixed(0)}%
          </span>
        </div>
        <div className="trinity-divider" />
        <div className="trinity-stat">
          <span className="trinity-stat-label">Regime</span>
          <span className={`trinity-stat-value ${regimes[0] === "positive" ? "text-emerald-400" : regimes[0] === "negative" ? "text-rose-400" : "text-slate-400"}`}>
            {regimes[0] || "—"}
          </span>
        </div>
      </div>
      <span className={`trinity-verdict ${verdictColor}`}>{verdictText}</span>
    </div>
  );
}

// ── Single Trinity Panel ───────────────────────────────────────────
function TrinityPanel({ ticker, data, onFocus }) {
  const spot = data?.spot;
  const nodes = data?.nodes;

  // Build sorted strike rows
  const rows = useMemo(() => {
    if (!data?.strikes) return [];
    return data.strikes
      .filter(s => s.strike != null && s.gex != null)
      .sort((a, b) => b.strike - a.strike);
  }, [data]);

  // Max abs GEX for color scaling within this panel
  const maxAbs = useMemo(() => {
    if (!rows.length) return 1;
    return Math.max(...rows.map(s => Math.abs(s.gex || 0)), 1);
  }, [rows]);

  // Current price row index (closest strike to spot)
  const spotIdx = useMemo(() => {
    if (!spot || !rows.length) return -1;
    let best = 0;
    let bestDist = Math.abs(rows[0].strike - spot);
    for (let i = 1; i < rows.length; i++) {
      const d = Math.abs(rows[i].strike - spot);
      if (d < bestDist) { bestDist = d; best = i; }
    }
    return best;
  }, [rows, spot]);

  // King node (strike with highest abs GEX)
  const kingStrike = useMemo(() => {
    if (!nodes?.king?.strike) return null;
    return nodes.king.strike;
  }, [nodes]);

  // Panel net GEX sum
  const netGex = useMemo(() => {
    if (!rows.length) return 0;
    return rows.reduce((sum, s) => sum + (s.gex || 0), 0);
  }, [rows]);

  // Min/max for footer gradient
  const [minGex, maxGex] = useMemo(() => {
    if (!rows.length) return [0, 0];
    const gexs = rows.map(s => s.gex || 0);
    return [Math.min(...gexs), Math.max(...gexs)];
  }, [rows]);

  const displayName = ticker.replace("^", "");
  const regime = nodes?.regime || "—";
  const regimeColor = regime === "positive" ? "text-emerald-400" : regime === "negative" ? "text-rose-400" : "text-slate-400";
  const regimeLabel = regime === "positive" ? "positive γ" : regime === "negative" ? "negative γ" : "neutral";

  // Total GEX from nodes (more accurate than summing strikes)
  const totalGex = nodes?.total_gex;

  return (
    <div className="trinity-panel">
      {/* Header */}
      <div className="trinity-panel-header">
        <span className="trinity-panel-ticker">{displayName}</span>
        <span className="trinity-panel-price">${fmt(spot, spot >= 1000 ? 2 : 2)}</span>
        <span className={`trinity-panel-regime ${regimeColor}`}>{regimeLabel}</span>
      </div>

      {/* Sub-header: King */}
      <div className="trinity-panel-subheader">
        <span className="trinity-king-dot" />
        <span className="trinity-king-label">King</span>
        {kingStrike != null && <span className="trinity-king-value">{fmt(kingStrike, 0)}</span>}
        <span className={`trinity-net-badge ${netGex >= 0 ? "trinity-net-pos" : "trinity-net-neg"}`}>
          {fmtGex(netGex)}
        </span>
      </div>

      {/* Data grid */}
      <div className="trinity-grid">
        {rows.length === 0 && (
          <div className="trinity-no-data">No strike data available</div>
        )}
        {rows.map((row, i) => {
          const isCurrent = i === spotIdx;
          const isKing = row.strike === kingStrike;
          const gex = row.gex || 0;
          const bg = rowColor(gex, maxAbs);
          const tc = textColor(gex, maxAbs);

          // Percentage of max for badge
          const pctVal = maxAbs > 0 ? Math.abs(gex / maxAbs) * 100 : 0;

          return (
            <div
              key={row.strike}
              className={`trinity-row ${isCurrent ? "trinity-row-current" : ""} ${isKing ? "trinity-row-king" : ""}`}
              style={{ background: bg }}
            >
              {/* Price */}
              <span className={`trinity-row-price ${isCurrent ? "trinity-price-current" : ""}`}>
                {isCurrent && <span className="trinity-price-triangle" />}
                {isKing && <span className="trinity-king-star">★</span>}
                {fmt(row.strike, row.strike >= 1000 ? 0 : 1)}
              </span>

              {/* Percentage badge */}
              <span className="trinity-row-pct">
                {pctVal > 15 && (
                  <span className={`trinity-pct-badge ${gex >= 0 ? "trinity-pct-pos" : "trinity-pct-neg"}`}>
                    {gex >= 0 ? "+" : ""}{pctVal.toFixed(0)}%
                  </span>
                )}
              </span>

              {/* Value */}
              <span className="trinity-row-value" style={{ color: tc }}>
                {fmtGex(gex)}
              </span>
            </div>
          );
        })}
      </div>

      {/* Footer gradient bar */}
      <div className="trinity-footer">
        <span className="trinity-footer-min">{fmtGex(minGex)}</span>
        <div className="trinity-gradient-bar">
          <div className="trinity-gradient-fill" />
        </div>
        <span className="trinity-footer-max">{fmtGex(maxGex)}</span>
      </div>

      {/* Focus link */}
      <button className="trinity-focus-btn" onClick={onFocus}>focus →</button>
    </div>
  );
}
