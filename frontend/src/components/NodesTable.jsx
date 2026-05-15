import React, { useState } from "react";

const fmt = (n, d = 2) => (n === null || n === undefined || isNaN(n)) ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });
const fmtAbs = (n) => {
  if (n === null || n === undefined || isNaN(n)) return "—";
  const a = Math.abs(n);
  if (a >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return n.toFixed(0);
};
const tagFor = (kind) => ({
  king: "tag king", floor: "tag floor", ceiling: "tag ceiling", gate: "tag gate", air: "tag air",
  fresh: "tag fresh", tested: "tag tested", delivered: "tag delivered", decaying: "tag decaying",
}[kind] || "tag");

export default function NodesTable({ data }) {
  const [sortKey, setSortKey] = useState("mag");
  const [sortDir, setSortDir] = useState("desc");
  if (!data?.nodes) return null;
  const spot = data.spot;
  const all = (data.strikes || []).map((s) => {
    const role = s.strike === data.nodes.king?.strike ? "King"
      : data.nodes.floors?.some(f => f.strike === s.strike) ? "Floor"
      : data.nodes.ceilings?.some(f => f.strike === s.strike) ? "Ceiling"
      : data.nodes.gatekeepers?.some(f => f.strike === s.strike) ? "Gatekeeper"
      : null;
    return { ...s, role, mag: Math.abs(s.gex), dist: Math.abs(s.strike - spot) / spot * 100 };
  }).filter(s => s.role || s.mag > 0);
  const sorted = [...all].sort((a, b) => {
    const va = a[sortKey], vb = b[sortKey];
    if (va == null) return 1;
    if (vb == null) return -1;
    return sortDir === "desc" ? vb - va : va - vb;
  });
  const head = (k, l) => (
    <th className="text-left text-[10px] uppercase tracking-widest text-slate-500 font-normal px-2 py-1 cursor-pointer hover:text-teal-400"
      onClick={() => { setSortKey(k); setSortDir(d => sortKey === k && d === "desc" ? "asc" : "desc"); }}>
      {l}{sortKey === k ? (sortDir === "desc" ? " ↓" : " ↑") : ""}
    </th>
  );
  return (
    <div className="panel p-3" data-testid="nodes-table">
      <div className="label mb-2">Structural Nodes</div>
      <div className="overflow-y-auto" style={{ maxHeight: 280 }}>
        <table className="w-full text-[11px] mono">
          <thead className="sticky top-0" style={{ background: "var(--panel)" }}>
            <tr>
              {head("strike", "Strike")}
              <th className="text-left text-[10px] uppercase tracking-widest text-slate-500 font-normal px-2 py-1">Role</th>
              {head("mag", "|GEX|")}
              {head("gex", "Net")}
              {head("dist", "Δ Spot")}
              {head("taps", "Taps")}
              <th className="text-left text-[10px] uppercase tracking-widest text-slate-500 font-normal px-2 py-1">Life</th>
            </tr>
          </thead>
          <tbody>
            {sorted.slice(0, 30).map((s) => (
              <tr key={s.strike} className="bar-row border-t border-slate-800/60">
                <td className="px-2 py-1 font-bold text-slate-200">{fmt(s.strike, 0)}</td>
                <td className="px-2 py-1">
                  {s.role && <span className={`tag ${s.role === "King" ? "king" : s.role === "Floor" ? "floor" : s.role === "Ceiling" ? "ceiling" : "gate"}`}>{s.role}</span>}
                </td>
                <td className="px-2 py-1 text-slate-300">{fmtAbs(s.mag)}</td>
                <td className={`px-2 py-1 ${s.gex > 0 ? "text-emerald-400" : "text-rose-400"}`}>{s.gex > 0 ? "+" : ""}{fmtAbs(s.gex)}</td>
                <td className="px-2 py-1 text-slate-500">{s.dist.toFixed(2)}%</td>
                <td className="px-2 py-1 text-slate-500">{s.taps}</td>
                <td className="px-2 py-1"><span className={tagFor(s.lifecycle)}>{s.lifecycle}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
