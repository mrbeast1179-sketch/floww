import React, { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import { fmt } from "../lib/helpers";

import { API } from "../config/api";

// ============ Flow Tape Viewer ============
export default function FlowTicker({ ticker }) {
  const [trades, setTrades] = useState([]);
  const [status, setStatus] = useState("idle"); // idle | connecting | live | error | ended
  const [error, setError] = useState(null);
  const [stats, setStats] = useState({ totalNotional: 0, sweepCount: 0, blockCount: 0, unusualCount: 0, msgCount: 0 });
  const [filter, setFilter] = useState("all"); // all | sweeps | blocks | unusual
  const [paused, setPaused] = useState(false);
  const pausedRef = useRef(paused);
  useEffect(() => { pausedRef.current = paused; }, [paused]);
  const esRef = useRef(null);
  const tradesRef = useRef([]);
  const maxTrades = 200;

  const connect = useCallback(() => {
    if (!ticker || ticker === "^SPX") return;
    setStatus("connecting");
    setError(null);
    setTrades([]);
    tradesRef.current = [];
    setStats({ totalNotional: 0, sweepCount: 0, blockCount: 0, unusualCount: 0, msgCount: 0 });

    // Close any live stream first — clicking Connect while already connected
    // (or on a ticker change) would otherwise orphan the previous EventSource,
    // which stays open server-side for max_seconds.
    if (esRef.current) esRef.current.close();

    const url = `${API}/flow/${ticker}?max_seconds=300&enforce_window=false`;
    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => setStatus("live");

    es.onmessage = (e) => {
      if (pausedRef.current) return;
      try {
        const trade = JSON.parse(e.data);
        addTrade(trade);
      } catch (err) { /* skip malformed */ }
    };

    const onReady = (e) => {
      try {
        const info = JSON.parse(e.data);
        setStatus("live");
      } catch (err) { /* skip */ }
    };
    const onWarning = (e) => {
      try {
        const warn = JSON.parse(e.data);
        setError(warn.warning || warn.error || "Warning");
      } catch (err) { /* skip */ }
    };
    const onError = (e) => {
      try {
        const err = JSON.parse(e.data);
        setError(err.error || err.detail || "Stream error");
        setStatus("error");
      } catch (err) {
        setError("Stream error");
        setStatus("error");
      }
      es.close();
    };
    const onEnd = () => {
      setStatus("ended");
      es.close();
    };

    es.addEventListener("ready", onReady);
    es.addEventListener("warning", onWarning);
    es.addEventListener("error", onError);
    es.addEventListener("end", onEnd);

    es.onerror = () => {
      if (status === "connecting") {
        setError("Connection failed. Databento Live license may be required.");
        setStatus("error");
      }
      es.close();
    };
  }, [ticker, paused]);
  const rafRef = useRef(null);
  const pendingTradesRef = useRef([]);

  const addTrade = (trade) => {
    pendingTradesRef.current.push(trade);
    // Batch updates with rAF to avoid re-render on every SSE message
    if (!rafRef.current) {
      rafRef.current = requestAnimationFrame(() => {
        const pending = pendingTradesRef.current;
        pendingTradesRef.current = [];
        rafRef.current = null;
        tradesRef.current = [...pending.reverse(), ...tradesRef.current].slice(0, maxTrades);
        setTrades([...tradesRef.current]);
        // Aggregate stats from pending batch
        setStats((s) => {
          let totalNotional = s.totalNotional, sweepCount = s.sweepCount, blockCount = s.blockCount, unusualCount = s.unusualCount, msgCount = s.msgCount;
          for (const t of pending) {
            totalNotional += t.notional || 0;
            if (t.sweep) sweepCount++;
            if (t.block) blockCount++;
            if (t.unusual) unusualCount++;
            msgCount++;
          }
          return { totalNotional, sweepCount, blockCount, unusualCount, msgCount };
        });
      });
    }
  };

  const disconnect = () => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    // Also tell backend to stop
    axios.post(`${API}/live/tape/stop`).catch((e) => {
      setError("Failed to stop tape stream");
    });
    setStatus("idle");
  };

  useEffect(() => {
    return () => {
      if (esRef.current) esRef.current.close();
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  const filteredTrades = trades.filter((t) => {
    if (filter === "all") return true;
    if (filter === "sweeps") return t.sweep;
    if (filter === "blocks") return t.block;
    if (filter === "unusual") return t.unusual;
    return true;
  });

  const formatTime = (ts) => {
    if (!ts) return "—";
    try {
      const d = new Date(ts / 1e6); // nanoseconds to ms
      return d.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
    } catch { return "—"; }
  };

  return (
    <div className="panel p-3 flex flex-col" style={{ maxHeight: 400 }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-2 flex-shrink-0">
        <div className="flex items-center gap-2">
          <div className="label mb-0">Flow Tape</div>
          {status === "live" && <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 flash-pulse">● LIVE</span>}
          {status === "connecting" && <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400">Connecting…</span>}
          {status === "error" && <span className="text-[9px] px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-400">Error</span>}
          {status === "ended" && <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-700 text-slate-400">Ended</span>}
        </div>
        <div className="flex gap-1">
          {status === "idle" || status === "ended" || status === "error" ? (
            <button onClick={connect} className="btn text-[10px]" disabled={!ticker || ticker === "^SPX"}>
              ▶ Start
            </button>
          ) : (
            <>
              <button onClick={() => setPaused(!paused)} className="btn text-[10px]">{paused ? "▶ Resume" : "⏸ Pause"}</button>
              <button onClick={disconnect} className="btn text-[10px]">⏹ Stop</button>
            </>
          )}
        </div>
      </div>

      {/* Error/Warning */}
      {error && (
        <div className="text-[9px] text-amber-400 bg-amber-500/10 rounded px-2 py-1 mb-2 flex-shrink-0">
          {typeof error === 'string' ? error : JSON.stringify(error)}
        </div>
      )}

      {/* Stats */}
      {stats.msgCount > 0 && (
        <div className="grid grid-cols-4 gap-2 mb-2 text-[9px] flex-shrink-0">
          <div className="text-center">
            <div className="text-slate-500">Trades</div>
            <div className="mono font-bold text-slate-300">{stats.msgCount}</div>
          </div>
          <div className="text-center">
            <div className="text-slate-500">Notional</div>
            <div className="mono font-bold text-slate-300">${(stats.totalNotional / 1e6).toFixed(1)}M</div>
          </div>
          <div className="text-center">
            <div className="text-slate-500">Sweeps</div>
            <div className="mono font-bold text-amber-400">{stats.sweepCount}</div>
          </div>
          <div className="text-center">
            <div className="text-slate-500">Blocks</div>
            <div className="mono font-bold text-rose-400">{stats.blockCount}</div>
          </div>
        </div>
      )}

      {/* Filters */}
      {trades.length > 0 && (
        <div className="flex gap-1 mb-2 flex-shrink-0">
          {["all", "sweeps", "blocks", "unusual"].map((f) => (
            <button key={f} onClick={() => setFilter(f)} className={`btn text-[9px] ${filter === f ? "active" : ""}`}>
              {f === "all" ? `All (${trades.length})` : f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      )}

      {/* Trade List */}
      <div className="flex-1 overflow-y-auto" style={{ maxHeight: 260 }}>
        {filteredTrades.length === 0 ? (
          <div className="text-slate-500 text-[10px] text-center py-4">
            {status === "idle" ? "Click Start to begin live trade stream" :
             status === "connecting" ? "Connecting to Databento…" :
             status === "live" ? "Waiting for trades…" :
             "No trades"}
          </div>
        ) : (
          <table className="w-full text-[10px] mono">
            <thead className="sticky top-0" style={{ background: "var(--panel)" }}>
              <tr className="text-slate-500 text-[9px] uppercase tracking-widest">
                <th className="text-left px-1 py-0.5">Time</th>
                <th className="text-left px-1 py-0.5">Type</th>
                <th className="text-right px-1 py-0.5">Strike</th>
                <th className="text-left px-1 py-0.5">Exp</th>
                <th className="text-right px-1 py-0.5">Price</th>
                <th className="text-right px-1 py-0.5">Size</th>
                <th className="text-right px-1 py-0.5">Notional</th>
                <th className="text-center px-1 py-0.5">Flags</th>
              </tr>
            </thead>
            <tbody>
              {filteredTrades.map((t, i) => (
                <tr
                  key={i}
                  className={`border-t border-slate-800/40 ${t.block ? "bg-rose-500/5" : t.sweep ? "bg-amber-500/5" : t.unusual ? "bg-sky-500/5" : ""}`}
                >
                  <td className="px-1 py-0.5 text-slate-500">{formatTime(t.ts)}</td>
                  <td className={`px-1 py-0.5 ${t.type === "call" ? "text-emerald-400" : "text-rose-400"}`}>{t.type === "call" ? "C" : "P"}</td>
                  <td className="text-right px-1 py-0.5 text-slate-300">{fmt(t.strike, 1)}</td>
                  <td className="px-1 py-0.5 text-slate-500">{t.expiry?.slice(5)}</td>
                  <td className="text-right px-1 py-0.5 text-slate-300">{fmt(t.price, 2)}</td>
                  <td className="text-right px-1 py-0.5 text-slate-300">{t.size}</td>
                  <td className="text-right px-1 py-0.5 text-slate-300">${(t.notional / 1e3).toFixed(0)}K</td>
                  <td className="text-center px-1 py-0.5">
                    {t.block && <span className="text-[8px] px-1 py-px rounded bg-rose-500/20 text-rose-400">BLK</span>}
                    {t.sweep && <span className="text-[8px] px-1 py-px rounded bg-amber-500/20 text-amber-400">SWP</span>}
                    {t.unusual && !t.sweep && !t.block && <span className="text-[8px] px-1 py-px rounded bg-sky-500/20 text-sky-400">UNU</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
