// @ts-nocheck
import React, { useState, useEffect, useMemo } from "react";
import { tradePnl, isTradeClosed, tradeOutcome } from "./tradeMath";

// Must match the key TradeJournal writes ("floww_trades_v2"); the old
// "floww_trades" was never written, so this panel was permanently empty.
const STORAGE_KEY = "floww_trades_v2";

function loadTrades() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
  } catch {
    return [];
  }
}

export function TradeAnalytics({ ticker }) {
  const [trades, setTrades] = useState([]);

  useEffect(() => {
    setTrades(loadTrades());
  }, []);

  const filtered = useMemo(() => {
    if (!ticker) return trades;
    return trades.filter(t => t.ticker === ticker);
  }, [trades, ticker]);

  const stats = useMemo(() => {
    // Only closed trades have realized P&L; records store entry/exit fields,
    // not a precomputed `pnl` — derive it with the shared tradeMath helpers.
    const closed = filtered.filter(isTradeClosed);
    if (closed.length === 0) return null;

    const wins = closed.filter(t => tradeOutcome(t) === "win");
    const losses = closed.filter(t => tradeOutcome(t) === "loss");
    const totalPnl = closed.reduce((sum, t) => sum + tradePnl(t), 0);
    const avgWin = wins.length > 0 ? wins.reduce((sum, t) => sum + tradePnl(t), 0) / wins.length : 0;
    const avgLoss = losses.length > 0 ? losses.reduce((sum, t) => sum + tradePnl(t), 0) / losses.length : 0;
    // Win rate over DECIDED trades (win+loss); scratches excluded.
    const decided = wins.length + losses.length;
    const winRate = decided > 0 ? (wins.length / decided) * 100 : 0;
    const profitFactor = Math.abs(avgLoss) > 0 ? Math.abs(avgWin * wins.length) / Math.abs(avgLoss * losses.length) : (wins.length > 0 ? Infinity : 0);

    // Daily P&L keyed by exit date (when the trade was realized).
    const dailyPnl = {};
    closed.forEach(t => {
      const date = t.exit_date ? String(t.exit_date).slice(0, 10) : (t.entry_date ? String(t.entry_date).slice(0, 10) : "unknown");
      dailyPnl[date] = (dailyPnl[date] || 0) + tradePnl(t);
    });

    const dailyEntries = Object.entries(dailyPnl)
      .sort((a, b) => a[0].localeCompare(b[0]))
      .slice(-14); // Last 14 days

    const maxDaily = Math.max(...dailyEntries.map(e => Math.abs(e[1])), 1);

    return {
      totalTrades: closed.length,
      wins: wins.length,
      losses: losses.length,
      totalPnl,
      avgWin,
      avgLoss,
      winRate,
      profitFactor,
      dailyEntries,
      maxDaily,
    };
  }, [filtered]);

  if (!stats) {
    return (
      <div className="panel-2 p-2">
        <div className="label mb-1">Trade Analytics</div>
        <div className="text-[10px] text-slate-500">No trades recorded yet</div>
      </div>
    );
  }

  return (
    <div className="panel-2 p-2">
      <div className="label mb-1">Trade Analytics</div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-1 mb-2">
        <div className="bg-slate-800/50 rounded px-2 py-1">
          <div className="text-[8px] text-slate-500">Total P&L</div>
          <div className={`text-[11px] font-bold ${stats.totalPnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {stats.totalPnl >= 0 ? "+" : ""}${(stats?.totalPnl)?.toFixed(2) ?? "—"}
          </div>
        </div>
        <div className="bg-slate-800/50 rounded px-2 py-1">
          <div className="text-[8px] text-slate-500">Win Rate</div>
          <div className="text-[11px] font-bold text-amber-400">{(stats?.winRate)?.toFixed(0) ?? "—"}%</div>
        </div>
        <div className="bg-slate-800/50 rounded px-2 py-1">
          <div className="text-[8px] text-slate-500">Avg Win</div>
          <div className="text-[10px] font-bold text-emerald-400">+${(stats?.avgWin)?.toFixed(2) ?? "—"}</div>
        </div>
        <div className="bg-slate-800/50 rounded px-2 py-1">
          <div className="text-[8px] text-slate-500">Avg Loss</div>
          <div className="text-[10px] font-bold text-rose-400">${(stats?.avgLoss)?.toFixed(2) ?? "—"}</div>
        </div>
      </div>

      {/* Win/Loss bar */}
      <div className="mb-2">
        <div className="flex justify-between text-[8px] text-slate-500 mb-0.5">
          <span>{stats.wins}W</span>
          <span>{stats.losses}L</span>
        </div>
        <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden flex">
          <div
            className="bg-emerald-500 h-full"
            style={{ width: `${stats.winRate}%` }}
          />
          <div
            className="bg-rose-500 h-full"
            style={{ width: `${100 - stats.winRate}%` }}
          />
        </div>
      </div>

      {/* Daily P&L chart */}
      {stats.dailyEntries?.length > 0 && (
        <div>
          <div className="text-[8px] text-slate-500 mb-1">Daily P&L (14d)</div>
          <div className="flex items-end gap-0.5 h-12">
            {stats.dailyEntries?.map?.(([date, pnl], i) => {
              const height = Math.max((Math.abs(pnl) / stats.maxDaily) * 100, 5);
              const isPositive = pnl >= 0;
              return (
                <div
                  key={i}
                  className="flex-1 flex flex-col justify-end items-center"
                  title={`${date}: ${pnl >= 0 ? "+" : ""}$${pnl?.toFixed?.(2) ?? "—"}`}
                >
                  <div
                    className={`w-full rounded-t ${isPositive ? "bg-emerald-500/60" : "bg-rose-500/60"}`}
                    style={{ height: `${height}%` }}
                  />
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Profit factor */}
      <div className="mt-1.5 text-[8px] text-slate-500 text-right">
        Profit Factor: {isFinite(stats.profitFactor) ? (stats?.profitFactor)?.toFixed(2) ?? "—" : "∞"} · {stats.totalTrades} trades
      </div>
    </div>
  );
}
