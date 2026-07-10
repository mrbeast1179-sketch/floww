import {
  bizDTE, scanTypeOf, scanScoreOf, estimateDelta, approxSpot, mkScanRow,
  fmtUSD, fmtK, fmtIV, scoreGradeOf, estPremium, evalAlerts, tickerRollup,
  archetypeOf, volSigma, annotateFirstSeen, sessionDay, fmtClock, fmtAge,
} from "./scanLogic";

describe("estimateDelta", () => {
  it("is ~±0.5 at the money", () => {
    expect(Math.abs(estimateDelta(100, 100, "call"))).toBeCloseTo(0.5, 1);
    expect(Math.abs(estimateDelta(100, 100, "put"))).toBeCloseTo(0.5, 1);
  });
  it("calls: deep ITM → +1ish, deep OTM → 0ish; puts mirror negatively", () => {
    expect(estimateDelta(50, 100, "call")).toBeGreaterThan(0.9);
    expect(estimateDelta(150, 100, "call")).toBeLessThan(0.1);
    expect(estimateDelta(150, 100, "put")).toBeLessThan(-0.9);
    expect(estimateDelta(50, 100, "put")).toBeGreaterThan(-0.1);
  });
  it("returns null without a spot", () => {
    expect(estimateDelta(100, null, "call")).toBeNull();
    expect(estimateDelta(null, 100, "call")).toBeNull();
  });
});

describe("IV unit heuristic (decimal IVs above 100% are real)", () => {
  it("fmtIV treats <3 as decimal, ≥3 as pct", () => {
    expect(fmtIV(1.5)).toBe("150.0%");
    expect(fmtIV(0.42)).toBe("42.0%");
    expect(fmtIV(42)).toBe("42.0%");
  });
  it("estPremium has no /100 cliff at iv=1.5 (meme-stock IV)", () => {
    const base = { strike: 100, vol: 1000, dte: 5, delta: 0.5 };
    const p075 = estPremium({ ...base, iv: 0.75 });
    const p150 = estPremium({ ...base, iv: 1.5 });
    expect(p150).toBeCloseTo(p075 * 2, 5);   // linear in iv — not divided by 100
  });
});

describe("approxSpot", () => {
  it("is the median strike", () => {
    expect(approxSpot([110, 90, 100])).toBe(100);
    expect(approxSpot([])).toBeNull();
    expect(approxSpot(null)).toBeNull();
  });
});

describe("scanTypeOf thresholds", () => {
  it("classifies by volume magnitude then vol/OI", () => {
    expect(scanTypeOf({ vol: 30000, volOI: 1 })).toBe("sweep");
    expect(scanTypeOf({ vol: 9000, volOI: 1 })).toBe("block");
    expect(scanTypeOf({ vol: 500, volOI: 2.5 })).toBe("unusual");
    expect(scanTypeOf({ vol: 500, volOI: 1.2 })).toBe("split");
    expect(scanTypeOf({ vol: 500, volOI: 0.2 })).toBe("regular");
  });
});

describe("scanScoreOf regime nudge", () => {
  const base = { volOI: 2, vol: 5000, notional: 5e6, dte: 2, delta: 0.3 };
  it("negative gamma boosts short-dated flow", () => {
    const plain = scanScoreOf({ ...base });
    const nudged = scanScoreOf({ ...base }, "negative");
    expect(nudged).toBeGreaterThan(plain);
    expect(nudged).toBeLessThanOrEqual(100);
  });
  it("positive gamma boosts fresh positioning (vol/OI ≥ 2)", () => {
    expect(scanScoreOf({ ...base }, "positive")).toBeGreaterThan(scanScoreOf({ ...base }));
  });
  it("records component parts on the row", () => {
    const r = { ...base };
    scanScoreOf(r, "negative");
    expect(r._parts.nudge).toBe(5);
    expect(r._parts.pos).toBeGreaterThan(0);
  });
  it("informed-positioning band (7-90 DTE, vol≥3×OI, ≥$25k) adds +4", () => {
    const inBand = { volOI: 3.5, vol: 5000, notional: 5e6, premium: 1e5, dte: 30, delta: 0.3 };
    scanScoreOf(inBand);
    expect(inBand._parts.band).toBe(4);
    const noFloor = { ...inBand, premium: 5e3 };
    scanScoreOf(noFloor);
    expect(noFloor._parts.band).toBe(0);
    const tooShort = { ...inBand, dte: 3 };
    scanScoreOf(tooShort);
    expect(tooShort._parts.band).toBe(0);
  });
});

describe("mkScanRow", () => {
  it("computes notional, volOI, dte, score and estimates delta from spot", () => {
    const r = mkScanRow("NVDA", "call", 120, "2099-01-08", 10000, 4000, 0.5, null, 118, "negative");
    expect(r.notional).toBe(10000 * 100 * 120);
    expect(r.volOI).toBeCloseTo(2.5);
    expect(r.deltaEst).toBe(true);
    expect(r.delta).not.toBeNull();
    expect(r.regime).toBe("negative");
    expect(r.score).toBeGreaterThan(0);
    expect(r._parts).toBeDefined();
    expect(r.ftype).toBe("block");
  });
  it("keeps a real delta when provided", () => {
    const r = mkScanRow("SPY", "put", 740, "2099-01-08", 2000, 1000, 0.2, -0.35, 744, null);
    expect(r.delta).toBe(-0.35);
    expect(r.deltaEst).toBe(false);
  });
  it("no spot + no delta → delta stays null, OTM component degrades gracefully", () => {
    const r = mkScanRow("TSLA", "call", 300, "2099-01-08", 5000, 1000, 0.6, null, null, null);
    expect(r.delta).toBeNull();
    expect(r.deltaEst).toBe(false);
    expect(r.score).toBeGreaterThan(0);
  });
});

describe("formatters", () => {
  it("fmtUSD / fmtK / fmtIV / scoreGradeOf", () => {
    expect(fmtUSD(2.5e9)).toBe("$2.50B");
    expect(fmtK(1500)).toBe("2k");
    expect(fmtIV(0.42)).toBe("42.0%");
    expect(scoreGradeOf(85)).toBe("crit");
    expect(scoreGradeOf(40)).toBe("norm");
  });
});

describe("estPremium", () => {
  it("null without iv or strike", () => {
    expect(estPremium({ iv: null, strike: 100, vol: 10, dte: 5 })).toBeNull();
    expect(estPremium({ iv: 0.3, strike: 0, vol: 10, dte: 5 })).toBeNull();
  });
  it("scales with volume and iv, handles pct-style iv", () => {
    const base = { strike: 100, vol: 1000, dte: 5, delta: 0.5 };
    const p1 = estPremium({ ...base, iv: 0.2 });
    const p2 = estPremium({ ...base, iv: 0.4 });
    const p2pct = estPremium({ ...base, iv: 40 });   // 40 ≡ 40%
    expect(p2).toBeGreaterThan(p1);
    expect(p2pct).toBeCloseTo(p2, 5);
    expect(estPremium({ ...base, iv: 0.2, vol: 2000 })).toBeCloseTo(p1 * 2, 5);
  });
  it("discounts deep OTM via delta, never below the floor price", () => {
    const atm = estPremium({ strike: 100, vol: 100, dte: 5, iv: 0.3, delta: 0.5 });
    const otm = estPremium({ strike: 100, vol: 100, dte: 5, iv: 0.3, delta: 0.05 });
    expect(otm).toBeLessThan(atm);
    expect(estPremium({ strike: 1, vol: 100, dte: 1, iv: 0.01, delta: 0.02 })).toBeGreaterThanOrEqual(100 * 100 * 0.05);
  });
});

describe("evalAlerts", () => {
  const mk = (over) => ({
    under: "SPY", type: "call", strike: 745, exp: "2099-01-08",
    score: 90, premium: 2e6, notional: 5e7, volOI: 3, dte: 5, _new: true, ...over,
  });
  it("only fires on _new rows", () => {
    expect(evalAlerts([mk({ _new: false })])).toEqual([]);
    expect(evalAlerts([mk()])).toHaveLength(1);
  });
  it("SCORE rule respects minScore", () => {
    const hits = evalAlerts([mk({ score: 84 }), mk({ score: 85, strike: 750 })], { minScore: 85 });
    expect(hits).toHaveLength(1);
    expect(hits[0].rule).toBe("SCORE");
    expect(hits[0].strike).toBe(750);
  });
  it("WHALE fires on premium threshold when score is quiet", () => {
    const hits = evalAlerts([mk({ score: 40, premium: 12e6 })], { minScore: 85, whalePremium: 10e6 });
    expect(hits).toHaveLength(1);
    expect(hits[0].rule).toBe("WHALE");
  });
  it("0DTE fires on short-dated near-threshold flow", () => {
    const hits = evalAlerts([mk({ score: 72, premium: 1e5, dte: 0 })], { minScore: 85, zeroDteScore: 70 });
    expect(hits).toHaveLength(1);
    expect(hits[0].rule).toBe("0DTE");
  });
  it("disabled rules are skipped and each row alerts at most once", () => {
    const rows = [mk({ score: 99, premium: 99e6, dte: 0 })];
    expect(evalAlerts(rows, { enabled: { score: false, whale: false, zerodte: false } })).toEqual([]);
    expect(evalAlerts(rows)).toHaveLength(1);   // matches SCORE first, not three times
  });
  it("carries a stable contract key", () => {
    const [hit] = evalAlerts([mk()]);
    expect(hit.key).toBe("SPY|call|745|2099-01-08");
  });
});

describe("annotateFirstSeen", () => {
  it("stamps the first sighting and preserves it across refreshes same session", () => {
    const t1 = new Date(2026, 6, 6, 10, 0, 0).getTime();
    const t2 = new Date(2026, 6, 6, 10, 5, 0).getTime();
    const rows1 = [{ under: "SPY", type: "call", strike: 745, exp: "2099-01-08" }];
    const { seen } = annotateFirstSeen(rows1, null, t1);
    expect(rows1[0].firstSeen).toBe(t1);
    const rows2 = [{ under: "SPY", type: "call", strike: 745, exp: "2099-01-08" }];
    annotateFirstSeen(rows2, seen, t2);
    expect(rows2[0].firstSeen).toBe(t1);   // preserved, not re-stamped
  });
  it("resets the map when the trading day rolls", () => {
    const t1 = new Date(2026, 6, 6, 10, 0, 0).getTime();
    const t2 = new Date(2026, 6, 7, 10, 0, 0).getTime();
    const rows1 = [{ under: "SPY", type: "call", strike: 745, exp: "2099-01-08" }];
    const { seen } = annotateFirstSeen(rows1, null, t1);
    expect(seen.day).toBe("2026-07-06");
    const rows2 = [{ under: "SPY", type: "call", strike: 745, exp: "2099-01-08" }];
    const out = annotateFirstSeen(rows2, seen, t2);
    expect(out.seen.day).toBe("2026-07-07");
    expect(rows2[0].firstSeen).toBe(t2);   // fresh session → fresh stamp
  });
  it("new contracts get the current time; tolerates empty input", () => {
    const now = new Date(2026, 6, 6, 11, 0, 0).getTime();
    expect(annotateFirstSeen([], null, now).rows).toEqual([]);
    const rows = [{ under: "AAPL", type: "put", strike: 200, exp: "2099-02-01" }];
    const { seen } = annotateFirstSeen(rows, { day: sessionDay(now), map: {} }, now);
    expect(rows[0].firstSeen).toBe(now);
    expect(seen.map["AAPL|put|200|2099-02-01"]).toBe(now);
  });
});

describe("fmtClock / fmtAge", () => {
  it("fmtClock returns — for null and a time string otherwise", () => {
    expect(fmtClock(null)).toBe("—");
    const s = fmtClock(new Date(2026, 6, 6, 13, 5, 0).getTime());
    expect(typeof s).toBe("string");
    expect(s.length).toBeGreaterThan(3);
  });
  it("fmtAge buckets seconds / minutes / hours", () => {
    const now = 10_000_000;
    expect(fmtAge(now - 5000, now)).toBe("5s");
    expect(fmtAge(now - 120000, now)).toBe("2m");
    expect(fmtAge(now - 7200000, now)).toBe("2h");
    expect(fmtAge(null, now)).toBe("—");
  });
});

describe("volSigma", () => {
  it("z-scores today's volume against the baseline", () => {
    expect(volSigma(150000, { avg: 100000, std: 20000, days: 5 })).toBeCloseTo(2.5);
    expect(volSigma(80000, { avg: 100000, std: 20000, days: 5 })).toBeCloseTo(-1.0);
  });
  it("null without a usable baseline", () => {
    expect(volSigma(150000, null)).toBeNull();
    expect(volSigma(150000, { avg: 100000, std: 0, days: 5 })).toBeNull();
    expect(volSigma(150000, { avg: 100000, std: 20000, days: 1 })).toBeNull();
    expect(volSigma(null, { avg: 100000, std: 20000, days: 5 })).toBeNull();
  });
});

describe("archetypeOf", () => {
  it("WHALE on ≥$10M estimated premium (first match wins)", () => {
    expect(archetypeOf({ premium: 12e6, delta: 0.1, dte: 1, volOI: 5, type: "call" })).toBe("WHALE");
  });
  it("LOTTO on deep-OTM short-dated", () => {
    expect(archetypeOf({ premium: 1e5, delta: 0.08, dte: 1, volOI: 1, type: "call" })).toBe("LOTTO");
    expect(archetypeOf({ premium: 1e5, delta: -0.12, dte: 2, volOI: 1, type: "put" })).toBe("LOTTO");
  });
  it("HEDGE on mid-delta long-dated puts", () => {
    expect(archetypeOf({ premium: 1e5, delta: -0.4, dte: 45, volOI: 1, type: "put" })).toBe("HEDGE");
    expect(archetypeOf({ premium: 1e5, delta: 0.4, dte: 45, volOI: 1, type: "call" })).toBeNull();
  });
  it("FRESH on vol/OI ≥ 3 with the $25k retail-noise premium floor", () => {
    expect(archetypeOf({ premium: 1e5, delta: 0.5, dte: 10, volOI: 3.5, type: "call" })).toBe("FRESH");
    expect(archetypeOf({ premium: 5e3, delta: 0.5, dte: 10, volOI: 3.5, type: "call" })).toBeNull();
    expect(archetypeOf({ premium: null, delta: 0.5, dte: 10, volOI: 3.5, type: "call" })).toBe("FRESH"); // no estimate ≠ small
  });
  it("null when nothing distinctive; tolerates missing fields", () => {
    expect(archetypeOf({ premium: 1e5, delta: 0.5, dte: 10, volOI: 1, type: "call" })).toBeNull();
    expect(archetypeOf({ volOI: 1, type: "call" })).toBeNull();
  });
  it("mkScanRow attaches arch", () => {
    const r = mkScanRow("SPY", "call", 745, "2099-01-08", 60000, 4000, 0.9, 0.5, 744, null);
    expect(r.arch).toBe("WHALE");
  });
});

describe("tickerRollup", () => {
  const row = (under, type, premium, score = 50, regime = null) => ({ under, type, premium, score, regime });
  it("aggregates premium per ticker, sorted desc, top-N", () => {
    const out = tickerRollup([
      row("SPY", "call", 5e6), row("SPY", "put", 3e6),
      row("QQQ", "call", 20e6), row("NVDA", "put", 1e6),
    ], 2);
    expect(out.map((e) => e.under)).toEqual(["QQQ", "SPY"]);
    expect(out[1].prem).toBe(8e6);
  });
  it("computes call% split and carries max score + regime", () => {
    const [spy] = tickerRollup([
      row("SPY", "call", 6e6, 91, "negative"), row("SPY", "put", 2e6, 55),
    ]);
    expect(spy.callPct).toBe(75);
    expect(spy.maxScore).toBe(91);
    expect(spy.regime).toBe("negative");
    expect(spy.count).toBe(2);
  });
  it("computes volume-based PCR (Pan-Poteshman) per ticker", () => {
    const r = (type, vol) => ({ under: "SPY", type, premium: 1e5, score: 50, regime: null, vol });
    const [spy] = tickerRollup([r("call", 4000), r("put", 1000), r("put", 1000)]);
    expect(spy.pcr).toBeCloseTo(0.5);
    const [noCalls] = tickerRollup([r("put", 1000)]);
    expect(noCalls.pcr).toBeNull();
  });
  it("handles null premiums and empty input", () => {
    expect(tickerRollup([])).toEqual([]);
    const [t] = tickerRollup([row("TSLA", "call", null)]);
    expect(t.prem).toBe(0);
    expect(t.callPct).toBe(50);
  });
});

describe("bizDTE", () => {
  it("expired → 0, null → null", () => {
    expect(bizDTE("2000-01-01")).toBe(0);
    expect(bizDTE(null)).toBeNull();
  });
  it("expiring today → 0 regardless of time of day (date-boundary based)", () => {
    const t = new Date();
    const today = `${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, "0")}-${String(t.getUTCDate()).padStart(2, "0")}`;
    expect(bizDTE(today)).toBe(0);
  });
  it("tomorrow is at most 1 trading day away", () => {
    const t = new Date(Date.now() + 86400000);
    const tomorrow = `${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, "0")}-${String(t.getUTCDate()).padStart(2, "0")}`;
    const d = bizDTE(tomorrow);
    expect(d === 0 || d === 1).toBe(true);   // 0 if tomorrow is a weekend day
  });
  it("counts only weekdays", () => {
    const d = new Date();
    d.setUTCDate(d.getUTCDate() + 14);
    const dte = bizDTE(d.toISOString().slice(0, 10));
    expect(dte).toBeGreaterThan(7);
    expect(dte).toBeLessThanOrEqual(11);
  });
});
