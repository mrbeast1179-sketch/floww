import {
  bizDTE, scanTypeOf, scanScoreOf, estimateDelta, approxSpot, mkScanRow,
  fmtUSD, fmtK, fmtIV, scoreGradeOf,
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

describe("bizDTE", () => {
  it("expired → 0, null → null", () => {
    expect(bizDTE("2000-01-01")).toBe(0);
    expect(bizDTE(null)).toBeNull();
  });
  it("counts only weekdays", () => {
    const d = new Date();
    d.setUTCDate(d.getUTCDate() + 14);
    const dte = bizDTE(d.toISOString().slice(0, 10));
    expect(dte).toBeGreaterThan(7);
    expect(dte).toBeLessThanOrEqual(11);
  });
});
