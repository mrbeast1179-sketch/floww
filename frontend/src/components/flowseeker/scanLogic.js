// Pure scanner math for FlowSeeker Pro — no React, no fetch. Tested in scanLogic.test.js.

export const fmtUSD = (v) => { const n = Math.abs(Number(v) || 0); if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`; if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`; if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}k`; return `$${Math.round(n)}`; };
export const fmtK = (v) => { const n = Number(v) || 0; if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`; if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`; if (n >= 1e3) return `${(n / 1e3).toFixed(0)}k`; return String(Math.round(n)); };
// Local trading-day key (America/Eastern for a Philly desk) — first-seen and
// the alert tape reset at local midnight so each session starts clean.
export function sessionDay(now = Date.now()) {
  const d = new Date(now);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// Wall-clock formatter. withSeconds for the alert tape (precise arrivals),
// HH:MM for the scanner's Seen column.
export function fmtClock(ms, withSeconds = false) {
  if (ms == null) return "—";
  return new Date(ms).toLocaleTimeString([], withSeconds
    ? { hour: "2-digit", minute: "2-digit", second: "2-digit" }
    : { hour: "2-digit", minute: "2-digit" });
}

// Compact elapsed age: 45s / 12m / 3h.
export function fmtAge(ms, now = Date.now()) {
  if (ms == null) return "—";
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m`;
  return `${Math.round(m / 60)}h`;
}

// Annotate each row with the timestamp its contract was FIRST seen this
// session (answers "what came in when"). seen = { day, map:{key:ms} } persists
// in the caller; the map resets when the local day rolls. Returns { rows, seen }.
export function annotateFirstSeen(rows, seen, now = Date.now()) {
  const day = sessionDay(now);
  const map = (seen && seen.day === day && seen.map) ? { ...seen.map } : {};
  for (const r of rows || []) {
    const key = `${r.under}|${r.type}|${r.strike}|${r.exp}`;
    if (map[key] == null) map[key] = now;
    r.firstSeen = map[key];
  }
  return { rows: rows || [], seen: { day, map } };
}

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
  // Informed-positioning band: 7-90 DTE + vol≥3×OI + ≥$25k premium is where
  // directional bets live (shorter = gamma noise, longer = hedges) — the
  // standard UOA filter conjunction; cf. Pan & Poteshman (RFS 2006) on option
  // volume carrying multi-day directional information.
  let band = 0;
  if (r.dte != null && r.dte >= 7 && r.dte <= 90 && (r.volOI || 0) >= 3 && (r.premium || 0) >= 25e3) band = 4;
  s += band;
  r._parts = { pos: +(pos * 34).toFixed(1), size: +(size * 24).toFixed(1), notl: +(notl * 18).toFixed(1), urg: +(urg * 14).toFixed(1), otm: +(otm * 10).toFixed(1), nudge, band };
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
// opts.allow: optional ticker allowlist (array) — scopes alerting to the
// user's universe so market-wide scans don't ping for 700 random symbols.
export function evalAlerts(rows, opts = {}) {
  const {
    minScore = 85,
    whalePremium = 10e6,
    zeroDteScore = 70,
    enabled = { score: true, whale: true, zerodte: true },
    allow = null,
  } = opts;
  const allowSet = allow && allow.length ? new Set(allow) : null;
  const out = [];
  for (const r of rows || []) {
    if (!r._new) continue;
    if (allowSet && !allowSet.has(r.under)) continue;
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

// σ-spike: today's cumulative options volume vs the ticker's baseline of
// prior days' end-of-day volumes (OptionScannerTWS-style anomaly detection —
// their signal was 4-5σ spikes preceding underlying moves). Needs ≥2 days of
// baseline history and a nonzero std; the backend accumulates the baselines.
export function volSigma(totalVol, baseline) {
  if (totalVol == null || !baseline || !baseline.std || (baseline.days || 0) < 2) return null;
  return +(((totalVol - baseline.avg) / baseline.std).toFixed(1));
}

// Next-day open-interest change for one contract — the print-less feed's only
// "was this opening flow?" confirmation. Returns null when there's no prior-day
// record (nothing to compare) or prior OI was 0. { abs, pct } otherwise:
// pct is fractional (0.42 = +42%). A FRESH contract whose OI rose held as new
// positioning; one whose OI fell was intraday churn.
export function oiChange(oi, prevOI) {
  if (prevOI == null || prevOI <= 0 || oi == null) return null;
  const abs = oi - prevOI;
  return { abs, pct: abs / prevOI };
}

// "While you were away" digest — pure. Everything that happened since sinceMs:
// alert counts by rule from the persisted tape, plus the top new contracts
// (first seen after sinceMs) by score. Null when the gap is too short to
// matter or there is nothing to report.
export function awaySummary(alertLog, rows, sinceMs, now = Date.now(), minGapMs = 30 * 60e3) {
  if (sinceMs == null || now - sinceMs < minGapMs) return null;
  const counts = {};
  let nAlerts = 0;
  for (const a of alertLog || []) {
    if (a.t > sinceMs) { counts[a.rule] = (counts[a.rule] || 0) + 1; nAlerts++; }
  }
  const topNew = (rows || [])
    .filter((r) => r.firstSeen != null && r.firstSeen > sinceMs)
    .sort((a, b) => (b.score || 0) - (a.score || 0))
    .slice(0, 3);
  if (!nAlerts && !topNew.length) return null;
  return { gapMs: now - sinceMs, counts, nAlerts, topNew };
}

// CSV for the current scanner view (premium is an estimate — header says so).
// Pure string builder so the export is Jest-testable.
const CSV_COLS = [
  ["firstSeen", "seen", (v) => (v == null ? "" : new Date(v).toISOString())],
  ["score", "score"], ["under", "ticker"], ["type", "type"], ["strike", "strike"],
  ["exp", "expiry"], ["dte", "dte"], ["vol", "volume"], ["oi", "oi"],
  ["oiChgPct", "oi_chg_pct", (v) => (v == null ? "" : v.toFixed(4))],
  ["volOI", "vol_oi"], ["premium", "premium_est"], ["notional", "notional"],
  ["iv", "iv"], ["ftype", "flow"], ["arch", "archetype"], ["lean", "lean"], ["regime", "regime"],
];
const csvCell = (v) => {
  const s = v == null ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};
export function scanRowsToCSV(rows) {
  const head = CSV_COLS.map(([, label]) => label).join(",");
  const body = (rows || []).map((r) =>
    CSV_COLS.map(([key, , fmt]) => csvCell(fmt ? fmt(r[key]) : r[key])).join(","));
  return [head, ...body].join("\n");
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
  // $25k premium floor cuts retail noise (a few cheap OTM contracts spike
  // vol/OI without being a signal); when no estimate exists, don't assume small.
  if ((r.volOI || 0) >= 3 && (r.premium == null || r.premium >= 25e3)) return "FRESH";
  return null;
}

// Per-ticker premium concentration — where the money is. Sorted by total
// estimated premium desc, top-N, with call/put split for a skew read.
export function tickerRollup(rows, top = 8) {
  const m = new Map();
  for (const r of rows || []) {
    const e = m.get(r.under) || {
      under: r.under, prem: 0, callPrem: 0, putPrem: 0,
      callVol: 0, putVol: 0, count: 0, maxScore: 0, regime: null,
    };
    const p = r.premium || 0;
    e.prem += p;
    if (r.type === "call") { e.callPrem += p; e.callVol += r.vol || 0; }
    else { e.putPrem += p; e.putVol += r.vol || 0; }
    e.count++;
    if ((r.score || 0) > e.maxScore) e.maxScore = r.score;
    if (r.regime) e.regime = r.regime;
    m.set(r.under, e);
  }
  const arr = [...m.values()].sort((a, b) => b.prem - a.prem).slice(0, top);
  for (const e of arr) {
    e.callPct = e.prem > 0 ? Math.round((e.callPrem / e.prem) * 100) : 50;
    // Volume-based put/call ratio — Pan & Poteshman (RFS 2006): low P/C
    // predicts outperformance (~40bps next day, >1% next week in their data).
    e.pcr = e.callVol > 0 ? +(e.putVol / e.callVol).toFixed(2) : null;
  }
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
