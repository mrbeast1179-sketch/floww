// Pure trade-math helpers — extracted from TradeJournal/QuickTradePanel so the
// money logic is unit-tested. Fixes from the 2026-07-11 wide audit:
//  - a trade closed at $0 (total loss) must count as CLOSED, not open, so its
//    loss isn't silently erased from P&L/win-rate.
//  - breakeven (scratch) trades are neither win nor loss.
//  - option strategy risk/reward must reflect the actual strategy, not a naive
//    "buy → defined risk / else Unlimited" split, and never render "$NaN".

// Closed if it has an exit date OR any non-empty exit price ("0" included —
// that's a total loss, the case the old exit_price>0 test wrongly dropped).
export function isTradeClosed(t) {
  const hasDate = t.exit_date != null && String(t.exit_date).trim() !== "";
  const hasPrice = t.exit_price != null && String(t.exit_price).trim() !== "";
  return hasDate || hasPrice;
}

// Realized P&L in dollars. exit_price "" → 0 (total loss). Longs gain when
// exit>entry; shorts invert.
export function tradePnl(t) {
  const entry = parseFloat(t.entry_price) || 0;
  const exit = parseFloat(t.exit_price) || 0;
  const qty = parseInt(t.quantity) || 1;
  return (exit - entry) * qty * 100 * (t.action === "buy" ? 1 : -1);
}

// "win" | "loss" | "scratch" — scratch (exit === entry) is excluded from both
// so it doesn't drag win-rate down or dilute avg-loss.
export function tradeOutcome(t) {
  const entry = parseFloat(t.entry_price) || 0;
  const exit = parseFloat(t.exit_price) || 0;
  if (exit === entry) return "scratch";
  const favorable = t.action === "buy" ? exit > entry : exit < entry;
  return favorable ? "win" : "loss";
}

const money = (n) => `$${Math.round(n).toLocaleString()}`;

// Max risk / reward display strings for an option strategy. estPrice is the
// per-share premium estimate (may be non-finite when IV is missing → "—").
// Correct at the strategy-category level; long debit trades have DEFINED risk
// (premium paid), short naked calls have unlimited risk, condors are defined
// both sides.
export function strategyRiskReward(strategy, estPrice, quantity, strike) {
  const q = parseInt(quantity) || 1;
  const px = Number(estPrice);
  if (!Number.isFinite(px)) return { maxRisk: "—", maxReward: "—" };
  const premium = px * q * 100;                       // debit paid / credit received
  const bounded = Number.isFinite(Number(strike))
    ? Math.max(0, (Number(strike) - px) * q * 100)    // long put profit / short put assignment risk
    : null;
  const boundedStr = bounded == null ? "Defined" : money(bounded);
  switch (strategy) {
    case "buy_call":
    case "straddle":                                   // long: pay premium, unbounded upside
      return { maxRisk: money(premium), maxReward: "Unlimited" };
    case "buy_put":
      return { maxRisk: money(premium), maxReward: boundedStr };
    case "sell_call":                                  // naked short call: unbounded risk
      return { maxRisk: "Unlimited", maxReward: money(premium) };
    case "sell_put":
      return { maxRisk: boundedStr, maxReward: money(premium) };
    case "iron_condor":                                // defined both sides (wings unknown here)
      return { maxRisk: "Defined", maxReward: money(premium) };
    default:
      return { maxRisk: money(premium), maxReward: "Unlimited" };
  }
}
