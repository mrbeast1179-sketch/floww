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
import { approxSpot, mkScanRow, fmtUSD, fmtK, fmtIV, scoreGradeOf } from "./scanLogic";
import "./FlowseekerProBlademap.css";

const API = `${BACKEND_URL}/api/flowseeker`;
const WATCH = ["SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL"];
const NOISE_FLOOR = 5; // ignore day-volume deltas below this many contracts

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
// Rough ATM premium estimate when cvserver isn't quoting bid/ask (per-contract $).
function estPrice(strike, iv, expiry) {
  const dte = Math.max(1, dteOf(expiry));
  const ivv = iv > 1 ? iv / 100 : (iv || 0.2);
  return Math.max(0.05, strike * ivv * Math.sqrt(dte / 365) * 0.4);
}

// Conviction from the row's own attributes — log-scaled so big premium / vol-oi
// SPREAD across the range instead of all saturating at the same total. Returns
// the 0-100 score plus the 4 components (used by the gauge + radar so they agree).
function rowConviction(p) {
  const cls = String(p.classification || "regular").toLowerCase();
  const pat = cls === "sweep" ? 24 : cls === "unusual" ? 18 : cls === "block" ? 14 : 8;     // 8-24 pattern
  const prem = Number(p.premium) || 0;
  const size = Math.min(30, Math.log10(Math.max(1e4, prem) / 1e4) * 9);                      // 0-30 size (log)
  const voi = Number(p.vol_oi_ratio) || 0;
  const stat = Math.min(26, Math.log10(Math.max(1, voi) + 1) * 14);                          // 0-26 unusualness (log)
  const dte = Number(dteOf(p.expiration)) || 0;
  const urg = dte <= 1 ? 14 : dte <= 7 ? 9 : dte <= 30 ? 5 : 2;                              // 2-14 urgency
  const conv = Math.round(Math.max(20, Math.min(99, pat + size + stat + urg)));
  return { pat: +pat.toFixed(1), size: +size.toFixed(1), stat: +stat.toFixed(1), urg: +urg.toFixed(1), conv };
}

// ---------- cross-symbol scanner (scenner34 BladeMap grid) ----------
// A broader universe than the flow watchlist so the scan surfaces hot names
// (ENPH, AMD, PLTR…) the way a market-wide screen does. Used only as the
// fallback path — when the efficient backend /scan endpoint is deployed the
// component prefers that (one call, the whole market).
const SCAN_UNIVERSE = ["SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AMD", "PLTR", "ENPH", "NFLX", "AVGO", "MU", "COIN", "SMCI"];
// (scanner math — bizDTE/scanTypeOf/scanScoreOf/estimateDelta/approxSpot/mkScanRow
// and the fmt* helpers — lives in ./scanLogic.js, tested in scanLogic.test.js)

const PREFS_KEY = "fsb-scan-prefs-v1";
function loadScanPrefs() {
  try { return JSON.parse(localStorage.getItem(PREFS_KEY)) || {}; } catch { return {}; }
}

// Mark rows unseen in the previous refresh (drives the NEW flash + alerts).
function markNew(rows, prevKeysRef) {
  const keys = new Set(rows.map((r) => `${r.under}|${r.type}|${r.strike}|${r.exp}`));
  if (prevKeysRef.current) {
    for (const r of rows) r._new = !prevKeysRef.current.has(`${r.under}|${r.type}|${r.strike}|${r.exp}`);
  }
  prevKeysRef.current = keys;
  return rows;
}

// ---------- component ----------
export default function FlowseekerProBlademap({ active = true }) {
  const [tab, setTab] = useState("scanner");   // land on the cross-symbol scanner (the hero view)
  const [ticker, setTicker] = useState("SPY");
  const [signals, setSignals] = useState([]);     // merged feed, newest first
  const [selected, setSelected] = useState(null);
  const [filter, setFilter] = useState("all");
  const [subtab, setSubtab] = useState("ofi");
  const [regime, setRegime] = useState({ label: "—", cls: "chop" });
  const [clock, setClock] = useState("");
  const [plotlyReady, setPlotlyReady] = useState(!!window.Plotly);
  const [volTicker, setVolTicker] = useState("SPY");
  // cross-symbol scanner state (Scanner tab) — filters/sort/universe persist in localStorage
  const prefs = useMemo(loadScanPrefs, []);
  const [scan, setScan] = useState([]);
  const [scanAt, setScanAt] = useState("");
  const [scanSort, setScanSort] = useState(prefs.scanSort || { key: "score", dir: "desc" });
  const [scanTypeF, setScanTypeF] = useState(prefs.scanTypeF || "all");
  const [scanMinVol, setScanMinVol] = useState(prefs.scanMinVol || 0);
  const [scanMinScore, setScanMinScore] = useState(prefs.scanMinScore || 0);
  const [scanQ, setScanQ] = useState("");
  const [scanMeta, setScanMeta] = useState({ mode: null, stale: false, symbols: 0 });
  const [universe, setUniverse] = useState(prefs.universe || SCAN_UNIVERSE);
  const [universeOnly, setUniverseOnly] = useState(!!prefs.universeOnly);
  const [alertScore, setAlertScore] = useState(prefs.alertScore ?? 85);
  const prevKeysRef = useRef(null);

  useEffect(() => {
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify({ scanTypeF, scanMinVol, scanMinScore, scanSort, universe, universeOnly, alertScore }));
    } catch { /* private mode — prefs just don't persist */ }
  }, [scanTypeF, scanMinVol, scanMinScore, scanSort, universe, universeOnly, alertScore]);

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

  // ---- live flow feed from CVFORGE (unusual options activity) ----
  // cvserver serves day-aggregated chain SNAPSHOTS (not a trade stream — day_volume
  // is static between short polls), so a per-trade tape isn't possible. Instead we
  // surface the most unusual activity by volume-vs-open-interest each refresh.
  // 100% cvserver data — the same source that powers GEX/regime here.
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    const ctrl = new AbortController();
    const poll = async () => {
      try {
        const d = await getJSON(`${API}/chain/${ticker}?fields=oi,volume,iv,bid,ask,lastPrice`, ctrl.signal);
        if (cancelled) return;
        const params = d.params || [];
        const vi = (name) => { const i = params.indexOf(name); return i > 0 ? i - 1 : -1; }; // vals skip strike
        const iVol = vi("volume"), iOI = vi("openInterest"), iIV = vi("impliedVolatility");
        const iBid = vi("bid"), iAsk = vi("ask"), iLast = vi("lastPrice");
        const rows = [];
        for (const exp of (d.chain || [])) {
          for (const s of (exp.strikes || [])) {
            const strike = s[0];
            for (const [sideU, vals] of [["CALL", s[1] || []], ["PUT", s[2] || []]]) {
              const vol = Number(vals[iVol]) || 0;
              if (vol < NOISE_FLOOR * 20) continue;             // only notable activity (>=100)
              const oi = Number(vals[iOI]) || 0;
              const voi = oi > 0 ? vol / oi : vol / 100;
              if (voi < 0.4) continue;                          // skip plain-vanilla
              const iv = Number(vals[iIV]) || 0;
              const last = Number(vals[iLast]) || 0;
              const mid = last || (((Number(vals[iBid]) || 0) + (Number(vals[iAsk]) || 0)) / 2) || estPrice(strike, iv, exp.expiration);
              const premium = Math.round(vol * mid * 100);
              const dte = dteOf(exp.expiration);
              // No trade-level tape on cvserver (bid/ask/prints are null), so the old
              // voi>=1.5 sweep test flagged EVERY row "sweep" (voi runs into the 1000s
              // here). Classify by live positioning proxies instead: institutional
              // notional = block, near-term urgency = sweep, otherwise unusual.
              const cls = premium >= 5e7 ? "block" : dte <= 2 ? "sweep" : "unusual";
              const p = {
                ticker, type: sideU.toLowerCase(), classification: cls,
                strike, expiration: exp.expiration, timestamp: Date.now(),
                volume: vol, oi, vol_oi_ratio: voi, iv: iv < 1 ? iv * 100 : iv,
                premium,
              };
              const cd = rowConviction(p);
              p._conv = cd.conv;
              p._cd = cd;
              rows.push(p);
            }
          }
        }
        rows.sort((a, b) => b.vol_oi_ratio - a.vol_oi_ratio);
        setSignals(rows.slice(0, 100));
      } catch { /* transient cvserver hiccup — keep last data */ }
    };
    poll();
    const id = setInterval(poll, 15000);
    return () => { cancelled = true; ctrl.abort(); clearInterval(id); };
  }, [active, ticker]);

  // ---- cross-symbol market scan (Scanner tab, scenner34 grid) ----
  // Prefer the efficient backend /scan endpoint (ONE market-wide cvforge screen);
  // if it isn't deployed yet, fall back to looping the live per-ticker /chain over
  // a universe. Both are 100% live cvserver day-volume-vs-OI — no synthetic data.
  useEffect(() => {
    if (!active || tab !== "scanner") return;   // poll only while the Scanner tab is visible
    let cancelled = false;
    const ctrl = new AbortController();
    const run = async () => {
      // Path A: market-wide backend endpoint (columns: underlying,ticker,type,
      // strike,exp,day_volume,oi,iv,delta,spot) + per-ticker regimes map.
      try {
        const d = await getJSON(`${API}/scan?limit=300`, ctrl.signal);
        if (!cancelled && d && Array.isArray(d.rows) && d.rows.length) {
          const regimes = d.regimes || {};
          const rows = d.rows.map((r) =>
            mkScanRow(r[0], r[2], r[3], r[4], Number(r[5]) || 0, Number(r[6]) || 0,
              r[7], r[8], Number(r[9]) || null, regimes[r[0]] || null));
          setScan(markNew(rows, prevKeysRef));
          setScanMeta({ mode: "market", stale: !!d.stale, symbols: new Set(rows.map((x) => x.under)).size });
          setScanAt(new Date().toLocaleTimeString());
          return;
        }
      } catch { /* endpoint down — fall through to the chain loop */ }
      // Path B: loop the live per-ticker chain over the universe and merge.
      // Spot isn't in the chain payload — median strike ≈ spot for delta estimates.
      try {
        const results = await Promise.all(universe.map((t) =>
          getJSON(`${API}/chain/${t}?fields=oi,volume,iv,delta`, ctrl.signal)
            .then((d) => ({ t, d })).catch(() => null)));
        if (cancelled) return;
        const rows = [];
        for (const res of results) {
          if (!res || !res.d) continue;
          const params = res.d.params || [];
          const vi = (name) => { const i = params.indexOf(name); return i > 0 ? i - 1 : -1; };
          const iVol = vi("volume"), iOI = vi("openInterest"), iIV = vi("impliedVolatility"), iDelta = vi("delta");
          const allStrikes = [];
          for (const exp of (res.d.chain || [])) for (const s of (exp.strikes || [])) allStrikes.push(s[0]);
          const spotEst = approxSpot(allStrikes);
          for (const exp of (res.d.chain || [])) {
            for (const s of (exp.strikes || [])) {
              const strike = s[0];
              for (const [sideU, vals] of [["call", s[1] || []], ["put", s[2] || []]]) {
                const vol = Number(vals[iVol]) || 0;
                if (vol < 1000) continue;   // notable activity only
                rows.push(mkScanRow(res.t, sideU, strike, exp.expiration, vol,
                  Number(vals[iOI]) || 0, Number(vals[iIV]) || 0,
                  iDelta >= 0 ? Number(vals[iDelta]) : null, spotEst, null));
              }
            }
          }
        }
        rows.sort((a, b) => b.vol - a.vol);
        setScan(markNew(rows.slice(0, 300), prevKeysRef));
        setScanMeta({ mode: "fallback", stale: false, symbols: universe.length });
        setScanAt(new Date().toLocaleTimeString());
      } catch { /* keep last data on a transient hiccup */ }
    };
    run();
    const id = setInterval(run, 20000);
    return () => { cancelled = true; ctrl.abort(); clearInterval(id); };
  }, [active, tab, universe]);

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

  // scanner: filter + sort + KPI rollup
  const scanRows = useMemo(() => {
    const q = (scanQ || "").trim().toUpperCase();
    const rows = scan.filter((r) => {
      if (universeOnly && !universe.includes(r.under)) return false;
      if (scanTypeF !== "all" && r.type !== scanTypeF) return false;
      if (scanMinVol && r.vol < scanMinVol) return false;
      if (scanMinScore && r.score < scanMinScore) return false;
      if (q && !(r.under || "").toUpperCase().includes(q)) return false;
      return true;
    });
    const k = scanSort.key, dir = scanSort.dir === "desc" ? -1 : 1;
    rows.sort((a, b) => {
      let av = a[k], bv = b[k];
      if (typeof av === "string" || typeof bv === "string") return String(av).localeCompare(String(bv)) * dir;
      av = av == null ? -Infinity : av; bv = bv == null ? -Infinity : bv;
      return (av < bv ? -1 : av > bv ? 1 : 0) * dir;
    });
    return rows;
  }, [scan, scanTypeF, scanMinVol, scanMinScore, scanQ, scanSort, universe, universeOnly]);

  const scanStats = useMemo(() => {
    let notl = 0, cv = 0, pv = 0, unusual = 0; const cnt = {};
    for (const r of scanRows) {
      notl += r.notional;
      if (r.type === "call") cv += r.vol; else pv += r.vol;
      if (r.volOI >= 2) unusual++;
      cnt[r.under] = (cnt[r.under] || 0) + 1;
    }
    let top = "—", best = 0;
    for (const u of Object.keys(cnt)) if (cnt[u] > best) { best = cnt[u]; top = u; }
    const tv = cv + pv, cpct = tv > 0 ? Math.round((cv / tv) * 100) : 0;
    return { notl, cpct, tv, unusual, top, best };
  }, [scanRows]);

  const sortScan = (k) => setScanSort((s) => (s.key === k
    ? { key: k, dir: s.dir === "desc" ? "asc" : "desc" }
    : { key: k, dir: (k === "under" || k === "type" || k === "ftype") ? "asc" : "desc" }));

  const SCAN_COLS = [
    ["score", "Score", false], ["under", "Ticker", true], ["type", "C/P", true],
    ["strike", "Strike", false], ["dte", "DTE", false], ["vol", "Volume", false],
    ["oi", "OI", false], ["volOI", "Vol/OI", false], ["notional", "Notional", false],
    ["iv", "IV", false], ["ftype", "Flow", true], ["lean", "Lean", true],
  ];

  function selectSignal(p) {
    setSelected(p);
    if (p?.ticker && p.ticker !== ticker) setTicker(p.ticker);
    requestAnimationFrame(() => { drawGauge(p); drawRadar(p); });
  }

  // ---------- charts ----------
  const P = useCallback(() => window.Plotly, []);
  function drawGauge(p) {
    if (!P() || !gaugeRef.current || !p) return;
    const c = p._conv != null ? p._conv : (p._cd ? p._cd.conv : 50);
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
    const d = p._cd || { stat: 0, pat: 0, size: 0, urg: 0 };
    const cats = ["Unusualness", "Pattern", "Size", "Urgency"];
    P().react(radarRef.current, [{
      type: "scatterpolar", r: [d.stat, d.pat, d.size, d.urg, d.stat],
      theta: cats.concat([cats[0]]), fill: "toself", fillcolor: "rgba(41,197,224,0.18)",
      line: { color: PL.blue, width: 2 }, marker: { color: PL.blue, size: 4 },
    }], { paper_bgcolor: PL.paper, polar: { bgcolor: "rgba(0,0,0,0)",
        radialaxis: { range: [0, 30], tickfont: { color: PL.muted, size: 8 }, gridcolor: PL.grid, linecolor: PL.axis },
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
  // Focused on institutional smart order flow — dropped Vol Surface (synthetic) + Academy (education).
  const TABS = [["flow", "Smart Order Flow"], ["gamma", "Dealer Positioning"], ["scanner", "Scanner"]];
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
                    <th>Ticker</th><th>Type</th><th>Side</th><th className="num">Strike</th>
                    <th>DTE</th><th className="num">Day $</th><th className="num">V/OI</th><th className="num">Conv</th>
                  </tr></thead>
                  <tbody>
                    {filtered.length === 0 && <tr><td colSpan={8} className="fsb-muted" style={{ padding: 14, lineHeight: 1.7 }}>Loading unusual options activity from <b style={{ color: "var(--fsb-blue)" }}>cvforge</b> (ranked by volume-vs-open-interest)…</td></tr>}
                    {filtered.slice(0, 80).map((p, i) => {
                      const conv = p._conv;
                      return (
                        <tr key={`${p.ticker}-${p.timestamp}-${i}`} className={selected === p ? "selected" : ""}
                            tabIndex={0} onClick={() => selectSignal(p)}
                            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectSignal(p); } }}>
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
                      <li>Classification: {String(selected.classification || "unusual")} — volume/OI positioning proxy (cvserver has no trade-level tape)</li>
                      <li>Vol/OI ratio: {Number(selected.vol_oi_ratio || 0).toFixed(1)}× · est. notional {fmtMoney(selected.premium)}</li>
                      {selected._cd && (
                        <li>Conviction {selected._conv}/99 = pattern {selected._cd.pat} + size {selected._cd.size} + unusualness {selected._cd.stat} + urgency {selected._cd.urg}</li>
                      )}
                    </ul>
                    <div className="fsb-muted fsb-small" style={{ marginTop: 6 }}>Regime: {regime.label}. VPIN toxicity &amp; Kyle-λ price-impact need a trade-level order-flow feed (not available on cvserver) — they populate when a print feed is connected.</div>
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

        {/* SCANNER VIEW — cross-symbol BladeMap scanner (scenner34 grid) */}
        <div className={`fsb-view${tab === "scanner" ? " active" : ""}`} style={{ gridTemplateColumns: "1fr" }}>
          <div className="fsb-scanwrap">
            <div className="fsb-scanbar">
              {[
                ["Contracts", `${scanRows.length} / ${scan.length}`, "b"],
                ["Notional Σ", fmtUSD(scanStats.notl), ""],
                ["Call/Put Vol", scanStats.tv > 0 ? `${scanStats.cpct}% / ${100 - scanStats.cpct}%` : "—", scanStats.cpct >= 50 ? "g" : "r"],
                ["Unusual (≥2×)", String(scanStats.unusual), "y"],
                ["Top Name", scanStats.top + (scanStats.best ? ` ·${scanStats.best}` : ""), ""],
                ["Updated", scanAt || "—", ""],
              ].map(([l, v, c]) => (
                <div key={l} className="fsb-skpi"><div className="fsb-skl">{l}</div><div className={`fsb-skv ${c}`}>{v}</div></div>
              ))}
            </div>
            <div className="fsb-scanctrl">
              <select value={scanTypeF} onChange={(e) => setScanTypeF(e.target.value)}>
                <option value="all">All Types</option><option value="call">Calls</option><option value="put">Puts</option>
              </select>
              <input type="number" min="0" step="1000" placeholder="Min Vol" value={scanMinVol || ""} onChange={(e) => setScanMinVol(parseFloat(e.target.value) || 0)} />
              <input type="number" min="0" max="100" step="5" placeholder="Min Score" value={scanMinScore || ""} onChange={(e) => setScanMinScore(parseFloat(e.target.value) || 0)} />
              <input placeholder="Ticker…" value={scanQ} onChange={(e) => setScanQ((e.target.value || "").toUpperCase())} />
              <span className="fsb-scannote">Live cross-symbol flow · cvforge day-volume vs OI. No per-trade tape on this feed — Flow-type = volume-magnitude class; Lean = contract-type bias.</span>
            </div>
            <div className="fsb-scantable">
              {scan.length === 0 ? (
                <div className="fsb-muted" style={{ padding: 16 }}>Scanning market flow across {SCAN_UNIVERSE.length} symbols…</div>
              ) : scanRows.length === 0 ? (
                <div className="fsb-muted" style={{ padding: 16 }}>No contracts pass these filters.</div>
              ) : (
                <table className="fsb-stab">
                  <thead><tr>
                    {SCAN_COLS.map(([k, t, l]) => (
                      <th key={k} className={`${l ? "l" : ""}${k === scanSort.key ? " on" : ""}`} onClick={() => sortScan(k)}>
                        {t}{k === scanSort.key ? (scanSort.dir === "desc" ? " ▾" : " ▴") : ""}
                      </th>
                    ))}
                  </tr></thead>
                  <tbody>
                    {scanRows.slice(0, 200).map((r, i) => {
                      const isCall = r.type === "call";
                      const otm = r.delta == null ? "" : (Math.abs(r.delta) < 0.45 ? "OTM" : "ITM");
                      return (
                        <tr key={`${r.under}-${r.strike}-${r.type}-${r.exp}-${i}`}
                            className={r.under === ticker ? "sel" : ""}
                            onClick={() => { setTicker(r.under); setTab("flow"); }}>
                          <td><span className={`fsb-sc ${scoreGradeOf(r.score)}`}>{r.score}</span></td>
                          <td className="l"><span className="tk">{r.under}</span> <span className="fsb-sub">{(r.exp || "").slice(5)}</span></td>
                          <td className={`l ${isCall ? "fsb-tcall" : "fsb-tput"}`}>{isCall ? "CALL" : "PUT"}</td>
                          <td>{r.strike % 1 === 0 ? r.strike.toFixed(0) : r.strike.toFixed(1)}</td>
                          <td>{r.dte == null ? "—" : `${r.dte}d`}</td>
                          <td>{fmtK(r.vol)}</td>
                          <td>{fmtK(r.oi)}</td>
                          <td>{r.volOI >= 99 ? "99+" : `${r.volOI.toFixed(1)}x`}</td>
                          <td>{fmtUSD(r.notional)}</td>
                          <td>{fmtIV(r.iv)}</td>
                          <td className="l"><span className={`fsb-flt ${r.ftype}`}>{r.ftype.toUpperCase()}</span></td>
                          <td className="l"><span className={`fsb-lean ${isCall ? "bull" : "bear"}`}>{isCall ? "▲ BULL" : "▼ BEAR"}</span>{otm ? <span className="fsb-sub"> {otm}</span> : null}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
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
        <span>Live cvforge data · GEX/OFI/regime from the decoder backend. VPIN/Kyle-λ need a trade-level feed (n/a on cvserver). Vol surface simulated.</span>
        <span>FlowSeeker Pro · Blademap layout</span>
      </div>
    </div>
  );
}
