import React, { useEffect, useState, useMemo, useRef, useCallback } from "react";
import axios from "axios";
import { fmt, fmtAbs, pctClass } from "../lib/helpers";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SORT_OPTIONS = [
  { v: "strike", l: "Strike" }, { v: "expiry", l: "Expiry" },
  { v: "oi", l: "OI" }, { v: "volume", l: "Vol" },
  { v: "iv", l: "IV" }, { v: "delta", l: "Delta" },
  { v: "gamma", l: "Gamma" }, { v: "gex", l: "GEX" },
  { v: "vanna", l: "Vanna" }, { v: "charm", l: "Charm" },
];

export default function OptionsChainTable({ ticker, spot }) {
  const [chain, setChain] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expiry, setExpiry] = useState("");
  const [moneyness, setMoneyness] = useState("all");
  const [minOi, setMinOi] = useState(100);
  const [sortBy, setSortBy] = useState("strike");
  const [sortDir, setSortDir] = useState("asc");
  const [side, setSide] = useState("all"); // all, calls, puts

  const fetchChain = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        min_oi: minOi, sort_by: sortBy, sort_dir: sortDir,
        moneyness: moneyness === "all" ? "" : moneyness,
      });
      if (expiry) params.set("expiry", expiry);
      const res = await axios.get(`${API}/chain/${ticker}?${params}`);
      setChain(res.data);
    } catch (e) { /* noop */ }
    setLoading(false);
  }, [ticker, expiry, moneyness, minOi, sortBy, sortDir]);

  useEffect(() => { fetchChain(); }, [fetchChain]);

  const filtered = useMemo(() => {
    if (!chain?.rows) return [];
    if (side === "calls") return chain.rows.filter(r => r.type === "call");
    if (side === "puts") return chain.rows.filter(r => r.type === "put");
    return chain.rows;
  }, [chain, side]);

  const toggleSort = (col) => {
    if (sortBy === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortBy(col); setSortDir("desc"); }
  };

  const sortArrow = (col) => {
    if (sortBy !== col) return " ";
    return sortDir === "asc" ? " ↑" : " ↓";
  };

  const ROW_HEIGHT = 22;
  const VISIBLE_ROWS = 40;
  const BUFFER = 10;
  const scrollRef = useRef(null);
  const [scrollTop, setScrollTop] = useState(0);

  const totalHeight = filtered.length * ROW_HEIGHT;
  const startIdx = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - BUFFER);
  const endIdx = Math.min(filtered.length, startIdx + VISIBLE_ROWS + BUFFER * 2);
  const visibleRows = useMemo(() => filtered.slice(startIdx, endIdx), [filtered, startIdx, endIdx]);
  const offsetY = startIdx * ROW_HEIGHT;

  const onScroll = useCallback((e) => {
    setScrollTop(e.target.scrollTop);
  }, []);

  // Reset scroll when filters change
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = 0;
    setScrollTop(0);
  }, [side, moneyness, expiry, minOi, sortBy, sortDir, ticker]);

  if (loading && !chain) return <div className="panel p-3 text-slate-500 text-xs">Loading chain…</div>;

  return (
    <div className="panel p-2">
      <div className="label mb-2">Options Chain {chain ? `(${filtered.length}/${chain.count})` : ""}</div>

      {/* Filters */}
      <div className="flex flex-wrap gap-1 mb-2">
        {["all", "calls", "puts"].map(s => (
          <button key={s} onClick={() => setSide(s)} className={`btn text-[9px] px-1.5 py-0.5 ${side === s ? "active" : ""}`}>{s.toUpperCase()}</button>
        ))}
        <select value={moneyness} onChange={e => setMoneyness(e.target.value)} className="btn text-[9px] px-1 py-0.5">
          <option value="all">All</option>
          <option value="itm">ITM</option>
          <option value="otm">OTM</option>
          <option value="atm">ATM</option>
        </select>
        <select value={expiry} onChange={e => setExpiry(e.target.value)} className="btn text-[9px] px-1 py-0.5">
          <option value="">All Expiries</option>
          {chain?.expiries?.map(e => <option key={e} value={e}>{e}</option>)}
        </select>
        <input type="number" value={minOi} onChange={e => setMinOi(Number(e.target.value))}
          className="btn text-[9px] px-1 py-0.5 w-16" placeholder="Min OI" />
        <select value={sortBy} onChange={e => setSortBy(e.target.value)} className="btn text-[9px] px-1 py-0.5">
          {SORT_OPTIONS.map(o => <option key={o.v} value={o.v}>Sort: {o.l}</option>)}
        </select>
        <button onClick={() => setSortDir(d => d === "asc" ? "desc" : "asc")} className="btn text-[9px] px-1.5 py-0.5">
          {sortDir === "asc" ? "↑" : "↓"}
        </button>
        {chain?.rows?.length > 0 && (
          <button onClick={() => {
            const cols = ["type","strike","expiry","dte","iv","delta","gamma","oi","volume","gex","vanna","charm","moneyness_pct"];
            const header = cols.join(",");
            const rows = filtered.map(r => cols.map(c => r[c] ?? "").join(",")).join("\n");
            const blob = new Blob([header + "\n" + rows], {type: "text/csv"});
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url; a.download = `${ticker}_chain_${new Date().toISOString().slice(0,10)}.csv`;
            a.click(); URL.revokeObjectURL(url);
          }} className="btn text-[9px] px-1.5 py-0.5">CSV</button>
        )}
      </div>

      {/* Table with virtual scrolling */}
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="overflow-auto text-[9px]"
        style={{ maxHeight: VISIBLE_ROWS * ROW_HEIGHT + 40 }}
      >
        <div style={{ height: totalHeight, position: "relative" }}>
          <table className="w-full border-collapse" style={{ position: "absolute", top: offsetY }}>
            <thead className="sticky top-0" style={{ background: "var(--panel)" }}>
              <tr>
                <th className="text-left px-1 py-0.5 text-slate-500">Type</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("strike")}>K{sortArrow("strike")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("expiry")}>Exp{sortArrow("expiry")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500">DTE</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("iv")}>IV{sortArrow("iv")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("delta")}>Δ{sortArrow("delta")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("gamma")}>Γ{sortArrow("gamma")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("oi")}>OI{sortArrow("oi")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("volume")}>Vol{sortArrow("volume")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("gex")}>GEX{sortArrow("gex")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("vanna")}>Vanna{sortArrow("vanna")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500 cursor-pointer" onClick={() => toggleSort("charm")}>Charm{sortArrow("charm")}</th>
                <th className="text-right px-1 py-0.5 text-slate-500">Moneyness</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((r, i) => {
                const actualIdx = startIdx + i;
                const isCall = r.type === "call";
                const gexClass = r.gex > 0 ? "text-teal-400" : r.gex < 0 ? "text-purple-400" : "text-slate-500";
                const nearSpot = spot && Math.abs(r.strike - spot) / spot < 0.01;
                return (
                  <tr key={actualIdx} style={{ height: ROW_HEIGHT }} className={`${nearSpot ? "bg-slate-700/30" : ""} hover:bg-slate-700/20`}>
                    <td className={`px-1 py-0.5 font-bold ${isCall ? "text-teal-400" : "text-purple-400"}`}>{isCall ? "C" : "P"}</td>
                    <td className="text-right px-1 py-0.5 mono">{r.strike.toFixed(r.strike < 10 ? 2 : 0)}</td>
                    <td className="text-right px-1 py-0.5 text-slate-400">{r.expiry?.slice(5)}</td>
                    <td className="text-right px-1 py-0.5 text-slate-400">{r.dte}</td>
                    <td className="text-right px-1 py-0.5 mono">{(r.iv * 100).toFixed(1)}%</td>
                    <td className="text-right px-1 py-0.5 mono">{r.delta.toFixed(2)}</td>
                    <td className="text-right px-1 py-0.5 mono">{r.gamma.toFixed(4)}</td>
                    <td className="text-right px-1 py-0.5">{r.oi >= 1000 ? (r.oi / 1000).toFixed(1) + "K" : r.oi}</td>
                    <td className="text-right px-1 py-0.5">{r.volume >= 1000 ? (r.volume / 1000).toFixed(1) + "K" : r.volume}</td>
                    <td className={`text-right px-1 py-0.5 mono ${gexClass}`}>{fmtAbs(r.gex)}</td>
                    <td className="text-right px-1 py-0.5 mono">{fmtAbs(r.vanna)}</td>
                    <td className="text-right px-1 py-0.5 mono">{fmtAbs(r.charm)}</td>
                    <td className={`text-right px-1 py-0.5 mono ${pctClass(r.moneyness_pct)}`}>{r.moneyness_pct > 0 ? "+" : ""}{r.moneyness_pct.toFixed(1)}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
