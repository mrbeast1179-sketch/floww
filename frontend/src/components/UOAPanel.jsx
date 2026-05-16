import React, { useEffect, useState } from "react";
import axios from "axios";
import { fmtAbs, pctClass } from "../lib/helpers";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SENTIMENT_COLOR = {
  bullish: "text-emerald-400",
  bearish: "text-rose-400",
  "mildly bullish": "text-emerald-300/70",
  "mildly bearish": "text-rose-300/70",
};

const SENTIMENT_BG = {
  bullish: "bg-emerald-500/10 border-emerald-500/20",
  bearish: "bg-rose-500/10 border-rose-500/20",
  "mildly bullish": "bg-emerald-500/5 border-emerald-500/10",
  "mildly bearish": "bg-rose-500/5 border-rose-500/10",
};

export default function UOAPanel({ ticker }) {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(true);
  const [minPremium, setMinPremium] = useState(50000);

  useEffect(() => {
    if (!ticker) return;
    axios.get(`${API}/uoa/${ticker}?min_premium=${minPremium}`).then(r => setData(r.data)).catch(() => {});
  }, [ticker, minPremium]);

  if (!data) return null;

  return (
    <div className="panel-2 p-2">
      <button className="flex items-center justify-between w-full text-left" onClick={() => setOpen(!open)}
        style={{ background: "none", border: "none", padding: 0, cursor: "pointer" }}>
        <div className="label mb-0">
          Unusual Options Activity
          {data.count > 0 && (
            <span className="ml-1 text-[8px] px-1 py-px rounded bg-amber-500/20 text-amber-400">
              {data.count}
            </span>
          )}
        </div>
        <span className="text-slate-500 text-[10px]">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="mt-1.5 space-y-1.5">
          {/* Stats bar */}
          <div className="flex justify-between text-[8px] text-slate-500 px-1">
            <span>Scanned: {data.stats?.total_contracts_scanned}</span>
            <span>Avg Vol: {fmtAbs(data.stats?.avg_volume)}</span>
            <span>Avg OI: {fmtAbs(data.stats?.avg_oi)}</span>
          </div>

          {/* Premium filter */}
          <div className="flex gap-1">
            {[10000, 50000, 100000, 500000].map(v => (
              <button key={v} onClick={() => setMinPremium(v)}
                className={`btn text-[8px] flex-1 ${minPremium === v ? "active" : ""}`}>
                ${v >= 1000 ? (v / 1000) + "K" : v}
              </button>
            ))}
          </div>

          {/* UOA list */}
          {data.unusual?.length === 0 ? (
            <div className="text-[9px] text-slate-500 p-2 text-center">No unusual activity above threshold</div>
          ) : (
            <div className="space-y-1">
              {(data.unusual || []).slice(0, 15).map((u, i) => (
                <div key={i} className={`rounded px-2 py-1 border ${SENTIMENT_BG[u.sentiment] || "bg-slate-800/50 border-slate-700"}`}>
                  <div className="flex justify-between items-baseline">
                    <div className="flex items-center gap-1">
                      <span className={`text-[9px] font-bold ${u.type === "call" ? "text-teal-400" : "text-purple-400"}`}>
                        {u.type === "call" ? "C" : "P"}
                      </span>
                      <span className="text-[10px] font-bold mono">{u.strike.toFixed(u.strike < 10 ? 2 : 0)}</span>
                      <span className="text-[8px] text-slate-500">{u.expiry?.slice(5)} ({u.dte}d)</span>
                    </div>
                    <div className="flex items-center gap-1">
                      <span className={`text-[8px] font-bold ${SENTIMENT_COLOR[u.sentiment] || "text-slate-400"}`}>
                        {u.sentiment}
                      </span>
                      <span className="text-[9px] mono text-amber-400">⚡{u.score}</span>
                    </div>
                  </div>
                  <div className="flex justify-between text-[8px] mt-0.5">
                    <span className="text-slate-400">Vol: {u.volume >= 1000 ? (u.volume / 1000).toFixed(1) + "K" : u.volume} · OI: {u.oi >= 1000 ? (u.oi / 1000).toFixed(1) + "K" : u.oi}</span>
                    <span className="text-slate-400">${fmtAbs(u.premium)}</span>
                  </div>
                  <div className="flex flex-wrap gap-1 mt-0.5">
                    {u.signals?.map((s, j) => (
                      <span key={j} className="text-[7px] px-1 py-px rounded bg-slate-700/50 text-slate-400">{s}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
