/**
 * FlowseekerProBlademap.jsx — Blademap.ai-style FlowSeeker Pro, wired to REAL
 * cvforge data. Ported from the /Users/nav/cv-apps/screener mock; mock used
 * synthetic ticks, this uses the live decoder endpoints:
 *   /api/flowseeker/live  /ofi/{t}  /regime/{t}  /vpin/{t}  /lambda/{t}
 *   /api/heatmap/{t} (real GEX grid)
 * Vol surface stays synthetic (no IV-surface backend) and is labelled SIM.
 *
 * Self-contained: scoped CSS (.fsb-root, fsb-* classes), Plotly via CDN.
 * The agent's FlowseekerProTab.jsx is left untouched.
 */
import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { BACKEND_URL } from "../../config/api";
import "./FlowseekerProBlademap.css";

const API = `${BACKEND_URL}/api/flowseeker`;
const WATCH = ["SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL"];
const FEED_TICKERS = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL"]; // merged into the tape

const PL = {
  paper: "rgba(0,0,0,0)", plot: "rgba(0,0,0,0)", grid: "#1c2230", axis: "#3a4358",
  text: "#b3b8c5", muted: "#6c7382", font: "11px ui-monospace, Menlo, monospace",
  green: "#19d27c", red: "#ff4d5e", blue: "#29c5e0", purple: "#a267ff", amber: "#f5b042",
};

// ---------- helpers ----------
const fmtMoney = (v) => {
  const n = Math.abs(Number(v) || 0);
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}k`;
  return `$${n.toFixed(0)}`;
};
const fmtTime = (ts) => { try { return new Date(ts).toLocaleTimeString(); } catch { return String(ts || ""); } };
const dteOf = (exp) => { try { const d = Math.round((new Date(exp) - Date.now()) / 86400000); return d >= 0 ? d : 0; } catch { return 0; } };
async function getJSON(url, signal) {
  const r = await fetch(url, { signal });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// Per-print conviction proxy (0-100) from classification + premium + vol/oi.
function rowConviction(p) {
  const cls = String(p.classification || "regular").toLowerCase();
  const pat = cls === "block" ? 22 : cls === "sweep" ? 20 : cls === "unusual" ? 15 : 8;
  const prem = Number(p.premium) || 0;
  const premPts = prem >= 2e6 ? 22 : prem >= 1e6 ? 18 : prem >= 5e5 ? 13 : prem >= 1e5 ? 8 : 3;
  const voi = Number(p.vol_oi_ratio) || 0;
  const stat = Math.min(25, voi * 6);
  const ctx = 14; // refined for the selected signal with regime confidence
  return Math.round(Math.min(100, pat + premPts + stat + ctx));
}

// Rich conviction for the SELECTED signal using ticker-level microstructure.
function richConviction(p, micro) {
  const cls = String(p.classification || "regular").toLowerCase();
  const pat = Math.min(25, (cls === "block" ? 20 : cls === "sweep" ? 22 : cls === "unusual" ? 15 : 8)
    + ((Number(p.premium) || 0) >= 1e6 ? 4 : 0));
  const stat = Math.min(25, (micro.vpin ?? 0.4) * 25);                 // toxicity
  const ctx = Math.min(25, (micro.regimeConf ?? 0.5) * 25);           // regime confidence
  const imp = Math.min(25, (micro.lambdaR2 ?? 0.4) * 25);             // Kyle-λ fit
  return { stat: +stat.toFixed(1), pat: +pat.toFixed(1), ctx: +ctx.toFixed(1), imp: +imp.toFixed(1),
           conv: Math.round(stat + pat + ctx + imp) };
}

// ---------- component ----------
export default function FlowseekerProBlademap({ active = true }) {
  const [tab, setTab] = useState("flow");
  const [ticker, setTicker] = useState("SPY");
  const [signals, setSignals] = useState([]);     // merged feed, newest first
  const [selected, setSelected] = useState(null);
  const [filter, setFilter] = useState("all");
  const [subtab, setSubtab] = useState("ofi");
  const [regime, setRegime] = useState({ label: "—", cls: "chop" });
  const [clock, setClock] = useState("");
  const [plotlyReady, setPlotlyReady] = useState(!!window.Plotly);
  const [volTicker, setVolTicker] = useState("SPY");

  const microRef = useRef({});            // { vpin, regimeConf, lambdaR2 } for selected ticker
  const gaugeRef = useRef(null), radarRef = useRef(null), ofiRef = useRef(null);
  const gexRef = useRef(null), volRef = useRef(null), gammaBarRef = useRef(null), gammaCurveRef = useRef(null);
  const ofiDataRef = useRef(null), gexDataRef = useRef(null);

  // Plotly CDN
  useEffect(() => {
    if (window.Plotly) { setPlotlyReady(true); return; }
    const s = document.createElement("script");
    s.src = "https://cdn.plot.ly/plotly-2.35.2.min.js";
    s.onload = () => setPlotlyReady(true);
    document.head.appendChild(s);
  }, []);

  // clock
  useEffect(() => {
    const id = setInterval(() => setClock(new Date().toLocaleTimeString()), 1000);
    return () => clearInterval(id);
  }, []);

  // ---- live flow feed: merge a few tickers into one tape ----
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const ctrl = new AbortController();
    const poll = async () => {
      try {
        const all = await Promise.all(FEED_TICKERS.map((t) =>
          getJSON(`${API}/live?ticker=${t}&limit=25`, ctrl.signal).catch(() => null)));
        if (cancelled) return;
        const prints = [];
        for (const r of all) for (const p of (r?.prints || [])) prints.push({ ...p, _conv: rowConviction(p) });
        prints.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        setSignals(prints.slice(0, 120));
      } catch { /* transient */ }
    };
    poll();
    const id = setInterval(poll, 4000);
    return () => { cancelled = true; ctrl.abort(); clearInterval(id); };
  }, [active]);

  // ---- per-ticker microstructure (regime pill + selected conviction inputs) ----
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const ctrl = new AbortController();
    const load = async () => {
      const [reg, vpin, lam, ofi, heat] = await Promise.all([
        getJSON(`${API}/regime/${ticker}`, ctrl.signal).catch(() => null),
        getJSON(`${API}/vpin/${ticker}`, ctrl.signal).catch(() => null),
        getJSON(`${API}/lambda/${ticker}`, ctrl.signal).catch(() => null),
        getJSON(`${API}/ofi/${ticker}`, ctrl.signal).catch(() => null),
        getJSON(`${BACKEND_URL}/api/heatmap/${ticker}?expiries=6&mode=day`, ctrl.signal).catch(() => null),
      ]);
      if (cancelled) return;
      microRef.current = {
        vpin: vpin?.vpin, regimeConf: reg?.confidence, lambdaR2: lam?.r_squared,
      };
      const st = String(reg?.current_state || "").toLowerCase();
      const cls = st.includes("trend") || st.includes("bull") ? "up"
        : st.includes("mean") || st.includes("bear") || st.includes("rever") ? "down" : "chop";
      setRegime({ label: reg?.current_state ? `${reg.current_state}${reg.is_warming ? " (warming)" : ""}` : "—", cls });
      ofiDataRef.current = ofi;
      gexDataRef.current = heat;
      drawOFI(); drawGEX();
    };
    load();
    const id = setInterval(load, 6000);
    return () => { cancelled = true; ctrl.abort(); clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker, active, plotlyReady]);

  // auto-select first signal only (don't steal user clicks)
  useEffect(() => {
    if (!selected && signals.length) selectSignal(signals[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signals]);

  const filtered = useMemo(() => signals.filter((s) => {
    const side = String(s.type || "").toLowerCase().startsWith("c") ? "CALL" : "PUT";
    const cls = String(s.classification || "").toUpperCase();
    switch (filter) {
      case "CALL": return side === "CALL";
      case "PUT": return side === "PUT";
      case "SWEEP": return cls === "SWEEP";
      case "BLOCK": return cls === "BLOCK";
      case "high": return s._conv >= 80;
      default: return true;
    }
  }), [signals, filter]);

  function selectSignal(p) {
    setSelected(p);
    if (p?.ticker && p.ticker !== ticker) setTicker(p.ticker);
    requestAnimationFrame(() => { drawGauge(p); drawRadar(p); });
  }

  // ---------- charts ----------
  const P = useCallback(() => window.Plotly, []);
  function drawGauge(p) {
    if (!P() || !gaugeRef.current || !p) return;
    const rich = richConviction(p, microRef.current);
    const c = rich.conv;
    const col = c >= 85 ? PL.green : c >= 70 ? PL.blue : c >= 55 ? PL.amber : PL.red;
    P().react(gaugeRef.current, [{
      type: "indicator", mode: "gauge+number", value: c,
      number: { font: { color: "#e6e8ee", size: 30, family: PL.font } },
      gauge: { axis: { range: [0, 100], tickcolor: PL.axis, tickfont: { color: PL.muted, size: 9 } },
        bar: { color: col, thickness: 0.25 }, bgcolor: "rgba(0,0,0,0)", borderwidth: 0,
        steps: [{ range: [0, 55], color: "rgba(255,77,94,0.10)" }, { range: [55, 70], color: "rgba(245,176,66,0.10)" },
          { range: [70, 85], color: "rgba(41,197,224,0.10)" }, { range: [85, 100], color: "rgba(25,210,124,0.10)" }],
        threshold: { line: { color: "#e6e8ee", width: 2 }, thickness: 0.75, value: c } },
    }], { paper_bgcolor: PL.paper, margin: { l: 8, r: 8, t: 14, b: 8 }, height: 190, font: { color: PL.text, family: PL.font } },
    { displayModeBar: false, responsive: true });
  }
  function drawRadar(p) {
    if (!P() || !radarRef.current || !p) return;
    const d = richConviction(p, microRef.current);
    const cats = ["Stat Anomaly", "Pattern", "Context", "Impact"];
    P().react(radarRef.current, [{
      type: "scatterpolar", r: [d.stat, d.pat, d.ctx, d.imp, d.stat],
      theta: cats.concat([cats[0]]), fill: "toself", fillcolor: "rgba(41,197,224,0.18)",
      line: { color: PL.blue, width: 2 }, marker: { color: PL.blue, size: 4 },
    }], { paper_bgcolor: PL.paper, polar: { bgcolor: "rgba(0,0,0,0)",
        radialaxis: { range: [0, 26], tickfont: { color: PL.muted, size: 8 }, gridcolor: PL.grid, linecolor: PL.axis },
        angularaxis: { tickfont: { color: PL.text, size: 9 }, gridcolor: PL.grid, linecolor: PL.axis } },
      margin: { l: 34, r: 34, t: 12, b: 12 }, height: 190, showlegend: false, font: { family: PL.font } },
    { displayModeBar: false, responsive: true });
  }
  function drawOFI() {
    if (!P() || !ofiRef.current) return;
    const o = ofiDataRef.current;
    const per = (o?.of_per_level || []).map(Number);
    if (!per.length) { P().react(ofiRef.current, [], { paper_bgcolor: PL.paper, margin: { t: 20 },
      annotations: [{ text: o ? "OFI warming up…" : "no OFI data", showarrow: false, font: { color: PL.muted } }] }, { displayModeBar: false }); return; }
    P().react(ofiRef.current, [{
      type: "bar", x: per.map((_, i) => `L${i + 1}`), y: per,
      marker: { color: per.map((v) => (v >= 0 ? PL.green : PL.red)) },
      hovertemplate: "%{x}: %{y:.3f}<extra></extra>",
    }], { paper_bgcolor: PL.paper, plot_bgcolor: PL.plot, margin: { l: 40, r: 14, t: 24, b: 28 },
      title: { text: `Order-Flow Imbalance · ${o.imbalance_label || ""} (agg ${(o.of_aggregated ?? 0).toFixed?.(2) ?? o.of_aggregated})`, font: { color: PL.text, size: 11, family: PL.font } },
      xaxis: { gridcolor: PL.grid, color: PL.muted }, yaxis: { gridcolor: PL.grid, color: PL.muted, zeroline: true, zerolinecolor: PL.axis },
      font: { family: PL.font } }, { displayModeBar: false, responsive: true });
  }
  function drawGEX() {
    if (!P() || !gexRef.current) return;
    const h = gexDataRef.current;
    const grid = h?.grid?.grid, expiries = h?.grid?.expiries || [], strikes = (h?.grid?.strikes || []).slice().sort((a, b) => a - b);
    if (!grid || !strikes.length) { P().react(gexRef.current, [], { paper_bgcolor: PL.paper, margin: { t: 20 },
      annotations: [{ text: "no GEX grid", showarrow: false, font: { color: PL.muted } }] }, { displayModeBar: false }); return; }
    const z = strikes.map((s) => expiries.map((e) => Number(grid?.[e]?.[String(s)] ?? grid?.[e]?.[s] ?? 0)));
    P().react(gexRef.current, [{
      type: "heatmap", x: expiries.map((e) => String(e).slice(5)), y: strikes.map((s) => `$${s}`), z,
      colorscale: [[0, "#5b1424"], [0.5, "#0c1322"], [1, "#1a5c7e"]], zmid: 0, xgap: 1, ygap: 1,
      colorbar: { thickness: 8, len: 0.7, tickfont: { color: PL.muted, size: 9 } },
      hovertemplate: "%{y} · %{x}<br>GEX %{z:.2f}<extra></extra>",
    }], { paper_bgcolor: PL.paper, margin: { l: 64, r: 14, t: 18, b: 34 },
      xaxis: { color: PL.muted, side: "top" }, yaxis: { color: PL.muted }, font: { family: PL.font } },
    { displayModeBar: false, responsive: true });
  }

  // synthetic vol surface (no IV-surface backend) — labelled SIM
  function drawVol() {
    if (!P() || !volRef.current) return;
    const mny = Array.from({ length: 21 }, (_, i) => 0.8 + i * 0.02);
    const exp = [7, 14, 30, 60, 90, 180];
    const z = exp.map((d) => mny.map((m) => {
      const skew = (1 - m) * 28; const term = 12 + 30 / Math.sqrt(d); const smile = Math.pow(m - 1, 2) * 60;
      return +(term + skew + smile).toFixed(2);
    }));
    P().react(volRef.current, [{ type: "surface", x: mny, y: exp, z,
      colorscale: [[0, "#2c1339"], [0.5, "#29c5e0"], [1, "#19d27c"]], showscale: true,
      colorbar: { thickness: 10, len: 0.6, tickfont: { color: PL.muted, size: 9 } },
      hovertemplate: "Mny %{x}<br>%{y}d<br>IV %{z}%<extra></extra>" }],
    { paper_bgcolor: PL.paper, scene: { camera: { eye: { x: 1.4, y: -1.6, z: 0.7 } },
      xaxis: { title: "Moneyness", color: PL.muted, gridcolor: PL.grid },
      yaxis: { title: "DTE", color: PL.muted, gridcolor: PL.grid },
      zaxis: { title: "IV %", color: PL.muted, gridcolor: PL.grid } },
      margin: { l: 8, r: 8, t: 8, b: 8 }, font: { family: PL.font, color: PL.text } },
    { displayModeBar: false, responsive: true });
  }
  // gamma profile from REAL heatmap net-GEX per strike
  function drawGamma() {
    if (!P() || !gammaBarRef.current) return;
    const h = gexDataRef.current, grid = h?.grid?.grid, expiries = h?.grid?.expiries || [];
    const strikes = (h?.grid?.strikes || []).slice().sort((a, b) => a - b);
    if (!grid || !strikes.length) return;
    const net = strikes.map((s) => expiries.reduce((a, e) => a + Number(grid?.[e]?.[String(s)] ?? 0), 0));
    P().react(gammaBarRef.current, [{ type: "bar", x: strikes.map((s) => `$${s}`), y: net,
      marker: { color: net.map((v) => (v >= 0 ? PL.green : PL.red)) },
      hovertemplate: "%{x}<br>Net GEX %{y:.2f}<extra></extra>" }],
    { paper_bgcolor: PL.paper, margin: { l: 44, r: 12, t: 24, b: 40 }, title: { text: "Net GEX by Strike", font: { color: PL.text, size: 11 } },
      xaxis: { color: PL.muted, gridcolor: PL.grid }, yaxis: { color: PL.muted, gridcolor: PL.grid, zeroline: true, zerolinecolor: PL.axis }, font: { family: PL.font } },
    { displayModeBar: false, responsive: true });
    let cum = 0; const cumA = net.map((v) => (cum += v));
    if (gammaCurveRef.current) P().react(gammaCurveRef.current, [{ type: "scatter", mode: "lines", x: strikes.map((s) => `$${s}`), y: cumA,
      line: { color: PL.blue, width: 2 }, fill: "tozeroy", fillcolor: "rgba(41,197,224,0.10)",
      hovertemplate: "%{x}<br>Cum %{y:.2f}<extra></extra>" }],
    { paper_bgcolor: PL.paper, margin: { l: 44, r: 12, t: 24, b: 40 }, title: { text: "Cumulative Dealer Gamma", font: { color: PL.text, size: 11 } },
      xaxis: { color: PL.muted, gridcolor: PL.grid }, yaxis: { color: PL.muted, gridcolor: PL.grid }, font: { family: PL.font } },
    { displayModeBar: false, responsive: true });
  }

  // redraw when tab/subtab/plotly changes
  useEffect(() => {
    if (!plotlyReady) return;
    if (tab === "flow") { if (subtab === "ofi") drawOFI(); else drawGEX(); if (selected) { drawGauge(selected); drawRadar(selected); } }
    if (tab === "vol") drawVol();
    if (tab === "gamma") drawGamma();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, subtab, plotlyReady, volTicker]);

  const sideOf = (p) => (String(p.type || "").toLowerCase().startsWith("c") ? "CALL" : "PUT");
  const typeOf = (p) => String(p.classification || "reg").toUpperCase();

  // ---------- render ----------
  const TABS = [["flow", "FlowSeeker Pro"], ["vol", "Vol Surface"], ["gamma", "Gamma Profile"], ["scanner", "Scanner"], ["academy", "Academy"]];
  return (
    <div className="fsb-root">
      <div className="fsb-topbar">
        <div className="fsb-brand">
          <span className="fsb-logo">◢</span>
          <span className="fsb-brand-name">FlowSeeker <span className="fsb-pro">Pro</span></span>
          <span className="fsb-status-chip" title="Live cvforge data. Vol surface is simulated (no IV-surface backend).">LIVE · CVFORGE</span>
        </div>
        <div className="fsb-tabs">
          {TABS.map(([id, label]) => (
            <button key={id} className={`fsb-tab${tab === id ? " active" : ""}`} onClick={() => setTab(id)}>{label}</button>
          ))}
        </div>
        <div className="fsb-meta">
          <span className={`fsb-regime-pill ${regime.cls}`}>{regime.label}</span>
          <span>{clock}</span>
        </div>
      </div>

      <div className="fsb-body">
        {/* FLOW VIEW */}
        <div className={`fsb-view fsb-view-flow${tab === "flow" ? " active" : ""}`}>
          {/* left */}
          <div className="fsb-col">
            <div className="fsb-panel" style={{ flex: "1 1 60%" }}>
              <div className="fsb-panel-h"><span>Watchlist</span><span className="fsb-muted fsb-small">{WATCH.length} symbols</span></div>
              <ul className="fsb-watchlist">
                {WATCH.map((t) => (
                  <li key={t} className={`fsb-wl-li${ticker === t ? " selected" : ""}`} onClick={() => setTicker(t)}>
                    <span className="fsb-wl-ticker">{t}</span>
                    <span className="fsb-wl-spot">{t === ticker ? "●" : ""}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="fsb-panel">
              <div className="fsb-panel-h">Filters</div>
              <div className="fsb-chips">
                {[["all", "All"], ["CALL", "Calls"], ["PUT", "Puts"], ["SWEEP", "Sweep"], ["BLOCK", "Block"], ["high", "≥80"]].map(([v, l]) => (
                  <button key={v} className={`fsb-chip${filter === v ? " active" : ""}`} onClick={() => setFilter(v)}>{l}</button>
                ))}
              </div>
            </div>
            <div className="fsb-panel">
              <div className="fsb-panel-h">Legend</div>
              <div className="fsb-legend">
                <span><i className="fsb-dot call" /> Call flow</span>
                <span><i className="fsb-dot put" /> Put flow</span>
                <span><i className="fsb-dot sweep" /> Sweep (urgent)</span>
                <span><i className="fsb-dot block" /> Block (negotiated)</span>
              </div>
            </div>
          </div>

          {/* center */}
          <div className="fsb-col">
            <div className="fsb-panel fsb-flow-panel">
              <div className="fsb-panel-h"><span>Live Flow Feed</span><span><i className="fsb-live-dot" /><span className="fsb-muted fsb-small">live · {filtered.length}</span></span></div>
              <div className="fsb-flow-wrap">
                <table className="fsb-table">
                  <thead><tr>
                    <th>Time</th><th>Ticker</th><th>Type</th><th>Side</th><th className="num">Strike</th>
                    <th>DTE</th><th className="num">Premium</th><th className="num">V/OI</th><th className="num">Conv</th>
                  </tr></thead>
                  <tbody>
                    {filtered.length === 0 && <tr><td colSpan={9} className="fsb-muted" style={{ padding: 14 }}>Waiting for live prints…</td></tr>}
                    {filtered.slice(0, 80).map((p, i) => {
                      const conv = p._conv;
                      return (
                        <tr key={`${p.ticker}-${p.timestamp}-${i}`} className={selected === p ? "selected" : ""}
                            tabIndex={0} onClick={() => selectSignal(p)}
                            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectSignal(p); } }}>
                          <td>{fmtTime(p.timestamp)}</td>
                          <td className="tk">{p.ticker}</td>
                          <td className={`fsb-type-${typeOf(p).toLowerCase()}`}>{typeOf(p)}</td>
                          <td className={sideOf(p) === "CALL" ? "fsb-side-call" : "fsb-side-put"}>{sideOf(p)}</td>
                          <td className="num">{Number(p.strike).toFixed(0)}</td>
                          <td>{dteOf(p.expiration)}d</td>
                          <td className="num">{fmtMoney(p.premium)}</td>
                          <td className="num">{Number(p.vol_oi_ratio || 0).toFixed(1)}</td>
                          <td className="num"><span className={`fsb-conv-bar${conv >= 80 ? "" : conv >= 65 ? " mid" : " low"}`} style={{ width: Math.max(8, conv) * 0.6 }} />{conv}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="fsb-panel fsb-sub-panel">
              <div className="fsb-subtabs">
                <button className={`fsb-subtab${subtab === "ofi" ? " active" : ""}`} onClick={() => setSubtab("ofi")}>Order Flow Imbalance</button>
                <button className={`fsb-subtab${subtab === "gex" ? " active" : ""}`} onClick={() => setSubtab("gex")}>Dealer GEX Heatmap</button>
              </div>
              <div ref={ofiRef} className="fsb-chart" style={{ display: subtab === "ofi" ? "block" : "none" }} />
              <div ref={gexRef} className="fsb-chart" style={{ display: subtab === "gex" ? "block" : "none" }} />
            </div>
          </div>

          {/* right */}
          <div className="fsb-col">
            <div className="fsb-panel fsb-action">
              <div className="fsb-panel-h">Selected Signal</div>
              {!selected ? <div className="fsb-sel-empty">Click any row to load its conviction profile.</div> : (
                <>
                  <div className="fsb-sel-head">
                    <span className="tk">{selected.ticker}</span>
                    <span className="strike">${Number(selected.strike).toFixed(0)} {sideOf(selected)[0]}</span>
                    <span className="fsb-muted fsb-small">{dteOf(selected.expiration)}d · {typeOf(selected)}</span>
                    <span className={`fsb-badge ${sideOf(selected) === "CALL" ? "call" : "put"}`}>{sideOf(selected)}</span>
                  </div>
                  <div className="fsb-con-grid">
                    <div ref={gaugeRef} className="fsb-chart small" />
                    <div ref={radarRef} className="fsb-chart small" />
                  </div>
                  <div className="fsb-rationale">
                    <div style={{ marginBottom: 6 }}><strong>{typeOf(selected)} {sideOf(selected)} · {fmtMoney(selected.premium)}</strong> on {selected.ticker}</div>
                    <ul>
                      <li>Classification: {String(selected.classification || "regular")}</li>
                      <li>Vol/OI ratio: {Number(selected.vol_oi_ratio || 0).toFixed(1)}× (unusual-activity proxy)</li>
                      <li>Toxicity (VPIN): {microRef.current.vpin != null ? microRef.current.vpin.toFixed(2) : "—"} · Kyle-λ fit R²: {microRef.current.lambdaR2 != null ? microRef.current.lambdaR2.toFixed(2) : "—"}</li>
                    </ul>
                    <div className="fsb-muted fsb-small" style={{ marginTop: 6 }}>Regime: {regime.label}. Conviction blends VPIN toxicity, Kyle-λ price impact, regime confidence, and flow pattern.</div>
                  </div>
                  <div className="fsb-actions">
                    <div className="fsb-panel-h" style={{ marginBottom: 6 }}>Context</div>
                    <ul>
                      <li><span className="tag tgt">GEX</span>See dealer positioning in the GEX subtab for {selected.ticker}.</li>
                      <li><span className="tag warn">RISK</span>Paper/educational only — not a trade recommendation.</li>
                    </ul>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>

        {/* VOL VIEW */}
        <div className={`fsb-view${tab === "vol" ? " active" : ""}`} style={{ gridTemplateColumns: "1fr" }}>
          <div className="fsb-panel">
            <div className="fsb-panel-h"><span>3D Implied Volatility Surface</span><span className="fsb-status-chip" style={{ color: "var(--fsb-amber)", background: "rgba(245,176,66,0.06)" }}>SIM</span></div>
            <div className="fsb-vol-controls">
              <label className="fsb-muted fsb-small">Ticker&nbsp;
                <select value={volTicker} onChange={(e) => setVolTicker(e.target.value)}>{["SPY", "QQQ", "NVDA", "TSLA", "AAPL"].map((t) => <option key={t}>{t}</option>)}</select>
              </label>
              <span className="fsb-muted fsb-small">Synthetic surface — no live IV-surface endpoint yet.</span>
            </div>
            <div ref={volRef} className="fsb-chart tall" />
          </div>
        </div>

        {/* GAMMA VIEW */}
        <div className={`fsb-view${tab === "gamma" ? " active" : ""}`} style={{ gridTemplateColumns: "1fr" }}>
          <div className="fsb-panel">
            <div className="fsb-panel-h"><span>Dealer Gamma Exposure · {ticker}</span><span className="fsb-muted fsb-small">real cvforge GEX</span></div>
            <div className="fsb-gamma-grid">
              <div ref={gammaBarRef} className="fsb-chart" />
              <div ref={gammaCurveRef} className="fsb-chart" />
            </div>
            <div className="fsb-notes"><strong>Read:</strong> red bars = dealer short-gamma (hedging amplifies moves), green = long-gamma (dampens). The cumulative line crosses zero at gamma-flip levels.</div>
          </div>
        </div>

        {/* SCANNER VIEW */}
        <div className={`fsb-view${tab === "scanner" ? " active" : ""}`} style={{ gridTemplateColumns: "1fr" }}>
          <div className="fsb-panel">
            <div className="fsb-panel-h"><span>Ticker Scanner</span><span className="fsb-muted fsb-small">live · top conviction across {FEED_TICKERS.length} symbols</span></div>
            <div className="fsb-flow-wrap">
              <table className="fsb-table">
                <thead><tr><th>Time</th><th>Ticker</th><th>Type</th><th>Side</th><th className="num">Strike</th><th>DTE</th><th className="num">Premium</th><th className="num">Conv</th></tr></thead>
                <tbody>
                  {signals.slice().sort((a, b) => b._conv - a._conv).slice(0, 40).map((p, i) => (
                    <tr key={`sc-${i}`} onClick={() => { setTab("flow"); selectSignal(p); }}>
                      <td>{fmtTime(p.timestamp)}</td><td className="tk">{p.ticker}</td>
                      <td className={`fsb-type-${typeOf(p).toLowerCase()}`}>{typeOf(p)}</td>
                      <td className={sideOf(p) === "CALL" ? "fsb-side-call" : "fsb-side-put"}>{sideOf(p)}</td>
                      <td className="num">{Number(p.strike).toFixed(0)}</td><td>{dteOf(p.expiration)}d</td>
                      <td className="num">{fmtMoney(p.premium)}</td>
                      <td className="num"><span className={`fsb-conv-bar${p._conv >= 80 ? "" : p._conv >= 65 ? " mid" : " low"}`} style={{ width: Math.max(8, p._conv) * 0.6 }} />{p._conv}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* ACADEMY VIEW */}
        <div className={`fsb-view${tab === "academy" ? " active" : ""}`} style={{ gridTemplateColumns: "1fr" }}>
          <div className="fsb-panel" style={{ overflow: "auto" }}>
            <div className="fsb-panel-h"><span>FlowSeeker Academy</span><span className="fsb-muted fsb-small">process · not signals</span></div>
            <div className="fsb-academy-grid">
              {[["01", "Market Microstructure", "Order flow, options mechanics, and dealer hedging — the mechanics behind every signal."],
                ["02", "Reading the Flow", "Sweep vs. block vs. split. How urgency, size, and persistence reveal institutional intent."],
                ["03", "Dealer Positioning", "Gamma, vanna, charm — translating dealer hedging pressure into actionable levels."],
                ["04", "Volatility Anatomy", "Skew dynamics, term structure, vol risk premium — and where institutions hide."],
                ["05", "Process & Execution", "Invalidation, position sizing, standing aside. The discipline that protects capital."],
                ["06", "Regime Adaptation", "Bull, bear, chop, melt-up — the same signal means different things across regimes."]].map(([n, t, d]) => (
                <div key={n} className="fsb-module"><div className="fsb-mod-num">{n}</div><div className="fsb-mod-title">{t}</div><p>{d}</p><div className="fsb-mod-meta">curriculum</div></div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="fsb-foot">
        <span>Live cvforge data · GEX/OFI/VPIN/Kyle-λ/regime from the decoder backend. Vol surface simulated.</span>
        <span>FlowSeeker Pro · Blademap layout</span>
      </div>
    </div>
  );
}
