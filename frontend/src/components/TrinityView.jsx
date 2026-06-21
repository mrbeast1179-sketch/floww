import React, { useEffect, useState, useMemo } from "react";
import axios from "axios";
import { fmt, fmtAbs, TRINITY } from "../lib/helpers";

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : "/api";

/**
 * Trinity 3-Panel View — Skylit DOM-ladder reference style
 *
 * View modes:
 * - "grid": strike × expiry heatmap (GEX per cell, colored)
 * - "bars": horizontal bar chart per strike
 * - "list": price ladder with % badges
 *
 * Key features:
 * - Current price row: white arrow pointer + inverted colors
 * - Zero gamma flip: purple highlighted row
 * - King node: gold glow + large star + pulse animation
 * - Color legend at bottom
 */

// ── Heatmap cell color (reference: green=pos, red/purple=neg, yellow=extreme, blue=extreme neg) ──
function heatColor(v, maxAbs) {
  if (v === null || v === undefined || isNaN(v) || v === 0) {
    return { bg: "rgba(11,17,33,0.95)", text: "#3a4560", star: false, extreme: false };
  }
  const norm = Math.min(1, Math.abs(v) / maxAbs);
  const isNeg = v < 0;
  if (norm > 0.85) {
    return isNeg
      ? { bg: `rgba(59,130,246,${0.6 + 0.3 * norm})`, text: "#e0f2fe", star: true, extreme: true }
      : { bg: `rgba(251,191,36,${0.75 + 0.2 * norm})`, text: "#0b1121", star: true, extreme: true };
  }
  if (norm > 0.50) {
    return isNeg
      ? { bg: `rgba(168,85,247,${0.45 + 0.25 * norm})`, text: "#e9d5ff", star: false, extreme: false }
      : { bg: `rgba(45,212,191,${0.45 + 0.25 * norm})`, text: "#0b1121", star: false, extreme: false };
  }
  if (norm > 0.20) {
    return isNeg
      ? { bg: `rgba(168,85,247,${0.15 + 0.15 * norm})`, text: "#c4b5fd", star: false, extreme: false }
      : { bg: `rgba(45,212,191,${0.15 + 0.15 * norm})`, text: "#6ee7b7", star: false, extreme: false };
  }
  return isNeg
    ? { bg: "rgba(88,28,135,0.08)", text: "#8b7fd4", star: false, extreme: false }
    : { bg: "rgba(22,78,99,0.08)", text: "#5ebfb0", star: false, extreme: false };
}

function rowColor(gexVal, maxAbs) {
  if (!gexVal || !maxAbs) return "transparent";
  const norm = Math.min(1, Math.abs(gexVal) / maxAbs);
  const isNeg = gexVal < 0;
  if (norm > 0.80) return "rgba(253,224,71,0.65)";
  if (norm > 0.50) return isNeg ? "rgba(168,85,247,0.40)" : "rgba(45,212,191,0.45)";
  if (norm > 0.20) return isNeg ? "rgba(168,85,247,0.22)" : "rgba(45,212,191,0.25)";
  return isNeg ? "rgba(88,28,135,0.10)" : "rgba(22,78,99,0.10)";
}

function textColor(gexVal, maxAbs) {
  if (!gexVal || !maxAbs) return "#4a5568";
  const norm = Math.min(1, Math.abs(gexVal) / maxAbs);
  if (norm > 0.80) return "#0a0e1a";
  if (norm > 0.50) return gexVal < 0 ? "#e9d5ff" : "#0a0e1a";
  return gexVal < 0 ? "#c4b5fd" : "#6ee7b7";
}

function isNeg(v) { return v < 0; }

function fmtGex(v) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  return `${sign}${abs.toFixed(0)}`;
}

// ── Node tag colors ──────────────────────────────────────────────────
const TAG_STYLES = {
  KING: { bg: "rgba(251,191,36,0.15)", border: "rgba(251,191,36,0.4)", text: "#fbbf24" },
  FLR: { bg: "rgba(52,211,153,0.12)", border: "rgba(52,211,153,0.35)", text: "#34d399" },
  CEIL: { bg: "rgba(248,113,113,0.12)", border: "rgba(248,113,113,0.35)", text: "#f87171" },
  GATE: { bg: "rgba(56,189,248,0.12)", border: "rgba(56,189,248,0.35)", text: "#38bdf8" },
  AIR: { bg: "rgba(148,163,184,0.08)", border: "rgba(148,163,184,0.25)", text: "#94a3b8" },
};

// ── View mode options ────────────────────────────────────────────────
const VIEW_MODES = [
  { id: "dom", label: "DOM", icon: "▦" },
  { id: "grid", label: "Grid", icon: "⊞" },
  { id: "bars", label: "Bars", icon: "▤" },
  { id: "chain", label: "Chain", icon: "☰" },
  { id: "list", label: "List", icon: "≡" },
];

const GEX_VEX_MODES = [
  { id: "gex", label: "GEX" },
  { id: "vex", label: "VEX" },
];

// ── Main Trinity View ──────────────────────────────────────────────
export default function TrinityView({ onFocusTicker }) {
  const [allData, setAllData] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [viewMode, setViewMode] = useState("dom");
  const [gexVexMode, setGexVexMode] = useState("gex");
  const [panelTickers, setPanelTickers] = useState({ "0": "^SPX", "1": "SPY", "2": "QQQ" });

  // Fetch all tickers on mount + track which tickers we have data for
  useEffect(() => {
    let mounted = true;
    const allTickers = ["^SPX", "SPY", "QQQ", "^NDX", "IWM", "DIA", "TLT"];
    const fetchAll = async () => {
      setLoading(true);
      try {
        const results = await Promise.allSettled(
          allTickers.map(t =>
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
      <ConfluenceBar data={allData} viewMode={viewMode} onViewModeChange={setViewMode} gexVexMode={gexVexMode} onGexVexChange={setGexVexMode} />
      <div className="trinity-panels">
        {TRINITY.map((defaultTicker, idx) => {
          const currentTicker = panelTickers[idx] || defaultTicker;
          return (
            <TrinityPanel
              key={idx}
              ticker={currentTicker}
              data={allData[currentTicker] || allData[defaultTicker]}
              viewMode={viewMode}
              gexVexMode={gexVexMode}
              onFocus={() => onFocusTicker && onFocusTicker(currentTicker)}
              onTickerChange={(t) => setPanelTickers(prev => ({ ...prev, [idx]: t }))}
            />
          );
        })}
      </div>
    </div>
  );
}

// ── Confluence Summary Bar ─────────────────────────────────────────
function ConfluenceBar({ data, viewMode, onViewModeChange, gexVexMode, onGexVexChange }) {
  const tickers = TRINITY.map(t => data[t]).filter(d => d && !d.error);
  if (tickers.length === 0) return null;

  const regimes = tickers.map(d => d.nodes?.regime).filter(Boolean);
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
      <div className="trinity-summary-right">
        <span className={`trinity-verdict ${verdictColor}`}>{verdictText}</span>
        <div className="trinity-view-toggle">
          {VIEW_MODES.map(vm => (
            <button
              key={vm.id}
              className={`trinity-view-btn${viewMode === vm.id ? " trinity-view-active" : ""}`}
              onClick={() => onViewModeChange(vm.id)}
              title={vm.label}
            >
              <span className="trinity-view-icon">{vm.icon}</span>
              <span className="trinity-view-label">{vm.label}</span>
            </button>
          ))}
        </div>
        <div className="trinity-gexvex-toggle">
          {GEX_VEX_MODES.map(m => (
            <button
              key={m.id}
              className={`trinity-gexvex-btn${gexVexMode === m.id ? " trinity-gexvex-active" : ""}`}
              onClick={() => onGexVexChange(m.id)}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Single Trinity Panel ───────────────────────────────────────────
const PANEL_TICKERS = ["^SPX", "SPY", "QQQ", "^NDX", "IWM", "DIA", "TLT"];

function TrinityPanel({ ticker, data, viewMode, gexVexMode, onFocus, onTickerChange }) {
  const [showTickerMenu, setShowTickerMenu] = useState(false);
  const spot = data?.spot;
  const nodes = data?.nodes;
  const gridData = data?.grid?.grid;

  // Sorted strikes
  const rows = useMemo(() => {
    if (!data?.strikes) return [];
    return data.strikes
      .filter(s => s.strike != null && s.gex != null)
      .sort((a, b) => b.strike - a.strike);
  }, [data]);

  // Expiries for grid view
  const expiries = useMemo(() => {
    if (!gridData) return [];
    return Object.keys(gridData).sort().slice(0, 6);
  }, [gridData]);

  // Max abs GEX for grid view (across all expiries and strikes)
  const gridMaxAbs = useMemo(() => {
    if (!gridData || !expiries.length) return 1;
    let m = 1;
    for (const exp of expiries) {
      const strikes = gridData[exp] || {};
      for (const s of Object.keys(strikes)) {
        const v = Math.abs(strikes[s]?.gex || 0);
        if (v > m) m = v;
      }
    }
    return m;
  }, [gridData, expiries]);

  // Max abs GEX for list/bars view
  const maxAbs = useMemo(() => {
    if (!rows.length) return 1;
    return Math.max(...rows.map(s => Math.abs(s.gex || 0)), 1);
  }, [rows]);

  // Current price row index
  const spotIdx = useMemo(() => {
    if (!spot || !rows.length) return -1;
    let best = 0, bestDist = Math.abs(rows[0].strike - spot);
    for (let i = 1; i < rows.length; i++) {
      const d = Math.abs(rows[i].strike - spot);
      if (d < bestDist) { bestDist = d; best = i; }
    }
    return best;
  }, [rows, spot]);

  // Zero gamma flip strike (from nodes.gamma_flip or calculate)
  const flipStrike = useMemo(() => {
    if (nodes?.gamma_flip) return nodes.gamma_flip;
    // Calculate: find where net GEX crosses zero
    let prev = rows[0]?.gex || 0;
    for (let i = 1; i < rows.length; i++) {
      const curr = rows[i]?.gex || 0;
      if ((prev > 0 && curr < 0) || (prev < 0 && curr > 0)) {
        return (rows[i - 1].strike + rows[i].strike) / 2;
      }
      prev = curr;
    }
    return null;
  }, [nodes, rows]);

  // King node (max abs GEX strike)
  const kingStrike = useMemo(() => {
    if (!rows.length) return null;
    let maxVal = 0, kingS = null;
    for (const row of rows) {
      const v = Math.abs(row.gex || 0);
      if (v > maxVal) { maxVal = v; kingS = row.strike; }
    }
    return kingS;
  }, [rows]);

  // Net GEX
  const netGex = useMemo(() => {
    if (!rows.length) return 0;
    return rows.reduce((sum, s) => sum + (s.gex || 0), 0);
  }, [rows]);

  const [minGex, maxGex] = useMemo(() => {
    if (!rows.length) return [0, 0];
    const gexs = rows.map(s => s.gex || 0);
    return [Math.min(...gexs), Math.max(...gexs)];
  }, [rows]);

  // Determine node tags for this panel
  const tags = useMemo(() => {
    const t = [];
    if (kingStrike != null) t.push("KING");
    if (flipStrike != null) t.push("FLR");
    if (nodes?.ceilings?.[0]) t.push("CEIL");
    if (nodes?.gatekeepers?.[0]) t.push("GATE");
    if (nodes?.air_pockets?.[0]) t.push("AIR");
    return t;
  }, [kingStrike, flipStrike, nodes]);

  const displayName = ticker.replace("^", "");
  const regime = nodes?.regime || "—";
  const regimeColor = regime === "positive" ? "text-emerald-400" : regime === "negative" ? "text-rose-400" : "text-slate-400";
  const regimeLabel = regime === "positive" ? "positive γ" : regime === "negative" ? "negative γ" : "neutral";

  // DOM column config based on GEX/VEX mode
  const domCols = useMemo(() => {
    if (gexVexMode === "vex") {
      return [
        { key: "call_vex", label: "Call VEX", field: "call_vex" },
        { key: "vex", label: "Net VEX", field: "vex" },
        { key: "put_vex", label: "Put VEX", field: "put_vex" },
        { key: "vomma", label: "Vomma", field: "vomma" },
        { key: "zomma", label: "Zomma", field: "zomma" },
      ];
    }
    return [
      { key: "call_gex", label: "Call GEX", field: "call_gex" },
      { key: "gex", label: "Net GEX", field: "gex" },
      { key: "put_gex", label: "Put GEX", field: "put_gex" },
      { key: "vex", label: "VEX", field: "vex" },
      { key: "charm", label: "Charm", field: "charm" },
    ];
  }, [gexVexMode]);

  const renderView = () => {
    if (rows.length === 0) return <div className="trinity-no-data">No strike data available</div>;
    switch (viewMode) {
      case "dom":
        return <DOMView rows={rows} domCols={domCols} spotIdx={spotIdx} kingStrike={kingStrike} flipStrike={flipStrike} tags={tags} />;
      case "chain":
        return <ChainView rows={rows} spotIdx={spotIdx} kingStrike={kingStrike} flipStrike={flipStrike} />;
      case "bars":
        return <BarsView rows={rows} maxAbs={maxAbs} spotIdx={spotIdx} kingStrike={kingStrike} tags={tags} />;
      case "list":
        return <ListView rows={rows} maxAbs={maxAbs} spotIdx={spotIdx} kingStrike={kingStrike} flipStrike={flipStrike} />;
      case "grid":
      default:
        return <GridView rows={rows} expiries={expiries} gridData={gridData} gridMaxAbs={gridMaxAbs} spotIdx={spotIdx} flipStrike={flipStrike} />;
    }
  };

  return (
    <div className="trinity-panel">
      {/* Header — DOM ladder style */}
      <div className="trinity-panel-header">
        <div className="trinity-ticker-wrap">
          <button
            className="trinity-ticker-btn"
            onClick={() => setShowTickerMenu(!showTickerMenu)}
            title="Switch ticker"
          >
            {displayName}
            <span className="trinity-ticker-caret">▾</span>
          </button>
          {showTickerMenu && (
            <div className="trinity-ticker-menu">
              {PANEL_TICKERS.map(t => (
                <button
                  key={t}
                  className={`trinity-ticker-option${t === ticker ? " trinity-ticker-active" : ""}`}
                  onClick={() => { onTickerChange(t); setShowTickerMenu(false); }}
                >
                  {t.replace("^", "")}
                </button>
              ))}
            </div>
          )}
        </div>
        <span className="trinity-panel-price">${fmt(spot, spot >= 1000 ? 2 : 2)}</span>
        <span className="trinity-live-dot" />
        <span className={`trinity-panel-regime ${regimeColor}`}>{regimeLabel}</span>
      </div>

      {/* Sub-header: King + Net GEX */}
      <div className="trinity-panel-subheader">
        <span className="trinity-king-dot" />
        <span className="trinity-king-label">King</span>
        {kingStrike != null && <span className="trinity-king-value">{fmt(kingStrike, 0)}</span>}
        <div className="trinity-tags">
          {tags.map(tag => (
            <span key={tag} className={`trinity-tag trinity-tag-${tag.toLowerCase()}`}>{tag}</span>
          ))}
        </div>
        <span className={`trinity-net-badge ${netGex >= 0 ? "trinity-net-pos" : "trinity-net-neg"}`}>
          {fmtGex(netGex)}
        </span>
      </div>

      {/* Data view */}
      <div className="trinity-grid">
        {renderView()}
      </div>

      {/* Color legend */}
      {viewMode === "grid" && (
        <div className="trinity-legend">
          <span className="trinity-legend-label">Scale</span>
          <div className="trinity-legend-bar">
            <span className="trinity-legend-seg legend-neg-strong" />
            <span className="trinity-legend-seg legend-neg-weak" />
            <span className="trinity-legend-seg legend-zero" />
            <span className="trinity-legend-seg legend-pos-weak" />
            <span className="trinity-legend-seg legend-pos-strong" />
          </div>
          <div className="trinity-legend-labels">
            <span>−</span>
            <span>0</span>
            <span>+</span>
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="trinity-footer">
        <span className="trinity-footer-min">{fmtGex(minGex)}</span>
        <div className="trinity-gradient-bar" />
        <span className="trinity-footer-max">{fmtGex(maxGex)}</span>
      </div>

      <button className="trinity-focus-btn" onClick={onFocus}>focus →</button>
    </div>
  );
}

// ── Grid View (strike × expiry heatmap) ───────────────────────────
function GridView({ rows, expiries, gridData, gridMaxAbs, spotIdx, flipStrike }) {
  if (!gridData || expiries.length === 0) {
    // Fallback to list view if no grid data
    return <div className="trinity-no-data">No grid data available</div>;
  }

  return (
    <div className="trinity-grid-scroll">
      <table className="trinity-grid-table">
        <thead>
          <tr className="trinity-grid-header">
            <th className="trinity-grid-th-price">Strike</th>
            {expiries.map(exp => (
              <th key={exp} className="trinity-grid-th">{exp.slice(5)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const isCurrent = i === spotIdx;
            const isFlip = flipStrike != null && Math.abs(row.strike - flipStrike) <= (rows[0]?.strike - rows[1]?.strike || 5) / 2;
            return (
              <tr
                key={row.strike}
                className={`trinity-grid-row${isCurrent ? " trinity-row-current" : ""}${isFlip ? " trinity-row-flip" : ""}`}
              >
                <td className={`trinity-grid-price${isCurrent ? " trinity-price-current" : ""}`}>
                  {isCurrent && <span className="trinity-price-arrow" />}
                  {fmt(row.strike, row.strike >= 1000 ? 0 : 1)}
                </td>
                {expiries.map(exp => {
                  const cellVal = gridData[exp]?.[row.strike]?.gex || 0;
                  const cc = heatColor(cellVal, gridMaxAbs);
                  return (
                    <td
                      key={exp}
                      className={`trinity-grid-cell${cc.star ? " trinity-grid-star" : ""}${cc.extreme ? " trinity-grid-extreme" : ""}`}
                      style={{ background: cc.bg, color: cc.text }}
                      title={`${fmt(row.strike, 0)} @ ${exp}: ${fmtGex(cellVal)}`}
                    >
                      {cc.star && <span className="trinity-grid-star-icon">★</span>}{fmtGex(cellVal)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── DOM Ladder View (strike × Greek columns) ────────────────────────
function DOMView({ rows, domCols, spotIdx, kingStrike, flipStrike, tags }) {
  // Compute maxAbs per DOM column for color scaling
  const colMaxAbs = useMemo(() => {
    const result = {};
    for (const col of domCols) {
      let m = 1;
      for (const row of rows) {
        const v = Math.abs(row[col.field] || 0);
        if (v > m) m = v;
      }
      result[col.field] = m;
    }
    return result;
  }, [rows, domCols]);

  return (
    <div className="trinity-dom-scroll">
      <table className="trinity-dom-table">
        <thead>
          <tr className="trinity-dom-header">
            <th className="trinity-dom-th-price">Strike</th>
            {domCols.map(col => (
              <th key={col.field} className="trinity-dom-th">{col.label}</th>
            ))}
            <th className="trinity-dom-th-tags">Tags</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const isCurrent = i === spotIdx;
            const isKing = row.strike === kingStrike;
            const isFlip = flipStrike != null && Math.abs(row.strike - flipStrike) <= (rows[0]?.strike - rows[1]?.strike || 5) / 2;
            return (
              <tr
                key={row.strike}
                className={`trinity-dom-row${isCurrent ? " trinity-row-current" : ""}${isKing ? " trinity-row-king" : ""}${isFlip ? " trinity-row-flip" : ""}`}
              >
                <td className={`trinity-dom-price${isCurrent ? " trinity-price-current" : ""}`}>
                  {isCurrent && <span className="trinity-price-arrow" />}
                  {isKing && <span className="trinity-king-star">★</span>}
                  {fmt(row.strike, row.strike >= 1000 ? 0 : 1)}
                </td>
                {domCols.map(col => {
                  const val = row[col.field] || 0;
                  const cc = heatColor(val, colMaxAbs[col.field]);
                  return (
                    <td
                      key={col.field}
                      className={`trinity-dom-cell${cc.star ? " trinity-grid-star" : ""}${cc.extreme ? " trinity-grid-extreme" : ""}`}
                      style={{ background: cc.bg, color: cc.text }}
                      title={`${col.label}: ${fmtGex(val)}`}
                    >
                      {cc.star && <span className="trinity-grid-star-icon">★</span>}{fmtGex(val)}
                    </td>
                  );
                })}
                <td className="trinity-dom-tags">
                  {tags.map(tag => (
                    <span key={tag} className={`trinity-tag trinity-tag-${tag.toLowerCase()}`}>{tag}</span>
                  ))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Chain View (raw options table) ─────────────────────────────────
function ChainView({ rows, spotIdx, kingStrike, flipStrike }) {
  return (
    <div className="trinity-chain-scroll">
      <table className="trinity-chain-table">
        <thead>
          <tr className="trinity-chain-header">
            <th className="trinity-chain-th">Strike</th>
            <th className="trinity-chain-th">Type</th>
            <th className="trinity-chain-th">GEX</th>
            <th className="trinity-chain-th">Call GEX</th>
            <th className="trinity-chain-th">Put GEX</th>
            <th className="trinity-chain-th">OI</th>
            <th className="trinity-chain-th">VEX</th>
            <th className="trinity-chain-th">Charm</th>
            <th className="trinity-chain-th">IV</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const isCurrent = i === spotIdx;
            const isKing = row.strike === kingStrike;
            const isFlip = flipStrike != null && Math.abs(row.strike - flipStrike) <= (rows[0]?.strike - rows[1]?.strike || 5) / 2;
            const rowBg = isKing
              ? "rgba(251,191,36,0.08)"
              : isFlip
                ? "rgba(167,139,250,0.06)"
                : "transparent";
            return (
              <tr
                key={row.strike}
                className={`trinity-chain-row${isCurrent ? " trinity-row-current" : ""}`}
                style={{ background: rowBg }}
              >
                <td className={`trinity-chain-price${isCurrent ? " trinity-price-current" : ""}`}>
                  {isCurrent && <span className="trinity-price-arrow" />}
                  {isKing && <span className="trinity-king-star">★</span>}
                  {fmt(row.strike, row.strike >= 1000 ? 0 : 1)}
                </td>
                <td className="trinity-chain-type">
                  <span className={`trinity-chain-type-badge ${row.gex >= 0 ? "type-call" : "type-put"}`}>
                    {row.call_gex > Math.abs(row.put_gex) ? "C" : "P"}
                  </span>
                </td>
                <td className="trinity-chain-cell" style={{ color: row.gex >= 0 ? "#6ee7b7" : "#c4b5fd" }}>
                  {fmtGex(row.gex)}
                </td>
                <td className="trinity-chain-cell" style={{ color: "#6ee7b7" }}>
                  {fmtGex(row.call_gex)}
                </td>
                <td className="trinity-chain-cell" style={{ color: "#c4b5fd" }}>
                  {fmtGex(row.put_gex)}
                </td>
                <td className="trinity-chain-cell trinity-chain-oi">
                  {fmtAbs(row.total_oi || 0)}
                </td>
                <td className="trinity-chain-cell" style={{ color: row.vex >= 0 ? "#6ee7b7" : "#c4b5fd" }}>
                  {fmtGex(row.vex)}
                </td>
                <td className="trinity-chain-cell" style={{ color: row.charm >= 0 ? "#6ee7b7" : "#c4b5fd" }}>
                  {fmtGex(row.charm)}
                </td>
                <td className="trinity-chain-cell trinity-chain-iv">
                  {row.iv != null ? `${(row.iv * 100).toFixed(1)}%` : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Bars View ──────────────────────────────────────────────────────
function BarsView({ rows, maxAbs, spotIdx, kingStrike, tags }) {
  return (
    <div className="trinity-bars-scroll">
      {rows.map((row, i) => {
        const isCurrent = i === spotIdx;
        const isKing = row.strike === kingStrike;
        const gex = row.gex || 0;
        const absGex = Math.abs(gex);
        const pct = maxAbs > 0 ? (absGex / maxAbs) * 100 : 0;
        const isNeg = gex < 0;
        const barColor = isKing
          ? "linear-gradient(90deg, rgba(251,191,36,0.9), rgba(253,224,71,0.95))"
          : isNeg
            ? "linear-gradient(90deg, rgba(168,85,247,0.6), rgba(168,85,247,0.3))"
            : "linear-gradient(90deg, rgba(45,212,191,0.6), rgba(45,212,191,0.3))";

        return (
          <div
            key={row.strike}
            className={`trinity-bar-row${isCurrent ? " trinity-row-current" : ""}${isKing ? " trinity-row-king-bar" : ""}`}
          >
            <span className={`trinity-bar-price${isCurrent ? " trinity-price-current" : ""}`}>
              {isCurrent && <span className="trinity-price-arrow" />}
              {isKing && <span className="trinity-king-star-bar">★</span>}
              {fmt(row.strike, row.strike >= 1000 ? 0 : 1)}
            </span>
            <div className="trinity-bar-track">
              <div
                className={`trinity-bar-fill${isKing ? " trinity-bar-king" : ""}`}
                style={{ width: `${Math.min(100, pct)}%`, background: barColor }}
              />
            </div>
            <span className="trinity-bar-value" style={{ color: isKing ? "#fbbf24" : isNeg ? "#c4b5fd" : "#6ee7b7" }}>
              {fmtGex(gex)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── List View (price ladder) ───────────────────────────────────────
function ListView({ rows, maxAbs, spotIdx, kingStrike, flipStrike }) {
  return (
    <>
      {rows.map((row, i) => {
        const isCurrent = i === spotIdx;
        const isKing = row.strike === kingStrike;
        const isFlip = flipStrike != null && Math.abs(row.strike - flipStrike) <= (rows[0]?.strike - rows[1]?.strike || 5) / 2;
        const gex = row.gex || 0;
        const bg = rowColor(gex, maxAbs);
        const tc = textColor(gex, maxAbs);
        const pctVal = maxAbs > 0 ? Math.abs(gex / maxAbs) * 100 : 0;

        return (
          <div
            key={row.strike}
            className={`trinity-row${isCurrent ? " trinity-row-current" : ""}${isKing ? " trinity-row-king" : ""}${isFlip ? " trinity-row-flip" : ""}`}
            style={{ background: bg }}
          >
            <span className={`trinity-row-price${isCurrent ? " trinity-price-current" : ""}`}>
              {isCurrent && <span className="trinity-price-arrow" />}
              {isKing && <span className="trinity-king-star">★</span>}
              {fmt(row.strike, row.strike >= 1000 ? 0 : 1)}
            </span>
            <span className="trinity-row-pct">
              {pctVal > 15 && (
                <span className={`trinity-pct-badge${gex >= 0 ? " trinity-pct-pos" : " trinity-pct-neg"}`}>
                  {gex >= 0 ? "+" : ""}{pctVal.toFixed(0)}%
                </span>
              )}
            </span>
            <span className="trinity-row-value" style={{ color: tc }}>
              {fmtGex(gex)}
            </span>
          </div>
        );
      })}
    </>
  );
}
