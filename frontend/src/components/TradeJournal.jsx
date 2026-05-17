import React, { useState, useEffect, useMemo } from "react";
import { fmt, fmtAbs, pctClass } from "../lib/helpers";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function TradeJournal({ ticker }) {
  const [trades, setTrades] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [filterTicker, setFilterTicker] = useState("");
  const [newTrade, setNewTrade] = useState({
    ticker: ticker || "SPY",
    type: "call",
    action: "buy",
    strike: "",
    expiry: "",
    quantity: "1",
    entry_price: "",
    exit_price: "",
    entry_date: new Date().toISOString().slice(0, 10),
    exit_date: "",
    notes: "",
    gex_regime: "",
    setup: "",
  });

  // Load trades from localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem("floww_trades");
      if (saved) setTrades(JSON.parse(saved));
    } catch {}
  }, []);

  // Save trades to localStorage
  useEffect(() => {
    localStorage.setItem("floww_trades", JSON.stringify(trades));
  }, [trades]);

  const handleAdd = () => {
    const trade = {
      ...newTrade,
      id: Date.now(),
      created_at: new Date().toISOString(),
    };
    setTrades(prev => [trade, ...prev]);
    setShowAdd(false);
    setNewTrade({
      ...newTrade,
      strike: "",
      entry_price: "",
      exit_price: "",
      notes: "",
    });
  };

  const handleUpdate = () => {
    setTrades(prev => prev.map(t => t.id === editingId ? { ...newTrade, id: editingId, updated_at: new Date().toISOString() } : t));
    setEditingId(null);
    setShowAdd(false);
    setNewTrade({
      ticker: ticker || "SPY",
      type: "call",
      action: "buy",
      strike: "",
      expiry: "",
      quantity: "1",
      entry_price: "",
      exit_price: "",
      entry_date: new Date().toISOString().slice(0, 10),
      exit_date: "",
      notes: "",
      gex_regime: "",
      setup: "",
    });
  };

  const handleEdit = (trade) => {
    setNewTrade({ ...trade });
    setEditingId(trade.id);
    setShowAdd(true);
  };

  const handleDelete = (id) => {
    setTrades(prev => prev.filter(t => t.id !== id));
  };

  const handleClose = (id, exitPrice) => {
    setTrades(prev => prev.map(t =>
      t.id === id ? { ...t, exit_price: exitPrice, exit_date: new Date().toISOString().slice(0, 10) } : t
    ));
  };

  // Unique tickers for filter
  const uniqueTickers = useMemo(() => {
    const set = new Set(trades.map(t => t.ticker));
    return Array.from(set).sort();
  }, [trades]);

  // Filtered trades
  const filteredTrades = useMemo(() => {
    if (!filterTicker) return trades;
    return trades.filter(t => t.ticker === filterTicker);
  }, [trades, filterTicker]);

  // Calculate stats
  const closedTrades = filteredTrades.filter(t => t.exit_price && parseFloat(t.exit_price) > 0);
  const openTrades = filteredTrades.filter(t => !t.exit_price || parseFloat(t.exit_price) === 0);
  const totalPnl = closedTrades.reduce((sum, t) => {
    const entry = parseFloat(t.entry_price) || 0;
    const exit = parseFloat(t.exit_price) || 0;
    const qty = parseInt(t.quantity) || 1;
    const mult = t.action === "buy" ? 1 : -1;
    return sum + (exit - entry) * qty * 100 * mult;
  }, 0);
  const wins = closedTrades.filter(t => {
    const entry = parseFloat(t.entry_price) || 0;
    const exit = parseFloat(t.exit_price) || 0;
    return t.action === "buy" ? exit > entry : exit < entry;
  }).length;
  const winRate = closedTrades.length > 0 ? (wins / closedTrades.length * 100).toFixed(0) : "—";
  const avgWin = wins > 0 ? closedTrades.filter(t => {
    const entry = parseFloat(t.entry_price) || 0;
    const exit = parseFloat(t.exit_price) || 0;
    return t.action === "buy" ? exit > entry : exit < entry;
  }).reduce((s, t) => s + (parseFloat(t.exit_price) - parseFloat(t.entry_price)) * parseInt(t.quantity) * 100 * (t.action === "buy" ? 1 : -1), 0) / wins : 0;
  const avgLoss = (closedTrades.length - wins) > 0 ? closedTrades.filter(t => {
    const entry = parseFloat(t.entry_price) || 0;
    const exit = parseFloat(t.exit_price) || 0;
    return t.action === "buy" ? exit <= entry : exit >= entry;
  }).reduce((s, t) => s + (parseFloat(t.exit_price) - parseFloat(t.entry_price)) * parseInt(t.quantity) * 100 * (t.action === "buy" ? 1 : -1), 0) / (closedTrades.length - wins) : 0;

  // Daily P&L aggregation
  const dailyPnl = useMemo(() => {
    const map = {};
    closedTrades.forEach(t => {
      const date = t.exit_date || t.entry_date || "unknown";
      const entry = parseFloat(t.entry_price) || 0;
      const exit = parseFloat(t.exit_price) || 0;
      const qty = parseInt(t.quantity) || 1;
      const mult = t.action === "buy" ? 1 : -1;
      const pnl = (exit - entry) * qty * 100 * mult;
      map[date] = (map[date] || 0) + pnl;
    });
    return Object.entries(map)
      .sort((a, b) => b[0].localeCompare(a[0]))
      .slice(0, 14);
  }, [closedTrades]);

  const maxDailyPnl = dailyPnl.length > 0 ? Math.max(...dailyPnl.map(([, v]) => Math.abs(v)), 1) : 1;

  return (
    <div className="p-4 flex-1 overflow-auto">
      <div className="max-w-4xl mx-auto space-y-3">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <div className="text-lg font-bold tracking-wider">TRADE JOURNAL</div>
            <div className="text-[10px] text-slate-500">Track every trade. Learn from wins and losses.</div>
          </div>
          <div className="flex items-center gap-2">
            {uniqueTickers.length > 1 && (
              <select
                value={filterTicker}
                onChange={e => setFilterTicker(e.target.value)}
                className="bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[10px] text-slate-300"
              >
                <option value="">All Tickers</option>
                {uniqueTickers.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            )}
            <button onClick={() => { setShowAdd(!showAdd); setEditingId(null); }} className="btn text-[11px]">
              {showAdd ? "Cancel" : "+ Add Trade"}
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="panel p-3">
          <div className="grid grid-cols-3 gap-3 text-center mb-2">
            <div>
              <div className="label">Total P&L</div>
              <div className={`text-xl mono font-bold ${totalPnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                {totalPnl >= 0 ? "+" : ""}${fmt(totalPnl, 0)}
              </div>
            </div>
            <div>
              <div className="label">Win Rate</div>
              <div className="text-xl mono font-bold text-slate-200">{winRate}%</div>
            </div>
            <div>
              <div className="label">Trades</div>
              <div className="text-xl mono font-bold text-slate-200">{closedTrades.length}W / {closedTrades.length - wins}L</div>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3 text-center text-[10px]">
            <div>
              <span className="text-slate-500">Avg Win: </span>
              <span className="mono text-emerald-400">+${fmt(avgWin, 0)}</span>
            </div>
            <div>
              <span className="text-slate-500">Avg Loss: </span>
              <span className="mono text-rose-400">${fmt(avgLoss, 0)}</span>
            </div>
            <div>
              <span className="text-slate-500">Open: </span>
              <span className="mono text-amber-400">{openTrades.length} positions</span>
            </div>
          </div>
        </div>

        {/* Daily P&L Chart */}
        {dailyPnl.length > 0 && (
          <div className="panel p-3">
            <div className="label mb-2">Daily P&L (Last {dailyPnl.length} days)</div>
            <div className="flex items-end gap-1 h-20">
              {dailyPnl.map(([date, pnl]) => {
                const isPos = pnl >= 0;
                const height = Math.min(100, Math.abs(pnl) / maxDailyPnl * 100);
                return (
                  <div key={date} className="flex-1 flex flex-col items-center gap-0.5 group relative">
                    <div className="absolute -top-6 hidden group-hover:block bg-slate-800 border border-slate-700 rounded px-1 py-0.5 text-[8px] mono z-10 whitespace-nowrap">
                      {isPos ? "+" : ""}${fmt(pnl, 0)}
                    </div>
                    <div
                      className={`w-full rounded-sm min-h-[2px] transition-all ${isPos ? "bg-emerald-500/70" : "bg-rose-500/70"}`}
                      style={{ height: `${Math.max(height, 4)}%` }}
                    />
                    <div className="text-[7px] text-slate-600 truncate w-full text-center">{date.slice(5)}</div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Add/Edit Trade Form */}
        {showAdd && (
          <div className="panel p-3">
            <div className="label mb-2">{editingId ? "Edit Trade" : "New Trade"}</div>
            <div className="grid grid-cols-3 gap-2 mb-2">
              <div>
                <div className="label mb-0.5">Ticker</div>
                <input value={newTrade.ticker} onChange={e => setNewTrade({...newTrade, ticker: e.target.value.toUpperCase()})}
                  className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200" />
              </div>
              <div>
                <div className="label mb-0.5">Type</div>
                <select value={newTrade.type} onChange={e => setNewTrade({...newTrade, type: e.target.value})}
                  className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200">
                  <option value="call">Call</option>
                  <option value="put">Put</option>
                </select>
              </div>
              <div>
                <div className="label mb-0.5">Action</div>
                <select value={newTrade.action} onChange={e => setNewTrade({...newTrade, action: e.target.value})}
                  className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200">
                  <option value="buy">Buy</option>
                  <option value="sell">Sell</option>
                </select>
              </div>
              <div>
                <div className="label mb-0.5">Strike</div>
                <input type="number" value={newTrade.strike} onChange={e => setNewTrade({...newTrade, strike: e.target.value})}
                  className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200" />
              </div>
              <div>
                <div className="label mb-0.5">Expiry</div>
                <input type="date" value={newTrade.expiry} onChange={e => setNewTrade({...newTrade, expiry: e.target.value})}
                  className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200" />
              </div>
              <div>
                <div className="label mb-0.5">Qty</div>
                <input type="number" value={newTrade.quantity} onChange={e => setNewTrade({...newTrade, quantity: e.target.value})}
                  className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200" />
              </div>
              <div>
                <div className="label mb-0.5">Entry $</div>
                <input type="number" step="0.01" value={newTrade.entry_price} onChange={e => setNewTrade({...newTrade, entry_price: e.target.value})}
                  className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200" />
              </div>
              <div>
                <div className="label mb-0.5">Exit $</div>
                <input type="number" step="0.01" value={newTrade.exit_price} onChange={e => setNewTrade({...newTrade, exit_price: e.target.value})}
                  className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200" />
              </div>
              <div>
                <div className="label mb-0.5">GEX Regime</div>
                <select value={newTrade.gex_regime} onChange={e => setNewTrade({...newTrade, gex_regime: e.target.value})}
                  className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200">
                  <option value="">—</option>
                  <option value="positive_gamma">Positive Gamma</option>
                  <option value="negative_gamma">Negative Gamma</option>
                  <option value="transitioning">Transitioning</option>
                </select>
              </div>
              <div>
                <div className="label mb-0.5">Setup</div>
                <input value={newTrade.setup} onChange={e => setNewTrade({...newTrade, setup: e.target.value})}
                  placeholder="e.g., IC at walls, straddle breakout"
                  className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200" />
              </div>
            </div>
            <div className="mb-2">
              <div className="label mb-0.5">Notes</div>
              <textarea value={newTrade.notes} onChange={e => setNewTrade({...newTrade, notes: e.target.value})}
                placeholder="Why did you enter this trade? What was the thesis?"
                className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 h-16 resize-none" />
            </div>
            <button onClick={editingId ? handleUpdate : handleAdd} className="btn w-full text-[11px]">
              {editingId ? "Update Trade" : "Save Trade"}
            </button>
          </div>
        )}

        {/* Open Trades */}
        {openTrades.length > 0 && (
          <div>
            <div className="label mb-1">Open Positions ({openTrades.length})</div>
            <div className="space-y-1">
              {openTrades.map(trade => (
                <TradeRow key={trade.id} trade={trade} onClose={handleClose} onDelete={handleDelete} onEdit={handleEdit} />
              ))}
            </div>
          </div>
        )}

        {/* Closed Trades */}
        {closedTrades.length > 0 && (
          <div>
            <div className="label mb-1">Closed Trades ({closedTrades.length})</div>
            <div className="space-y-1">
              {closedTrades.map(trade => (
                <TradeRow key={trade.id} trade={trade} onClose={handleClose} onDelete={handleDelete} onEdit={handleEdit} />
              ))}
            </div>
          </div>
        )}

        {filteredTrades.length === 0 && (
          <div className="panel p-6 text-center text-slate-500 text-[11px]">
            {trades.length === 0 ? "No trades yet. Add your first trade above." : "No trades match the filter."}
          </div>
        )}
      </div>
    </div>
  );
}

function TradeRow({ trade, onClose, onDelete, onEdit }) {
  const [exitPrice, setExitPrice] = useState("");
  const entry = parseFloat(trade.entry_price) || 0;
  const exit = parseFloat(trade.exit_price) || 0;
  const qty = parseInt(trade.quantity) || 1;
  const isClosed = exit > 0;
  const pnl = isClosed ? (exit - entry) * qty * 100 * (trade.action === "buy" ? 1 : -1) : 0;
  const isWinner = pnl > 0;

  return (
    <div className={`panel p-2 text-[10px] ${isClosed ? (isWinner ? "border-emerald-500/20" : "border-rose-500/20") : ""}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`font-bold ${trade.type === "call" ? "text-teal-400" : "text-purple-400"}`}>
            {trade.type.toUpperCase()}
          </span>
          <span className={`font-bold ${trade.action === "buy" ? "text-emerald-400" : "text-rose-400"}`}>
            {trade.action.toUpperCase()}
          </span>
          <span className="text-slate-300">{trade.ticker}</span>
          <span className="mono">{trade.strike}</span>
          <span className="text-slate-500">{trade.expiry}</span>
          <span className="text-slate-500">x{qty}</span>
        </div>
        <div className="flex items-center gap-2">
          {isClosed ? (
            <span className={`mono font-bold ${isWinner ? "text-emerald-400" : "text-rose-400"}`}>
              {pnl >= 0 ? "+" : ""}${fmt(pnl, 0)}
            </span>
          ) : (
            <div className="flex items-center gap-1">
              <input type="number" step="0.01" value={exitPrice} onChange={e => setExitPrice(e.target.value)}
                placeholder="Exit $"
                className="w-16 bg-slate-800/60 border border-slate-700 rounded px-1 py-0.5 text-[10px] text-slate-200" />
              <button onClick={() => onClose(trade.id, parseFloat(exitPrice) || 0)} className="btn text-[9px] px-1 py-0.5">Close</button>
            </div>
          )}
          {!isClosed && (
            <button onClick={() => onEdit(trade)} className="text-slate-500 hover:text-teal-400 text-[9px]">✎</button>
          )}
          <button onClick={() => onDelete(trade.id)} className="text-rose-400 hover:text-rose-300 text-[9px]">✕</button>
        </div>
      </div>
      <div className="flex items-center gap-2 mt-0.5 text-[9px] text-slate-500">
        <span>Entry: ${entry.toFixed(2)}</span>
        {isClosed && <span>Exit: ${exit.toFixed(2)}</span>}
        {trade.gex_regime && <span>• GEX: {trade.gex_regime.replace("_", " ")}</span>}
        {trade.setup && <span>• {trade.setup}</span>}
      </div>
      {trade.notes && <div className="text-[9px] text-slate-600 mt-0.5 italic">{trade.notes}</div>}
    </div>
  );
}
