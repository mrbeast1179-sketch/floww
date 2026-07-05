// Pure scanner math for FlowSeeker Pro — no React, no fetch. Tested in scanLogic.test.js.

export const fmtUSD = (v) => { const n = Math.abs(Number(v) || 0); if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`; if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`; if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}k`; return `$${Math.round(n)}`; };
export const fmtK = (v) => { const n = Number(v) || 0; if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`; if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`; if (n >= 1e3) return `${(n / 1e3).toFixed(0)}k`; return String(Math.round(n)); };
// IV unit heuristic: decimal IVs legitimately exceed 1 on hot names (1.5 =
// 150%), while pct-style feeds send 20–200 — treat < 3 as decimal, ≥ 3 as pct.
const normIV = (v) => (v == null ? null : (Number(v) >= 3 ? Number(v) / 100 : Number(v)));
export const fmtIV = (v) => (v == null ? "—" : `${(normIV(v) * 100).toFixed(1)}%`);

// Trading-day DTE — weekdays strictly after today (UTC date) through the
// expiry date. Date-boundary based: a Monday expiry reads 1 all weekend and a
// contract expiring today reads 0 regardless of time of day.
export function bizDTE(expStr) {
  if (!expStr) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(expStr));
  if (!m) return null;
  const end = Date.UTC(+m[1], +m[2] - 1, +m[3]);
  const t0 = new Date();
  const today = Date.UTC(t0.getUTCFullYear(), t0.getUTCMonth(), t0.getUTCDate());
  if (end <= today) return 0;
  let d = 0;
  const cap = Math.min(end, today + 800 * 86400000);
  for (let t = today + 86400000; t <= cap; t += 86400000) {
    const wd = new Date(t).getUTCDay();
    if (wd !== 0 && wd !== 6) d++;
  }
  return d;
}

// Flow-type by volume magnitude + vol/OI — the only signals a print-less feed supports.
export function scanTypeOf(r) {
  if (r.vol >= 25000) return "sweep";
  if (r.vol >= 8000) return "block";
  if (r.volOI >= 2) return "unusual";
  if (r.volOI >= 1) return "split";
  return "regular";
}

export const scoreGradeOf = (s) => (s >= 80 ? "crit" : s >= 65 ? "high" : s >= 50 ? "elev" : "norm");

// |delta| estimate from moneyness when the feed omits delta. Logistic squash of
// signed distance-to-spot in ~8%-of-spot units — labeled as an ESTIMATE in the UI.
export function estimateDelta(strike, spot, type) {
  if (!spot || !strike) return null;
  const isCall = String(type || "").toLowerCase().startsWith("c");
  const x = (spot - strike) / (spot * 0.08);
  const d = 1 / (1 + Math.exp(-1.7 * (isCall ? x : -x)));
  const abs = Math.max(0.02, Math.min(0.98, d));
  return isCall ? abs : -abs;
}

// Median strike ≈ spot (chains are built around the money). Fallback-path only.
export function approxSpot(strikes) {
  if (!strikes || !strikes.length) return null;
  const s = [...strikes].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

// Flow Score 0-100 — positioning freshness, size, notional, urgency, OTM lean,
// plus a small gamma-regime nudge when the ticker's regime is known:
// negative gamma amplifies short-dated aggressive flow (dealers chase moves);
// positive gamma pins — fresh positioning (vol/OI ≥ 2) matters more.
export function scanScoreOf(r, regime = null) {
  const dl = Math.abs(r.delta || 0);
  const pos = Math.min(r.volOI / 3, 1);
  const size = Math.min(Math.log(Math.max(r.vol, 1)) / Math.log(50000), 1);
  const notl = Math.min(Math.log(Math.max(r.notional, 1)) / Math.log(50e6), 1);
  const urg = r.dte == null ? 0.3 : (r.dte <= 2 ? 1 : r.dte <= 7 ? 0.7 : r.dte <= 30 ? 0.4 : 0.15);
  const otm = r.delta == null ? 0.3 : Math.max(0, Math.min((0.5 - dl) / 0.4, 1));
  let s = (pos * 0.34 + size * 0.24 + notl * 0.18 + urg * 0.14 + otm * 0.10) * 100;
  let nudge = 0;
  if (regime === "negative" && r.dte != null && r.dte <= 7) nudge = 5;
  else if (regime === "positive" && r.volOI >= 2) nudge = 3;
  s += nudge;
  r._parts = { pos: +(pos * 34).toFixed(1), size: +(size * 24).toFixed(1), notl: +(notl * 18).toFixed(1), urg: +(urg * 14).toFixed(1), otm: +(otm * 10).toFixed(1), nudge };
  return Math.max(0, Math.min(100, Math.round(s)));
}

// Premium spent estimate (institutions read premium, not contract notional).
// BS-lite ATM price ≈ strike·iv·√(dte/365)·0.4, discounted toward deep OTM by
// |delta| when known, floored at $0.05/contract. Always labeled ~ in the UI —
// there is no quote feed on this data.
export function estPremium(r) {
  const iv = normIV(r.iv);
  if (!iv || !r.strike) return null;
  const dte = Math.max(1, r.dte ?? 5);
  let px = r.strike * iv * Math.sqrt(dte / 365) * 0.4;
  if (r.delta != null) px *= Math.min(1, 0.3 + Math.abs(r.delta) * 1.4);
  px = Math.max(0.05, px);
  return (r.vol || 0) * 100 * px;
}

// Alert engine — pure. Evaluates NEW rows against the enabled rules; a row
// fires at most one alert (first matching rule wins, in priority order).
export function evalAlerts(rows, opts = {}) {
  const {
    minScore = 85,
    whalePremium = 10e6,
    zeroDteScore = 70,
    enabled = { score: true, whale: true, zerodte: true },
  } = opts;
  const out = [];
  for (const r of rows || []) {
    if (!r._new) continue;
    let rule = null;
    if (enabled.score && r.score >= minScore) rule = "SCORE";
    else if (enabled.whale && r.premium != null && r.premium >= whalePremium) rule = "WHALE";
    else if (enabled.zerodte && r.dte != null && r.dte <= 1 && r.score >= zeroDteScore) rule = "0DTE";
    if (!rule) continue;
    out.push({
      key: `${r.under}|${r.type}|${r.strike}|${r.exp}`,
      rule, under: r.under, type: r.type, strike: r.strike, exp: r.exp,
      score: r.score, premium: r.premium, notional: r.notional,
      volOI: r.volOI, dte: r.dte,
    });
  }
  return out;
}

// Institutional flow archetype from real fields only (no tape). First match
// wins: WHALE (premium size), LOTTO (deep-OTM short-dated), HEDGE (mid-delta
// long-dated puts — protective duration), FRESH (volume ≥ 3× open interest,
// new positioning). null when nothing distinctive.
export function archetypeOf(r) {
  if (r.premium != null && r.premium >= 10e6) return "WHALE";
  const dl = r.delta == null ? null : Math.abs(r.delta);
  if (dl != null && dl <= 0.15 && r.dte != null && r.dte <= 2) return "LOTTO";
  if (r.type === "put" && dl != null && dl >= 0.25 && dl <= 0.6 && r.dte != null && r.dte >= 30) return "HEDGE";
  if ((r.volOI || 0) >= 3) return "FRESH";
  return null;
}

// Per-ticker premium concentration — where the money is. Sorted by total
// estimated premium desc, top-N, with call/put split for a skew read.
export function tickerRollup(rows, top = 8) {
  const m = new Map();
  for (const r of rows || []) {
    const e = m.get(r.under) || {
      under: r.under, prem: 0, callPrem: 0, putPrem: 0,
      count: 0, maxScore: 0, regime: null,
    };
    const p = r.premium || 0;
    e.prem += p;
    if (r.type === "call") e.callPrem += p; else e.putPrem += p;
    e.count++;
    if ((r.score || 0) > e.maxScore) e.maxScore = r.score;
    if (r.regime) e.regime = r.regime;
    m.set(r.under, e);
  }
  const arr = [...m.values()].sort((a, b) => b.prem - a.prem).slice(0, top);
  for (const e of arr) e.callPct = e.prem > 0 ? Math.round((e.callPrem / e.prem) * 100) : 50;
  return arr;
}

// Build one scanner row. spot enables delta estimation when the feed omits
// delta; regime (from the backend heatmap cache) feeds the score nudge.
export function mkScanRow(under, type, strike, exp, vol, oi, iv, delta, spot = null, regime = null) {
  const stk = Number(strike) || 0;
  const volOI = oi > 0 ? vol / oi : (vol > 0 ? 99 : 0);
  const given = delta == null ? null : Number(delta);
  const est = given == null ? estimateDelta(stk, spot, type) : null;
  const r = {
    under, type: String(type || "").toLowerCase().startsWith("c") ? "call" : "put",
    strike: stk, exp, vol, oi, iv,
    delta: given != null ? given : est,
    deltaEst: given == null && est != null,
    spot, regime,
    volOI, notional: vol * 100 * stk, dte: bizDTE(exp),
  };
  r.premium = estPremium(r);
  r.score = scanScoreOf(r, regime); r.ftype = scanTypeOf(r);
  r.arch = archetypeOf(r);
  return r;
}
