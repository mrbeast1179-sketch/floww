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

// Mid of one option leg. Prefers (bid+ask)/2, then last/midpoint, then
// whichever side exists. NaN when nothing is quoted (far-OTM SOFI case).
export function contractMid(c) {
  if (!c || typeof c !== "object") return NaN;
  const bid = Number(c.bid);
  const ask = Number(c.ask);
  const last = Number(c.last ?? c.midpoint);
  if (Number.isFinite(bid) && Number.isFinite(ask) && bid > 0 && ask > 0) {
    return (bid + ask) / 2;
  }
  if (Number.isFinite(last) && last > 0) return last;
  if (Number.isFinite(bid) && bid > 0) return bid;
  if (Number.isFinite(ask) && ask > 0) return ask;
  return NaN;
}

function legMids(selection) {
  const s = selection || {};
  return {
    call: contractMid({ bid: s.call_bid, ask: s.call_ask, last: s.call_last }),
    put: contractMid({ bid: s.put_bid, ask: s.put_ask, last: s.put_last }),
  };
}

function ivEstimate(selection) {
  const spot = Number(selection?.spot);
  const iv = Number(selection?.iv);
  if (Number.isFinite(spot) && Number.isFinite(iv) && spot > 0 && iv > 0) {
    return spot * iv * 0.01;
  }
  return NaN;
}

// Effective per-share premium for the ticket, with source for the UI.
// Priority: limit override > live leg mid/last > IV estimate > NaN.
// Straddle sums both legs. Iron condor has no wings here — limit or IV only.
export function effectiveOptionPrice(selection, strategy, limitOverride) {
  const lim = Number(limitOverride);
  if (Number.isFinite(lim) && lim > 0) return { price: lim, source: "limit" };
  const { call, put } = legMids(selection);
  const isStraddle = strategy === "straddle";
  const isCondor = strategy === "iron_condor";
  const wantsCall = strategy.includes("call") || isStraddle || isCondor;
  const wantsPut = strategy.includes("put") || isStraddle || isCondor;
  if (isStraddle) {
    if (Number.isFinite(call) && Number.isFinite(put)) {
      return { price: call + put, source: "mid" };
    }
  } else if (wantsCall && !wantsPut && Number.isFinite(call)) {
    return { price: call, source: callSource(selection, "call") };
  } else if (wantsPut && !wantsCall && Number.isFinite(put)) {
    return { price: put, source: callSource(selection, "put") };
  }
  const iv = ivEstimate(selection);
  if (Number.isFinite(iv)) return { price: iv, source: "iv" };
  return { price: NaN, source: "none" };
}

function callSource(selection, side) {
  const s = selection || {};
  const bid = Number(side === "call" ? s.call_bid : s.put_bid);
  const ask = Number(side === "call" ? s.call_ask : s.put_ask);
  if (Number.isFinite(bid) && Number.isFinite(ask) && bid > 0 && ask > 0) return "mid";
  return "last";
}

// Notional display: never "$0" on a missing price (the SOFI bug).
export function formatNotional(price, quantity) {
  const px = Number(price);
  const q = parseInt(quantity) || 0;
  if (!Number.isFinite(px) || q <= 0) return "—";
  return money(px * q * 100);
}

// Shared journal key — MUST match TradeJournal + TradeAnalytics.
export const JOURNAL_STORAGE_KEY = "floww_trades_v2";

const TICKET_STRATEGY_MAP = {
  buy_call: { type: "call", action: "buy", setup: "BUY CALL" },
  buy_put: { type: "put", action: "buy", setup: "BUY PUT" },
  sell_call: { type: "call", action: "sell", setup: "SELL CALL" },
  sell_put: { type: "put", action: "sell", setup: "SELL PUT" },
  straddle: { type: "call", action: "buy", setup: "STRADDLE" },
  iron_condor: { type: "call", action: "sell", setup: "IRON CONDOR" },
};

// Ticket -> TradeJournal-shaped entries. One entry per ticket (multi-leg
// strategies collapse with the strategy in `setup` — never fabricate legs).
// Missing price journals with entry_price "" (open, unknown) — a ticket is
// never dropped: the drop was the "trades vanish" bug.
export function ticketToJournalEntries(ticket) {
  const t = ticket || {};
  const m = TICKET_STRATEGY_MAP[t.strategy] || { type: "call", action: "buy", setup: String(t.strategy || "SINGLE").toUpperCase() };
  const px = Number(t.effectivePrice);
  const entry = {
    ticker: String(t.ticker || "").replace("^", "").toUpperCase(),
    type: m.type,
    action: m.action,
    strike: t.strike ?? "",
    expiry: t.expiry ?? "",
    quantity: String(t.quantity ?? 1),
    entry_price: Number.isFinite(px) && px > 0 ? px : "",
    exit_price: "",
    entry_date: (t.timestamp || new Date().toISOString()).slice(0, 10),
    exit_date: "",
    notes: `Quick trade @ spot ${t.spot ?? "—"}${t.priceSource ? ` (${t.priceSource} price)` : ""}`,
    gex_regime: "",
    setup: m.setup,
    tags: "quick-trade",
    source: "quick-trade",
  };
  return [entry];
}

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
