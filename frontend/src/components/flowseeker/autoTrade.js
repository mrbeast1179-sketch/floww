/**
 * autoTrade.js — client side of the Flowseeker signal-to-trade bridge.
 *
 * previewAutoTrades()  → GET /api/flowseeker/auto-trade/preview
 * executeAutoTrades()  → POST /api/flowseeker/auto-trade/execute?confirm=true
 *                        Submits paper orders server-side AND returns
 *                        journal_seeds shaped like floww_trades_v2 entries.
 * mergeJournalSeeds()  → idempotently merges seeds into the TradeJournal's
 *                        localStorage store. Dedupe key = ticker|type|action|
 *                        strike|expiry|entry_date so re-executing the same
 *                        contract never creates duplicate journal cards.
 */

const API_BASE = "http://localhost:8000/api";
export const JOURNAL_KEY = "floww_trades_v2";

export async function previewAutoTrades({ tier = "SILVER", minDte = 2, equity } = {}) {
  const qs = new URLSearchParams({ tier, min_dte: String(minDte) });
  if (equity != null) qs.set("equity", String(equity));
  const res = await fetch(`${API_BASE}/flowseeker/auto-trade/preview?${qs}`);
  if (!res.ok) throw new Error(`preview failed: HTTP ${res.status}`);
  return res.json();
}

export async function executeAutoTrades({ tier = "SILVER", minDte = 2, equity } = {}) {
  const qs = new URLSearchParams({ confirm: "true", tier, min_dte: String(minDte) });
  if (equity != null) qs.set("equity", String(equity));
  const res = await fetch(`${API_BASE}/flowseeker/auto-trade/execute?${qs}`, { method: "POST" });
  if (!res.ok) throw new Error(`execute failed: HTTP ${res.status}`);
  return res.json();
}

export function journalSeedKey(seed) {
  return [
    seed.ticker, seed.type, seed.action,
    seed.strike ?? "", seed.expiry ?? "", seed.entry_date ?? "",
  ].join("|");
}

/** Merge seeds into existing journal trades; returns the NEW array (does not write). */
export function mergeJournalSeeds(existingTrades, seeds) {
  const existingKeys = new Set((existingTrades || []).map(journalSeedKey));
  const fresh = (seeds || [])
    .filter(s => s && s.ticker)
    .filter(s => !existingKeys.has(journalSeedKey(s)))
    .map((s, i) => ({
      ...s,
      id: Date.now() + i,
      created_at: new Date().toISOString(),
      source: "flowseeker-auto",
    }));
  return [...fresh, ...(existingTrades || [])];
}

/** Read-modify-write floww_trades_v2. Returns number of journal cards added. */
export function persistJournalSeeds(seeds) {
  let existing = [];
  try {
    existing = JSON.parse(localStorage.getItem(JOURNAL_KEY)) || [];
  } catch { /* corrupted store — start clean */ }
  const merged = mergeJournalSeeds(existing, seeds);
  const added = merged.length - existing.length;
  if (added > 0) localStorage.setItem(JOURNAL_KEY, JSON.stringify(merged));
  return added;
}
