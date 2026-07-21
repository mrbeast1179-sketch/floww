// convictionUi.js — Pure formatters & detectors for Conviction v2 chips.
//
// Mirrors the backend contract (backend/services/flow_alerts.py +
// backend/services/flow_quality.py); the scanner-tab UI surfaces every
// lever + the prime bracket without recomputing the math — it just
// renders what the engine wrote.
//
// Five conviction levers:
//   spread_leg   → strategy demotion (tier capped BRONZE, no direction)
//   cw_spread    → Cremers-Weinbaum IV-gap confirms bias
//   cluster      → ≥3 same-bias laddered contracts in this snapshot
//   sigma_ticker → BH-FDR surviving σ spike (already filtered server-side)
//   prime        → premium ≥ $250k AND vol/OI ≥ 5 (the 55-62% bracket)
// Tiers: GOLD ≥ 3 factors, SILVER 2, BRONZE 1 (spread-leg capped BRONZE).

// ── thresholds (mirror backend/services/flow_quality.py) ────────────────
export const PRIME_PREMIUM = 250_000;
export const PRIME_VOL_OI = 5.0;
export const CW_CONFIRM = 0.015;

// ── formatters ────────────────────────────────────────────────────────
export function fmtCW(v) {
  if (v == null || Number.isNaN(v)) return "—";
  // Backend stores the IV-gap in raw decimal (e.g. 0.04 = 4 vol points).
  // Multiply by 100 so a 0.04 reads "4.0σ" style — the units a desk speaks.
  const pct = v * 100;
  if (pct === 0) return "0.00%";
  const sign = v > 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

export function fmtMovePct(v) {
  if (v == null || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

// ── tier badge ─────────────────────────────────────────────────────────
// tier ∈ {"GOLD","SILVER","BRONZE"} → {label, className, rank}.
// Spread-leg alerts always return BRONZE — the engine forces it, the UI
// just reflects the same so a downstream filter (`side === "STRATEGY"`)
// and a chip colour agree.
export const TIER_RANK = { GOLD: 0, SILVER: 1, BRONZE: 2 };

export function tierBadge(tier, side) {
  const t = String(tier || "").toUpperCase();
  if (t === "GOLD")   return { label: "GOLD",   className: "fsp-tier fsp-tier-gold",   rank: 0 };
  if (t === "SILVER") return { label: "SILVER", className: "fsp-tier fsp-tier-silver", rank: 1 };
  // Spread-leg / directionless rows always BRONZE …
  if (t === "BRONZE" || !t) {
    const isStrategy = String(side || "").toUpperCase() === "STRATEGY";
    return isStrategy
      ? { label: "STRATEGY", className: "fsp-tier fsp-tier-strategy", rank: 2 }
      : { label: "BRONZE",   className: "fsp-tier fsp-tier-bronze", rank: 2 };
  }
  return { label: t, className: "fsp-tier fsp-tier-bronze", rank: 2 };
}

// ── chip detectors (row-level, derived from server-stamped fields) ─────

// spread_leg: server flips side to STRATEGY + tier to BRONZE for paired
// strategy legs. The visual cue lives on the tier pill itself
// (tierBadge("BRONZE","STRATEGY") → STRATEGY label/class), so we do NOT
// expose a spreadChip helper here — adding one would double-label the same
// fact in two widgets. Backend factors: see services/flow_alerts._finalize.

// cw_confirm: a positive cw_spread that CONFIRMS a bullish bias, or a
// negative one that confirms bearish — the affirmative IVF-spread signal.
// Reuses the backend 0.015 threshold so the chip stays in sync with the
// factor scoring that lit up the tier.
export function cwConfirmChip(alert) {
  if (!alert) return null;
  const cw = alert.cw_spread;
  const bias = String(alert.bias || "").toUpperCase();
  if (cw == null || !bias) return null;
  if (bias === "BULLISH" && cw >= CW_CONFIRM) {
    return { label: `CW +${(cw * 100).toFixed(1)}% confirms`, className: "fsp-chip fsp-chip-cw-bull" };
  }
  if (bias === "BEARISH" && cw <= -CW_CONFIRM) {
    return { label: `CW ${(cw * 100).toFixed(1)}% confirms`, className: "fsp-chip fsp-chip-cw-bear" };
  }
  return null;
}

// cluster: from v2.1 the backend stamps `cluster: bool` on every persisted
// alert (see backend/services/flow_alerts._mk_alert → cluster field from
// _common_factors(factors)["cluster"]). The chip only fires when the
// server-stamped bool is true, so we can render this without a tier proxy.
export function clusterChip(alert) {
  if (!alert) return null;
  if (alert.cluster !== true) return null;
  return { label: "CLUSTER", className: "fsp-chip fsp-chip-cluster" };
}

// prime: the empirically measured $250k + volOI>=5 bracket; badge as PRIME.
export function primeChip(alert) {
  if (!isPrime(alert)) return null;
  return { label: "PRIME",   className: "fsp-chip fsp-chip-prime" };
}

// Sigma survivor chip: an FDG-surviving σ alert gets a clear "σ X.X" so
// the desk sees the spike magnitude right next to the tier pill.
export function sigmaChip(sigma) {
  if (sigma == null || Number.isNaN(sigma)) return null;
  return {
    label: `σ ${sigma >= 0 ? "+" : ""}${sigma.toFixed(1)}`,
    className: "fsp-chip fsp-chip-sigma",
  };
}

// Backend uses _common_factors + tier thresholds; the chip fires for any
// premium ≥ brim with vol/OI ≥ 5. Mirrors services/flow_quality.is_prime.
export function isPrime(alert) {
  if (!alert) return false;
  const prem = Number(alert.premium || 0);
  const voi = Number(alert.vol_oi || 0);
  return prem >= PRIME_PREMIUM && voi >= PRIME_VOL_OI;
}

// ── quality strip ─────────────────────────────────────────────────────
// The /alerts/quality endpoint returns rows of {rule, tier, n, n_measured,
// hit_rate, avg_move_pct}. The UI aggregates by tier (the desk cares about
// GOLD vs SILVER vs BRONZE) and divides into "measured" (n_measured>0) and
// "thin" (n_measured==0) buckets so an underpowered tier doesn't read like
// 0% hit-rate.
//
// v2.2: accepts EITHER the legacy `{ quality: [...], days: N }` shape OR
// the batched `{ quality_windows: {7: [...], 14: [...], 30: [...]}, days: [7,14,30] }`
// response from /alerts/quality?days=7,14,30. For the strip itself we
// project the LONGEST window (a desk's macro read); trend sparklines
// consume every window via qualityTrendForTier.
//
// v2.3: each tier's cell carries a Wilson 90% binomial CI on the AGGREGATE
// hit count so a desk sees "65% [49%, 79%]" instead of "65%" — the point
// estimate alone is meaningless on n=4 samples (a single new alert swings
// it 25pp). Wilson (1927, JASA 22:209) is the canonical small-sample
// adjustment; the z²/(4n²) term keeps bounds inside [0,1] even at
// x=0 or x=n (no special cases needed).
export function summarizeQuality(payload, daysHint = null) {
  const isBatched = payload && typeof payload === "object" && payload.quality_windows;
  const flatRows = isBatched ? pickStripRows(payload.quality_windows) : (payload?.quality || []);
  const byTier = { GOLD: null, SILVER: null, BRONZE: null };
  // v2.4 — per-(rule, tier) accumulator alongside byTier. After byTier
  // rolls hits across all rules in a tier (for the headline hit_rate +
  // Wilson CI), this preserves the per-rule picture so bestRuleForTier can
  // rank rules within the same tier by sample-size-weighted hit count.
  const byRuleAndTier = {};
  for (const row of flatRows || []) {
    const t = String(row.tier || "").toUpperCase();
    if (!(t in byTier)) continue;
    // v2.3 — wins starts as `null`. We only set it when a row carries the
    // backend column. Initializing to 0 would shadow legacy payloads (no
    // `wins` field) as zero-wins and silently lock the Wilson fallback path
    // off — the classic "0 != null" nullability trap. The winsSrc selection
    // null-checks rather than truthy-checks for the same reason.
    const prev = byTier[t] || { tier: t, n: 0, n_measured: 0, hits: 0, wins: null, sum_move: 0, n_move: 0 };
    prev.n += Number(row.n) || 0;
    prev.n_measured += Number(row.n_measured) || 0;
    const hr = Number(row.hit_rate);
    if (!Number.isNaN(hr) && (row.n_measured || 0) > 0) {
      prev.hits += hr * (row.n_measured || 0);
    }
    if (row.wins != null) {
      prev.wins = (prev.wins ?? 0) + Number(row.wins);
    }
    const mv = Number(row.avg_move_pct);
    if (!Number.isNaN(mv) && mv != null) {
      prev.sum_move += mv * (row.n_measured || 0);
      prev.n_move += row.n_measured || 0;
    }
    byTier[t] = prev;
    // Per-(rule, tier) rollup. Key uses underscore to avoid colliding
    // with any single-rule tier names that might contain "|".
    const r = String(row.rule || "").toUpperCase();
    if (!r) continue;
    const rtKey = `${r}_${t}`;
    const rPrev = byRuleAndTier[rtKey] || {
      rule: r, tier: t, n: 0, n_measured: 0, hits: 0, wins: null,
    };
    rPrev.n += Number(row.n) || 0;
    rPrev.n_measured += Number(row.n_measured) || 0;
    if (!Number.isNaN(hr) && (row.n_measured || 0) > 0) {
      rPrev.hits += hr * (row.n_measured || 0);
    }
    if (row.wins != null) {
      rPrev.wins = (rPrev.wins ?? 0) + Number(row.wins);
    }
    byRuleAndTier[rtKey] = rPrev;
  }
  const days = isBatched
    ? (Array.isArray(payload.days) ? payload.days[payload.days.length - 1] : (daysHint || 30))
    : (payload?.days ?? daysHint ?? 30);
  const windows = isBatched && Array.isArray(payload.days) ? payload.days : [days];
  const out = [];
  for (const t of ["GOLD", "SILVER", "BRONZE"]) {
    const x = byTier[t];
    if (!x || !x.n) continue;
    const hitRate = x.n_measured > 0 ? x.hits / x.n_measured : null;
    const avgMove = x.n_move > 0 ? x.sum_move / x.n_move : null;
    // v2.3 — Wilson 90% CI on the aggregate integer hits. When the backend's
    // alert_quality SQL emits `wins` (bit-exact INT) we use it directly; we
    // fall back to Math.round(x.hits) for legacy payloads without the
    // column. The Math.round fallback can drift by ±0.5 on average values
    // that don't divide cleanly — acceptable for forward-compat, inferior
    // to the bit-exact path. The exact counts feed the rendered point
    // estimate and the bracket via the same number so the two never
    // disagree on the same payload.
    const winsSrc = x.wins != null ? x.wins : (x.n_measured > 0 ? Math.round(x.hits) : 0);
    const wilson = wilsonBounds(winsSrc, x.n_measured, WILSON_Z);
    out.push({
      tier: t,
      n: x.n,
      n_measured: x.n_measured,
      hits: winsSrc,
      hit_rate: hitRate,                 // null → "thin"
      hit_lo: wilson.lo,                 // null when n_measured=0
      hit_hi: wilson.hi,
      avg_move_pct: avgMove,
      thin: x.n_measured === 0,
      best_rule: bestRuleForTier(t, byRuleAndTier),  // v2.4 extension
    });
  }
  return { tiers: out, days, windows, hasData: out.length > 0 };
}

// ── Wilson 90% binomial confidence interval (v2.3) ──────────────────
// Single layer that owns the math + confidence level — a desk can tune by
// exporting a different z constant. Reference: Wilson (1927) "Probable
// Inference, the Law of Succession, and Statistical Inference", JASA.
//
// Formula (canonical):
//   p̂ = x/n
//   denom = 1 + z²/n
//   center = p̂ + z²/(2n)
//   spread = z √( p̂(1-p̂)/n + z²/4n² )
//   lo = (center - spread) / denom
//   hi = (center + spread) / denom
//
// Returns {lo: null, hi: null} when n=0 so the UI renders "—" instead of a
// divided-by-zero NaN. Math is bounded in [0,1] for x∈[0,n] by construction.
export const WILSON_Z = 1.645;   // 90% CI — tunable for v2.4 if a desk wants 95%

export function wilsonBounds(x, n, z = WILSON_Z) {
  if (!Number.isFinite(n) || n <= 0) return { lo: null, hi: null };
  const p = Number(x) / n;
  const z2 = z * z;
  const denom = 1 + z2 / n;
  const center = p + z2 / (2 * n);
  const spread = z * Math.sqrt((p * (1 - p)) / n + z2 / (4 * n * n));
  return {
    lo: Math.max(0, (center - spread) / denom),
    hi: Math.min(1, (center + spread) / denom),
  };
}

// ── best rule per tier (v2.4 extension) ────────────────────────────
// The backend's alert_quality SQL GROUP BY (rule, tier) lets us ask a
// sharper question: within a tier, WHICH rule is producing the most hits?
// Ranking by hit_rate alone biases toward small n (1/1 = 100% looks
// stronger than 10/20 = 50%). We rank by sample-size-weighted hit count
// (hit_rate * n_measured, i.e. the same numerator the byTier rollup
// computes) so SIGMA with 80/100 wins over SCORE with 1/1. Returns the
// top rule or null when:
//
//   - the tier's ruleset is underpowered (< 2 distinct rules OR top
//     n_measured below BEST_RULE_MIN_N) — no comparative signal;
//   - the tier is entirely thin (no measured alerts).
//
// A future v2.5 could swap the ranking key for a Wilson lower-bound per
// (rule, tier) for a strictly statistical read. The current key matches
// the existing byTier aggregation discipline (weighted hits) so the
// UI math stays consistent with the cell's headline hit_rate.
export const BEST_RULE_MIN_N = 3;

export function bestRuleForTier(tier, byRuleAndTier) {
  const tierKey = String(tier || "").toUpperCase();
  const candidates = Object.values(byRuleAndTier || {})
    .filter((c) => c.tier === tierKey)
    .filter((c) => Number(c.n_measured) > 0)
    .map((c) => ({
      rule: c.rule,
      hit_rate: c.n_measured > 0 ? c.hits / c.n_measured : 0,
      n_measured: c.n_measured,
      // Sample-size-weighted hit count — preserved on the mapped object
      // so the trailing .sort can rank by it. The byTier rollup stores
      // this same value as `c.hits` (= Σ hit_rate × n_measured), so SIGMA
      // with 80/100 edges SCORE with 1/1 (the obvious noise trap).
      hits: c.hits,
    }))
    .sort((a, b) => b.hits - a.hits);
  if (!candidates.length) return null;
  const best = candidates[0];
  // Single-rule tier = no "best" signal; thin tiers are already handled
  // upstream by the outer thin flag. BEST_RULE_MIN_N guards against
  // single-hit rule becoming the visual default.
  if (candidates.length < 2 || best.n_measured < BEST_RULE_MIN_N) {
    return null;
  }
  return {
    rule: best.rule,
    hit_rate: best.hit_rate,
    n_measured: best.n_measured,
  };
}

// Pick the rows representing the strip from a batched response — convention:
// the LONGEST window in the map drives the headline (a desk's macro read).
function pickStripRows(qualityWindows) {
  if (!qualityWindows || typeof qualityWindows !== "object") return [];
  let longest = 0;
  for (const k of Object.keys(qualityWindows)) {
    const n = Number(k);
    if (!Number.isNaN(n) && n > longest) longest = n;
  }
  return longest ? (qualityWindows[longest] || []) : [];
}

// ── priority sort for the institutional alerts table ───────────────────
// GOLD first, then most-recent; SIGMA-only (no strike) sorts to the top
// of its tier so the cross-symbol σ spikes aren't buried by the noise.
export function compareAlerts(a, b) {
  const ra = TIER_RANK[String(a.tier || "").toUpperCase()] ?? 3;
  const rb = TIER_RANK[String(b.tier || "").toUpperCase()] ?? 3;
  if (ra !== rb) return ra - rb;
  // Within tier, newer first (asof_ts lexical compares correctly because
  // it's an ISO string; the engine stamps with timespec="seconds").
  const ta = String(a.asof_ts || a.asof || "");
  const tb = String(b.asof_ts || b.asof || "");
  if (ta && tb && ta !== tb) return ta < tb ? 1 : -1;
  return 0;
}

// ── quality trend helper (sparkline data) ──────────────────────────────
// Three overlapping windows (7d / 14d / 30d) plotted left-to-right show
// whether the recent calibration is hotter or colder than the longer one.
// Each window is an array of {tier, hit_rate, n_measured} rows from
// /alerts/quality?days=N.
//
// Statistical discipline (per the v2.2 design review):
//   1. n_measured < TREND_MIN_N in the LONGEST window → "unknown". A single
//      win/loss on a tier with n=2 swings the rate 50ppt; the visual
//      direction would be pure noise to a desk.
//   2. The 2pp threshold in v2.1 was a coin-flip on small samples; replaced
//      with TREND_FLAT_BAND (10pp) so the line stays calm under sample noise.
//   3. Overlapping windows are fine for visual scan — 7d ⊂ 14d ⊂ 30d is
//      conceptually a moving-window average, just expressed as two
//      non-overlapping measurement endpoints.
export const TREND_FLAT_BAND = 0.10;
export const TREND_MIN_N = 3;

export function qualityTrendForTier(tier, windowsByDays) {
  const order = [7, 14, 30];
  // `rowsFor` distinguishes ABSENT (key missing OR array empty for the tier)
  // from PRESENT-but-null (the tier row exists with a null hit_rate). The
  // trend signal needs to behave differently in the two cases. An absent
  // window in the payload is a structural data gap; an explicit null is a
  // tier that returned but had no measured alerts — we tolerate the latter
  // and use the endpoints, while an absent window forces direction=unknown.
  const tierKey = String(tier || "").toUpperCase();
  const rowsFor = (n) => {
    const w = windowsByDays && windowsByDays[n];
    if (!Array.isArray(w)) return { present: false, rows: [] };
    return {
      present: true,
      rows: w.filter((r) => String(r.tier || "").toUpperCase() === tierKey),
    };
  };
  const picks = order.map((d) => {
    const { present, rows } = rowsFor(d);
    if (!present || !rows.length) {
      return { hr: null, n_measured: 0, present: false };
    }
    const r = rows[0];
    const hr = Number(r.hit_rate);
    const trimmed = !Number.isNaN(hr) && r.n_measured > 0;
    return { hr: trimmed ? hr : null, n_measured: r.n_measured || 0, present: true };
  });
  const finite = picks.filter((p) => p.hr != null);
  // Gate on the LONGEST window's n_measured: if the macro sample is
  // underpowered, no trend signal deserves to be plotted.
  const longestN = picks.length ? picks[picks.length - 1].n_measured : 0;
  // `thin` = the tier is underpowered in at least one PRESENT window
  // (data was returned but n_measured fell below TREND_MIN_N). Absent
  // windows are NOT counted as thin — they're a structural gap, surfaced
  // separately via direction="unknown" + a muted dot in the sparkline.
  const thin = picks.some((p) => p.present && p.n_measured < TREND_MIN_N);
  let direction = "unknown";
  let delta = null;
  // ALL three windows must be present in the payload AND the longest
  // window must have n_measured >= TREND_MIN_N. The first gate prevents
  // a 2-dot up/down from a brute-force endpoints read; the second prevents
  // a wild trend swing on a single win/loss in a tier with n=1.
  const allPresent = picks.every((p) => p.present);
  if (allPresent && finite.length >= 2 && longestN >= TREND_MIN_N) {
    // SIGN CONVENTION (v2.2):
    //   order = [7, 14, 30] → finite[0] is the RECENT window, finite[last] is the MACRO.
    //   delta = RECENT - MACRO:
    //     positive            → recent hotter than macro → "up"
    //     negative beyond band → recent cooler than macro → "down"
    //     within ±flat band   → sample noise              → "flat"
    delta = finite[0].hr - finite[finite.length - 1].hr;
    if (Math.abs(delta) < TREND_FLAT_BAND) direction = "flat";
    else direction = delta > 0 ? "up" : "down";
  }
  return {
    points: picks,
    direction,
    delta,
    thin,
    has_7: picks[0].hr != null,
  };
}

// Closest Tier value to color the sparkline. Pure; consumed by the panel.
export const TREND_COLOR = {
  up: "#19d27c",        // green — recent window hotter than longer
  down: "#ff4d5e",      // red  — recent window cooler than longer
  flat: "#b3b8c5",      // slate — direction noise
  unknown: "#6c7382",   // muted — underpowered / missing windows
};

// ── v2.5 daily sparkline (per-tier N-day series) ─────────────────
// Backend's /alerts/quality response carries a `daily_series: {GOLD: [...],
// SILVER: [...], BRONZE: [...]}` map with one row per (date, tier) that
// fired at least one directional alert in the last `daily_series_days`
// days. Each row: {date, n, n_measured, hits, hit_rate, avg_move_pct}.
//
// Visual contract: render one dot per trading-day cell in the strip.
// MISSING DAYS are NOT backfilled with 0% — a gap in the line is
// information ("no measured alerts = no signal"), the SVG path breaks
// at the gap so a desk reads it as noise, not as a losing day.
//
// Statistical contract:
//   1. A day with n_measured < DAILY_MIN_N (default 1, surface only
//      measured days; underpowered days never carry a direction) renders
//      as a muted dot, NOT a colored line point.
//   2. A SINGLE point tier (n_measured==1 across the whole window) is
//      rendered as one muted dot, no line — the desk should not see a
//      "trend" from n=1.
//
// `dailySeriesForTier` returns a stable, slot-aligned array length
// `days.length`. Empty slots are `null` — never coalesced to 0% — and
// the consumer renders gaps accordingly.
export const DAILY_MIN_N = 1;       // one measured alert is the floor
export const DAILY_MIN_DAYS = 1;    // zero points is a meaningless sparkline

export function dailySeriesForTier(tier, dailyMap, opts = {}) {
  const tierKey = String(tier || "").toUpperCase();
  const rows = (dailyMap && dailyMap[tierKey]) || [];
  // Index existing rows by ISO date so absent days can be backfilled
  // with null (a gap), never 0. Order preserved ascending by date.
  const byDate = new Map();
  for (const r of rows || []) {
    const d = String(r?.date || "");
    if (!d) continue;
    // Defensively separate the null/undefined path from the numeric
    // coercion path. Number(null) = 0 would silently downgrade a
    // no-observation day to a "0% hit rate" point — the exact opposite
    // of the gap-is-information contract documented above.
    const hrRaw = r?.hit_rate;
    const hrNumeric = hrRaw == null ? null : Number(hrRaw);
    const hr = hrNumeric == null ? null
      : (Number.isFinite(hrNumeric) ? hrNumeric : null);
    byDate.set(d, {
      date: d,
      n: Number(r.n) || 0,
      n_measured: Number(r.n_measured) || 0,
      wins: Number(r.wins) || 0,
      hit_rate: hr,
      avg_move_pct: r.avg_move_pct == null ? null : Number(r.avg_move_pct),
    });
  }
  // No raw rows → return an inert shape that downstream still renders.
  if (!byDate.size) {
    return { points: [], n_measured_total: 0, has_data: false, gaps: 0 };
  }
  const sorted = Array.from(byDate.values()).sort((a, b) =>
    a.date < b.date ? -1 : a.date > b.date ? 1 : 0
  );
  // Gap stats: a "gap" is a calendar-day cell with no data between first
  // and last observed dates. A back-to-back bursty cluster has gaps, an
  // evenly-active tier has gaps=0.
  const first = new Date(sorted[0].date + "T00:00:00Z");
  const last = new Date(sorted[sorted.length - 1].date + "T00:00:00Z");
  const span = Math.max(
    Math.round((last.getTime() - first.getTime()) / (24 * 3600 * 1000)),
    0,
  );
  const gaps = Math.max(span - sorted.length + 1, 0);
  // Trim to the last `opts.maxPoints` cells if the caller asks — the
  // strip's render thread's memory budget is bounded.
  const maxPoints = opts.maxPoints || 90;
  const trimmed = sorted.length > maxPoints ? sorted.slice(-maxPoints) : sorted;
  const n_measured_total = trimmed.reduce((s, p) => s + p.n_measured, 0);
  return {
    points: trimmed,
    n_measured_total,
    has_data: n_measured_total > 0,
    gaps,
  };
}
