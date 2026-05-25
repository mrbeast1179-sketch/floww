import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function PaperTrade({ ticker, spot }) {
  const [portfolio, setPortfolio] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    symbol: ticker || "SPY",
    option_type: "call",
    strike: "",
    expiry: "",
    quantity: "1",
    is_long: true,
    entry_price: "",
  });

  const fetchPortfolio = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const res = await axios.get(`${API}/paper-trading/portfolio`);
      setPortfolio(res.data);
    } catch (e) {
      setErr(e.response?.data?.detail ?? e.message);
      setPortfolio(null);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchPortfolio();
  }, [fetchPortfolio]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErr(null);
    const entryPrice = form.entry_price ? parseFloat(form.entry_price) : undefined;
    const side = form.is_long ? "buy" : "sell";
    try {
      await axios.post(`${API}/paper-trading/execute`, {
        order_id: `paper-${Date.now()}`,
        market: {
          symbol: form.symbol,
          bid: entryPrice ?? spot ?? 0,
          ask: entryPrice ? entryPrice * 1.01 : (spot ?? 0) * 1.01,
          last: entryPrice ?? spot ?? 0,
          bid_size: 100,
          ask_size: 100,
          volume: 1000000,
          volatility: 0.15,
        },
        symbol: form.symbol,
        option_type: form.option_type,
        strike: parseFloat(form.strike),
        expiry: form.expiry,
        quantity: parseInt(form.quantity),
        is_long: form.is_long,
        entry_price: entryPrice,
      });
      await fetchPortfolio();
      setForm((f) => ({
        ...f,
        strike: "",
        expiry: "",
        quantity: "1",
        entry_price: "",
      }));
    } catch (e) {
      setErr(e.response?.data?.detail ?? e.message);
    }
  };

  return (
    <div className="panel p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-lg font-bold tracking-wider">PAPER TRADE</div>
        <button onClick={fetchPortfolio} className="btn text-[10px]" disabled={loading}>
          {loading ? "…" : "Refresh"}
        </button>
      </div>

      {err && <div className="text-rose-400 text-[11px] bg-rose-900/20 rounded px-3 py-2">{err}</div>}

      {/* Portfolio Summary */}
      {portfolio ? (
        <div className="panel p-3 space-y-2">
          <div className="label mb-1">Portfolio Summary</div>
          <div className="grid grid-cols-3 gap-3 text-center">
            <div>
              <div className="label">Total P&L</div>
              <div className={`text-lg mono font-bold ${
                (portfolio?.total_pnl ?? 0) > 0 ? "text-emerald-400" :
                (portfolio?.total_pnl ?? 0) < 0 ? "text-rose-400" : "text-slate-300"
              }`}>
                {(portfolio?.total_pnl ?? 0) > 0 ? "+" : ""}
                {(portfolio?.total_pnl)?.toFixed(2) ?? "—"}
              </div>
            </div>
            <div>
              <div className="label">P&L %</div>
              <div className={`text-lg mono font-bold ${
                (portfolio?.total_pnl_pct ?? 0) > 0 ? "text-emerald-400" :
                (portfolio?.total_pnl_pct ?? 0) < 0 ? "text-rose-400" : "text-slate-300"
              }`}>
                {(portfolio?.total_pnl_pct ?? 0) > 0 ? "+" : ""}
                {portfolio?.total_pnl_pct?.toFixed(2) ?? "—"}
              </div>
            </div>
            <div>
              <div className="label">Positions</div>
              <div className="text-lg mono text-slate-300">
                {portfolio?.positions?.length ?? 0}
              </div>
            </div>
          </div>

          {/* Positions table */}
          {portfolio?.positions?.length > 0 && (
            <table className="w-full text-[10px] mono">
              <thead>
                <tr className="text-slate-500">
                  <th className="text-left px-1">Sym</th>
                  <th className="text-left px-1">Type</th>
                  <th className="text-right px-1">Strike</th>
                  <th className="text-right px-1">Qty</th>
                  <th className="text-right px-1">Entry</th>
                  <th className="text-right px-1">P&L</th>
                </tr>
              </thead>
              <tbody>
                {(portfolio?.positions ?? []).map((p, i) => (
                  <tr key={i} className="border-t border-slate-800/60">
                    <td className="px-1 py-0.5">{p.symbol ?? "—"}</td>
                    <td className={`px-1 py-0.5 ${(p.option_type ?? "") === "call" ? "text-emerald-400" : "text-rose-400"}`}>
                      {p.option_type ?? "—"}
                    </td>
                    <td className="text-right px-1 py-0.5">{p.strike?.toFixed(1) ?? "—"}</td>
                    <td className="text-right px-1 py-0.5">{p.quantity ?? "—"}</td>
                    <td className="text-right px-1 py-0.5">{p.entry_price?.toFixed(2) ?? "—"}</td>
                    <td className={`text-right px-1 py-0.5 ${
                      (p.pnl ?? 0) > 0 ? "text-emerald-400" :
                      (p.pnl ?? 0) < 0 ? "text-rose-400" : "text-slate-400"
                    }`}>
                      {p.pnl?.toFixed(2) ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : (
        !err && (
          <div className="panel p-4 text-center text-slate-500 text-[11px]">
            {loading ? "Loading…" : "No portfolio data yet. Submit a trade to get started."}
          </div>
        )
      )}

      {/* Trade Entry Form */}
      <form onSubmit={handleSubmit} className="panel p-3 space-y-2">
        <div className="label mb-1">New Trade</div>
        <div className="grid grid-cols-2 gap-1.5">
          <div>
            <div className="label mb-0.5">Symbol</div>
            <input
              className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none"
              value={form.symbol}
              onChange={(e) => set("symbol", e.target.value.toUpperCase())}
            />
          </div>
          <div>
            <div className="label mb-0.5">Option Type</div>
            <select
              className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none"
              value={form.option_type}
              onChange={(e) => set("option_type", e.target.value)}
            >
              <option value="call">Call</option>
              <option value="put">Put</option>
            </select>
          </div>
          <div>
            <div className="label mb-0.5">Strike</div>
            <input
              type="number" step="0.5"
              className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none"
              value={form.strike}
              onChange={(e) => set("strike", e.target.value)}
              required
            />
          </div>
          <div>
            <div className="label mb-0.5">Expiry</div>
            <input
              type="date"
              className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none"
              value={form.expiry}
              onChange={(e) => set("expiry", e.target.value)}
              required
            />
          </div>
          <div>
            <div className="label mb-0.5">Quantity</div>
            <input
              type="number"
              className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none"
              value={form.quantity}
              onChange={(e) => set("quantity", e.target.value)}
              required
            />
          </div>
          <div>
            <div className="label mb-0.5">Entry Price (opt)</div>
            <input
              type="number" step="0.01"
              placeholder={spot ? String(spot) : ""}
              className="w-full bg-slate-800/60 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 focus:border-teal-500 focus:outline-none"
              value={form.entry_price}
              onChange={(e) => set("entry_price", e.target.value)}
            />
          </div>
        </div>
        <div className="flex gap-2 items-center">
          <label className="flex items-center gap-1 text-[11px] text-slate-400">
            <input
              type="checkbox"
              checked={form.is_long}
              onChange={(e) => set("is_long", e.target.checked)}
              className="accent-teal-500"
            />
            Long
          </label>
        </div>
        <button type="submit" className="btn w-full text-[11px]">
          Submit Trade
        </button>
      </form>
    </div>
  );
}
