import React from "react";
import { classificationBadge, rowHighlightClass, typeColor, sideColor } from "./flowHighlights";

function fmtPremium(v) {
  const n = Number(v) || 0;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}k`;
  return `$${n.toFixed(0)}`;
}

function fmtTime(ts) {
  try { return new Date(ts).toLocaleTimeString(); } catch { return String(ts || ""); }
}

export default function FlowTable({ prints, loading, error, onSelect, isTracked, onToggleTrack }) {
  if (error) {
    return <div className="panel p-3 text-rose-400 text-[11px]">Error: {error}</div>;
  }

  if (loading && (!prints || prints.length === 0)) {
    return <div className="panel p-3 text-slate-500 text-[11px] animate-pulse">Loading flow…</div>;
  }

  if (!prints || prints.length === 0) {
    return <div className="panel p-3 text-slate-500 text-[11px]">No flow prints.</div>;
  }

  return (
    <div className="panel p-0 overflow-auto" style={{ maxHeight: "70vh" }}>
      <table className="w-full text-[11px] mono border-collapse">
        <thead className="sticky top-0" style={{ background: "var(--panel)" }}>
          <tr className="text-slate-400">
            {onToggleTrack && <th className="px-1 py-1 text-left w-6"></th>}
            <th className="px-1 py-1 text-left">Time</th>
            <th className="px-1 py-1 text-left">Ticker</th>
            <th className="px-1 py-1 text-left">Type</th>
            <th className="px-1 py-1 text-right">Strike</th>
            <th className="px-1 py-1 text-left">Exp</th>
            <th className="px-1 py-1 text-left">Side</th>
            <th className="px-1 py-1 text-right">Size</th>
            <th className="px-1 py-1 text-right">Price</th>
            <th className="px-1 py-1 text-right">Premium</th>
            <th className="px-1 py-1 text-right">Vol</th>
            <th className="px-1 py-1 text-right">OI</th>
            <th className="px-1 py-1 text-right">V/OI</th>
            <th className="px-1 py-1 text-left">Class</th>
          </tr>
        </thead>
        <tbody>
          {prints.map((p, i) => {
            const badge = classificationBadge(p.classification);
            const rowCls = rowHighlightClass(p);
            return (
              <tr
                key={i}
                className={`bar-row cursor-pointer ${rowCls} ${isTracked && isTracked(p) ? "ring-1 ring-amber-400/40" : ""}`}
                onClick={() => onSelect && onSelect(p)}
              >
                {onToggleTrack && (
                  <td className="px-1 py-0.5" onClick={(e) => { e.stopPropagation(); onToggleTrack(p); }}>
                    <span className="cursor-pointer">{isTracked && isTracked(p) ? "★" : "☆"}</span>
                  </td>
                )}
                <td className="px-1 py-0.5 text-slate-400">{fmtTime(p.timestamp)}</td>
                <td className="px-1 py-0.5 text-slate-300">{p.ticker}</td>
                <td className={`px-1 py-0.5 ${typeColor(p.type)}`}>{p.type}</td>
                <td className="px-1 py-0.5 text-right text-slate-300">{p.strike}</td>
                <td className="px-1 py-0.5 text-slate-400">{p.expiration}</td>
                <td className={`px-1 py-0.5 ${sideColor(p.side)}`}>{p.side}</td>
                <td className="px-1 py-0.5 text-right text-slate-300">{p.size}</td>
                <td className="px-1 py-0.5 text-right text-slate-300">{Number(p.price).toFixed(2)}</td>
                <td className="px-1 py-0.5 text-right text-amber-300">{fmtPremium(p.premium)}</td>
                <td className="px-1 py-0.5 text-right text-slate-400">{p.volume}</td>
                <td className="px-1 py-0.5 text-right text-slate-400">{p.oi}</td>
                <td className="px-1 py-0.5 text-right text-slate-400">
                  {Number(p.vol_oi_ratio).toFixed(1)}
                </td>
                <td className="px-1 py-0.5">
                  {badge ? (
                    <span className={`text-[8px] px-1 rounded ${badge.className}`}>{badge.label}</span>
                  ) : (
                    <span className="text-slate-500">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
