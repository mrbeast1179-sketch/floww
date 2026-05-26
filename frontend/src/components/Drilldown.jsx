import React, { useState, useEffect } from "react";
import axios from "axios";
import { BACKEND_URL, API } from "../config/api";

// API imported from config/api.js
const fmt = (n, d = 2) => (n === null || n === undefined || isNaN(n)) ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });
const fmtAbs = (n) => {
  if (n === null || n === undefined || isNaN(n)) return "—";
  const a = Math.abs(n);
  if (a >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return n.toFixed(0);
};

export default function Drilldown({ ticker, expiry, strike, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    const params = new URLSearchParams();
    if (expiry) params.set("expiry", expiry);
    if (strike) params.set("strike", strike);
    axios.get(`${API}/contract/${encodeURIComponent(ticker)}?${params.toString()}`)
      .then(r => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [ticker, expiry, strike]);
  if (!data && !loading) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.7)" }} onClick={onClose}>
      <div className="panel p-4 max-w-4xl w-[90%] max-h-[80vh] overflow-auto" onClick={(e) => e.stopPropagation()} data-testid="drilldown-modal">
        <div className="flex justify-between items-center mb-3">
          <div>
            <div className="label">Contract Drilldown</div>
            <div className="text-lg font-bold">{ticker} {strike ? `· ${strike}` : ""} {expiry ? `· ${expiry}` : ""}</div>
          </div>
          <button onClick={onClose} className="btn" data-testid="drilldown-close">close ✕</button>
        </div>
        {loading && <div className="text-slate-500">loading…</div>}
        {data && (
          <div>
            <div className="text-[11px] text-slate-500 mb-2">Spot {fmt(data.spot, 2)} · {data.count} contracts · source {data.data_source}</div>
            {data.count === 0 ? (
              <div className="text-slate-500 text-xs py-8 text-center">
                No contracts at this strike × expiry combination.
                <div className="text-[10px] text-slate-600 mt-1">(Empty cells = no OI or no IV data available for this leg.)</div>
              </div>
            ) : (
            <table className="w-full text-[11px] mono">
              <thead className="text-slate-500 text-[10px] uppercase tracking-widest">
                <tr>
                  <th className="text-left px-2 py-1">Type</th>
                  <th className="text-left px-2 py-1">Strike</th>
                  <th className="text-left px-2 py-1">Expiry</th>
                  <th className="text-right px-2 py-1">OI</th>
                  <th className="text-right px-2 py-1">Volume</th>
                  <th className="text-right px-2 py-1">IV</th>
                  <th className="text-right px-2 py-1">Δ</th>
                  <th className="text-right px-2 py-1">Γ</th>
                  <th className="text-right px-2 py-1">GEX</th>
                  <th className="text-left px-2 py-1">Src</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r, i) => (
                  <tr key={i} className="bar-row border-t border-slate-800/60">
                    <td className={`px-2 py-1 ${r.type === "call" ? "text-emerald-400" : "text-rose-400"}`}>{r.type}</td>
                    <td className="px-2 py-1 font-bold">{fmt(r.strike, 0)}</td>
                    <td className="px-2 py-1 text-slate-400">{r.expiry}</td>
                    <td className="px-2 py-1 text-right">{fmt(r.oi, 0)}</td>
                    <td className="px-2 py-1 text-right text-slate-500">{fmt(r.volume, 0)}</td>
                    <td className="px-2 py-1 text-right text-slate-400">{(r.iv * 100).toFixed(1)}%</td>
                    <td className="px-2 py-1 text-right text-slate-400">{r.delta?.toFixed(3)}</td>
                    <td className="px-2 py-1 text-right text-slate-500">{r.gamma?.toFixed(5)}</td>
                    <td className={`px-2 py-1 text-right ${r.gex > 0 ? "text-emerald-400" : "text-rose-400"}`}>{fmtAbs(r.gex)}</td>
                    <td className="px-2 py-1 text-[10px] text-slate-600">{r.oi_source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
