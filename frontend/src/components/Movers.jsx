import React, { useState, useEffect } from "react";
import axios from "axios";
import { BACKEND_URL, API } from "../config/api";

// API imported from config/api.js
const fmt = (n, d = 2) => (n === null || n === undefined || isNaN(n)) ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });
const pctClass = (v) => v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "text-slate-400";

export default function Movers({ onPick }) {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    let mounted = true;
    const f = async () => {
      try {
        const res = await axios.get(`${API}/movers?limit=12`);
        if (mounted) setRows(res.data.results || []);
      } catch (e) { /* noop */ }
    };
    f();
    const id = setInterval(f, 60000);
    return () => { mounted = false; clearInterval(id); };
  }, []);
  return (
    <div className="panel p-3" data-testid="movers-panel">
      <div className="label mb-2">Top Movers (prev session %)</div>
      <div className="flex flex-col gap-1 text-[11px]">
        {rows.length === 0 && <div className="text-slate-500">…</div>}
        {rows.map((r) => (
          <button key={r.ticker} data-testid={`mover-${r.ticker}`} onClick={() => onPick && onPick(r.ticker)}
            className="flex justify-between items-center px-2 py-1 hover:bg-slate-800/40 rounded">
            <span className="font-bold w-14 text-left">{r.ticker}</span>
            <span className="mono text-slate-400 w-20 text-right">${fmt(r.close, 2)}</span>
            <span className={`mono w-16 text-right ${pctClass(r.pct)}`}>{r.pct >= 0 ? "+" : ""}{r.pct}%</span>
          </button>
        ))}
      </div>
    </div>
  );
}
