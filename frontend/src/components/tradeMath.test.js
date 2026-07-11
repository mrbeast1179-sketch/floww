import { isTradeClosed, tradePnl, tradeOutcome, strategyRiskReward } from "./tradeMath";

describe("isTradeClosed", () => {
  it("open when no exit date and no exit price", () => {
    expect(isTradeClosed({ exit_price: "", exit_date: "" })).toBe(false);
    expect(isTradeClosed({})).toBe(false);
  });
  it("closed at $0 total loss (the bug: exit_price 0 with an exit_date)", () => {
    expect(isTradeClosed({ exit_price: 0, exit_date: "2026-07-11" })).toBe(true);
    expect(isTradeClosed({ exit_price: "0", exit_date: "2026-07-11" })).toBe(true);
  });
  it("closed when exit price is set even without a date", () => {
    expect(isTradeClosed({ exit_price: "5.25", exit_date: "" })).toBe(true);
  });
});

describe("tradePnl", () => {
  it("long total loss = -entry*qty*100", () => {
    expect(tradePnl({ action: "buy", entry_price: "5", exit_price: 0, quantity: "10" })).toBe(-5000);
  });
  it("long winner", () => {
    expect(tradePnl({ action: "buy", entry_price: "2", exit_price: "5", quantity: "1" })).toBe(300);
  });
  it("short winner (credit kept)", () => {
    expect(tradePnl({ action: "sell", entry_price: "3", exit_price: "1", quantity: "1" })).toBe(200);
  });
});

describe("tradeOutcome", () => {
  it("scratch when exit == entry", () => {
    expect(tradeOutcome({ action: "buy", entry_price: "5", exit_price: "5" })).toBe("scratch");
  });
  it("win/loss by direction", () => {
    expect(tradeOutcome({ action: "buy", entry_price: "5", exit_price: "6" })).toBe("win");
    expect(tradeOutcome({ action: "buy", entry_price: "5", exit_price: "4" })).toBe("loss");
    expect(tradeOutcome({ action: "sell", entry_price: "5", exit_price: "4" })).toBe("win");
  });
  it("total loss is a loss, not scratch", () => {
    expect(tradeOutcome({ action: "buy", entry_price: "5", exit_price: 0 })).toBe("loss");
  });
});

describe("strategyRiskReward", () => {
  it("returns — for both when IV/price estimate is missing (no $NaN)", () => {
    const r = strategyRiskReward("buy_call", "—", 1, 100);
    expect(r).toEqual({ maxRisk: "—", maxReward: "—" });
    expect(r.maxRisk).not.toContain("NaN");
  });
  it("long call: defined risk (premium), unlimited reward", () => {
    const r = strategyRiskReward("buy_call", 5, 2, 100);
    expect(r.maxRisk).toBe("$1,000");           // 5 * 2 * 100
    expect(r.maxReward).toBe("Unlimited");
  });
  it("straddle is a LONG debit — defined risk, not 'Unlimited' risk", () => {
    const r = strategyRiskReward("straddle", 5, 1, 100);
    expect(r.maxRisk).toBe("$500");
    expect(r.maxReward).toBe("Unlimited");
  });
  it("iron condor is defined-risk both sides, never 'Unlimited'", () => {
    const r = strategyRiskReward("iron_condor", 2, 1, 100);
    expect(r.maxRisk).toBe("Defined");
    expect(r.maxReward).toBe("$200");
  });
  it("naked short call keeps unlimited risk", () => {
    const r = strategyRiskReward("sell_call", 3, 1, 100);
    expect(r.maxRisk).toBe("Unlimited");
    expect(r.maxReward).toBe("$300");
  });
});
