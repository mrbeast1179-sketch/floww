import React, { useState, useEffect } from "react";
import { fmt, fmtAbs, pctClass } from "../lib/helpers";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export function TradeJournal({ ticker }) {
  const [trades, setTrades] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
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

  const handleDelete = (id) => {
    setTrades(prev => prev.filter(t => t.id !== id));
  };

  const handleClose = (id, exitPrice) => {
    setTrades(prev => prev.map(t =>
      t.id === id ? { ...t, exit_price: exitPrice, exit_date: new Date().toISOString().slice(0, 10) } : t
    ));
  };

  // Calculate stats
  const closedTrades = trades.filter(t => t.exit_price && parseFloat(t.exit_price) > 0);
  const openTrades = trades.filter(t => !t.exit_price || parseFloat(t.exit_price) === 0);
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

  return (
    <div className="p-4 flex-1 overflow-auto">
      <div className="max-w-4xl mx-auto space-y-3">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <div className="text-lg font-bold tracking-wider">TRADE JOURNAL</div>
            <div className="text-[10px] text-slate-500">Track every trade. Learn from wins and losses.</div>
          </div>
          <button onClick={() => setShowAdd(!showAdd)} className="btn text-[11px]">
            {showAdd ? "Cancel" : "+ Add Trade"}
          </button>
        </div>

        {/* Stats */}
        <div className="panel p-3">
          <div className="grid grid-cols-4 gap-3 text-center">
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
              <div className="label">Closed</div>
              <div className="text-xl mono font-bold text-slate-200">{closedTrades.length}</div>
            </div>
            <div>
              <div className="label">Open</div>
              <div className="text-xl mono font-bold text-amber-400">{openTrades.length}</div>
            </div>
          </div>
        </div>

        {/* Add Trade Form */}
        {showAdd && (
          <div className="panel p-3">
            <div className="label mb-2">New Trade</div>
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
            <button onClick={handleAdd} className="btn w-full text-[11px]">Save Trade</button>
          </div>
        )}

        {/* Open Trades */}
        {openTrades.length > 0 && (
          <div>
            <div className="label mb-1">Open Positions ({openTrades.length})</div>
            <div className="space-y-1">
              {openTrades.map(trade => (
                <TradeRow key={trade.id} trade={trade} onClose={handleClose} onDelete={handleDelete} />
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
                <TradeRow key={trade.id} trade={trade} onClose={handleClose} onDelete={handleDelete} />
              ))}
            </div>
          </div>
        )}

        {trades.length === 0 && (
          <div className="panel p-6 text-center text-slate-500 text-[11px]">
            No trades yet. Add your first trade above.
          </div>
        )}
      </div>
    </div>
  );
}

function TradeRow({ trade, onClose, onDelete }) {
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
