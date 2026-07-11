/**
 * TrinityVolatility.jsx — Three volatility analysis lenses ported from the
 * cvforge screener (cv-apps/scenner34):
 *   1) IV Skew / Smile (selected expiry, call & put)
 *   2) ATM IV Term Structure (contango/backwardation across expiries)
 *   3) 25Δ Risk Reversal (put−call skew steepness by expiry)
 *
 * Reads from the existing decoder endpoint:
 *   /api/chain/{ticker}?expiries=N
 * which returns { spot, expiries, rows:[{strike, expiry, type, iv, delta, ...}] }.
 *
 * Self-contained: scoped CSS (.tv-root, tv-* classes), Plotly via CDN.
 */
import React, { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import "./TrinityVolatility.css";

class ErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { hasError: false, error: null }; }
  static getDerivedStateFromError(error) { return { hasError: true, error }; }
  render() {
    if (this.state.hasError) return (
      <div style={{color:'#ff6b6b', padding:'20px', fontFamily:'monospace'}}>
        Trinity component error: {this.state.error?.message}
      </div>
    );
    return this.props.children;
  }
}

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : "/api";

const PLOT = { responsive: true, displayModeBar: false };

// ---- color palette (matches decoder dark theme) ----
const C = {
  bg: "#0b0d12", panel: "#11141a", border: "rgba(255,255,255,.06)",
  text: "#b0b8c4", muted: "#7a8599", grid: "#1e293b",
  call: "#34d399", put: "#f43f5e", spot: "#38bdf8", mauve: "#a855f7",
  amber: "#fbbf24", faint1: "#7dd3fc", faint2: "#c4b5fd",
};

// ---- helpers ----
const fmtPct = (v) => (v == null || isNaN(v)) ? "—" : (v * 100).toFixed(1) + "%";
const fmtStrike = (v) => (v == null) ? "—" : (v % 1 === 0 ? v.toFixed(0) : v.toFixed(1));
const dteOf = (exp) => { try { return Math.max(0, Math.round((new Date(exp) - Date.now()) / 86400000)); } catch { return 0; } };

// Find nearest-strike IV for a given type in a set of rows
function nearestIv(rows, spot, type) {
  let best = null, bestGap = Infinity;
  for (const r of rows) {
    if (r.type !== type || r.iv == null) continue;
    const gap = Math.abs(r.strike - spot);
    if (gap < bestGap) { bestGap = gap; best = r; }
  }
  return best;
}

// ---- main component ----
export default function TrinityVolatility({ ticker = "SPY", expiries = 8 }) {
  const [rows, setRows] = useState([]);
  const [spot, setSpot] = useState(0);
  const [expiryList, setExpiryList] = useState([]);
  const [selExpIdx, setSelExpIdx] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [plotlyReady, setPlotlyReady] = useState(!!window.Plotly);

  const skewRef = useRef(null);
  const termRef = useRef(null);
  const rrRef = useRef(null);

  // Load Plotly CDN if not present (matches FlowseekerProBlademap pattern)
  useEffect(() => {
    if (window.Plotly) { setPlotlyReady(true); return; }
    const s = document.createElement("script");
    s.src = "https://cdn.plot.ly/plotly-2.35.2.min.js";
    s.charset = "utf-8";
    s.onload = () => setPlotlyReady(true);
    document.head.appendChild(s);
  }, []);

  // Fetch chain data — reqSeq guard prevents stale responses from overwriting
  // current ticker's data when the user switches symbols quickly.
  const reqSeqRef = useRef(0);
  const fetchChain = useCallback(async () => {
    const myId = ++reqSeqRef.current;
    setLoading(true);
    setErr(null);
    try {
      const r = await axios.get(`${API}/chain/${ticker}?expiries=${expiries}`, { timeout: 20000 });
      if (myId !== reqSeqRef.current) return; // superseded
      if (!r.data || !r.data.rows || !r.data.rows.length) {
        setErr("No chain data for " + ticker);
        setLoading(false);
        return;
      }
      setSpot(r.data.spot || 0);
      setExpiryList(r.data.expiries || []);
      setRows(r.data.rows);
      setSelExpIdx(0);
      setLoading(false);
    } catch (e) {
      if (myId !== reqSeqRef.current) return;
      setErr(e.message || "Failed to load chain");
      setLoading(false);
    }
  }, [ticker, expiries]);

  useEffect(() => { fetchChain(); }, [fetchChain]);

  // ---- compute derived data ----
  const selExp = expiryList[selExpIdx] || "";

  // Rows for the selected expiry
  const expRows = rows.filter((r) => r.expiry === selExp);
  const callRows = expRows.filter((r) => r.type === "call" && r.iv != null);
  const putRows = expRows.filter((r) => r.type === "put" && r.iv != null);

  // IV Skew: call & put IV by strike, near spot (±15%)
  const skewData = (() => {
    if (!spot || !callRows.length || !putRows.length) return null;
    const lo = spot * 0.85, hi = spot * 1.15;
    const allStrikes = [...new Set([...callRows, ...putRows].map((r) => r.strike))].filter(
      (s) => s >= lo && s <= hi
    ).sort((a, b) => a - b);
    const callMap = {}; callRows.forEach((r) => { callMap[r.strike] = r.iv; });
    const putMap = {}; putRows.forEach((r) => { putMap[r.strike] = r.iv; });
    return {
      strikes: allStrikes,
      callIv: allStrikes.map((s) => callMap[s] != null ? callMap[s] * 100 : null),
      putIv: allStrikes.map((s) => putMap[s] != null ? putMap[s] * 100 : null),
    };
  })();

  // Next 2 expiries for faint context smiles. IVs MUST align to
  // skewData.strikes (the selected expiry's sorted unique strikes) or every
  // point is plotted against an unrelated strike. Build a strike→IV map
  // (avg of call/put present) and index it by the same strike axis.
  const faintSmiles = (() => {
    const out = [];
    if (!skewData) return out;
    for (let j = 1; j <= 2; j++) {
      const e2 = expiryList[selExpIdx + j];
      if (!e2) break;
      const r2 = rows.filter((r) => r.expiry === e2 && r.iv != null);
      if (!r2.length) continue;
      const ivByStrike = {};
      for (const r of r2) {
        const prev = ivByStrike[r.strike];
        ivByStrike[r.strike] = prev == null ? r.iv : (prev + r.iv) / 2;
      }
      const ivs = skewData.strikes.map((s) => (ivByStrike[s] != null ? ivByStrike[s] * 100 : null));
      if (!ivs.some((v) => v != null)) continue;
      out.push({ exp: e2, color: j === 1 ? C.faint1 : C.faint2, ivs });
    }
    return out;
  })();

  // ATM IV term structure: mean call/put IV at nearest-spot strike per expiry
  const termData = (() => {
    if (!spot) return [];
    return expiryList.map((exp) => {
      const r2 = rows.filter((r) => r.expiry === exp && r.iv != null);
      const c = nearestIv(r2, spot, "call");
      const p = nearestIv(r2, spot, "put");
      if (!c || !p) return { exp, iv: null };
      return { exp, iv: ((c.iv + p.iv) / 2) * 100 };
    }).filter((d) => d.iv != null);
  })();

  // 25Δ Risk Reversal: IV(put@Δ≈-0.25) − IV(call@Δ≈+0.25), in vol points
  const rrData = (() => {
    return expiryList.map((exp) => {
      const r2 = rows.filter((r) => r.expiry === exp && r.iv != null && r.delta != null);
      let bestC = null, bestP = null, gc = Infinity, gp = Infinity;
      for (const r of r2) {
        if (r.type === "call") {
          const d = Math.abs(r.delta - 0.25);
          if (d < gc) { gc = d; bestC = r.iv; }
        } else {
          const d = Math.abs(r.delta + 0.25);
          if (d < gp) { gp = d; bestP = r.iv; }
        }
      }
      if (bestC == null || bestP == null) return { exp, rr: null };
      return { exp, rr: (bestP - bestC) * 100 };
    }).filter((d) => d.rr != null);
  })();

  // ---- draw charts (via window.Plotly) ----
  const drawSkew = useCallback(() => {
    const el = skewRef.current;
    if (!el || !window.Plotly || !skewData) {
      if (el) window.Plotly.purge(el);
      return;
    }
    const traces = [
      { x: skewData.strikes, y: skewData.callIv, type: "scatter", mode: "lines", name: "Call IV",
        line: { color: C.call, width: 2.5 }, connectgaps: true },
      { x: skewData.strikes, y: skewData.putIv, type: "scatter", mode: "lines", name: "Put IV",
        line: { color: C.put, width: 2.5 }, connectgaps: true },
    ];
    // Faint context smiles
    faintSmiles.forEach((sm, i) => {
      traces.push({
        x: skewData.strikes,
        y: sm.ivs,
        type: "scatter", mode: "lines",
        name: sm.exp.slice(5),
        line: { color: sm.color, width: 1, dash: "dot" },
        opacity: 0.55, connectgaps: true,
      });
    });
    const layout = {
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      margin: { l: 40, r: 8, t: 6, b: 28 },
      xaxis: { color: C.muted, tickfont: { color: C.muted, size: 9 }, gridcolor: C.grid },
      yaxis: { title: { text: "IV %", font: { size: 9 } }, color: C.muted, tickfont: { color: C.muted, size: 9 }, gridcolor: C.grid },
      legend: { orientation: "h", y: 1.12, font: { size: 8 } },
      hovermode: "x unified",
      shapes: spot ? [{ type: "line", x0: spot, x1: spot, y0: 0, y1: 1, yref: "paper",
        line: { color: C.spot, width: 1, dash: "dot" } }] : [],
      uirevision: "skew",
    };
    window.Plotly.react(el, traces, layout, PLOT);
  }, [skewData, faintSmiles, spot]);

  const drawTerm = useCallback(() => {
    const el = termRef.current;
    if (!el || !window.Plotly) return;
    if (!termData.length) { window.Plotly.purge(el); return; }
    const trace = {
      x: termData.map((d) => d.exp), y: termData.map((d) => d.iv),
      type: "scatter", mode: "lines+markers",
      line: { color: C.mauve, width: 2 }, marker: { size: 5, color: C.mauve },
      hovertemplate: "%{x}<br>ATM IV %{y:.1f}%<extra></extra>",
    };
    const layout = {
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      margin: { l: 38, r: 8, t: 6, b: 64 },
      xaxis: { color: C.muted, tickfont: { color: C.muted, size: 8 }, tickangle: -40, type: "category" },
      yaxis: { title: { text: "ATM IV %", font: { size: 9 } }, color: C.muted, tickfont: { color: C.muted, size: 9 }, gridcolor: C.grid },
      uirevision: "term",
    };
    window.Plotly.react(el, [trace], layout, PLOT);
  }, [termData]);

  const drawRR = useCallback(() => {
    const el = rrRef.current;
    if (!el || !window.Plotly) return;
    if (!rrData.length) { window.Plotly.purge(el); return; }
    const trace = {
      x: rrData.map((d) => d.exp), y: rrData.map((d) => d.rr),
      type: "bar",
      marker: { color: rrData.map((d) => d.rr >= 0 ? "rgba(244,63,94,0.7)" : "rgba(52,211,153,0.7)") },
      hovertemplate: "%{x}<br>25Δ RR %{y:.1f} vol pts<extra></extra>",
    };
    const layout = {
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      margin: { l: 36, r: 8, t: 6, b: 64 },
      xaxis: { color: C.muted, tickfont: { color: C.muted, size: 8 }, tickangle: -40, type: "category" },
      yaxis: { title: { text: "vol pts", font: { size: 9 } }, color: C.muted, tickfont: { color: C.muted, size: 9 },
        zeroline: true, zerolinecolor: "#475569", gridcolor: C.grid },
      uirevision: "rr",
    };
    window.Plotly.react(el, [trace], layout, PLOT);
  }, [rrData]);

  // Redraw on data / plotly ready change
  useEffect(() => {
    if (!plotlyReady) return;
    drawSkew();
    drawTerm();
    drawRR();
  }, [plotlyReady, drawSkew, drawTerm, drawRR]);

  // Purge Plotly instances on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      [skewRef, termRef, rrRef].forEach(ref => {
        if (ref.current && window.Plotly) window.Plotly.purge(ref.current);
      });
    };
  }, []);

  // ---- render ----
  if (loading) {
    return <div className="tv-root"><div className="tv-loading">Loading {ticker} volatility…</div></div>;
  }
  if (err) {
    return <div className="tv-root"><div className="tv-error">{err}</div></div>;
  }

  return (
    <ErrorBoundary>
    <div className="tv-root">
      <div className="tv-header">
        <span className="tv-title">△ Trinity Volatility</span>
        <span className="tv-sub">{ticker} · spot {spot ? spot.toFixed(2) : "—"} · {expiryList.length} expiries</span>
        <span className="tv-controls">
          <label>Expiry:&nbsp;
            <select value={selExpIdx} onChange={(e) => setSelExpIdx(Number(e.target.value))}>
              {expiryList.map((e, i) => <option key={e} value={i}>{e}</option>)}
            </select>
          </label>
        </span>
      </div>

      <div className="tv-grid">
        <div className="tv-cell">
          <div className="tv-cell-h">IV Skew <small>{selExp}</small></div>
          <div className="tv-cell-b" ref={skewRef} />
          <div className="tv-legend">
            <span style={{ color: C.call }}>● Call IV</span>
            <span style={{ color: C.put }}>● Put IV</span>
            {faintSmiles.map((sm, i) => (
              <span key={i} style={{ color: sm.color }}>┄ {sm.exp.slice(5)}</span>
            ))}
            <span style={{ color: C.spot }}>┄ Spot</span>
          </div>
        </div>

        <div className="tv-cell">
          <div className="tv-cell-h">ATM IV Term Structure <small>vol vs expiry</small></div>
          <div className="tv-cell-b" ref={termRef} />
        </div>

        <div className="tv-cell">
          <div className="tv-cell-h">25Δ Risk Reversal <small>put−call skew by expiry</small></div>
          <div className="tv-cell-b" ref={rrRef} />
          <div className="tv-legend">
            <span style={{ color: "rgba(244,63,94,0.9)" }}>■ Puts bid (positive skew)</span>
            <span style={{ color: "rgba(52,211,153,0.9)" }}>■ Calls bid (negative skew)</span>
          </div>
        </div>
      </div>
    </div>
    </ErrorBoundary>
  );
}
