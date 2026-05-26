import React, { useState, useEffect } from "react";
import axios from "axios";
import { fmt, fmtAbs } from "../lib/helpers";
import { BACKEND_URL, API } from "../config/api";

// API imported from config/api.js

export default function HistoryPanel({ ticker }) {
  const [snapshots, setSnapshots] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!ticker || !open) return;
    setLoading(true);
    axios.get(`${API}/history/${ticker}?limit=10`)
      .then((r) => setSnapshots(r.data.snapshots || []))
      .catch(() => setSnapshots([]))
      .finally(() => setLoading(false));
  }, [ticker, open]);

  return (
    <div className="panel-2 p-2">
      <button
        className="flex items-center justify-between w-full text-left"
        onClick={() => setOpen(!open)}
        style={{ background: "none", border: "none", padding: 0, cursor: "pointer" }}
      >
        <div className="label mb-0">History</div>
        <span className="text-slate-500 text-[10px]">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="mt-1.5">
          {loading && <div className="text-slate-500 text-[10px]">Loading…</div>}
          {!loading && snapshots.length === 0 && (
            <div className="text-slate-500 text-[10px]">No snapshots yet</div>
          )}
          {snapshots.length > 0 && (
            <div className="space-y-1">
              {snapshots.map((s, i) => {
                const ts = s.ts ? new Date(s.ts) : null;
                const spot = s.spot || s.spot_price;
                const totalGex = s.total_gex || s.net_gex;
                const regime = s.regime || s.nodes?.regime;
                return (
                  <div key={i} className="text-[9px] px-1.5 py-1 bg-slate-800/40 rounded">
                    <div className="flex justify-between items-center">
                      <span className="text-slate-500">
                        {ts ? ts.toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "—"}
                        {ts && <span className="ml-1">{ts.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false })}</span>}
                      </span>
                      {regime && (
                        <span className={`mono ${regime === "positive" ? "text-emerald-400" : regime === "negative" ? "text-rose-400" : "text-slate-400"}`}>
                          {regime}
                        </span>
                      )}
                    </div>
                    <div className="flex justify-between mt-0.5">
                      <span className="text-slate-400">Spot: <span className="mono text-slate-300">{spot ? fmt(spot, 1) : "—"}</span></span>
                      {totalGex !== undefined && (
                        <span className={`mono ${totalGex > 0 ? "text-emerald-400" : "text-rose-400"}`}>
                          GEX: {fmtAbs(totalGex)}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
