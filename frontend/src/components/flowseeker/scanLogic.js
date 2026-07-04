// Pure scanner math for FlowSeeker Pro — no React, no fetch. Tested in scanLogic.test.js.

export const fmtUSD = (v) => { const n = Math.abs(Number(v) || 0); if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`; if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`; if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}k`; return `$${Math.round(n)}`; };
export const fmtK = (v) => { const n = Number(v) || 0; if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`; if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`; if (n >= 1e3) return `${(n / 1e3).toFixed(0)}k`; return String(Math.round(n)); };
export const fmtIV = (v) => (v == null ? "—" : `${(Number(v) < 1 ? Number(v) * 100 : Number(v)).toFixed(1)}%`);

// Trading-day DTE — calendar days minus weekends.
export function bizDTE(expStr) {
  if (!expStr) return null;
  const end = new Date(`${expStr}T16:00:00Z`), now = Date.now();
  if (end <= now) return 0;
  const full = Math.min(Math.floor((end - now) / 86400000), 800); let d = 0; const cur = new Date(now);
  for (let i = 0; i < full; i++) { cur.setUTCDate(cur.getUTCDate() + 1); const wd = cur.getUTCDay(); if (wd !== 0 && wd !== 6) d++; }
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
  r.score = scanScoreOf(r, regime); r.ftype = scanTypeOf(r);
  return r;
}
