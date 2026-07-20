import {
  PRIME_PREMIUM,
  PRIME_VOL_OI,
  CW_CONFIRM,
  fmtCW,
  fmtMovePct,
  tierBadge,
  cwConfirmChip,
  clusterChip,
  primeChip,
  qualityTrendForTier,
  sigmaChip,
  isPrime,
  summarizeQuality,
  compareAlerts,
  TREND_FLAT_BAND,
  TREND_MIN_N,
  wilsonBounds,
  WILSON_Z,
} from "./convictionUi";
import * as convictionUi from "./convictionUi";

const { bestRuleForTier, BEST_RULE_MIN_N } = convictionUi;

const alert = (over = {}) => ({
  tier: "GOLD",
  side: "BUY",
  bias: "BULLISH",
  premium: 300_000,
  vol_oi: 6.0,
  cw_spread: 0.04,
  sigma: null,
  rule: "SCORE",
  under: "PLTR",
  asof_ts: "2026-07-20T14:30:00-04:00",
  ...over,
});

describe("Constants mirror backend thresholds", () => {
  test("thresholds match services/flow_quality.py constants", () => {
    expect(PRIME_PREMIUM).toBe(250_000);
    expect(PRIME_VOL_OI).toBe(5.0);
    expect(CW_CONFIRM).toBe(0.015);
  });
});

describe("fmtCW + fmtMovePct", () => {
  test("fmtCW adds + sign for positive and % suffix", () => {
    expect(fmtCW(0.0482)).toBe("+4.82%");
    expect(fmtCW(-0.012)).toBe("-1.20%");
    expect(fmtCW(0)).toBe("0.00%");
  });
  test("fmtCW placeholder on null / NaN", () => {
    expect(fmtCW(null)).toBe("—");
    expect(fmtCW(NaN)).toBe("—");
  });
  test("fmtMovePct adds + sign for positive move", () => {
    expect(fmtMovePct(3.92)).toBe("+3.92%");
    expect(fmtMovePct(-1.2)).toBe("-1.20%");
    expect(fmtMovePct(null)).toBe("—");
  });
});

describe("tierBadge", () => {
  test("GOLD / SILVER / BRONZE map to canonical classes", () => {
    expect(tierBadge("GOLD")).toMatchObject({ label: "GOLD", rank: 0 });
    expect(tierBadge("GOLD").className).toContain("fsp-tier-gold");
    expect(tierBadge("SILVER").className).toContain("fsp-tier-silver");
    expect(tierBadge("BRONZE").className).toContain("fsp-tier-bronze");
  });
  test("BRONZE + side STRATEGY → STRATEGY badge (spread-leg demotion)", () => {
    const t = tierBadge("BRONZE", "STRATEGY");
    expect(t.label).toBe("STRATEGY");
    expect(t.className).toContain("fsp-tier-strategy");
  });
  test("null / unknown tier → BRONZE fallback", () => {
    expect(tierBadge(null).label).toBe("BRONZE");
    expect(tierBadge("NOT-A-TIER").className).toContain("fsp-tier-bronze");
  });
  test("case-insensitive", () => {
    expect(tierBadge("gold").label).toBe("GOLD");
  });
});

describe("spread-leg signal", () => {
  test("panel renders the STRATEGY tier pill instead of a separate chip", () => {
    // The server already demotes spread legs to (side="STRATEGY", tier="BRONZE")
    // — tierBadge("BRONZE","STRATEGY") returns the STRATEGY label & class,
    // so the panel relies on that pill alone rather than a second chip.
    expect(convictionUi.spreadChip).toBeUndefined();
    const pill = tierBadge("BRONZE", "STRATEGY");
    expect(pill.label).toBe("STRATEGY");
    expect(pill.className).toContain("fsp-tier-strategy");
  });
});

describe("cwConfirmChip", () => {
  test("bullish + cw above threshold → +% label", () => {
    const c = cwConfirmChip(alert({ bias: "BULLISH", cw_spread: 0.04 }));
    expect(c?.label).toMatch(/CW/);
    expect(c?.label).toMatch(/\+4\.0%/);
    expect(c?.className).toContain("fsp-chip-cw-bull");
  });
  test("bearish + cw ≤ -threshold → negative confirms", () => {
    const c = cwConfirmChip(alert({ bias: "BEARISH", cw_spread: -0.03 }));
    expect(c?.label).toMatch(/-/);
    expect(c?.className).toContain("fsp-chip-cw-bear");
  });
  test("mismatched sign → null (chip only fires when it CONFIRMS bias)", () => {
    expect(cwConfirmChip(alert({ bias: "BULLISH", cw_spread: -0.05 }))).toBeNull();
    expect(cwConfirmChip(alert({ bias: "BEARISH", cw_spread: 0.05 }))).toBeNull();
  });
  test("below the 0.015 threshold → null", () => {
    expect(cwConfirmChip(alert({ bias: "BULLISH", cw_spread: 0.01 }))).toBeNull();
  });
  test("null cw_spread / null bias → null", () => {
    expect(cwConfirmChip(alert({ cw_spread: null, bias: null }))).toBeNull();
    expect(cwConfirmChip(alert({ cw_spread: 0.04, bias: null }))).toBeNull();
  });
});

describe("primeChip", () => {
  test("lights up at the 250k + vol/OI 5 floor", () => {
    expect(primeChip(alert({ premium: 250_000, vol_oi: 5.0 }))?.label).toBe("PRIME");
    expect(primeChip(alert({ premium: 300_000, vol_oi: 6.0 }))?.label).toBe("PRIME");
  });
  test("stays off under either floor", () => {
    expect(primeChip(alert({ premium: 100_000, vol_oi: 6 }))).toBeNull();
    expect(primeChip(alert({ premium: 300_000, vol_oi: 3 }))).toBeNull();
  });
  test("isPrime mirrors chip (pure detection)", () => {
    expect(isPrime(alert({ premium: 250_000, vol_oi: 5.0 }))).toBe(true);
    expect(isPrime(alert({ premium: 249_999, vol_oi: 5.0 }))).toBe(false);
    expect(isPrime(alert({ premium: 250_000, vol_oi: 4.999 }))).toBe(false);
    expect(isPrime({})).toBe(false);
    expect(isPrime(null)).toBe(false);
  });
});

describe("sigmaChip", () => {
  test("renders σ-string for non-null value", () => {
    expect(sigmaChip(5.3)?.label).toBe("σ +5.3");
    expect(sigmaChip(-2.1)?.label).toBe("σ -2.1");
    expect(sigmaChip(0)?.label).toBe("σ +0.0");
  });
  test("null / NaN → null", () => {
    expect(sigmaChip(null)).toBeNull();
    expect(sigmaChip(NaN)).toBeNull();
  });
});

describe("clusterChip (server-stamped bool)", () => {
  test("lights up only when alert.cluster is true", () => {
    expect(clusterChip(alert({ cluster: true }))?.label).toBe("CLUSTER");
  });
  test("stays off when cluster is false / null / missing", () => {
    expect(clusterChip(alert({ cluster: false }))).toBeNull();
    expect(clusterChip(alert({ cluster: null }))).toBeNull();
    expect(clusterChip(alert({}))).toBeNull();
  });
  test("null row → null", () => {
    expect(clusterChip(null)).toBeNull();
  });
});

describe("qualityTrendForTier (v2.2 sparkline math)", () => {
  const gold = (n_measured, hit_rate) => ({ tier: "GOLD", n_measured, hit_rate });
  test("up when RECENT (7d) > MACRO (30d) past flat band", () => {
    const t = qualityTrendForTier("GOLD", { 7: [gold(4, 0.85)], 14: [gold(8, 0.70)], 30: [gold(12, 0.60)] });
    expect(t.direction).toBe("up");
    // delta = RECENT - MACRO = 0.85 - 0.60 = +0.25 (positive → "up")
    expect(t.delta).toBeCloseTo(0.25);
  });
  test("flat when delta is within the 10pp band", () => {
    expect(TREND_FLAT_BAND).toBe(0.10);
    const t = qualityTrendForTier("GOLD", { 7: [gold(4, 0.65)], 14: [gold(8, 0.66)], 30: [gold(12, 0.70)] });
    // delta = 0.65 - 0.70 = -0.05 → |0.05| < 0.10 → flat
    expect(t.direction).toBe("flat");
    expect(Math.abs(t.delta)).toBeLessThan(TREND_FLAT_BAND);
  });
  test("down when RECENT < MACRO past flat band", () => {
    const t = qualityTrendForTier("GOLD", { 7: [gold(4, 0.40)], 14: [gold(8, 0.50)], 30: [gold(12, 0.75)] });
    expect(t.direction).toBe("down");
    expect(t.delta).toBeCloseTo(-0.35);
  });
  test("unknown when longest-window n_measured < TREND_MIN_N", () => {
    expect(TREND_MIN_N).toBe(3);
    // 7d has 1, 30d has 2 → under threshold even though both finite.
    const t = qualityTrendForTier("GOLD", { 7: [gold(1, 0.90)], 14: [gold(2, 0.60)], 30: [gold(2, 0.50)] });
    expect(t.direction).toBe("unknown");
  });
  test("unknown when one or more windows have no data", () => {
    const t = qualityTrendForTier("GOLD", { 7: [gold(4, 0.80)], 14: [], 30: [gold(12, 0.50)] });
    expect(t.direction).toBe("unknown");
  });
  test("null hit_rate in middle window tolerated, longest-window rules direction", () => {
    const t = qualityTrendForTier("GOLD", { 7: [gold(4, 0.80)], 14: [{ tier: "GOLD", hit_rate: null }], 30: [gold(12, 0.55)] });
    // 14d row is missing n_measured; finite [7d(hr=0.80), 30d(hr=0.55)].
    // delta = 0.80 - 0.55 = 0.25 → "up". longest-window n_measured=12 (>=3).
    expect(t.direction).toBe("up");
    expect(t.delta).toBeCloseTo(0.25);
  });
  test("thin flag set when ANY window is underpowered", () => {
    const t = qualityTrendForTier("GOLD", { 7: [gold(4, 0.80)], 14: [gold(2, 0.50)], 30: [gold(12, 0.55)] });
    expect(t.thin).toBe(true);
  });
  test("absent input → unknown with null delta", () => {
    const t = qualityTrendForTier("GOLD", null);
    expect(t.direction).toBe("unknown");
    expect(t.delta).toBeNull();
  });
});

describe("summarizeQuality", () => {
  test("groups by tier; thin tier stays thin", () => {
    const out = summarizeQuality({
      quality: [
        { tier: "GOLD",   n: 4, n_measured: 4, hit_rate: 0.75, avg_move_pct: 2.1 },
        { tier: "SILVER", n: 3, n_measured: 3, hit_rate: 0.50, avg_move_pct: 1.4 },
        { tier: "BRONZE", n: 7, n_measured: 0, hit_rate: null, avg_move_pct: null },
      ],
      days: 30,
    });
    expect(out.hasData).toBe(true);
    expect(out.tiers).toHaveLength(3);
    expect(out.tiers.find((t) => t.tier === "GOLD").hit_rate).toBeCloseTo(0.75);
    expect(out.tiers.find((t) => t.tier === "BRONZE").thin).toBe(true);
    expect(out.tiers.find((t) => t.tier === "BRONZE").hit_rate).toBeNull();
  });
  test("v2.3 — each tier carries a Wilson 90% CI on the aggregate hits", () => {
    const out = summarizeQuality({
      quality: [
        // GOLD: 4 measured wins out of 5 total, 80% hit rate.
        { tier: "GOLD", n: 5, n_measured: 5, hit_rate: 0.80, avg_move_pct: 1.0 },
      ],
      days: 30,
    });
    const gold = out.tiers.find((t) => t.tier === "GOLD");
    // 4/5 → 90% Wilson should bracket roughly [49%, 94%].
    expect(gold.hit_rate).toBeCloseTo(0.80);
    expect(gold.hit_lo).toBeGreaterThan(0.40);
    expect(gold.hit_lo).toBeLessThan(0.50);
    expect(gold.hit_hi).toBeGreaterThan(0.90);
    expect(gold.hit_hi).toBeLessThan(0.98);
    expect(gold.hit_lo).toBeLessThan(gold.hit_rate);
    expect(gold.hit_rate).toBeLessThan(gold.hit_hi);
    expect(gold.hits).toBe(4);
  });

  test("v2.3 wins-column round-trip (bit-exact integer path)", () => {
    // Backend's integer `wins` column is preferred over the float-round
    // fallback when present. End-to-end exercise of the wins-cleared path.
    const out = summarizeQuality({
      quality: [
        { tier: "GOLD", wins: 4, n: 5, n_measured: 5, hit_rate: 0.80, avg_move_pct: 1.0 },
      ],
      days: 30,
    });
    const gold = out.tiers.find((t) => t.tier === "GOLD");
    expect(gold.hits).toBe(4);
    expect(gold.hit_lo).toBeGreaterThan(0.40);
    expect(gold.hit_lo).toBeLessThan(0.50);
    expect(gold.hit_hi).toBeGreaterThan(0.90);
    expect(gold.hit_hi).toBeLessThan(0.98);
  });

  test("v2.3 partial payload (mixed wins coverage)", () => {
    // Real-world payloads can mix backend-format rows (wins present) and
    // legacy rows (only hit_rate). The accumulator's null-safe
    // `prev.wins ?? 0` keeps the integer path alive without NaN poisoning.
    const out = summarizeQuality({
      quality: [
        { tier: "GOLD", wins: 1, n: 2, n_measured: 2, hit_rate: 1.00, avg_move_pct: 3.0 },
        { tier: "GOLD",              n: 3, n_measured: 3, hit_rate: 0.20, avg_move_pct: 0.5 },
      ],
      days: 30,
    });
    const gold = out.tiers.find((t) => t.tier === "GOLD");
    // Row 1 contributes wins=1; row 2 has wins=undefined and is skipped.
    expect(gold.hits).toBe(1);
    expect(gold.hit_rate).toBeCloseTo((1.0 * 2 + 0.20 * 3) / 5, 2);
    // WilsonBounds(1, 5, z=1.645): lo ~0.052, hi ~0.647. Bracket loosely.
    expect(gold.hit_lo).toBeGreaterThan(0.04);
    expect(gold.hit_lo).toBeLessThan(0.15);
    expect(gold.hit_hi).toBeGreaterThan(0.55);
    expect(gold.hit_hi).toBeLessThan(0.75);
  });
  test("v2.3 — thin tier carries null bounds (Wilson undefined at n=0)", () => {
    const out = summarizeQuality({
      quality: [
        { tier: "BRONZE", n: 7, n_measured: 0, hit_rate: null, avg_move_pct: null },
      ],
      days: 30,
    });
    const bronze = out.tiers.find((t) => t.tier === "BRONZE");
    expect(bronze.hit_lo).toBeNull();
    expect(bronze.hit_hi).toBeNull();
  });
  test("sums n and n_measured within a tier (multiple rules)", () => {
    const out = summarizeQuality({
      quality: [
        { tier: "GOLD", n: 2, n_measured: 2, hit_rate: 1.0, avg_move_pct: 3.0 },
        { tier: "GOLD", n: 3, n_measured: 3, hit_rate: 0.67, avg_move_pct: 1.5 },
      ],
      days: 30,
    });
    const gold = out.tiers.find((t) => t.tier === "GOLD");
    expect(gold.n).toBe(5);
    expect(gold.n_measured).toBe(5);
    expect(gold.hit_rate).toBeCloseTo((2 * 1.0 + 3 * 0.67) / 5, 5);
    expect(gold.avg_move_pct).toBeCloseTo((2 * 3.0 + 3 * 1.5) / 5, 5);
  });
  test("empty input → empty result, hasData false", () => {
    expect(summarizeQuality({}).hasData).toBe(false);
    expect(summarizeQuality(null).tiers).toEqual([]);
    expect(summarizeQuality({ quality: [] }).tiers).toEqual([]);
  });
  test("v2.2 batched shape: project the longest window for the headline strip", () => {
    const out = summarizeQuality({
      quality_windows: {
        7:  [{ tier: "GOLD", n: 4, n_measured: 4, hit_rate: 0.80, avg_move_pct: 2.5 }],
        14: [{ tier: "GOLD", n: 8, n_measured: 8, hit_rate: 0.70, avg_move_pct: 2.0 }],
        30: [{ tier: "GOLD", n: 12, n_measured: 12, hit_rate: 0.65, avg_move_pct: 1.7 }],
      },
      days: [7, 14, 30],
    });
    // Headline strip uses the 30d window — the macro read.
    const gold = out.tiers.find((t) => t.tier === "GOLD");
    expect(gold.hit_rate).toBeCloseTo(0.65);
    expect(out.windows).toEqual([7, 14, 30]);
    expect(out.days).toBe(30);
  });
  test("v2.4 — best_rule attached per tier from per-(rule, tier) accumulator", () => {
    const out = summarizeQuality({
      quality: [
        // Two rules in GOLD with sufficient n; SIGMA has more weighted hits.
        { rule: "SCORE", tier: "GOLD", n: 2, n_measured: 2, hit_rate: 0.50, avg_move_pct: 1.0 },
        { rule: "SIGMA", tier: "GOLD", n: 10, n_measured: 10, hit_rate: 0.80, avg_move_pct: 2.0 },
      ],
      days: 30,
    });
    const gold = out.tiers.find((t) => t.tier === "GOLD");
    expect(gold.best_rule).toEqual({
      rule: "SIGMA", hit_rate: 0.80, n_measured: 10,
    });
  });
  test("v2.4 — best_rule null when only one rule qualifies per tier", () => {
    const out = summarizeQuality({
      quality: [{ rule: "SCORE", tier: "GOLD", n: 5, n_measured: 5, hit_rate: 0.80, avg_move_pct: 1.5 }],
      days: 30,
    });
    const gold = out.tiers.find((t) => t.tier === "GOLD");
    expect(gold.best_rule).toBeNull();
  });
});

describe("bestRuleForTier (v2.4 extension)", () => {
  test("returns null when tier has only one rule (no comparative signal)", () => {
    const byRuleAndTier = {
      SCORE_GOLD: { rule: "SCORE", tier: "GOLD", hits: 8, n_measured: 10 },
    };
    expect(bestRuleForTier("GOLD", byRuleAndTier)).toBeNull();
  });
  test("null when top candidate's n_measured is below BEST_RULE_MIN_N", () => {
    // WHALE has the highest sample-size-weighted hits (1.98) but its
    // pool is only n=2 (99% hit rate × 2). Under sort-by-hits, WHALE
    // outranks SCORE (0.50 hits from a single 100%/n=1 sample), but a
    // pool smaller than BEST_RULE_MIN_N=3 cannot anchor the "best"
    // headline. The threshold on the top-by-hits candidate fires.
    const byRuleAndTier = {
      SCORE_GOLD: { rule: "SCORE", tier: "GOLD", hits: 0.50, n_measured: 1 },
      WHALE_GOLD: { rule: "WHALE", tier: "GOLD", hits: 1.98, n_measured: 2 },
    };
    expect(bestRuleForTier("GOLD", byRuleAndTier)).toBeNull();
  });
  test("ranks by sample-size-weighted hit count: SIGMA beats SCORE despite lower hit_rate", () => {
    // SCORE: 1/2 = 50% (n_measured=2 → weak), weighted_hits = 1.0
    // SIGMA: 8/10 = 80% (n_measured=10 → strong), weighted_hits = 8.0
    // SIGMA wins because the ranking key is hit_rate * n_measured, not
    // hit_rate alone. Mirrors byTier aggregation discipline.
    const byRuleAndTier = {
      SCORE_GOLD: { rule: "SCORE", tier: "GOLD", hits: 1, n_measured: 2 },
      SIGMA_GOLD: { rule: "SIGMA", tier: "GOLD", hits: 8, n_measured: 10 },
    };
    const r = bestRuleForTier("GOLD", byRuleAndTier);
    expect(r.rule).toBe("SIGMA");
    expect(r.hit_rate).toBeCloseTo(0.80);
    expect(r.n_measured).toBe(10);
  });
  test("null when no measured alerts (winner has n_measured=0)", () => {
    const byRuleAndTier = {
      SCORE_GOLD: { rule: "SCORE", tier: "GOLD", hits: 0, n_measured: 0 },
      WHALE_GOLD: { rule: "WHALE", tier: "GOLD", hits: 0, n_measured: 0 },
    };
    expect(bestRuleForTier("GOLD", byRuleAndTier)).toBeNull();
  });
  test("filters other-tier rows out of the candidate set, returns null on single-rule GOLD", () => {
    // SCORE_GOLD has n=10 hits in GOLD; SCORE_SILVER has n=200 hits in
    // SILVER — the heavy silver row must be filtered out by tier before
    // ranking. With only SCORE_GOLD remaining as a candidate, the
    // documented "no comparative signal" guard fires and returns null.
    const byRuleAndTier = {
      SCORE_GOLD:   { rule: "SCORE", tier: "GOLD",   hits: 9, n_measured: 10  },
      SCORE_SILVER: { rule: "SCORE", tier: "SILVER", hits: 100, n_measured: 200 },
    };
    expect(bestRuleForTier("GOLD", byRuleAndTier)).toBeNull();
  });
});

describe("wilsonBounds (v2.3 statistical-honesty CI)", () => {
  test("x=0/n=10 → lower-bound clamped at 0, upper around 31%", () => {
    const { lo, hi } = wilsonBounds(0, 10);
    expect(lo).toBeCloseTo(0, 5);
    expect(hi).toBeGreaterThan(0.20);
    expect(hi).toBeLessThan(0.32);
  });
  test("x=n/n=10 → upper clamped at 1, lower around 69%", () => {
    const { lo, hi } = wilsonBounds(10, 10);
    expect(hi).toBeCloseTo(1, 5);
    expect(lo).toBeGreaterThan(0.68);
    expect(lo).toBeLessThan(0.80);
  });
  test("x=3/n=4 → '75%' but Wilson 90% bands roughly [33%, 95%] (the small-sample honesty)", () => {
    const { lo, hi } = wilsonBounds(3, 4);
    expect(lo).toBeGreaterThan(0.30);
    expect(lo).toBeLessThan(0.40);
    expect(hi).toBeGreaterThan(0.85);
    expect(hi).toBeLessThan(1.0);
  });
  test("n=0 → null/null (UI renders em-dash instead of NaN)", () => {
    expect(wilsonBounds(0, 0)).toEqual({ lo: null, hi: null });
    expect(wilsonBounds(5, 0)).toEqual({ lo: null, hi: null });
  });
  test("n=1 still bounded (yields ~[5%, 90%] for the single hit)", () => {
    // Edge case we documented NOT to suppress — the wide band is exactly the point.
    const { lo, hi } = wilsonBounds(1, 1);
    expect(lo).toBeGreaterThanOrEqual(0);
    expect(hi).toBeLessThanOrEqual(1);
    expect(hi - lo).toBeGreaterThan(0.7);   // wide band -> underpowered
  });
});

describe("compareAlerts tier-priority sort", () => {
  test("GOLD before SILVER before BRONZE", () => {
    const sorted = [
      alert({ tier: "BRONZE", asof_ts: "2026-07-20T11:00:00-04:00" }),
      alert({ tier: "GOLD",   asof_ts: "2026-07-20T10:00:00-04:00" }),
      alert({ tier: "SILVER", asof_ts: "2026-07-20T11:00:00-04:00" }),
    ].sort(compareAlerts);
    expect(sorted.map((a) => a.tier)).toEqual(["GOLD", "SILVER", "BRONZE"]);
  });
  test("within a tier, newer asof_ts wins", () => {
    const sorted = [
      alert({ tier: "GOLD", asof_ts: "2026-07-20T10:00:00-04:00" }),
      alert({ tier: "GOLD", asof_ts: "2026-07-20T11:00:00-04:00" }),
    ].sort(compareAlerts);
    expect(sorted[0].asof_ts).toBe("2026-07-20T11:00:00-04:00");
  });
  test("unknown tier sinks to the bottom", () => {
    const sorted = [
      alert({ tier: "MARMALADE", asof_ts: "2026-07-20T11:00:00-04:00" }),
      alert({ tier: "GOLD",      asof_ts: "2026-07-20T10:00:00-04:00" }),
    ].sort(compareAlerts);
    expect(sorted[0].tier).toBe("GOLD");
  });
});
